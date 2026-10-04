"""history 域路由（§2.3，B9 真实化）：SQLite 终态条目 + 文件视图 + 动作。

数据源：store.executions（终态行）+ services.history + engine.finalize。
事件经 mock state.emit 记入 SSE 重放窗口（B11 事件总线真实化前过渡）：
requeue → pending.snapshot；return-candidate → candidates.changed(created)；
归档与清理无事件（sse.md §3 推送时机表）。
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter
from fastapi import Response
from starlette import status

from ..errors import err
from ..mock import get_state
from ..services import history as history_svc

router = APIRouter(tags=["history"])

_STATES = ("succeeded", "failed", "skipped")
_SORTS = ("submitted_desc", "finished_desc", "finished_asc",
          "filename_asc", "filename_desc")


@router.get("/history")
def list_history(state: str | None = None, queue_id: str | None = None,
                 archived: bool | None = None, page: int = 1,
                 page_size: int | None = None,
                 sort: str | None = None) -> dict:
    if state is not None and state not in _STATES:
        raise err("INVALID_REQUEST", "state 取值不合法", http=400)
    if sort is not None and sort not in _SORTS:
        raise err("INVALID_REQUEST", "sort 取值不合法", http=400)
    return history_svc.list_entries(state, queue_id, archived, page, page_size,
                                    sort or "submitted_desc")


@router.post("/history/cleanup")
def cleanup_transients(scope: str = "expired") -> dict:
    """双档 chk 清理（openapi /history/cleanup）：expired 超期档 /
    all 无视保留期档；failed 的保全 chk 两档均不触碰。"""
    if scope not in ("expired", "all"):
        raise err("INVALID_REQUEST", "scope 取值不合法", http=400)
    return history_svc.cleanup(scope)


@router.post("/history/export")
def export_history_outputs(payload: dict) -> Response:
    """批量导出选中条目输出为 ZIP（openapi /history/export；前端 blob 下载）。"""
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids or not all(
            isinstance(i, int) and not isinstance(i, bool) and i > 0
            for i in ids):
        raise err("INVALID_REQUEST", "ids 须为非空正整数数组", http=400)
    data = history_svc.export_outputs(ids)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return Response(
        content=data, media_type="application/zip",
        headers={"Content-Disposition":
                 f"attachment; filename=gauforge-outputs-{stamp}.zip"})


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
        # 导出命名 .out（G16 输出正规扩展；内容为 run/<id>/input.log）
        headers = {"Content-Disposition":
                   f"attachment; filename*=UTF-8''{quote(stem + '.out')}"}
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
