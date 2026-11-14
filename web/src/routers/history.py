"""history 域路由（§2.3，B9 真实化）：SQLite 终态条目 + 文件视图 + 动作。

数据源：store.executions（终态行）+ services.history + engine.finalize。
事件经 mock state.emit 记入 SSE 重放窗口（B11 事件总线真实化前过渡）：
requeue → pending.snapshot；return-candidate → candidates.changed(created)；
归档与清理无事件（sse.md §3 推送时机表）。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter
from fastapi import Response
from fastapi.responses import FileResponse
from starlette import status
from starlette.background import BackgroundTask

from ..errors import err
from ..models.models import Scope
from ..mock import get_state
from ..services import history as history_svc

router = APIRouter(tags=["history"])

_STATES = ("succeeded", "failed", "skipped")
_SORTS = ("submitted_desc", "finished_desc", "finished_asc",
          "filename_asc", "filename_desc")
# scope 合法值单源：openapi enum → gen_models 生成 Scope（chk-export-plan
# §2.1），路由校验由此派生，不另写元组副本
_EXPORT_SCOPES = tuple(s.value for s in Scope)


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
    """批量导出选中条目为 ZIP（openapi /history/export；前端 blob 下载）。

    scope=out（缺省）走内存路径整包回发；scope=chk/all 服务层落临时文件，
    经 FileResponse 分块流式发送、BackgroundTask 删临时文件（失败残留由
    启动清扫兜底）。包名三 scope 同名，仅时间戳区分（2026-11-14 裁决 3）。
    """
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids or not all(
            isinstance(i, int) and not isinstance(i, bool) and i > 0
            for i in ids):
        raise err("INVALID_REQUEST", "ids 须为非空正整数数组", http=400)
    scope = payload.get("scope", "out")
    if scope not in _EXPORT_SCOPES:
        raise err("INVALID_REQUEST", "scope 取值不合法", http=400)
    result = history_svc.export_outputs(ids, scope)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    headers = {"Content-Disposition":
               f"attachment; filename=gauforge-outputs-{stamp}.zip"}
    if isinstance(result, Path):  # chk/all 临时文件路径：流式发送 + 用后即删
        return FileResponse(result, media_type="application/zip",
                            headers=headers,
                            background=BackgroundTask(os.unlink, result))
    return Response(content=result, media_type="application/zip",
                    headers=headers)


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


@router.post("/history/{id}/resume/preview")
def preview_resume(id: int) -> dict:
    """断点续跑预览（M4 B9）：探针+注入矩阵+输入 diff；无副作用、恒 200
    （ineligible 以 eligible=false + reason 表达，五态见 services.resume）。"""
    from ..services import resume as resume_svc
    return resume_svc.preview(id)


@router.post("/history/{id}/resume")
def resume_from_checkpoint(id: int) -> dict:
    """断点续跑确认（M4 B9）：幂等重探 → 新建任务（注入改写副本）入
    待执行队列；ineligible 422、满员 409；freq 回落原样重跑同经此端点。"""
    from ..services import resume as resume_svc
    out = resume_svc.confirm(id)
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
