"""pending 域路由：待执行席位管理（§2.3，M0 mock）。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Response

from ..errors import NOT_FOUND, err
from ..mock import get_state
from starlette import status

router = APIRouter(tags=["pending"])


@router.get("/pending")
def get_pending() -> dict:
    return get_state().pending()


@router.put("/pending/order")
def reorder_pending(payload: dict) -> dict:
    state = get_state()
    seat_order = payload.get("seat_order")
    if not isinstance(seat_order, list):
        raise err("INVALID_REQUEST", "seat_order 须为列表", http=400)
    existing = {s["seat_id"] for s in state.seats}
    if set(seat_order) != existing:
        raise err("INVALID_REQUEST", "seat_order 必须覆盖全部在席席位", http=400)
    if any(s["locked"] for s in state.seats):
        raise err("SEAT_WINDOW_LOCKED", "已有并行窗口触及席位，不可整席重排",
                  http=409)
    by_id = {s["seat_id"]: s for s in state.seats}
    state.seats = [by_id[sid] for sid in seat_order]
    for pos, s in enumerate(state.seats):
        s["position"] = pos
    state.emit("pending.snapshot", state.pending())
    return state.pending()


@router.delete("/pending/seats/{seat_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_seat(seat_id: int) -> Response:
    state = get_state()
    seat = next((s for s in state.seats if s["seat_id"] == seat_id), None)
    if seat is None:
        raise NOT_FOUND("seat", seat_id)
    if seat["locked"]:
        raise err("SEAT_WINDOW_LOCKED", "席位已被并行窗口触及", http=409)
    state.seats = [s for s in state.seats if s["seat_id"] != seat_id]
    for pos, s in enumerate(state.seats):
        s["position"] = pos
    for m in seat.get("members", []):
        # 单任务坐准确退回候选：新建候选记录（id 延续）。
        tid = m["task_id"]
        cand = state.add_candidate(f"job{tid}.gjf", origin="returned_unrun")
        state.emit("candidates.changed", {"action": "moved_in",
                                          "candidate_id": cand["id"]})
    state.emit("pending.snapshot", state.pending())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/pending/seats/{seat_id}/members/{task_id}")
def remove_seat_member(seat_id: int, task_id: int) -> dict:
    state = get_state()
    seat = next((s for s in state.seats if s["seat_id"] == seat_id), None)
    if seat is None:
        raise NOT_FOUND("seat", seat_id)
    if seat["locked"]:
        raise err("SEAT_WINDOW_LOCKED", "席位已被并行窗口触及", http=409)
    before = len(seat["members"])
    seat["members"] = [m for m in seat["members"] if m["task_id"] != task_id]
    if len(seat["members"]) == before:
        raise NOT_FOUND("task", task_id)
    cand = state.add_candidate(f"job{task_id}.gjf", origin="returned_unrun")
    state.emit("candidates.changed", {"action": "moved_in",
                                      "candidate_id": cand["id"]})
    state.emit("pending.snapshot", state.pending())
    return state.pending()