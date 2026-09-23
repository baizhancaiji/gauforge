"""history 域路由（§2.3，B9 真实化）：SQLite 终态条目 + 文件视图 + 动作。

数据源：store.executions（终态行）+ services.history + engine.finalize。
事件经 mock state.emit 记入 SSE 重放窗口（B11 事件总线真实化前过渡）：
requeue → pending.snapshot；return-candidate → candidates.changed(created)；
归档与清理无事件（sse.md §3 推送时机表）。
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter
from fastapi import Response
from starlette import status

from ..errors import err
from ..mock import get_state
from ..services import history as history_svc

router = APIRouter(tags=["history"])

_STATES = ("succeeded", "failed", "skipped")


@router.get("/history")
def list_history(state: str | None = None, queue_id: str | None = None,
                 archived: bool | None = None, page: int = 1,
                 page_size: int | None = None) -> dict:
    if state is not None and state not in _STATES:
        raise err("INVALID_REQUEST", "state 取值不合法", http=400)
    return history_svc.list_entries(state, queue_id, archived, page, page_size)


@router.post("/history/cleanup")
def cleanup_transients() -> dict:
    return history_svc.cleanup()


@router.get("/history/{id}")
def get_history_entry(id: int) -> dict:
    return history_svc.get_entry(id)


@router.get("/history/{id}/input")
def get_history_input(id: int) -> Response:
    return Response(content=history_svc.load_input(id),
                    media_type="text/plain; charset=utf-8")


@router.get("/history/{id}/output")
def get_history_output(id: int, download: bool = False) -> Response:
    data = history_svc.load_output(id)
    headers = None
    if download:
        name = history_svc.get_entry(id)["filename"]
        stem = name.rsplit(".", 1)[0] if "." in name else name
        headers = {"Content-Disposition":
                   f"attachment; filename*=UTF-8''{quote(stem + '.log')}"}
    return Response(content=data, media_type="text/plain; charset=utf-8",
                    headers=headers)


@router.post("/history/{id}/archive",
             status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def archive_history_entry(id: int) -> Response:
    history_svc.archive(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/history/{id}/requeue")
def requeue_history_entry(id: int) -> dict:
    out = history_svc.requeue(id)
    get_state().emit("pending.snapshot", _pending_snapshot())
    return out


@router.post("/history/{id}/return-candidate",
             status_code=status.HTTP_201_CREATED)
def return_candidate(id: int) -> dict:
    cand = history_svc.return_candidate(id)
    get_state().emit("candidates.changed",
                     {"action": "created", "candidate_id": cand["id"]})
    return cand


def _pending_snapshot() -> dict:
    from ..services import pending as pending_svc
    return pending_svc.snapshot()
