"""队列删除增强与 id 全库查重测试（B4，m2-plan §5 test_queue_delete）。

覆盖：四态矩阵（unsubmitted 成员退回 / submitted 撤席+pending.snapshot+退回 /
executing 409 / completed 成员只留历史）；id 生成对照全库（含历史引用）查重。
"""
from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from web.src import config
from web.src.errors import ApiError
from web.src.services import queues as queues_svc
from web.src.services.candidates import import_files
from web.src.services.pending import append_queue, snapshot
from web.src.store import executions, queues, tasks

INPUT = "%mem=1GB\n%nprocshared=4\n#p opt\n\nt#\n\n0 1\nO 0 0 0\n\n"


def _inp(n: int = 0) -> str:
    return INPUT.replace("t#", f"t{n}")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch) -> Path:
    (tmp_path / "inputs").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


def _mk(name: str) -> int:
    (out,) = import_files([(name, _inp(0).encode("utf-8"))],
                          inputs_dir=config.HOME_DIR / "inputs")
    return out["id"]


def _mk_queue(n: int, *, qid: str, state: str | None = None) -> list[int]:
    ids = [_mk(f"t{i}.gjf") for i in range(n)]
    queues().create(qid, name="队列", skip_failed=False)
    for pos, tid in enumerate(ids):
        tasks().enqueue(tid, qid, pos)
    if state:
        queues().set_state(qid, state)
    return ids


# ---------------- 四态矩阵 ----------------

def test_delete_unsubmitted_returns_members():
    ids = _mk_queue(2, qid="QQ0001")
    out = queues_svc.delete_queue("QQ0001")
    assert sorted(out["moved_in"]) == ids
    assert out["seat_removed"] is False
    assert queues().get("QQ0001") is None
    for tid in ids:
        row = tasks().get(tid)
        assert row["form"] == "candidate"
        assert row["origin"] == "returned_unrun"  # id 延续


def test_delete_submitted_removes_seat_and_returns_members():
    ids = _mk_queue(2, qid="QQ0002", state="submitted")
    append_queue("QQ0002")  # 整队占席
    assert any(s["kind"] == "queue" and s["queue_id"] == "QQ0002"
               for s in snapshot()["seats"])
    out = queues_svc.delete_queue("QQ0002")
    assert out["seat_removed"] is True
    assert queues().get("QQ0002") is None
    # 席位消失、容量回收
    snap = snapshot()
    assert snap["seats"] == []
    assert snap["capacity"]["occupied"] == 0
    for tid in ids:
        assert tasks().get(tid)["form"] == "candidate"


def test_delete_executing_rejected():
    _mk_queue(2, qid="QQ0003", state="executing")
    with pytest.raises(ApiError) as ei:
        queues_svc.delete_queue("QQ0003")
    assert ei.value.body()["error"]["code"] == "QUEUE_STATE_CONFLICT"
    assert queues().get("QQ0003") is not None


def test_delete_completed_keeps_members_in_history_only():
    ids = _mk_queue(2, qid="QQ0004", state="completed")
    out = queues_svc.delete_queue("QQ0004")
    assert out["moved_in"] == []  # 无退回：全成员已执行
    assert queues().get("QQ0004") is None
    for tid in ids:
        row = tasks().get(tid)
        assert row["form"] == "finished"  # 只留历史（经历史页触达）
        assert row["queue_id"] is None  # 归属清除
    assert tasks().count_by_form("candidate") == 0  # 不生成新候选


def test_delete_missing_404():
    with pytest.raises(ApiError) as ei:
        queues_svc.delete_queue("NOPE00")
    assert ei.value.body()["error"]["code"] == "NOT_FOUND"


# ---------------- 队列 id 全库查重（含历史引用，永不复用） ----------------

def test_new_queue_id_avoids_existing_queue(monkeypatch):
    queues().create("AAAAAA", name="已有", skip_failed=False)
    chars = iter(list("AAAAAA") + list("BBBBBB"))
    monkeypatch.setattr(secrets, "choice", lambda alphabet: next(chars))
    assert queues_svc.new_queue_id() == "BBBBBB"  # 命中现存队列即重试


def test_new_queue_id_avoids_historical_references(monkeypatch):
    """已删除队列的 id 在任务/执行记录中的引用同样不可复用。"""
    tid = _mk("t.gjf")
    executions().create(task_id=tid, filename="t.gjf", queue_id="CCCCCC",
                        resources={"nproc": {"value": 1, "defaulted": True},
                                   "mem_gb": {"value": 1.0, "defaulted": True}})
    chars = iter(list("CCCCCC") + list("DDDDDD"))
    monkeypatch.setattr(secrets, "choice", lambda alphabet: next(chars))
    assert queues_svc.new_queue_id() == "DDDDDD"


def test_new_queue_id_random_shape():
    qid = queues_svc.new_queue_id()
    assert len(qid) == 6
    assert all(c in "ABCDEFGHJKMNPQRSTUVWXYZ23456789" for c in qid)
