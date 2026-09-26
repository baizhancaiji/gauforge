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
from ..services import verify as verify_svc
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


def _readable_row(cid: int) -> dict:
    """预览/原文读取守卫（M2：id 跨形态延续，与 PUT blocks 守卫一致）。

    放行候选与失败回退队列成员（unsubmitted 且 rollback_flag=true）——
    分块编辑初始化与 CRLF 检出需要两端点；其余形态 404（契约 openapi.yaml
    previewCandidate/getCandidateInput 描述口径）。
    """
    row = tasks_store().get(cid)
    if row is None:
        raise not_found("candidate", cid)
    if row["form"] == "candidate":
        return row
    if row["form"] == "queue_member":
        q = candidates_svc.get_queue_row(row["queue_id"])
        if q is not None and q["state"] == "unsubmitted" \
                and bool(q.get("rollback_flag")):
            return row
    raise not_found("candidate", cid)


def _candidate_view(row: dict) -> dict:
    return {"id": row["id"], "filename": row["filename"],
            "origin": row["origin"], "failure_note": row["failure_note"],
            "created_at": row["created_at"],
            "title": candidates_svc.resolve_title(row["id"])}


def _load_input(cid: int) -> str:
    """读 inputs/<id> 原文（副本与源文件独立，CRLF 不转）。

    守卫走 _readable_row（M2 跨形态：候选与失败回退队列成员可读）。
    """
    _readable_row(cid)
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
                            mode: str = Form("files"),
                            queue_from_folder: bool = Form(False),
                            folder_name: str | None = Form(None)) -> dict:
    """导入（M2 增补队列选项，m2-plan §2.3）。

    勾选保存为队列：受支持文件数 2–10 成队（queue 明示），越界拒绝成队、
    回落全部生成候选（queue_fallback_reason 明示原因）。成队事件序列
    （sse.md §3）：candidates.changed(created) ×N → moved_out ×N →
    queues.changed(created)，不省略 moved_out。
    """
    if queue_from_folder:
        if mode != "folder":
            raise err("VALIDATION_FAILED", "queue_from_folder 仅在"
                      " mode=folder 时有效",
                      {"errors": [{"field": "queue_from_folder",
                                   "reason": "requires_folder_mode"}]},
                      http=422)
        if not folder_name or not folder_name.strip():
            raise err("VALIDATION_FAILED", "queue_from_folder=true 时"
                      " folder_name 必填",
                      {"errors": [{"field": "folder_name",
                                   "reason": "required"}]}, http=422)
    payload = [(f.filename or "", await f.read()) for f in files]
    if queue_from_folder:
        out, queue, fallback = candidates_svc.import_folder_as_queue(
            payload, mode=mode, folder_name=folder_name.strip())
    else:
        out, queue, fallback = candidates_svc.import_files(payload,
                                                           mode=mode), None, None
    for item in out:  # 导入落候选
        get_state().emit("candidates.changed",
                         {"action": "created", "candidate_id": item["id"]})
    if queue:  # 成队转换 + 建队列
        for item in out:
            get_state().emit("candidates.changed",
                             {"action": "moved_out", "candidate_id": item["id"]})
        get_state().emit("queues.changed",
                         {"action": "created", "queue_id": queue["queue_id"]})
    return {"files": out, "queue": queue, "queue_fallback_reason": fallback}


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
    row = _readable_row(id)
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
    normalized = verify_svc.verify_and_store(id)  # 提交核验：先落盘后建席
    sid = pending_svc.append_task(id)
    get_state().emit("candidates.changed",
                     {"action": "moved_out", "candidate_id": id})
    get_state().emit("pending.snapshot", pending_svc.snapshot())
    return {"seat_id": sid, "task_id": id, "normalized": normalized}
