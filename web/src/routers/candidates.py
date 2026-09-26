"""candidates 域路由（§2.3/§2.4，M1 真实化；M2 分块编辑保存真实化）。

数据源：store.tasks + services.candidates（inputs/<id> 输入副本）。
事件经 mock state.emit 记入 SSE 重放窗口。
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, Response, UploadFile
from starlette import status

from ..errors import err, not_found
from ..mock import get_state
from ..parse.blocks import parse_input
from ..parse.naturalsort import natural_key
from ..services import candidates as candidates_svc
from ..services import pending as pending_svc
from ..store import settings as settings_store
from ..store import tasks as tasks_store

router = APIRouter(tags=["candidates"])

_ORIGIN_ENUM = ("imported", "returned_unrun", "returned_failed",
                "returned_succeeded")


def _candidate_row(cid: int) -> dict:
    row = tasks_store().get(cid)
    if row is None or row["form"] != "candidate":
        raise not_found("candidate", cid)
    return row


def _candidate_view(row: dict) -> dict:
    return {"id": row["id"], "filename": row["filename"],
            "origin": row["origin"], "failure_note": row["failure_note"],
            "created_at": row["created_at"],
            "title": candidates_svc.resolve_title(row["id"])}


def _load_input(cid: int) -> str:
    """读 inputs/<id> 原文（副本与源文件独立，CRLF 不转）。"""
    _candidate_row(cid)
    try:
        return (candidates_svc.default_inputs_dir() / str(cid)).read_text(
            encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise not_found("input", cid)


@router.get("/candidates")
def list_candidates(origin: str | None = None, page: int = 1,
                    page_size: int | None = None) -> dict:
    if origin is not None and origin not in _ORIGIN_ENUM:
        raise err("INVALID_REQUEST", "origin 取值不合法", http=400)
    items = [_candidate_view(r)
             for r in tasks_store().list_by_form("candidate")]
    if origin:
        items = [c for c in items if c["origin"] == origin]
    # 切片前全量排序（openapi /candidates）：导入时间倒序为主序（新批在上），
    # 同秒导入的批内按自然序（先自然序、再 created_at 倒序，两趟稳定排序）；
    # created_at 为恒定时区 UTC ISO，字典序即时序。排序唯一实现在取数端，
    # 跨页全局有序
    items.sort(key=lambda c: natural_key(c["filename"]))
    items.sort(key=lambda c: c["created_at"], reverse=True)
    total = len(items)
    size = (page_size if page_size is not None
            else int(settings_store().get("page_size")))
    start = (page - 1) * size
    return {"items": items[start:start + size], "page": page,
            "page_size": size, "total": total}


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
async def import_candidates(files: list[UploadFile] = File(...),
                            mode: str = Form("files")) -> dict:
    payload = [(f.filename or "", await f.read()) for f in files]
    out = candidates_svc.import_files(payload, mode=mode)
    for item in out:
        get_state().emit("candidates.changed",
                         {"action": "created", "candidate_id": item["id"]})
    return {"files": out}


@router.get("/candidates/{id}")
def get_candidate(id: int) -> dict:
    return _candidate_view(_candidate_row(id))


@router.delete("/candidates/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(id: int) -> Response:
    candidates_svc.delete_candidate(id)
    get_state().emit("candidates.changed",
                     {"action": "deleted", "candidate_id": id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/candidates/{id}/preview")
def preview_candidate(id: int) -> dict:
    row = _candidate_row(id)
    r = parse_input(_load_input(id))
    return {"candidate_id": row["id"], "filename": row["filename"],
            "blocks": r["blocks"], "parse_errors": r["parse_errors"]}


@router.get("/candidates/{id}/input")
def get_candidate_input(id: int) -> Response:
    return Response(content=_load_input(id),
                    media_type="text/plain; charset=utf-8")


@router.put("/candidates/{id}/blocks/{section}")
def save_block(id: int, section: str, payload: dict) -> dict:
    """分块编辑保存（M2 B2）：服务层流水①–⑤，响应 InputPreview + warnings。"""
    lines = payload.get("lines") if isinstance(payload, dict) else None
    if not isinstance(lines, list) or any(not isinstance(x, str) for x in lines):
        raise err("INVALID_REQUEST", "lines 须为字符串数组",
                  {"field": "lines"}, http=400)
    return candidates_svc.save_block(id, section, lines)


@router.post("/candidates/{id}/submit")
def submit_candidate(id: int, payload: dict | None = None) -> dict:
    _candidate_row(id)  # 404 语义先行（非候选形态同按不存在处理）
    sid = pending_svc.append_task(id)
    get_state().emit("candidates.changed",
                     {"action": "moved_out", "candidate_id": id})
    get_state().emit("pending.snapshot", pending_svc.snapshot())
    return {"seat_id": sid, "task_id": id}
