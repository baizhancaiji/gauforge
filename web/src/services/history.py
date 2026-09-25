"""历史领域服务（B9）：终态条目序列化、输入/输出视图、归档、重新排队、
退回候选、过期清理。

- 历史条目 = executions 终态行（m1-plan §2.2 运行与历史同表）；wall_time_s
  按 started_at→finished_at 派生（契约标注 F 字段不落库）；
- 重新排队：仅 failed/skipped、且任务不归属任何队列（队列成员经队列
  重新提交，防止撕裂队列成员构成）；沿用原任务 id 建席（finished→
  seat_task），满员 409 与一般任务同待遇（roadmap §2.1）；
- 退回候选：以 run/<id>/input.gjf 实际执行副本新建候选（新 id，skipped
  等无执行目录者回落任务输入副本），来源标记按终态分流——succeeded→
  returned_succeeded、failed→returned_failed(附归因)、skipped→
  returned_unrun（roadmap §2.1）；
- 清理：仅删「正常结束且超保留期」的 chk/rwf（engine/finalize）。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .. import config
from ..engine import finalize as finalize_files
from ..errors import err, not_found
from ..services import candidates as candidates_svc
from ..store import executions, seats, settings, tasks
from ..store.db import now_iso

_TERMINAL = ("succeeded", "failed", "skipped")
_ORIGIN_BY_STATE = {"succeeded": "returned_succeeded",
                    "failed": "returned_failed",
                    "skipped": "returned_unrun"}


def _iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _wall_time_s(row: dict) -> float:
    if row.get("started_at") and row.get("finished_at"):
        return (_iso(row["finished_at"]) - _iso(row["started_at"])).total_seconds()
    return 0.0


def entry_shape(row: dict) -> dict:
    """HistoryEntry 序列化：bool 转换、派生 wall_time_s、chk_snapshot 缺省。"""
    return {**row,
            "archived": bool(row.get("archived")),
            "wall_time_s": _wall_time_s(row),
            "chk_snapshot": row.get("chk_snapshot")
            or {"protected": False, "location": None},
            "result_ref": row.get("result_ref")}


def _terminal_row(execution_id: int) -> dict:
    row = executions().get(execution_id)
    if row is None or row["state"] not in _TERMINAL:
        raise not_found("history", execution_id)
    return row


def list_entries(state: str | None, queue_id: str | None,
                 archived: bool | None, page: int, page_size: int | None,
                 sort: str = "submitted_desc") -> dict:
    size = page_size if page_size is not None \
        else int(settings().get("page_size"))
    items, total = executions().list_terminal(
        state=state, queue_id=queue_id, archived=archived,
        page=page, page_size=size, sort=sort)
    return {"items": [entry_shape(r) for r in items], "page": page,
            "page_size": size, "total": total}


def get_entry(execution_id: int) -> dict:
    return entry_shape(_terminal_row(execution_id))


def load_input(execution_id: int) -> bytes:
    """输入查看：run/<id>/input.gjf 实际执行副本；skipped 等无执行目录
    者回落任务输入副本（roadmap §2.1）。"""
    row = _terminal_row(execution_id)
    src = _run_dir(execution_id) / "input.gjf"
    if not src.is_file():
        src = candidates_svc.default_inputs_dir() / str(row["task_id"])
    try:
        return src.read_bytes()
    except OSError:
        raise not_found("input", execution_id)


def load_output(execution_id: int) -> bytes:
    """输出纯文本：run/<id>/input.log（g16 自写日志）。"""
    _terminal_row(execution_id)
    src = _run_dir(execution_id) / "input.log"
    try:
        return src.read_bytes()
    except OSError:
        raise not_found("output", execution_id)


def archive(execution_id: int) -> None:
    _terminal_row(execution_id)  # 404 语义先行
    executions().set_archived(execution_id)


def requeue(execution_id: int) -> dict:
    """重新排队（原样重跑）：沿用原任务 id 建席，满员 409。

    事件（pending.snapshot）由路由层发（#8 模式）。
    """
    row = _terminal_row(execution_id)
    if row["state"] == "succeeded":
        raise err("TASK_STATE_CONFLICT",
                  "succeeded 条目无重新排队（结果沿用或经队列重提交）",
                  {"state": row["state"]}, http=409)
    tid = row["task_id"]
    task = tasks().get(tid)
    if task is None:
        raise not_found("task", tid)
    if task["form"] == "queue_member":
        raise err("TASK_STATE_CONFLICT",
                  "队列成员经所属队列重新提交，不经历史重排队",
                  {"task_id": tid}, http=409)
    limit = int(settings().get("pending_seat_limit"))
    if seats().count() >= limit:
        raise err("PENDING_CAPACITY_FULL", "在途席位满员",
                  {"limit": limit}, http=409)
    sid = seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)  # finished → seat_task（沿用原 id）
    return {"seat_id": sid, "task_id": tid}


def return_candidate(execution_id: int) -> dict:
    """退回候选：新 id、带来源标记（编辑再提交入口）。

    事件（candidates.changed created）由路由层发（#8 模式）。
    """
    row = _terminal_row(execution_id)
    tid = row["task_id"]
    if tasks().get(tid) is None:
        raise not_found("task", tid)
    src = _run_dir(execution_id) / "input.gjf"
    if not src.is_file():
        src = candidates_svc.default_inputs_dir() / str(tid)
    try:
        data = src.read_bytes()
    except OSError:
        raise not_found("input", execution_id)
    origin = _ORIGIN_BY_STATE[row["state"]]
    note = row.get("cause") if row["state"] == "failed" else None
    new_id = tasks().create_candidate(row["filename"], origin,
                                      failure_note=note)
    (candidates_svc.default_inputs_dir() / str(new_id)).write_bytes(data)
    row2 = tasks().get(new_id)
    return {"id": row2["id"], "filename": row2["filename"],
            "origin": row2["origin"], "failure_note": row2["failure_note"],
            "created_at": row2["created_at"],
            "title": candidates_svc.resolve_title(new_id)}


def cleanup() -> dict:
    """手动触发过期 chk/rwf 清理（自动定时延后启用，m1-plan §8 决策点 11）。"""
    return finalize_files.cleanup_expired(
        executions().list_by_state("succeeded"), config.HOME_DIR / "run",
        int(settings().get("chk_rwf_retention_days")), _iso(now_iso()))


def _run_dir(execution_id: int) -> Path:
    return config.HOME_DIR / "run" / str(execution_id)
