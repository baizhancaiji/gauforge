"""chk 物化器与 formchk 探针测试（M4 B7，m4-plan §4.4/§5 test_materialize）。

覆盖：物化重写内容断言（%oldchk=@task:X → dep-<X>.chk、前缀小写归一、
零符号残留）、
上游原件零改动（哈希前后一致）、缺源失败分支（MaterializeError）、
哈希跳过溯源（当前输入哈希匹配的被沿用执行）、@exec 资产取数
（protected 优先）、formchk 探针三分支（正常 chk/损坏 chk/空 fchk 段/
超时）、派发接线（重写落盘 + crash_limit=0 重入① + 物化失败落
failed(program_error)）。
"""
from __future__ import annotations

import hashlib
import stat
from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.engine import materialize
from web.src.engine.materialize import (
    MaterializeError,
    materialize_chk,
    needs_materialization,
    probe_chk,
    resolve_upstream_chk,
)
from web.src.engine.workspace import resolve_link0
from web.src.store import executions, seats, settings, tasks
from web.src.store.db import now_iso

TAIL = ("#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\nH 1 0.96\n\n")
NPROC_DEFAULT, MEM_DEFAULT = 2, 1.0


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


def _mk_task(text: str, name: str = "t.gjf") -> int:
    tid = tasks().create_candidate(name, "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(text, encoding="utf-8")
    return tid


def _succeed_with_chk(task_id: int, chk_bytes: bytes = b"upstream-chk",
                      input_hash: str | None = None) -> int:
    """造一条 succeeded 执行并落 run/<eid>/input.chk。"""
    eid = executions().create(
        task_id=task_id, filename="t.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}},
        input_hash=input_hash)
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True)
    (run_d / "input.chk").write_bytes(chk_bytes)
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at=now_iso())
    return eid


# ---------------- 物化器单元 ----------------

def test_rewrite_oldchk_and_no_leftover(tmp_path):
    upstream = _mk_task("%chk=u.chk\n" + TAIL, "u.gjf")
    _succeed_with_chk(upstream)
    text = f"%OldChk=@task:{upstream}\n%Chk=own.chk\n" + TAIL
    run_d = tmp_path / "run" / "900"
    run_d.mkdir()
    out = materialize_chk(run_d, text, nproc_default=NPROC_DEFAULT,
                          mem_gb_default=MEM_DEFAULT)
    assert f"%oldchk=dep-{upstream}.chk" in out
    assert "%Chk=own.chk" in out  # 续用/只读两行互不干扰（无引用行前缀原样）
    assert (run_d / f"dep-{upstream}.chk").read_bytes() == b"upstream-chk"
    assert not needs_materialization(out)  # 零符号残留


def test_upstream_untouched(tmp_path):
    """上游原件零改动：内容哈希与 mtime 前后一致（复制语义）。"""
    upstream = _mk_task("%chk=u.chk\n" + TAIL, "u.gjf")
    eid = _succeed_with_chk(upstream, b" precious chk ")
    src = config.HOME_DIR / "run" / str(eid) / "input.chk"
    before = (hashlib.sha256(src.read_bytes()).hexdigest(), src.stat().st_mtime_ns)
    text = f"%OldChk=@task:{upstream}\n" + TAIL
    run_d = tmp_path / "run" / "901"
    run_d.mkdir()
    materialize_chk(run_d, text)
    after = (hashlib.sha256(src.read_bytes()).hexdigest(), src.stat().st_mtime_ns)
    assert before == after


def test_missing_source_raises(tmp_path):
    upstream = _mk_task("%chk=u.chk\n" + TAIL, "u.gjf")  # 无成功执行
    run_d = tmp_path / "run" / "902"
    run_d.mkdir()
    with pytest.raises(MaterializeError) as ei:
        materialize_chk(run_d, f"%OldChk=@task:{upstream}\n" + TAIL)
    assert ei.value.details["upstream_task_id"] == upstream


def test_cleaned_source_raises(tmp_path):
    upstream = _mk_task("%chk=u.chk\n" + TAIL, "u.gjf")
    eid = _succeed_with_chk(upstream)
    (config.HOME_DIR / "run" / str(eid) / "input.chk").unlink()
    run_d = tmp_path / "run" / "903"
    run_d.mkdir()
    with pytest.raises(MaterializeError) as ei:
        materialize_chk(run_d, f"%OldChk=@task:{upstream}\n" + TAIL)
    assert ei.value.details["execution_id"] == eid


def test_hash_skip_source_resolution(tmp_path):
    """哈希跳过溯源：X 当前输入哈希匹配旧成功执行 → 物化取被沿用的那次
    chk（而非最近成功执行）。"""
    old_text = "%chk=u.chk\n%nprocshared=2\n" + TAIL
    tid = _mk_task(old_text, "u.gjf")
    old_hash = content_hash_of(old_text)
    old_eid = _succeed_with_chk(tid, b"old-exec-chk", input_hash=old_hash)
    new_eid = _succeed_with_chk(tid, b"newer-exec-chk")  # 更近但哈希不匹配
    src = resolve_upstream_chk(tid)
    assert src == config.HOME_DIR / "run" / str(old_eid) / "input.chk"
    assert src.read_bytes() == b"old-exec-chk"
    assert new_eid > old_eid


def content_hash_of(text: str) -> str:
    resolved = resolve_link0(text, NPROC_DEFAULT, MEM_DEFAULT)
    from web.src.engine.workspace import content_hash
    return content_hash(resolved["completed_text"])


def test_exec_asset_protected_first(tmp_path):
    """@exec 取数：protected/ 保全 chk 优先于保留期 input.chk（§2.2）。"""
    owner = _mk_task("%chk=o.chk\n" + TAIL, "o.gjf")
    eid = _succeed_with_chk(owner, b"top-level")
    run_d = config.HOME_DIR / "run" / str(eid)
    prot = run_d / "protected"
    prot.mkdir()
    (prot / "input.chk").write_bytes(b"protected-chk")
    text = f"%OldChk=@exec:{eid}\n" + TAIL
    out_d = tmp_path / "run" / "904"
    out_d.mkdir()
    out = materialize_chk(out_d, text)
    assert (out_d / f"dep-exec-{eid}.chk").read_bytes() == b"protected-chk"
    assert f"%oldchk=dep-exec-{eid}.chk" in out


# ---------------- formchk 探针三分支 ----------------

def _fake_g16(formchk_mode: str, tmp_path: Path) -> Path:
    """构造假 g16_root：formchk 脚本按 mode 模拟三分支行为。

    ok=写非空 fchk 退出 0；corrupt=退出 3；empty=写空 fchk 退出 0。
    """
    root = tmp_path / f"g16-{formchk_mode}"
    root.mkdir(exist_ok=True)
    script = root / "formchk"
    body = {
        "ok": f'#!/bin/sh\necho "Header ... End" > "$2"\nexit 0\n',
        "corrupt": "#!/bin/sh\necho bad >&2\nexit 3\n",
        "empty": '#!/bin/sh\n: > "$2"\nexit 0\n',
    }[formchk_mode]
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return root


def test_probe_three_branches(tmp_path):
    chk = tmp_path / "sample.chk"
    chk.write_bytes(b"binary-chk")
    ok, reason = probe_chk(chk, _fake_g16("ok", tmp_path))
    assert ok is True and reason is None
    ok, reason = probe_chk(chk, _fake_g16("corrupt", tmp_path))
    assert ok is False and reason == "chk_corrupted"
    ok, reason = probe_chk(chk, _fake_g16("empty", tmp_path))
    assert ok is False and reason == "chk_corrupted"  # 缺 fchk 数据段
    # 源 chk 不被探针触碰
    assert chk.read_bytes() == b"binary-chk"


# ---------------- 派发接线（FakeGateway） ----------------

def _seat(tid: int) -> None:
    sid = seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)


def test_dispatch_no_dep_keeps_default_retry(tmp_path):
    """无物化依赖的执行提交 HQ 保持缺省 crash_limit（None，行为零变化）。"""
    rec: list = []
    gw = FakeGateway(cpus=8)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    w = _mk_task("%chk=w.chk\n" + TAIL, "w.gjf")
    _seat(w)
    disp.advance()
    assert len(gw.submitted) == 1
    assert gw.submitted[0]["crash_limit"] is None


def test_dispatch_materializes_and_disables_retry(tmp_path):
    """下游派发物化：dep chk 落位、input.gjf 重写零残留、HQ 提交参数
    crash_limit=0（重入①）。"""
    rec: list = []
    gw = FakeGateway(cpus=8)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    u = _mk_task("%chk=u.chk\n" + TAIL, "u.gjf")
    d = _mk_task(f"%OldChk=@task:{u}\n" + TAIL, "d.gjf")
    _succeed_with_chk(u)  # 溯源源（u 已成功）
    _seat(d)
    disp.advance()
    assert len(gw.submitted) == 1
    dep = gw.submitted[0]
    assert dep["name"] == "d.gjf"
    assert dep["crash_limit"] == 0
    run_d = Path(dep["cwd"])
    text = (run_d / "input.gjf").read_text(encoding="utf-8")
    assert "@task:" not in text  # 物化后零符号残留
    assert f"%oldchk=dep-{u}.chk" in text
    assert (run_d / f"dep-{u}.chk").read_bytes() == b"upstream-chk"


def test_dispatch_materialize_failure_terminal(tmp_path):
    """物化失败：成员 failed(program_error) 落历史（溯源 chk 被清理），
    不留 running 行、HQ 未被提交。"""
    rec: list = []
    gw = FakeGateway(cpus=8)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    u = _mk_task("%chk=u.chk\n" + TAIL, "u.gjf")
    d = _mk_task(f"%OldChk=@task:{u}\n" + TAIL, "d.gjf")
    eid = _succeed_with_chk(u)
    (config.HOME_DIR / "run" / str(eid) / "input.chk").unlink()
    _seat(d)
    disp.advance()
    d_rows = [e for e in executions().list_by_task(d)]
    assert d_rows and d_rows[-1]["state"] == "failed"
    assert d_rows[-1]["cause"] == "program_error"
    assert gw.submitted == []
