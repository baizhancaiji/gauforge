"""chk 物化器与 formchk 探针测试（M4 B7，m4-plan §4.4/§5 test_materialize）。

覆盖：物化重写内容断言（%oldchk=@task:X → dep-<X>.chk、前缀小写归一、
零符号残留）、按声明定位溯源（3.5.0：命名 chk/符号三段链/绝对路径/
未声明文案）、上游原件零改动（哈希前后一致）、缺源失败分支
（MaterializeError）、哈希跳过溯源（当前输入哈希匹配的被沿用执行）、
@exec 资产取数（protected 优先、顶层按声明名回落、无执行副本回落
input.chk）、formchk 探针三分支（正常 chk/损坏 chk/空 fchk 段/超时）、
派发接线（重写落盘 + crash_limit=0 重入① + 物化失败落
failed(program_error)）。
"""
from __future__ import annotations

import hashlib
import re
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

# Link0 口径与 workspace.parse_chk_line（link0_only=True）同步维护
# （T3 时点该纯函数尚未迁移，助手内联同规则；迁移后助手不预依赖）
_CHK_LINE_RE = re.compile(r"^%chk\s*=\s*(.+)$", re.IGNORECASE)


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


def _declared_chk_name(text: str) -> str | None:
    """任务输入 Link0 区首个 %chk 声明名（仅扫前导空行/! 注释后的连续
    % 行，符号值 @task:/@exec: 原样返回——「已声明」即按名同落执行副本，
    资产由物化改写决定）。"""
    lines = text.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    while i < n and lines[i].lstrip().startswith("%"):
        m = _CHK_LINE_RE.match(lines[i].strip())
        if m:
            raw = m.group(1).strip().strip('"').strip("'")
            return raw or None
        i += 1
    return None


def _succeed_with_chk(task_id: int, chk_bytes: bytes = b"upstream-chk",
                      input_hash: str | None = None) -> int:
    """造一条 succeeded 执行：按任务输入 Link0 %chk 声明落 chk 资产——
    命名 chk 与声明该名的执行副本 input.gjf 两者同落（缺执行副本时
    resolve_chk 走无声明回落仍按 input.chk 命中，红用例无法转绿）。

    无声明防御回落现行为 input.chk；符号声明（@task:/@exec:）只落执行
    副本、不写资产（物化改写后的产物名由 dep-*.chk 决定）；绝对路径
    声明不写资产文件（防写出 tmp_path 之外，绝对路径产态由
    test_absolute_chk_declared 在 tmp_path 内手工构造）。"""
    eid = executions().create(
        task_id=task_id, filename="t.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}},
        input_hash=input_hash)
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True)
    text = (config.HOME_DIR / "inputs" / str(task_id)).read_text(
        encoding="utf-8", errors="replace")
    (run_d / "input.gjf").write_text(text, encoding="utf-8")
    declared = _declared_chk_name(text)
    if declared is None:
        (run_d / "input.chk").write_bytes(chk_bytes)  # 防御回落现行为
    elif not declared.startswith("@") and not Path(declared).anchor:
        target = run_d / declared
        if not target.suffix:
            target = target.with_name(target.name + ".chk")
        target.write_bytes(chk_bytes)
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
    src = config.HOME_DIR / "run" / str(eid) / "u.chk"  # 按声明名放置
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
    (config.HOME_DIR / "run" / str(eid) / "u.chk").unlink()  # 按声明名清理
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
    assert src == config.HOME_DIR / "run" / str(old_eid) / "u.chk"  # 声明名
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


# ---------------- 按声明定位溯源（3.5.0，chk-materialize-fix §2.1/§2.4） ----------------

def test_named_upstream_chk_materializes(tmp_path):
    """上游声明 %chk=opt.chk（真实 G16 命名规则，非固定 input.chk）：溯源按
    执行副本声明定位，物化拷 dep-<u>.chk 字节相等、改写行小写形态、零残留。"""
    upstream = _mk_task("%chk=opt.chk\n" + TAIL, "u.gjf")
    _succeed_with_chk(upstream, b"named-chk")
    run_d = tmp_path / "run" / "910"
    run_d.mkdir()
    out = materialize_chk(run_d, f"%OldChk=@task:{upstream}\n" + TAIL)
    assert f"%oldchk=dep-{upstream}.chk" in out
    assert (run_d / f"dep-{upstream}.chk").read_bytes() == b"named-chk"
    assert not needs_materialization(out)  # 零符号残留


def test_symbol_chk_chain_three_level(tmp_path):
    """三段符号链 A（%chk=a.chk）→ B（%chk=@task:A）→ C（%OldChk=@task:B）：
    B 物化改写后执行副本声明 dep-A.chk，C 溯源按 B 改写后执行副本命中。"""
    a = _mk_task("%chk=a.chk\n" + TAIL, "a.gjf")
    _succeed_with_chk(a, b"a-chk")
    b = _mk_task(f"%chk=@task:{a}\n" + TAIL, "b.gjf")
    eid_b = executions().create(
        task_id=b, filename="b.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    run_b = config.HOME_DIR / "run" / str(eid_b)
    run_b.mkdir()
    out_b = materialize_chk(run_b, f"%chk=@task:{a}\n" + TAIL)  # 续用形态改写
    (run_b / "input.gjf").write_text(out_b, encoding="utf-8")
    executions().finalize(execution_id=eid_b, state="succeeded",
                          finished_at=now_iso())
    assert (run_b / f"dep-{a}.chk").read_bytes() == b"a-chk"
    run_c = tmp_path / "run" / "911"
    run_c.mkdir()
    out_c = materialize_chk(run_c, f"%OldChk=@task:{b}\n" + TAIL)
    assert f"%oldchk=dep-{b}.chk" in out_c
    assert (run_c / f"dep-{b}.chk").read_bytes() == b"a-chk"


def test_absolute_chk_declared(tmp_path):
    """执行副本声明绝对路径（tmp_path 内）且资产在 → 按绝对路径拷入
    （助手只落执行副本不写资产，绝对路径产态由本用例手工构造）。"""
    asset = tmp_path / "abs" / "abs.chk"
    asset.parent.mkdir()
    asset.write_bytes(b"abs-chk")
    upstream = _mk_task(f"%chk={asset}\n" + TAIL, "u.gjf")
    eid = _succeed_with_chk(upstream)
    assert (config.HOME_DIR / "run" / str(eid) / "input.gjf").is_file()
    run_d = tmp_path / "run" / "912"
    run_d.mkdir()
    out = materialize_chk(run_d, f"%OldChk=@task:{upstream}\n" + TAIL)
    assert f"%oldchk=dep-{upstream}.chk" in out
    assert (run_d / f"dep-{upstream}.chk").read_bytes() == b"abs-chk"


def test_undeclared_source_message(tmp_path):
    """源执行副本无 %chk 声明且无 input.chk → MaterializeError 文案如实
    「未声明 %chk」并引导补写（现状误导「已被清理」——修复前红）。"""
    upstream = _mk_task(TAIL, "u.gjf")  # 输入无 %chk 声明
    eid = executions().create(
        task_id=upstream, filename="u.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    run_u = config.HOME_DIR / "run" / str(eid)
    run_u.mkdir()
    (run_u / "input.gjf").write_text(TAIL, encoding="utf-8")
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at=now_iso())
    run_d = tmp_path / "run" / "913"
    run_d.mkdir()
    with pytest.raises(MaterializeError) as ei:
        materialize_chk(run_d, f"%OldChk=@task:{upstream}\n" + TAIL)
    assert "未声明 %chk" in str(ei.value)
    assert "补写" in str(ei.value)
    assert ei.value.details["execution_id"] == eid


def test_exec_asset_named_top_level(tmp_path):
    """@exec 取数按声明定位：源执行输入声明 %chk=o.chk、按名放置顶层
    o.chk（无 protected/）→ execution_chk_asset 返回 o.chk、物化拷入
    dep-exec-<eid>.chk 字节相等（resume 探针取数同源跟随）。"""
    from web.src.services.dependencies import execution_chk_asset
    owner = _mk_task("%chk=o.chk\n" + TAIL, "o.gjf")
    eid = _succeed_with_chk(owner, b"named-top")
    assert execution_chk_asset(eid) == \
        config.HOME_DIR / "run" / str(eid) / "o.chk"
    run_d = tmp_path / "run" / "914"
    run_d.mkdir()
    out = materialize_chk(run_d, f"%OldChk=@exec:{eid}\n" + TAIL)
    assert (run_d / f"dep-exec-{eid}.chk").read_bytes() == b"named-top"
    assert f"%oldchk=dep-exec-{eid}.chk" in out


def test_exec_asset_top_level_fallback(tmp_path):
    """resolve_chk 回落正向锚点：无 protected、无执行副本 input.gjf、顶层
    input.chk 存在 → execution_chk_asset 返回 input.chk（OSError 回落
    语义，不得随本计划改动）。"""
    from web.src.services.dependencies import execution_chk_asset
    owner = _mk_task("%chk=o.chk\n" + TAIL, "o.gjf")
    eid = executions().create(
        task_id=owner, filename="o.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True)
    (run_d / "input.chk").write_bytes(b"legacy-top")  # 无执行副本手工盘面
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at=now_iso())
    assert execution_chk_asset(eid) == run_d / "input.chk"


def test_exec_copy_missing_treated_as_undeclared(tmp_path):
    """执行副本 input.gjf 缺失视同无声明（防御从严）：顶层 input.chk 手工
    在场也不放行——生产链路执行副本恒在，不为手工盘面形态放宽。"""
    upstream = _mk_task("%chk=u.chk\n" + TAIL, "u.gjf")
    eid = executions().create(
        task_id=upstream, filename="u.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    run_u = config.HOME_DIR / "run" / str(eid)
    run_u.mkdir(parents=True)
    (run_u / "input.chk").write_bytes(b"orphan-top")  # 执行副本缺失
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at=now_iso())
    run_d = tmp_path / "run" / "915"
    run_d.mkdir()
    with pytest.raises(MaterializeError) as ei:
        materialize_chk(run_d, f"%OldChk=@task:{upstream}\n" + TAIL)
    assert "未声明 %chk" in str(ei.value)


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
    (config.HOME_DIR / "run" / str(eid) / "u.chk").unlink()  # 按声明名清理
    _seat(d)
    disp.advance()
    d_rows = [e for e in executions().list_by_task(d)]
    assert d_rows and d_rows[-1]["state"] == "failed"
    assert d_rows[-1]["cause"] == "program_error"
    assert gw.submitted == []
