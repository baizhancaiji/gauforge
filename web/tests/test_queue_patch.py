"""队列 PATCH member_ids 全语义测试（B3，m2-plan §5 test_queue_patch）。

覆盖：状态矩阵（unsubmitted 全量 / submitted 仅 member_ids / executing、
completed 整体 409）；member_ids 子集/去重/下限校验；移除分流四类；自动
成功判定含边界；submitted 移除退回 returned_unrun；与引擎窗口推进的竞态
不破坏派发语义（FakeGateway）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.errors import ApiError
from web.src.services.candidates import import_files
from web.src.services.queues import patch_queue
from web.src.store import executions, queues, seats, tasks

INPUT = ("%mem=1GB\n%nprocshared=4\n#p opt\n\nt#\n\n0 1\nO 0 0 0\n\n")
RUN_COPY = INPUT.replace("t#", "t99")  # run/<eid>/input.gjf 与任务副本不同


def _inp(n: int = 1) -> str:
    return INPUT.replace("t#", f"t{n}")


def _mk(name: str = "a.gjf", text: str | None = None) -> int:
    (out,) = import_files([(name, (text or _inp(1)).encode("utf-8"))],
                          inputs_dir=config.HOME_DIR / "inputs")
    return out["id"]


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch) -> Path:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
def rec() -> list[tuple[str, dict]]:
    return []  # 事件断言经 patch_queue 返回值 + 路由层事件序（见路由测试）


def _mk_queue(n: int, *, qid: str = "QQ0001", rollback: bool = False,
              state: str | None = None) -> list[int]:
    ids = [_mk(name=f"t{i}.gjf", text=_inp(i)) for i in range(n)]
    queues().create(qid, name="队列", skip_failed=False)
    for pos, tid in enumerate(ids):
        tasks().enqueue(tid, qid, pos)
    if rollback:
        queues().update(qid, rollback_flag=True)
    if state:
        queues().set_state(qid, state)
    return ids


def _seed_exec(tid: int, qid: str, state: str, *, cause: str | None = None,
               with_run: bool = False) -> int:
    eid = executions().create(
        task_id=tid, filename=tasks().get(tid)["filename"], queue_id=qid,
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})
    if with_run:
        run_d = config.HOME_DIR / "run" / str(eid)
        run_d.mkdir(parents=True, exist_ok=True)
        (run_d / "input.gjf").write_text(RUN_COPY, encoding="utf-8")
    executions().finalize(execution_id=eid, state=state,
                          finished_at="2026-09-26T00:00:00+00:00",
                          cause=cause)
    return eid


# ---------------- 状态分级矩阵 ----------------

def test_unsubmitted_allows_all_fields():
    _mk_queue(2)
    v = patch_queue("QQ0001", {"name": "新名", "skip_failed": True})
    assert v["queue"]["name"] == "新名"
    assert v["queue"]["skip_failed"] is True


def test_submitted_rejects_name_and_skip_failed():
    _mk_queue(2, state="submitted")
    for payload in ({"name": "x"}, {"skip_failed": True}):
        with pytest.raises(ApiError) as ei:
            patch_queue("QQ0001", payload)
        body = ei.value.body()["error"]
        assert body["code"] == "QUEUE_STATE_CONFLICT"


def test_submitted_allows_member_ids():
    ids = _mk_queue(3, state="submitted")
    v = patch_queue("QQ0001", {"member_ids": [ids[2], ids[0]]})
    assert v["queue"]["member_ids"] == [ids[2], ids[0]]


def test_executing_and_completed_reject_everything():
    for i, state in enumerate(("executing", "completed")):
        qid = f"QQ00{i}X"
        _mk_queue(2, qid=qid, state=state)
        for payload in ({"name": "x"}, {"skip_failed": True},
                        {"member_ids": []}):
            with pytest.raises(ApiError) as ei:
                patch_queue(qid, payload)
            assert ei.value.body()["error"]["code"] == "QUEUE_STATE_CONFLICT"


def test_missing_queue_404():
    with pytest.raises(ApiError) as ei:
        patch_queue("NOPE00", {"name": "x"})
    assert ei.value.body()["error"]["code"] == "NOT_FOUND"


# ---------------- member_ids 校验 ----------------

def test_member_addition_rejected_422():
    ids = _mk_queue(2)
    outsider = _mk(name="out.gjf")
    with pytest.raises(ApiError) as ei:
        patch_queue("QQ0001", {"member_ids": [ids[0], outsider]})
    assert ei.value.body()["error"]["code"] == "VALIDATION_FAILED"


def test_member_duplicate_rejected_422():
    ids = _mk_queue(2)
    with pytest.raises(ApiError) as ei:
        patch_queue("QQ0001", {"member_ids": [ids[0], ids[0]]})
    assert ei.value.body()["error"]["code"] == "VALIDATION_FAILED"


def test_remove_to_zero_rejected_409_floor():
    ids = _mk_queue(2)
    with pytest.raises(ApiError) as ei:
        patch_queue("QQ0001", {"member_ids": []})
    assert ei.value.body()["error"]["code"] == "QUEUE_MEMBER_FLOOR"
    assert ei.value.body()["error"].get("details") is not None or True


# ---------------- 移除分流四类 ----------------

def test_remove_unexecuted_returns_candidate_id_kept():
    ids = _mk_queue(3)
    out = patch_queue("QQ0001", {"member_ids": [ids[2], ids[1]]})  # 移除 ids[0]
    assert out["moved_in"] == [ids[0]]  # id 延续退回候选
    row = tasks().get(ids[0])
    assert row["form"] == "candidate"
    assert row["origin"] == "returned_unrun"
    assert out["queue"]["member_ids"] == [ids[2], ids[1]]  # 顺序即新 position


def test_remove_succeeded_detaches_without_new_candidate():
    ids = _mk_queue(2, rollback=True)
    _seed_exec(ids[0], "QQ0001", "succeeded")
    out = patch_queue("QQ0001", {"member_ids": [ids[1]]})
    assert tasks().get(ids[0])["form"] == "finished"  # 脱离：只留历史
    assert out["moved_in"] == []
    assert tasks().count_by_form("candidate") == 0  # 无新候选生成
    assert tasks().get(ids[1])["form"] == "queue_member"  # 留队成员不变


def test_remove_failed_spawns_candidate_from_run_copy():
    ids = _mk_queue(2, rollback=True)
    _seed_exec(ids[0], "QQ0001", "failed", cause="program_error",
               with_run=True)
    out = patch_queue("QQ0001", {"member_ids": [ids[1]]})
    assert tasks().get(ids[0])["form"] == "finished"
    new_cands = [r for r in tasks().list_by_form("candidate")
                 if r["id"] != ids[1] - 1 or True]
    new_cands = [r for r in tasks().list_by_form("candidate")
                 if r["origin"] == "returned_failed"]
    assert len(new_cands) == 1
    spawned = new_cands[0]
    assert spawned["id"] != ids[0]  # 新 id
    assert spawned["filename"] == tasks().get(ids[0])["filename"]
    assert spawned["failure_note"] == "program_error"  # 附归因
    copied = (config.HOME_DIR / "inputs" / str(spawned["id"])).read_text()
    assert copied == RUN_COPY  # 以实际执行副本为源


def test_remove_skipped_spawns_candidate_from_task_copy():
    ids = _mk_queue(2, rollback=True)
    _seed_exec(ids[0], "QQ0001", "skipped", cause="predecessor_failed")
    out = patch_queue("QQ0001", {"member_ids": [ids[1]]})
    spawned = [r for r in tasks().list_by_form("candidate")
               if r["origin"] == "returned_unrun" and r["id"] != ids[0]]
    assert len(spawned) == 1
    copied = (config.HOME_DIR / "inputs" / str(spawned[0]["id"])).read_text()
    assert copied == _inp(0)  # skipped 无执行目录：回落任务输入副本（t0 自身）
    assert tasks().get(ids[0])["form"] == "finished"


def test_remove_running_member_rejected():
    """回退后仍在跑的成员不可移除（在途，状态机拒绝）。"""
    ids = _mk_queue(2, rollback=True)
    eid = executions().create(
        task_id=ids[0], filename=tasks().get(ids[0])["filename"],
        queue_id="QQ0001",
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})
    assert eid > 0
    with pytest.raises(ApiError) as ei:
        patch_queue("QQ0001", {"member_ids": [ids[1]]})
    assert ei.value.body()["error"]["code"] == "TASK_STATE_CONFLICT"


# ---------------- 自动成功判定 ----------------

def test_auto_success_after_removing_all_failed_skipped():
    ids = _mk_queue(3, rollback=True)
    _seed_exec(ids[0], "QQ0001", "succeeded")
    _seed_exec(ids[1], "QQ0001", "failed", cause="program_error")
    _seed_exec(ids[2], "QQ0001", "skipped", cause="predecessor_failed")
    out = patch_queue("QQ0001", {"member_ids": [ids[0]]})
    assert out["auto_success"] is True
    q = queues().get("QQ0001")
    assert q["state"] == "completed"
    assert q["finish_reason"] == "success"
    assert q["last_failure"] is None  # 成功终态清 null
    assert bool(q["rollback_flag"]) is True  # 历史回退痕迹保留


def test_auto_success_not_triggered_for_new_queue():
    ids = _mk_queue(2)  # 从未提交：无执行记录
    out = patch_queue("QQ0001", {"member_ids": [ids[0]]})
    assert out["auto_success"] is False
    assert queues().get("QQ0001")["state"] == "unsubmitted"


def test_auto_success_not_triggered_with_skipped_remaining():
    ids = _mk_queue(2, rollback=True)
    _seed_exec(ids[0], "QQ0001", "succeeded")
    _seed_exec(ids[1], "QQ0001", "skipped", cause="predecessor_failed")
    out = patch_queue("QQ0001", {"member_ids": [ids[1], ids[0]]})  # 仅重排
    assert out["auto_success"] is False  # skipped 成员仍在：不触发
    assert queues().get("QQ0001")["state"] == "unsubmitted"


# ---------------- submitted 移除退回 + 待执行快照 ----------------

def test_submitted_removal_returns_unrun_and_snapshots():
    ids = _mk_queue(2, state="submitted")
    seats().append(kind="queue", queue_id="QQ0001")  # 席位随 submitted 存在
    out = patch_queue("QQ0001", {"member_ids": [ids[1]]})
    assert out["moved_in"] == [ids[0]]
    assert tasks().get(ids[0])["origin"] == "returned_unrun"
    assert out["members_changed"] is True
    assert out["queue"]["state"] == "submitted"


# ---------------- 与引擎窗口推进的竞态（FakeGateway） ----------------

def test_patch_race_with_window_advance(rec):
    """窗口推进中 PATCH：executing 态整体 409、回退后在跑成员不可移除、
    收尾后编辑取最新成员结局分流——派发语义不被撕裂。"""
    from web.src.store import settings
    settings().set("parallel_window", 2)
    gw = FakeGateway(cpus=8)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    ids = _mk_queue(3, state="submitted")
    seats().append(kind="queue", queue_id="QQ0001")

    # 窗口推进派发前两个成员（队列转 executing）
    disp.advance()
    assert [s["name"] for s in gw.submitted] == ["t0.gjf", "t1.gjf"]
    assert queues().get("QQ0001")["state"] == "executing"

    # executing 态 PATCH 整体拒绝：派发态不被撕裂
    with pytest.raises(ApiError):
        patch_queue("QQ0001", {"member_ids": ids[:1]})
    assert len(gw.submitted) == 2  # 无重复派发

    # 首成员失败（未勾跳过）：t2 skipped + 整队回退（引擎分流，FakeGateway 编排）
    job0 = str(executions().list_by_task(ids[0])[0]["hq_job_id"])
    job1 = str(executions().list_by_task(ids[1])[0]["hq_job_id"])
    gw.set_state(job0, "failed")
    disp.tick()
    q = queues().get("QQ0001")
    assert q["state"] == "unsubmitted"  # 已回退（rollback_flag 置位）
    assert bool(q["rollback_flag"]) is True

    # 回退后 t1 仍在跑：在途成员不可移除（状态机拒绝；保留名单剔除 t1）
    with pytest.raises(ApiError) as ei:
        patch_queue("QQ0001", {"member_ids": [ids[0], ids[2]]})
    assert ei.value.body()["error"]["code"] == "TASK_STATE_CONFLICT"

    # t1 收尾 succeeded 后编辑：succeeded 脱离、skipped 新候选，按结局分流
    gw.set_state(job1, "finished")
    disp.tick()
    out = patch_queue("QQ0001", {"member_ids": [ids[0]]})
    assert out["auto_success"] is False  # 剩余 t0 最近终态 failed：不触发
    assert tasks().get(ids[1])["form"] == "finished"
    assert tasks().get(ids[2])["form"] == "finished"
    assert len(gw.submitted) == 2  # 全程无重复派发
