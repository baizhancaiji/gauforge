"""queues 域路由（§2.3；M1 真实化：真实 queues/tasks/seats 存储）。

队列席位全语义（引擎序列展开/失败分流/回退）由引擎实现并以单测覆盖
（m1-plan §0「无 UI 亦有引擎」）；本路由负责创建/编辑/提交在真实存储
的落位与领域事件发射。GUI 队列组建属 M2。
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter
from fastapi import Response
from starlette import status

from ..errors import NOT_FOUND, VALIDATION_FAILED, err
from ..mock import get_state  # 事件总线（B11：emit → 领域事件扇出）
from ..services import pending as pending_svc
from ..services import verify as verify_svc
from ..store import queues as queues_store
from ..store import tasks as tasks_store

router = APIRouter(tags=["queues"])


def _new_queue_id() -> str:
    """短随机队列 id（大写字母数字去易混字符）。"""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def _queue_view(row: dict) -> dict:
    """契约 Queue 视图：聚合 member_ids（position 序）+ last_failure 反序列化
    （库行存 JSON 文本；list 路径的行未经 repo.get 解码）+ SQLite 整数布尔
    还原（skip_failed/rollback_flag 契约为 boolean）。"""
    row = dict(row)
    row["member_ids"] = [m["id"] for m in tasks_store().list_queue_members(row["id"])]
    row["skip_failed"] = bool(row.get("skip_failed"))
    row["rollback_flag"] = bool(row.get("rollback_flag"))
    lf = row.get("last_failure")
    if isinstance(lf, str):
        import json
        row["last_failure"] = json.loads(lf)
    return row


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
    qid = _new_queue_id()
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
    q = queues_store().get(id)
    if q is None:
        raise NOT_FOUND("queue", id)
    if q["state"] != "unsubmitted":
        raise err("QUEUE_STATE_CONFLICT", "仅未提交队列可编辑",
                  {"state": q["state"]}, http=409)
    fields: dict = {}
    if "name" in payload:
        fields["name"] = payload["name"]
    if "skip_failed" in payload:
        fields["skip_failed"] = bool(payload["skip_failed"])
    queues_store().update(id, **fields)
    get_state().emit("queues.changed", {"action": "updated", "queue_id": id})
    return _queue_view(queues_store().get(id))


@router.delete("/queues/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_queue(id: str) -> Response:
    q = queues_store().get(id)
    if q is None:
        raise NOT_FOUND("queue", id)
    if q["state"] != "unsubmitted":
        # 已提交/执行中队列占席运行中，删除会与引擎派发冲突（M2 队列管理处理）
        raise err("QUEUE_STATE_CONFLICT", "仅未提交队列可删除",
                  {"state": q["state"]}, http=409)
    for m in tasks_store().list_queue_members(id):
        tasks_store().return_to_candidate(m["id"], "returned_unrun")
        get_state().emit("candidates.changed",
                         {"action": "moved_in", "candidate_id": m["id"]})
    queues_store().delete(id)
    get_state().emit("queues.changed", {"action": "deleted", "queue_id": id})
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
