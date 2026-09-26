"""queues 域路由（§2.3；M1 真实化：真实 queues/tasks/seats 存储）。

队列席位全语义（引擎序列展开/失败分流/回退）由引擎实现并以单测覆盖
（m1-plan §0「无 UI 亦有引擎」）；本路由负责创建/编辑/提交在真实存储
的落位与领域事件发射。GUI 队列组建属 M2。
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Response
from starlette import status

from ..errors import NOT_FOUND, VALIDATION_FAILED, err
from ..mock import get_state  # 事件总线（B11：emit → 领域事件扇出）
from ..services import pending as pending_svc
from ..services import queues as queues_svc
from ..services import verify as verify_svc
from ..store import queues as queues_store
from ..store import tasks as tasks_store

router = APIRouter(tags=["queues"])


def _queue_view(row: dict) -> dict:
    """契约视图统一走服务层实现（services.queues.queue_view）。"""
    return queues_svc.queue_view(row)


@router.get("/queues")
def list_queues() -> list:
    return [_queue_view(r) for r in queues_store().list()]


@router.post("/queues", status_code=status.HTTP_201_CREATED)
def create_queue(payload: dict) -> dict:
    name = payload.get("name")
    member_ids = payload.get("member_ids")
    skip_failed = payload.get("skip_failed")
    if not name or not isinstance(member_ids, list):
        raise VALIDATION_FAILED(
            [{"field": "name", "reason": "required"},
             {"field": "member_ids", "reason": "required_list"}]
            if not name else
            [{"field": "member_ids", "reason": "required_list"}])
    if not (2 <= len(member_ids) <= 10):
        raise err("QUEUE_MEMBER_RANGE", "队列成员数须为 2–10",
                  {"actual": len(member_ids), "min": 2, "max": 10}, http=422)
    # 成员必须全部存在且仍为候选（默认仅生成候选，from §2.4）
    for cid in member_ids:
        row = tasks_store().get(cid)
        if row is None or row["form"] != "candidate":
            raise err("INVALID_MEMBERS",
                      f"任务 {cid} 不存在或不在候选列表", http=422)
    qid = queues_svc.new_queue_id()  # 对照全库（含历史引用）查重
    queues_store().create(qid, name=str(name), skip_failed=bool(skip_failed))
    for pos, cid in enumerate(member_ids):
        tasks_store().enqueue(cid, qid, pos)  # candidate → queue_member
        get_state().emit("candidates.changed",
                         {"action": "moved_out", "candidate_id": cid})
    get_state().emit("queues.changed", {"action": "created", "queue_id": qid})
    return _queue_view(queues_store().get(qid))


@router.get("/queues/{id}")
def get_queue(id: str) -> dict:
    q = queues_store().get(id)
    if q is None:
        raise NOT_FOUND("queue", id)
    return _queue_view(q)


@router.patch("/queues/{id}")
def update_queue(id: str, payload: dict) -> dict:
    """队列编辑（M2 全语义，m2-plan §2.2 状态分级矩阵）。

    事件时序（sse.md §3 队列编辑行）：退回成员 moved_in ×N 在前 →
    queues.changed(updated) → 自动成功 queue.status(unsubmitted→completed)；
    submitted 态成员变化另推 pending.snapshot（席位成员表更新）。
    """
    out = queues_svc.patch_queue(id, payload)
    for tid in out["moved_in"]:
        get_state().emit("candidates.changed",
                         {"action": "moved_in", "candidate_id": tid})
    get_state().emit("queues.changed", {"action": "updated", "queue_id": id})
    if out["auto_success"]:
        get_state().emit("queue.status",
                         {"queue_id": id, "from": "unsubmitted",
                          "to": "completed", "finish_reason": "success"})
    elif out["members_changed"] and out["queue"]["state"] == "submitted":
        get_state().emit("pending.snapshot", pending_svc.snapshot())
    return out["queue"]


@router.delete("/queues/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_queue(id: str) -> Response:
    """队列删除（M2 分级：submitted 撤席/completed 成员只留历史）。

    事件时序（sse.md §3）：moved_in ×N → queues.changed(deleted)；
    删除在待执行队列另推 pending.snapshot（在两者之后，席位撤销释放）。
    """
    action = queues_svc.delete_queue(id)
    for tid in action["moved_in"]:
        get_state().emit("candidates.changed",
                         {"action": "moved_in", "candidate_id": tid})
    get_state().emit("queues.changed", {"action": "deleted", "queue_id": id})
    if action["seat_removed"]:
        get_state().emit("pending.snapshot", pending_svc.snapshot())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/queues/{id}/submit")
def submit_queue(id: str) -> dict:
    q = queues_store().get(id)
    if q is None:
        raise NOT_FOUND("queue", id)
    if q["state"] != "unsubmitted":
        raise err("QUEUE_STATE_CONFLICT", "仅未提交队列可提交", http=409)
    # 提交核验逐成员统一执行（m2-plan §2.5）：任一失败整队拒绝并指明成员，
    # 核验在提交事务内先于建席位；有变化的副本规范化写回。
    normalized = False
    for m in tasks_store().list_queue_members(id):
        if verify_svc.verify_and_store(m["id"]):
            normalized = True
    # 整条队列占一席（尾部追加、容量校验、state→submitted），引擎按执行
    # 序列展开派发（含失败分流/回退，engine/dispatcher）。
    seat_id = pending_svc.append_queue(id)
    get_state().emit("queue.status", {"queue_id": id, "from": "unsubmitted",
                                      "to": "submitted"})
    get_state().emit("pending.snapshot", pending_svc.snapshot())
    first = tasks_store().list_queue_members(id)[0]
    return {"seat_id": seat_id, "task_id": first["id"], "normalized": normalized}
