"""pending 域路由（§2.3，M1 真实化：快照/重排/整席移除/成员移除）。

数据源：services.pending（store.seats/tasks/queues）；事件经 mock
state.emit 记入 SSE 重放窗口（B11 事件总线真实化前过渡）。
"""
from __future__ import annotations

from fastapi import APIRouter, Response
from starlette import status

from ..errors import err
from ..mock import get_state
from ..services import pending as pending_svc

router = APIRouter(tags=["pending"])


def _emit_removed(action: dict) -> None:
    """依领域动作清单发事件：moved_in / 队列回退 / 席位快照。"""
    for tid in action["moved_in"]:
        get_state().emit("candidates.changed",
                         {"action": "moved_in", "candidate_id": tid})
    qid = action["queue_unsubmitted"]
    if qid is not None:
        get_state().emit("queue.status",
                         {"queue_id": qid, "from": "submitted",
                          "to": "unsubmitted"})
    get_state().emit("pending.snapshot", pending_svc.snapshot())


@router.get("/pending")
def get_pending() -> dict:
    return pending_svc.snapshot()


@router.put("/pending/order")
def reorder_pending(payload: dict) -> dict:
    seat_order = payload.get("seat_order") if isinstance(payload, dict) else None
    if not isinstance(seat_order, list):
        raise err("INVALID_REQUEST", "seat_order 须为列表", http=400)
    snap = pending_svc.reorder(seat_order)
    get_state().emit("pending.snapshot", snap)
    return snap


@router.delete("/pending/seats/{seat_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_seat(seat_id: int) -> Response:
    _emit_removed(pending_svc.remove_seat(seat_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/pending/seats/{seat_id}/members/{task_id}")
def remove_seat_member(seat_id: int, task_id: int) -> dict:
    _emit_removed(pending_svc.remove_member(seat_id, task_id))
    return pending_svc.snapshot()
