"""queues 域路由（§2.3，M0 mock）。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Response

from ..errors import NOT_FOUND, VALIDATION_FAILED, err
from ..mock import get_state
from starlette import status

router = APIRouter(tags=["queues"])


@router.get("/queues")
def list_queues() -> list:
    return [dict(q) for q in get_state().queues]


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
    state = get_state()
    q = state.create_queue(name, member_ids, bool(skip_failed))
    for cid in member_ids:
        if (c := state.get_candidate(cid)) is not None:
            state.remove_candidate(cid)
            state.emit("candidates.changed", {"action": "moved_out",
                                              "candidate_id": cid})
    state.emit("queues.changed", {"action": "created", "queue_id": q["id"]})
    return dict(q)


@router.get("/queues/{id}")
def get_queue(id: str) -> dict:
    q = get_state().get_queue(id)
    if q is None:
        raise NOT_FOUND("queue", id)
    return dict(q)


@router.patch("/queues/{id}")
def update_queue(id: str, payload: dict) -> dict:
    q = get_state().get_queue(id)
    if q is None:
        raise NOT_FOUND("queue", id)
    if q["state"] != "unsubmitted":
        raise err("QUEUE_STATE_CONFLICT", "仅未提交队列可编辑",
                  {"state": q["state"]}, http=409)
    if "name" in payload:
        q["name"] = payload["name"]
    if "skip_failed" in payload:
        q["skip_failed"] = bool(payload["skip_failed"])
    if "member_ids" in payload:
        q["member_ids"] = payload["member_ids"]
    q["updated_at"] = _now_iso()
    get_state().emit("queues.changed", {"action": "updated", "queue_id": id})
    return dict(q)


@router.delete("/queues/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_queue(id: str) -> Response:
    if not get_state().delete_queue(id):
        raise NOT_FOUND("queue", id)
    get_state().emit("queues.changed", {"action": "deleted", "queue_id": id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/queues/{id}/submit")
def submit_queue(id: str) -> dict:
    state = get_state()
    q = state.get_queue(id)
    if q is None:
        raise NOT_FOUND("queue", id)
    if q["state"] != "unsubmitted":
        raise err("QUEUE_STATE_CONFLICT", "仅未提交队列可提交", http=409)
    limit = int(state.get_runtime("seat_limit"))
    if len(state.seats) >= limit:
        raise err("PENDING_CAPACITY_FULL", "在途席位满员",
                  {"limit": limit}, http=409)
    seat_id = state.next_id()
    members = [{"task_id": cid,
                "filename": (state.get_candidate(cid) or {}).get("filename",
                                                                 f"job{cid}.gjf"),
                "state": "staged"} for cid in q["member_ids"]]
    state.seats.append({
        "seat_id": seat_id, "kind": "queue", "task_id": None, "queue_id": id,
        "position": len(state.seats), "members": members, "locked": False,
    })
    q["state"] = "submitted"
    state.emit("queue.status", {"queue_id": id, "from": "unsubmitted",
                                "to": "submitted"})
    state.emit("pending.snapshot", state.pending())
    return {"seat_id": seat_id, "task_id": q["member_ids"][0]}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")