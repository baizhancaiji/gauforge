"""待执行席位领域服务（B5）：追加/重排/整席移除/成员移除/容量挤出/窗口锁定。

语义出处：roadmap §2.4 待执行队列/队列/派发原则、m1-plan §4.3 B5。
- 容量 = 在途席位上限（单任务与整条队列各计 1 席，含执行中席位）；
  满员 409 PENDING_CAPACITY_FULL。
- 窗口触及席位（实体存在 running 执行）→ locked：不可整席重排/移除；
  席位内规则不变（执行中队列可移除未执行成员）。
- 整席移除：单任务退候选（origin=returned_unrun，id 延续）；队列回退
  未提交（成员不变，state→unsubmitted，无回退标记）。
- 成员移除：未执行者退候选；已执行（存在任何执行记录）409
  SEAT_MEMBER_EXECUTED；未开始队列至多移除至剩 1 个（409
  SEAT_MEMBER_LAST）；执行中队列可清至只剩在跑成员。
- 上限调小挤出：自队尾、只挤窗口未触及席位、在跑不追溯（可临时超限）。

事件（candidates.changed(moved_in)/pending.snapshot/queue.status）由路由层
（#8）依本层返回的动作清单发出，本层不发事件、不写 SQL。
"""
from __future__ import annotations

from ..errors import err, not_found
from ..store import executions, queues, seats, settings, tasks


def _limit() -> int:
    return int(settings().get("pending_seat_limit"))


def window_size() -> int:
    return int(settings().get("parallel_window"))


def _running_task_ids() -> set[int]:
    return {r["task_id"] for r in executions().list_by_state("running")}


def locked_seat_ids() -> set[int]:
    """并行窗口触及席位：实体存在 running 执行（引擎保证位于头部区）。"""
    running = _running_task_ids()
    locked = set()
    for s in seats().list_by_position():
        if s["kind"] == "task":
            hit = s["task_id"] in running
        else:
            hit = any(m["id"] in running
                      for m in tasks().list_queue_members(s["queue_id"]))
        if hit:
            locked.add(s["seat_id"])
    return locked


def capacity() -> dict:
    occupied = seats().count()
    limit = _limit()
    return {"limit": limit, "occupied": occupied,
            "available": max(0, limit - occupied)}


def _member_view(m: dict) -> dict:
    exs = executions().list_by_task(m["id"])
    if any(e["state"] == "running" for e in exs):
        state = "running"
    elif exs:
        state = exs[-1]["state"]  # 最近一次终态
    else:
        state = "staged"
    return {"task_id": m["id"], "filename": m["filename"], "state": state}


def snapshot() -> dict:
    """PendingResponse：席位（含成员概览/locked）+ 容量 + 窗口。"""
    locked = locked_seat_ids()
    items = []
    for s in seats().list_by_position():
        if s["kind"] == "task":
            row = tasks().get(s["task_id"])
            members = [_member_view(row)] if row else []
        else:
            members = [_member_view(m)
                       for m in tasks().list_queue_members(s["queue_id"])]
        items.append({"seat_id": s["seat_id"], "kind": s["kind"],
                      "task_id": s["task_id"], "queue_id": s["queue_id"],
                      "position": s["position"], "members": members,
                      "locked": s["seat_id"] in locked})
    return {"seats": items, "capacity": capacity(),
            "window_size": window_size()}


def _check_capacity() -> None:
    cap = capacity()
    if cap["occupied"] >= cap["limit"]:
        raise err("PENDING_CAPACITY_FULL", "在途席位满员",
                  {"limit": cap["limit"]}, http=409)


def append_task(task_id: int) -> int:
    """行内提交：candidate → 尾部席位（kind=task），form→seat_task。"""
    row = tasks().get(task_id)
    if row is None or row["form"] != "candidate":
        raise not_found("candidate", task_id)
    _check_capacity()
    sid = seats().append(kind="task", task_id=task_id)
    tasks().to_seat_task(task_id)
    return sid


def append_queue(queue_id: str) -> int:
    """队列提交：整条队列占一席（尾部追加），state→submitted。"""
    if queues().get(queue_id) is None:
        raise not_found("queue", queue_id)
    _check_capacity()
    sid = seats().append(kind="queue", queue_id=queue_id)
    queues().set_state(queue_id, "submitted")
    return sid


def reorder(seat_order: list[int]) -> dict:
    """PUT /pending/order 全量原子重排；存在窗口触及席位即 409。"""
    existing = {s["seat_id"] for s in seats().list_by_position()}
    if (not isinstance(seat_order, list)
            or len(seat_order) != len(existing)
            or set(seat_order) != existing):
        raise err("INVALID_REQUEST", "seat_order 必须为在席席位的全量排列",
                  http=400)
    locked = locked_seat_ids()
    if locked:
        raise err("SEAT_WINDOW_LOCKED", "并行窗口已触及席位，不可整席重排",
                  {"seat_ids": sorted(locked)}, http=409)
    seats().reorder(list(seat_order))
    return snapshot()


def remove_seat(seat_id: int) -> dict:
    """整席移除。返回动作清单供路由层发事件：
    {"moved_in": [task_id…], "queue_unsubmitted": queue_id|None}。"""
    seat = seats().get(seat_id)
    if seat is None:
        raise not_found("seat", seat_id)
    if seat_id in locked_seat_ids():
        raise err("SEAT_WINDOW_LOCKED", "席位已被并行窗口触及",
                  {"seat_id": seat_id}, http=409)
    moved: list[int] = []
    qid = None
    if seat["kind"] == "task":
        tasks().return_to_candidate(seat["task_id"], "returned_unrun")
        moved = [seat["task_id"]]
    else:
        qid = seat["queue_id"]
        queues().set_state(qid, "unsubmitted")
    seats().remove(seat_id)
    seats().reorder([s["seat_id"] for s in seats().list_by_position()])
    return {"moved_in": moved, "queue_unsubmitted": qid}


def remove_member(seat_id: int, task_id: int) -> dict:
    """席位内移除成员：未执行者退候选（id 延续）。返回动作清单。

    单任务席位成员移除即整席移除（席位随任务离席）。
    """
    seat = seats().get(seat_id)
    if seat is None:
        raise not_found("seat", seat_id)
    if seat["kind"] == "task":
        if seat["task_id"] != task_id:
            raise not_found("task", task_id)
        return remove_seat(seat_id)
    members = tasks().list_queue_members(seat["queue_id"])
    if not any(m["id"] == task_id for m in members):
        raise not_found("task", task_id)
    if executions().list_by_task(task_id):
        raise err("SEAT_MEMBER_EXECUTED", "已执行成员不可移除",
                  {"task_id": task_id}, http=409)
    running = _running_task_ids()
    n_running = sum(1 for m in members if m["id"] in running)
    floor = n_running if n_running else 1
    if len(members) - 1 < floor:
        raise err("SEAT_MEMBER_LAST", "队列席位成员不可再移除",
                  {"seat_id": seat_id}, http=409)
    tasks().return_to_candidate(task_id, "returned_unrun")
    tasks().repack_queue(seat["queue_id"])
    return {"moved_in": [task_id], "queue_unsubmitted": None}


def apply_capacity_limit(new_limit: int) -> dict:
    """上限调小挤出：自队尾、只挤窗口未触及席位、在跑不追溯。

    返回 {"removed": [remove_seat 动作清单…], "over": bool}；over=True 表示
    余下均为窗口触及席位，在途席位临时超出上限（roadmap §2.5）。
    """
    removed: list[dict] = []
    while seats().count() > new_limit:
        locked = locked_seat_ids()
        free = [s for s in seats().list_by_position()
                if s["seat_id"] not in locked]
        if not free:
            break
        removed.append(remove_seat(free[-1]["seat_id"]))
    return {"removed": removed, "over": seats().count() > new_limit}
