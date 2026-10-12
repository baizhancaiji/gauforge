"""依赖模型与 DAG 静态校验测试（M4 B6，m4-plan §4.3/§5 test_dependencies）。

场景矩阵：合法链、环、自环、跨队、悬引用、文法残缺、PATCH 移除被依赖
成员、crest 成员组队拒绝、单任务席位载体 @task: 引用拒绝（行内提交与
历史重新排队）、@exec 载体约束（队列成员拒绝/单任务席位三点校验）、
溯源 chk 已清理提交拒绝（CHK_SOURCE_MISSING）、上游无执行记录放行。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from web.src.errors import ApiError
from web.src.services import history as history_svc
from web.src.services import queues as queues_svc
from web.src.services.candidates import import_files
from web.src.store import executions, get_db, queues as queues_store, tasks
from web.src.routers.candidates import submit_candidate
from web.src.routers.queues import create_queue, submit_queue

_CLEAN_TAIL = (  # 规范形态（沿 test_submit_verify）：节末恰一空行、末尾空行
    "#p b3lyp/6-31g(d)\n"
    "\n"
    "水分子示例\n"
    "\n"
    "0 1\n"
    "O 0.0 0.0 0.0\n"
    "H 1 R1\n"
    "\n"
    "Variables:\n"
    "R1 0.96\n"
    "\n"
)


def _input(link0: str) -> str:
    return link0 + _CLEAN_TAIL


@pytest.fixture()
def ind(tmp_path, monkeypatch) -> Path:
    """工作区隔离（沿 test_submit_verify 先例）：HOME_DIR 指向 tmp。"""
    from web.src import config
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    d = tmp_path / "inputs"
    d.mkdir()
    return d


def _mk(ind: Path, text: str, name: str = "a.gjf") -> int:
    (out,) = import_files([(name, text.encode("utf-8"))], inputs_dir=ind)
    return out["id"]


def _set_input(ind: Path, tid: int, text: str) -> None:
    (ind / str(tid)).write_text(text, encoding="utf-8")


def _plain(ind: Path, name: str) -> int:
    return _mk(ind, _input("%chk=point.chk\n%nprocshared=2\n"), name)


def _mk_execution(task_id: int, filename: str, state: str,
                  cause: str | None = None) -> int:
    eid = executions().create(
        task_id=task_id, filename=filename,
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    executions().finalize(execution_id=eid, state=state,
                          finished_at=datetime.now().isoformat(),
                          cause=cause)
    return eid


# ---------------- 队列创建/提交载体 ----------------

def test_legal_chain_passes(ind):
    """合法链（freq %OldChk=@task:opt）：创建与提交均通过；上游无执行
    记录属正常（依赖满足时必然有产出，§2.1 放行）。"""
    opt = _plain(ind, "opt.gjf")
    freq = _mk(ind, _input(f"%OldChk=@task:{opt}\n%nprocshared=2\n"),
               "freq.gjf")
    q = create_queue({"name": "chain", "member_ids": [opt, freq],
                      "skip_failed": False})
    assert q["member_ids"] == [opt, freq]
    out = submit_queue(q["id"])
    assert out["task_id"] in (opt, freq)


def test_cycle_rejected(ind):
    a = _plain(ind, "a.gjf")
    b = _mk(ind, _input(f"%chk=@task:{a}\n"), "b.gjf")
    _set_input(ind, a, _input(f"%chk=@task:{b}\n"))
    with pytest.raises(ApiError) as ei:
        create_queue({"name": "cyc", "member_ids": [a, b],
                      "skip_failed": False})
    assert ei.value.code == "DEPENDENCY_CYCLE"
    assert ei.value.details["cycle"][0] == ei.value.details["cycle"][-1]


def test_self_reference_rejected(ind):
    a = _mk(ind, _input(f"%chk=@task:{0}\n"), "a.gjf")
    _set_input(ind, a, _input(f"%chk=@task:{a}\n"))
    with pytest.raises(ApiError) as ei:
        create_queue({"name": "self",
                      "member_ids": [a, _plain(ind, "b.gjf")],
                      "skip_failed": False})
    assert ei.value.code == "DEPENDENCY_CYCLE"


def test_cross_queue_reference_rejected(ind):
    """跨队列引用：引用 id 是另一队列成员（非本队列现存成员）。"""
    other = _plain(ind, "o.gjf")
    create_queue({"name": "other",
                  "member_ids": [other, _plain(ind, "x.gjf")],
                  "skip_failed": False})
    a = _mk(ind, _input(f"%OldChk=@task:{other}\n"), "a.gjf")
    with pytest.raises(ApiError) as ei:
        create_queue({"name": "cq",
                      "member_ids": [a, _plain(ind, "b.gjf")],
                      "skip_failed": False})
    assert ei.value.code == "DEPENDENCY_UNREACHABLE"


def test_dangling_reference_rejected(ind):
    a = _mk(ind, _input("%chk=@task:999999\n"), "a.gjf")
    with pytest.raises(ApiError) as ei:
        create_queue({"name": "dang",
                      "member_ids": [a, _plain(ind, "b.gjf")],
                      "skip_failed": False})
    assert ei.value.code == "DEPENDENCY_UNREACHABLE"


def test_malformed_reference_rejected(ind):
    a = _mk(ind, _input("%chk=@task:abc\n"), "a.gjf")
    with pytest.raises(ApiError) as ei:
        create_queue({"name": "mal",
                      "member_ids": [a, _plain(ind, "b.gjf")],
                      "skip_failed": False})
    assert ei.value.code == "DEPENDENCY_UNREACHABLE"


def test_exec_ref_rejected_in_queue(ind):
    """@exec 为 resume 专用文法，队列成员载体拒绝。"""
    a = _mk(ind, _input("%OldChk=@exec:1\n"), "a.gjf")
    with pytest.raises(ApiError) as ei:
        create_queue({"name": "exc",
                      "member_ids": [a, _plain(ind, "b.gjf")],
                      "skip_failed": False})
    assert ei.value.code == "DEPENDENCY_UNREACHABLE"


def test_crest_member_rejected(ind):
    """crest 任务不可组队（INVALID_MEMBERS 复用，details 注明）。"""
    a = _plain(ind, "a.gjf")
    b = _plain(ind, "b.gjf")
    get_db().run("UPDATE tasks SET kind = 'crest' WHERE id = ?", (b,))
    assert tasks().get(b)["kind"] == "crest"
    with pytest.raises(ApiError) as ei:
        create_queue({"name": "cr", "member_ids": [a, b],
                      "skip_failed": False})
    assert ei.value.code == "INVALID_MEMBERS"
    assert ei.value.details["task_ids"] == [b]


# ---------------- PATCH 移除被依赖成员 ----------------

def test_patch_remove_depended_member_rejected(ind):
    """三段链移除中段（被末段依赖）拒绝，details 注明被谁依赖；
    先解除下游引用再移除则放行。"""
    a = _plain(ind, "a.gjf")
    b = _mk(ind, _input(f"%OldChk=@task:{a}\n"), "b.gjf")
    c = _mk(ind, _input(f"%OldChk=@task:{b}\n"), "c.gjf")
    qid = create_queue({"name": "p", "member_ids": [a, b, c],
                        "skip_failed": False})["id"]
    with pytest.raises(ApiError) as ei:
        queues_svc.patch_queue(qid, {"member_ids": [a, c]})
    assert ei.value.code == "DEPENDENCY_UNREACHABLE"
    assert ei.value.details["depended_by"] == c
    assert ei.value.details["targets"] == [b]
    # 先解除下游引用（移除 c）→ 再移除 b 放行
    queues_svc.patch_queue(qid, {"member_ids": [a, b]})
    out = queues_svc.patch_queue(qid, {"member_ids": [a]})
    assert out["members_changed"] is True


# ---------------- 溯源 chk 存在性 ----------------

def test_chk_source_missing_rejected(ind, tmp_path):
    """上游已有成功执行但 run/<eid>/input.chk 已被清理 → 队列提交拒绝，
    details 注明缺失的执行 id 与重跑上游指引。"""
    a = _plain(ind, "a.gjf")
    b = _mk(ind, _input(f"%OldChk=@task:{a}\n"), "b.gjf")
    eid = _mk_execution(a, "a.gjf", "succeeded")
    run_d = tmp_path / "run" / str(eid)
    run_d.mkdir(parents=True)
    (run_d / "input.chk").write_bytes(b"chk")
    qid = create_queue({"name": "ok", "member_ids": [a, b],
                        "skip_failed": False})["id"]
    # 清理上游 chk → 提交（提交时点重校验）拒绝
    (run_d / "input.chk").unlink()
    with pytest.raises(ApiError) as ei:
        submit_queue(qid)
    assert ei.value.code == "CHK_SOURCE_MISSING"
    assert ei.value.details["execution_id"] == eid
    assert ei.value.details["upstream_task_id"] == a


# ---------------- 单任务席位载体 ----------------

def test_inline_submit_task_ref_rejected(ind):
    """行内提交（单任务席位）携带 @task: 引用拒绝，引导组建队列。"""
    other = _plain(ind, "o.gjf")
    a = _mk(ind, _input(f"%chk=@task:{other}\n"), "a.gjf")
    with pytest.raises(ApiError) as ei:
        submit_candidate(a, None)
    assert ei.value.code == "DEPENDENCY_UNREACHABLE"


def test_requeue_task_ref_rejected(ind):
    """历史重新排队（单任务席位）对含 @task: 引用的原输入拒绝（§2.1：
    原输入含引用者经「重新排队」将被此校验拒绝，引导先重建队列）。"""
    other = _plain(ind, "o.gjf")
    a = _mk(ind, _input(f"%chk=@task:{other}\n"), "a.gjf")
    eid = _mk_execution(a, "a.gjf", "failed", cause="program_error")
    with pytest.raises(ApiError) as ei:
        history_svc.requeue(eid)
    assert ei.value.code == "DEPENDENCY_UNREACHABLE"


def test_exec_ref_validated_on_single_seat(ind):
    """@exec 单任务席位三点校验：执行不存在 → UNREACHABLE。"""
    a = _mk(ind, _input("%OldChk=@exec:424242\n"), "a.gjf")
    with pytest.raises(ApiError) as ei:
        submit_candidate(a, None)
    assert ei.value.code == "DEPENDENCY_UNREACHABLE"
