"""executions 表 DAL（运行与历史同表：历史 = 终态行，m1-plan §2.2）。"""
from __future__ import annotations

import json

from .db import Database, now_iso


class ExecutionsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def _deserialize(self, row: dict | None) -> dict | None:
        if row is None:
            return None
        for col in ("resources", "monitor_summary", "chk_snapshot"):
            if row.get(col) is not None:
                row[col] = json.loads(row[col])
        return row

    def get(self, execution_id: int) -> dict | None:
        return self._deserialize(
            self._db.one("SELECT * FROM executions WHERE id = ?", (execution_id,)))

    def list_by_state(self, state: str) -> list[dict]:
        """默认 id 倒序（新在前）。"""
        rows = self._db.query(
            "SELECT * FROM executions WHERE state = ? ORDER BY id DESC", (state,))
        return [self._deserialize(r) for r in rows]  # type: ignore[misc]

    def create(self, *, task_id: int, filename: str, resources: dict,
               queue_id: str | None = None, input_hash: str | None = None,
               hq_job_id: int | None = None,
               submitted_at: str | None = None) -> int:
        """创建运行中执行记录（state=running；staged 由席位表达不建行）。"""
        with self._db.tx() as conn:
            cur = conn.execute(
                "INSERT INTO executions (task_id, queue_id, state, submitted_at,"
                " input_hash, resources, hq_job_id, filename)"
                " VALUES (?, ?, 'running', ?, ?, ?, ?, ?)",
                (task_id, queue_id, submitted_at or now_iso(), input_hash,
                 json.dumps(resources, ensure_ascii=False), hq_job_id, filename))
            return int(cur.lastrowid)

    def update_hq_job_id(self, execution_id: int, hq_job_id: int | None) -> None:
        self._db.run("UPDATE executions SET hq_job_id = ? WHERE id = ?",
                     (hq_job_id, execution_id))

    def finalize(self, *, execution_id: int, state: str, finished_at: str,
                 cause: str | None = None,
                 monitor_summary: dict | None = None) -> None:
        """终态冻结（B9 管线调用；冻结后仅 archived 可变）。"""
        self._db.run(
            "UPDATE executions SET state = ?, finished_at = ?, cause = ?,"
            " monitor_summary = ? WHERE id = ?",
            (state, finished_at, cause,
             json.dumps(monitor_summary, ensure_ascii=False)
             if monitor_summary is not None else None,
             execution_id))
