"""待执行席位领域逻辑测试（B5，m1-plan §5 测试表 + 错误码语义）。

构造数据驱动：队列席位/在跑执行均经 repo 构造，不依赖引擎。
"""
import pytest

from web.src.errors import ApiError
from web.src.services import pending
from web.src.store import executions, queues, seats, tasks


def _cand(name: str) -> int:
    return tasks().create_candidate(name, "imported")


def _queue(qid: str, n: int) -> str:
    queues().create(qid, name=qid)
    for i in range(n):
        tid = tasks().create_candidate(f"{qid}-m{i}.gjf", "imported")
        tasks().enqueue(tid, qid, i)
    return qid


def _run(tid: int, qid: str | None = None) -> int:
    return executions().create(task_id=tid, filename=f"t{tid}.gjf",
                               resources={"nproc": 4, "mem_gb": 8},
                               queue_id=qid)


def _seat_ids() -> list[int]:
    return [s["seat_id"] for s in seats().list_by_position()]


# ---------------- 追加与容量 ----------------

def test_append_task_tail_and_form_transition():
    t1, t2 = _cand("a.gjf"), _cand("b.gjf")
    s1 = pending.append_task(t1)
    s2 = pending.append_task(t2)
    assert _seat_ids() == [s1, s2]  # 尾部追加
    assert tasks().get(t1)["form"] == "seat_task"
    snap = pending.snapshot()
    assert snap["capacity"] == {"limit": 3, "occupied": 2, "available": 1}
    assert snap["window_size"] == 1
    assert snap["seats"][0]["members"] == [
        {"task_id": t1, "filename": "a.gjf", "state": "staged"}]


def test_append_queue_marks_submitted_one_seat():
    qid = _queue("qa", 3)
    sid = pending.append_queue(qid)
    assert len(_seat_ids()) == 1  # 整条队列占一席
    assert queues().get(qid)["state"] == "submitted"
    snap = pending.snapshot()
    assert snap["seats"][0]["kind"] == "queue"
    assert [m["task_id"] for m in snap["seats"][0]["members"]] == \
        [m["id"] for m in tasks().list_queue_members(qid)]


def test_capacity_full_409():
    for i in range(3):  # 默认上限 3
        pending.append_task(_cand(f"t{i}.gjf"))
    with pytest.raises(ApiError) as ei:
        pending.append_task(_cand("x.gjf"))
    e = ei.value.body()["error"]
    assert e["code"] == "PENDING_CAPACITY_FULL"
    assert ei.value.http == 409
    assert e["details"] == {"limit": 3}


# ---------------- 重排 ----------------

def test_reorder_atomic_and_positions():
    ids = [pending.append_task(_cand(f"t{i}.gjf")) for i in range(3)]
    snap = pending.reorder([ids[2], ids[0], ids[1]])
    assert [s["seat_id"] for s in snap["seats"]] == [ids[2], ids[0], ids[1]]
    assert [s["position"] for s in snap["seats"]] == [0, 1, 2]


def test_reorder_rejects_bad_payload_unchanged():
    ids = [pending.append_task(_cand(f"t{i}.gjf")) for i in range(3)]
    with pytest.raises(ApiError) as ei:
        pending.reorder([ids[0], ids[1]])  # 缺席位
    assert ei.value.body()["error"]["code"] == "INVALID_REQUEST"
    with pytest.raises(ApiError):
        pending.reorder(ids + [ids[0]])  # 重复
    assert [s["seat_id"] for s in pending.snapshot()["seats"]] == ids


def test_reorder_with_locked_409():
    t1, t2 = _cand("a.gjf"), _cand("b.gjf")
    s1 = pending.append_task(t1)
    pending.append_task(t2)
    _run(t1)  # 头部席位开跑 → 窗口触及
    with pytest.raises(ApiError) as ei:
        pending.reorder(list(reversed(_seat_ids())))
    e = ei.value.body()["error"]
    assert e["code"] == "SEAT_WINDOW_LOCKED"
    assert ei.value.http == 409
    assert e["details"]["seat_ids"] == [s1]
    assert pending.snapshot()["seats"][0]["locked"] is True


def test_reorder_allows_waiting_area_when_locked_in_place():
    """锁定席位保持原下标 → 放行等待区互换（roadmap §2.1：未在执行
    成员可重排）。GUI 走查实测：原实现存在锁定席位即全量 409，
    等待区拖拽在窗口非空时永不生效。"""
    t1, t2, t3 = (_cand(f"t{i}.gjf") for i in range(3))
    pending.append_task(t1)  # s 头部，_run 后锁定
    pending.append_task(t2)
    pending.append_task(t3)
    _run(t1)
    current = [s["seat_id"] for s in pending.snapshot()["seats"]]
    locked = current[0]
    pending.reorder([current[0], current[2], current[1]])  # 锁定原位，等待区互换
    assert [s["seat_id"] for s in pending.snapshot()["seats"]] == \
        [current[0], current[2], current[1]]
    with pytest.raises(ApiError) as ei:  # 移动锁定席位仍 409
        pending.reorder([current[1], current[0], current[2]])
    assert ei.value.body()["error"]["code"] == "SEAT_WINDOW_LOCKED"
    assert ei.value.body()["error"]["details"]["seat_ids"] == [locked]


# ---------------- 整席移除 ----------------

def test_remove_task_seat_returns_candidate():
    t1 = _cand("a.gjf")
    s1 = pending.append_task(t1)
    out = pending.remove_seat(s1)
    assert out == {"moved_in": [t1], "queue_unsubmitted": None}
    row = tasks().get(t1)
    assert row["form"] == "candidate" and row["origin"] == "returned_unrun"
    assert _seat_ids() == []


def test_remove_queue_seat_rolls_back_unsubmitted():
    qid = _queue("qa", 2)
    sid = pending.append_queue(qid)
    out = pending.remove_seat(sid)
    assert out == {"moved_in": [], "queue_unsubmitted": "qa"}
    assert queues().get(qid)["state"] == "unsubmitted"
    assert all(m["form"] == "queue_member"
               for m in tasks().list_queue_members(qid))  # 成员不变
    assert _seat_ids() == []


def test_remove_locked_seat_409():
    t1 = _cand("a.gjf")
    s1 = pending.append_task(t1)
    _run(t1)
    with pytest.raises(ApiError) as ei:
        pending.remove_seat(s1)
    assert ei.value.body()["error"]["code"] == "SEAT_WINDOW_LOCKED"
    assert _seat_ids() == [s1]


def test_remove_repacks_positions():
    ids = [pending.append_task(_cand(f"t{i}.gjf")) for i in range(3)]
    pending.remove_seat(ids[1])
    assert [s["position"] for s in pending.snapshot()["seats"]] == [0, 1]


# ---------------- 席位内成员移除 ----------------

def test_member_removal_floor_unstarted_queue():
    qid = _queue("qa", 3)
    sid = pending.append_queue(qid)
    m0, m1, m2 = [m["id"] for m in tasks().list_queue_members(qid)]
    assert pending.remove_member(sid, m1)["moved_in"] == [m1]
    assert tasks().get(m1)["form"] == "candidate"
    assert tasks().get(m1)["origin"] == "returned_unrun"
    assert [m["position"] for m in tasks().list_queue_members(qid)] == [0, 1]
    assert pending.remove_member(sid, m2)["moved_in"] == [m2]
    with pytest.raises(ApiError) as ei:  # 未开始队列至多移除至剩 1 个
        pending.remove_member(sid, m0)
    assert ei.value.body()["error"]["code"] == "SEAT_MEMBER_LAST"
    assert len(tasks().list_queue_members(qid)) == 1


def test_member_executed_409_running_and_final():
    qid = _queue("qa", 2)
    sid = pending.append_queue(qid)
    m0, m1 = [m["id"] for m in tasks().list_queue_members(qid)]
    ex = _run(m0, qid)
    with pytest.raises(ApiError) as ei:
        pending.remove_member(sid, m0)
    assert ei.value.body()["error"]["code"] == "SEAT_MEMBER_EXECUTED"
    executions().finalize(execution_id=ex, state="succeeded",
                          finished_at="2026-01-01T00:00:00+08:00")
    with pytest.raises(ApiError):  # 终态已执行同样不可移除
        pending.remove_member(sid, m0)


def test_member_removal_running_queue_clears_to_running():
    """执行中队列可清至只剩在跑成员。"""
    qid = _queue("qa", 2)
    sid = pending.append_queue(qid)
    m0, m1 = [m["id"] for m in tasks().list_queue_members(qid)]
    _run(m0, qid)
    out = pending.remove_member(sid, m1)  # 只剩在跑成员合法
    assert out == {"moved_in": [m1], "queue_unsubmitted": None}
    assert [m["id"] for m in tasks().list_queue_members(qid)] == [m0]


def test_task_seat_member_removal_equals_seat_removal():
    t1 = _cand("a.gjf")
    s1 = pending.append_task(t1)
    out = pending.remove_member(s1, t1)
    assert out == {"moved_in": [t1], "queue_unsubmitted": None}
    assert _seat_ids() == []
    assert tasks().get(t1)["form"] == "candidate"


def test_member_removal_not_found():
    qid = _queue("qa", 1)
    sid = pending.append_queue(qid)
    with pytest.raises(ApiError) as ei:
        pending.remove_member(sid, 999999)
    assert ei.value.body()["error"]["code"] == "NOT_FOUND"


# ---------------- 上限调小挤出 ----------------

def test_shrink_tail_first_keeps_locked():
    t0, t1, t2 = (_cand("a.gjf"), _cand("b.gjf"), _cand("c.gjf"))
    pending.append_task(t0)
    s2 = pending.append_task(t1)
    s3 = pending.append_task(t2)
    _run(t1)  # 中间席位开跑（构造数据）→ 锁定，不追溯
    out = pending.apply_capacity_limit(1)
    # 自队尾挤未触及席位：先队尾 t2，再队头 t0；锁定席位 t1 保留
    assert [r["moved_in"] for r in out["removed"]] == [[t2], [t0]]
    assert out["over"] is False
    assert _seat_ids() == [s2]
    assert tasks().get(t1)["form"] == "seat_task"  # 在跑不追溯
    assert tasks().get(t2)["form"] == "candidate"


def test_shrink_over_when_all_locked():
    t0, t1 = _cand("a.gjf"), _cand("b.gjf")
    pending.append_task(t0)
    pending.append_task(t1)
    _run(t0)
    _run(t1)
    out = pending.apply_capacity_limit(1)
    assert out["removed"] == []
    assert out["over"] is True  # 在途席位临时超出上限
    assert len(_seat_ids()) == 2


# ---------------- snapshot 成员状态 ----------------

def test_snapshot_member_states():
    qid = _queue("qa", 2)
    sid = pending.append_queue(qid)
    m0, m1 = [m["id"] for m in tasks().list_queue_members(qid)]
    ex = _run(m0, qid)
    snap = pending.snapshot()
    states = {m["task_id"]: m["state"] for m in snap["seats"][0]["members"]}
    assert states == {m0: "running", m1: "staged"}
    executions().finalize(execution_id=ex, state="failed",
                          finished_at="2026-01-01T00:00:00+08:00",
                          cause="program_error")
    snap = pending.snapshot()
    states = {m["task_id"]: m["state"] for m in snap["seats"][0]["members"]}
    assert states[m0] == "failed"
