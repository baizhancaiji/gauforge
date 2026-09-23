"""history 域路由：终态冻结历史（§2.3，M0 mock）。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Response

from ..errors import NOT_FOUND, err
from ..mock import get_state
from starlette import status

router = APIRouter(tags=["history"])

_HIST_INPUT = (
    "#B3LYP/6-31G(d) Opt\n\nwater\n\n0 1\nO 0 0 0\n"
    "H 0 0 0.95\nH 0 0.75 -0.6\n\n"
)
_HIST_OUTPUT = (
    " Gaussian 16  Revision C.01  Sept 2021\n"
    " ---------------------------------------------\n"
    " #B3LYP/6-31G(d) Opt\n\n"
    " Step number   1 out of a maximum of 10\n"
    " SCF Done:  E(RB3LYP) = -76.40\n\n"
)


@router.get("/history")
def list_history(state: str | None = None, queue_id: str | None = None,
                 archived: bool | None = None, page: int = 1,
                 page_size: int = 50) -> dict:
    items = [dict(h) for h in get_state().history]
    if state:
        items = [h for h in items if h["state"] == state]
    if queue_id:
        items = [h for h in items if h.get("queue_id") == queue_id]
    if archived is not None:
        items = [h for h in items
                 if (bool(h.get("archived"))) == archived]
    items.sort(key=lambda h: h["id"], reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size],
            "page": page, "page_size": page_size, "total": total}


@router.get("/history/{id}")
def get_history_entry(id: int) -> dict:
    h = next((e for e in get_state().history if e["id"] == id), None)
    if h is None:
        raise NOT_FOUND("history", id)
    return dict(h)


@router.get("/history/{id}/input")
def get_history_input(id: int) -> Response:
    _ensure(id)
    return Response(content=_HIST_INPUT, media_type="text/plain; charset=utf-8")


@router.get("/history/{id}/output")
def get_history_output(id: int, download: bool = False) -> Response:
    _ensure(id)
    headers = {"Content-Disposition": f'attachment; filename="run-{id}.log"'} \
        if download else None
    return Response(content=_HIST_OUTPUT, media_type="text/plain; charset=utf-8",
                    headers=headers)


@router.post("/history/{id}/archive",
             status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def archive_history_entry(id: int) -> Response:
    h = next((e for e in get_state().history if e["id"] == id), None)
    if h is None:
        raise NOT_FOUND("history", id)
    h["archived"] = True
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/history/{id}/requeue")
def requeue_history_entry(id: int) -> dict:
    state = get_state()
    h = next((e for e in state.history if e["id"] == id), None)
    if h is None:
        raise NOT_FOUND("history", id)
    limit = int(state.get_runtime("seat_limit"))
    if len(state.seats) >= limit:
        raise err("PENDING_CAPACITY_FULL", "在途席位满员",
                  {"limit": limit}, http=409)
    seat_id = state.next_id()
    tid = h["task_id"]
    state.seats.append({
        "seat_id": seat_id, "kind": "task", "task_id": tid, "queue_id": None,
        "position": len(state.seats), "members": [{
            "task_id": tid, "filename": h["filename"], "state": "staged",
        }], "locked": False,
    })
    state.emit("pending.snapshot", state.pending())
    return {"seat_id": seat_id, "task_id": tid}


@router.post("/history/{id}/return-candidate",
             status_code=status.HTTP_201_CREATED)
def return_candidate(id: int) -> dict:
    state = get_state()
    h = next((e for e in state.history if e["id"] == id), None)
    if h is None:
        raise NOT_FOUND("history", id)
    origin = ("returned_succeeded" if h["state"] == "succeeded"
              else "returned_failed")
    cand = state.add_candidate(h["filename"], origin=origin,
                               failure_note="原执行失败归因" if origin ==
                               "returned_failed" else None)
    state.emit("candidates.changed", {"action": "created",
                                      "candidate_id": cand["id"]})
    return dict(cand)


@router.post("/history/cleanup")
def cleanup_transients() -> dict:
    state = get_state()
    checked = len(state.history)
    return {"checked": checked, "removed_chk": (checked % 2),
            "removed_rwf": (checked // 2)}


def _ensure(id: int) -> None:
    if not any(e["id"] == id for e in get_state().history):
        raise NOT_FOUND("history", id)