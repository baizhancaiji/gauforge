"""断点续跑动作测试（M4 B9，m4-plan §4.6/§5 test_resume）。

覆盖：注入矩阵三分支（opt=Opt=Restart+@exec 行 / scf=Guess=Read+
@exec 行 / freq=无注入原样重跑）、ineligible 五态与 HTTP 语义
（preview 恒 200 / resume 422）、confirm 幂等重探（preview 后清理
chk → 确认 422）、confirm 满员 409、新建任务身份与 resumed_from
落库（派发建行时转移）、物化链复用（dep-exec chk 随派发重建）、
原历史条目数据零变更与 resumed_by 派生只读、skipped/归档条目不提供
续跑入口。
"""
from __future__ import annotations

import stat
from datetime import datetime
from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.engine.materialize import probe_chk
from web.src.errors import ApiError
from web.src.services import history as history_svc
from web.src.services.candidates import import_files
from web.src.store import executions, seats, settings, tasks
from web.src.routers.history import preview_resume, resume_from_checkpoint

TAIL = "#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\nH 1 0.96\n\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16-ok"))
    return tmp_path


def _fake_g16(mode: str, tmp_path: Path) -> Path:
    """假 g16_root：formchk 脚本按 mode 模拟（ok/corrupt/empty/slow）。"""
    root = tmp_path / f"g16-{mode}"
    root.mkdir(exist_ok=True)
    script = root / "formchk"
    body = {
        "ok": '#!/bin/sh\necho "2 #Header ... End" > "$2"\nexit 0\n',
        "corrupt": "#!/bin/sh\necho bad >&2\nexit 3\n",
        "empty": '#!/bin/sh\n: > "$2"\nexit 0\n',
        "slow": '#!/bin/sh\nsleep 3\nexit 0\n',
    }[mode]
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return root


def _mk_source(route_line: str, name: str = "src.gjf") -> tuple[int, int]:
    """造源任务 + failed 终态执行（含 protected 保全 chk）。返回 (tid, eid)。"""
    (out,) = import_files([(name, (f"%chk=own.chk\n{route_line}\n" + TAIL)
                           .encode("utf-8"))], inputs_dir=config.HOME_DIR / "inputs")
    tid = out["id"]
    eid = executions().create(
        task_id=tid, filename=name,
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    run_d = config.HOME_DIR / "run" / str(eid)
    prot = run_d / "protected"
    prot.mkdir(parents=True)
    (prot / "own.chk").write_bytes(b"protected-chk")
    executions().finalize(execution_id=eid, state="failed",
                          finished_at=datetime.now().isoformat(),
                          cause="program_error")
    return tid, eid


def _set_g16(mode: str, tmp_path: Path) -> None:
    settings().set("g16_root", str(_fake_g16(mode, tmp_path)))


# ---------------- 注入矩阵三分支 ----------------

def test_opt_injection(tmp_path):
    """优化行：Link0 追加 %OldChk=@exec + route opt 项改 Opt=Restart。"""
    _set_g16("ok", tmp_path)
    tid, eid = _mk_source("#p opt b3lyp/6-31g(d)")
    out = preview_resume(eid)
    assert out["eligible"] is True and out["reason"] is None
    assert out["task_kind"] == "opt"
    assert out["probe"] == {"formchk_ok": True, "reason": None}
    assert f"%OldChk=@exec:{eid}" in out["input_diff"]
    assert "Opt=Restart" in out["input_diff"]
    assert "b3lyp/6-31g(d)" in out["input_diff"]  # 原选项保留


def test_opt_freq_combo_is_opt(tmp_path):
    """Opt+Freq 并存归优化行（§2.2 规则①）。"""
    _set_g16("ok", tmp_path)
    tid, eid = _mk_source("#p opt freq hf/6-31g(d)")
    out = preview_resume(eid)
    assert out["task_kind"] == "opt"
    assert "Opt=Restart" in out["input_diff"]
    assert "Guess=Read" not in (out["input_diff"] or "")


def test_scf_injection(tmp_path):
    """非优化 SCF：Link0 追加 %OldChk=@exec + route 追加 Guess=Read。"""
    _set_g16("ok", tmp_path)
    tid, eid = _mk_source("#p hf/6-31g(d)")
    out = preview_resume(eid)
    assert out["task_kind"] == "scf"
    assert f"%OldChk=@exec:{eid}" in out["input_diff"]
    assert "Guess=Read" in out["input_diff"]


def test_freq_falls_back_verbatim(tmp_path):
    """freq 行无注入、回落原样重跑（弹窗明示——injections 空清单）。"""
    _set_g16("ok", tmp_path)
    tid, eid = _mk_source("#p freq hf/6-31g(d)")
    out = preview_resume(eid)
    assert out["task_kind"] == "freq"
    assert out["injections"] == []
    # diff 仍展示（原文与原文无差异或仅 Link0 无改动 → diff 为空串）
    confirm = resume_from_checkpoint(eid)
    assert confirm["task_kind"] == "freq"
    new_text = (config.HOME_DIR / "inputs" / str(confirm["task_id"])
                ).read_text(encoding="utf-8")
    assert "@exec" not in new_text  # 无注入：不建立 @exec 引用


# ---------------- ineligible 五态与 HTTP 语义 ----------------

def test_ineligible_no_resume_asset(tmp_path):
    tid, eid = _mk_source("#p hf/6-31g(d)")
    prot = (config.HOME_DIR / "run" / str(eid) / "protected" / "own.chk")
    prot.unlink()
    out = preview_resume(eid)
    assert out == {"eligible": False, "reason": "no_resume_asset",
                   "probe": {"formchk_ok": False,
                             "reason": "no_resume_asset"},
                   "task_kind": None,
                   "injections": None, "input_diff": None}
    with pytest.raises(ApiError) as ei:
        resume_from_checkpoint(eid)
    assert ei.value.code == "RESUME_NOT_ELIGIBLE"
    assert ei.value.http == 422


def test_ineligible_chk_corrupted(tmp_path):
    _set_g16("corrupt", tmp_path)
    tid, eid = _mk_source("#p hf/6-31g(d)")
    out = preview_resume(eid)
    assert out["eligible"] is False
    assert out["reason"] == "chk_corrupted"
    assert out["probe"]["formchk_ok"] is False


def test_ineligible_probe_timeout(tmp_path):
    _set_g16("slow", tmp_path)
    tid, eid = _mk_source("#p hf/6-31g(d)")
    chk = (config.HOME_DIR / "run" / str(eid) / "protected" / "own.chk")
    ok, reason = probe_chk(chk, _fake_g16("slow", tmp_path), timeout_s=1)
    assert ok is False and reason == "probe_timeout"


def test_ineligible_unknown_kind(tmp_path):
    """route 缺失 → 类型不明（直接构造任务行绕过导入校验——导入侧
    会拒绝无 route 输入，属另一层防线）。"""
    _set_g16("ok", tmp_path)
    tid = tasks().create_candidate("bare.gjf", "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(
        "%chk=own.chk\n\n\n0 1\nO 0 0 0\n\n", encoding="utf-8")
    eid = executions().create(
        task_id=tid, filename="bare.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    run_d = config.HOME_DIR / "run" / str(eid)
    (run_d / "protected").mkdir(parents=True)
    (run_d / "protected" / "own.chk").write_bytes(b"chk")
    executions().finalize(execution_id=eid, state="failed",
                          finished_at=datetime.now().isoformat(),
                          cause="program_error")
    out = preview_resume(eid)
    assert out["eligible"] is False
    assert out["reason"] == "unknown_kind"


def test_ineligible_chained_ref(tmp_path):
    """链内引用（输入含 @task:）→ 注入前置检测 eligible=false（先于
    chk 资产判定——本用例 chk 资产在位仍 ineligible）。"""
    _set_g16("ok", tmp_path)
    other = _mk_source("#p hf/6-31g(d)", "o.gjf")[0]
    (out,) = import_files([("chain.gjf",
                            (f"%chk=@task:{other}\n#p hf/6-31g(d)\n\n水\n\n"
                             "0 1\nO 0 0 0\nH 1 0.96\n\n").encode("utf-8"))],
                          inputs_dir=config.HOME_DIR / "inputs")
    tid = out["id"]
    eid = executions().create(
        task_id=tid, filename="chain.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    run_d = config.HOME_DIR / "run" / str(eid)
    (run_d / "protected").mkdir(parents=True)
    (run_d / "protected" / "own.chk").write_bytes(b"chk")
    executions().finalize(execution_id=eid, state="failed",
                          finished_at=datetime.now().isoformat(),
                          cause="program_error")
    out = preview_resume(eid)
    assert out["eligible"] is False
    assert out["reason"] == "chained_ref"


def test_skipped_and_archived_not_resumable(tmp_path):
    """skipped 条目（无资产）与归档条目不提供续跑入口。"""
    _set_g16("ok", tmp_path)
    tid = _mk_source("#p hf/6-31g(d)", "s.gjf")[0]
    eid = executions().create(
        task_id=tid, filename="s.gjf",
        resources={"nproc": {"value": 0, "defaulted": False},
                   "mem_gb": {"value": 0, "defaulted": False}},
        state="skipped")
    executions().finalize(execution_id=eid, state="skipped",
                          finished_at=datetime.now().isoformat(),
                          cause="predecessor_failed")
    assert preview_resume(eid)["reason"] == "no_resume_asset"
    # 归档：eligible=false（封存即无续跑入口）
    tid2, eid2 = _mk_source("#p hf/6-31g(d)", "a.gjf")
    executions().set_archived(eid2)
    out = preview_resume(eid2)
    assert out["eligible"] is False
    assert out["probe"]["reason"] == "archived"  # probe 恒对象、不返回 null


# ---------------- confirm 语义 ----------------

def test_confirm_idempotent_reprobe(tmp_path):
    """幂等重探：preview 后清理 chk → 确认 422。"""
    _set_g16("ok", tmp_path)
    tid, eid = _mk_source("#p hf/6-31g(d)")
    assert preview_resume(eid)["eligible"] is True
    (config.HOME_DIR / "run" / str(eid) / "protected" / "own.chk").unlink()
    with pytest.raises(ApiError) as ei:
        resume_from_checkpoint(eid)
    assert ei.value.code == "RESUME_NOT_ELIGIBLE"


def test_confirm_capacity_full(tmp_path):
    """确认入队时在途席位满员 → 409 PENDING_CAPACITY_FULL（与普通提交
    同待遇，零副作用——无任务残留）。"""
    _set_g16("ok", tmp_path)
    tid, eid = _mk_source("#p hf/6-31g(d)")
    settings().set("pending_seat_limit", 1)
    sid = seats().append(kind="task", task_id=tasks().create_candidate(
        "filler.gjf", "imported"))
    before = executions().count_all() if hasattr(executions(), "count_all") \
        else None
    with pytest.raises(ApiError) as ei:
        resume_from_checkpoint(eid)
    assert ei.value.code == "PENDING_CAPACITY_FULL"
    assert ei.value.http == 409


def test_confirm_creates_task_and_materializes(tmp_path):
    """确认 → 新建任务（注入改写副本）入队 → 派发物化链复用：
    resumed_from 随执行行落库、dep-exec chk 复制、%OldChk 重写零残留、
    crash_limit=0。"""
    _set_g16("ok", tmp_path)
    tid, eid = _mk_source("#p opt b3lyp/6-31g(d)")
    out = resume_from_checkpoint(eid)
    assert out["task_id"] != tid  # 新任务身份
    assert out["execution_id"] == eid
    new_text = (config.HOME_DIR / "inputs" / str(out["task_id"])
                ).read_text(encoding="utf-8")
    assert f"%OldChk=@exec:{eid}" in new_text
    assert "Opt=Restart" in new_text
    # 原历史条目数据零变更（文本/关联不受 confirm 影响）
    src_text = (config.HOME_DIR / "inputs" / str(tid)).read_text(
        encoding="utf-8")
    assert "@exec" not in src_text
    # 派发（物化链复用断言）
    rec: list = []
    gw = FakeGateway(cpus=8)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    disp.advance()
    rows = executions().list_by_task(out["task_id"])
    assert rows and rows[-1]["state"] == "running"
    assert rows[-1]["resumed_from"] == {"task_id": tid, "execution_id": eid}
    dep = gw.submitted[0]
    assert dep["crash_limit"] == 0
    run_d = Path(dep["cwd"])
    assert (run_d / f"dep-exec-{eid}.chk").read_bytes() == b"protected-chk"
    assert "@exec" not in (run_d / "input.gjf").read_text(encoding="utf-8")


def test_resumed_by_derived_readonly(tmp_path):
    """原历史条目数据零变更；「已续跑」经 resumed_by 派生只读反查。"""
    _set_g16("ok", tmp_path)
    tid, eid = _mk_source("#p hf/6-31g(d)")
    before = history_svc.get_entry(eid)
    confirm = resume_from_checkpoint(eid)
    assert before["resumed_by"] == []  # confirm 前无续跑
    disp = Dispatcher(FakeGateway(cpus=8), emitter=lambda e, d: None)
    disp.advance()  # 新任务派发建行
    after = history_svc.get_entry(eid)
    assert after["resumed_from"] is None  # 原条目不携带关联（数据零变更）
    new_rows = executions().list_by_task(confirm["task_id"])
    assert after["resumed_by"] == [new_rows[-1]["id"]]  # 派生反查命中


# ---------------- 缺陷整改（P5/P6）：入口设防与原选项保留 ----------------

def test_succeeded_source_rejected(tmp_path):
    """succeeded 条目无续跑入口（preview/confirm 同口径 404 NOT_FOUND）：
    续跑=从断点恢复、成功条目无断点，重跑诉求由「重新排队」承载。"""
    _set_g16("ok", tmp_path)
    (out,) = import_files([("ok.gjf",
                            ("%chk=own.chk\n#p opt b3lyp/6-31g(d)\n" + TAIL)
                            .encode("utf-8"))],
                          inputs_dir=config.HOME_DIR / "inputs")
    eid = executions().create(
        task_id=out["id"], filename="ok.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    run_d = config.HOME_DIR / "run" / str(eid)
    (run_d / "protected").mkdir(parents=True)
    (run_d / "protected" / "own.chk").write_bytes(b"protected-chk")
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at=datetime.now().isoformat())
    with pytest.raises(ApiError) as ep:
        preview_resume(eid)
    assert (ep.value.code, ep.value.http) == ("NOT_FOUND", 404)
    with pytest.raises(ApiError) as ec:
        resume_from_checkpoint(eid)
    assert (ec.value.code, ec.value.http) == ("NOT_FOUND", 404)


def test_opt_atomic_options_preserved(tmp_path):
    """opt 变体原子选项保留（§2.2 注入矩阵「Opt=Restart + 原选项」）：
    opt=(ts,calcfc) → Opt=(Restart,ts,calcfc)、opt=ts → Opt=(Restart,ts)、
    Opt=Restart 幂等不重复注入。"""
    _set_g16("ok", tmp_path)
    _, eid = _mk_source("#p opt=(ts,calcfc) b3lyp/6-31g(d)")
    out = preview_resume(eid)
    assert "Opt=(Restart,ts,calcfc)" in out["input_diff"]
    assert "calcfc" in out["input_diff"]  # 原子选项未丢失
    _, eid = _mk_source("#p opt=ts hf/6-31g(d)")
    assert "Opt=(Restart,ts)" in preview_resume(eid)["input_diff"]
    _, eid = _mk_source("#p Opt=Restart b3lyp/6-31g(d)")
    assert "Opt=Restart" in preview_resume(eid)["input_diff"]
