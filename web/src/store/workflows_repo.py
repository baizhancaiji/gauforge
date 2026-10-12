"""workflows 表 DAL（M4 B10/B11：组合流记录，GET /workflows 系端点数据源）。"""
from __future__ import annotations

import json

from .db import Database, now_iso


class WorkflowsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def _deserialize(self, row: dict | None) -> dict | None:
        if row is None:
            return None
        row = dict(row)
        row["refine_queue_pending"] = bool(row.get("refine_queue_pending"))
        return row

    def create(self, workflow_id: str, *, source_candidate_id: int,
               top_n: int, crest_task_id: int | None = None) -> str:
        ts = now_iso()
        with self._db.tx() as conn:
            conn.execute(
                "INSERT INTO workflows (workflow_id, source_candidate_id,"
                " state, refine_queue_pending, crest_execution_id,"
                " refine_queue_id, top_n, created_at, updated_at)"
                " VALUES (?, ?, 'crest_running', 0, NULL, NULL, ?, ?, ?)",
                (workflow_id, source_candidate_id, top_n, ts, ts))
        return workflow_id

    def get(self, workflow_id: str) -> dict | None:
        return self._deserialize(self._db.one(
            "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)))

    def list(self, limit: int = 20) -> list[dict]:
        rows = self._db.query(
            "SELECT * FROM workflows ORDER BY updated_at DESC LIMIT ?",
            (limit,))
        return [self._deserialize(r) for r in rows]  # type: ignore[misc]

    def list_open(self) -> list[dict]:
        """非终态 workflow 行（启动对账扫描：crest_running/refining）。"""
        rows = self._db.query(
            "SELECT * FROM workflows WHERE state IN"
            " ('crest_running','refining') ORDER BY updated_at")
        return [self._deserialize(r) for r in rows]  # type: ignore[misc]

    def get_by_refine_queue(self, queue_id: str) -> dict | None:
        """精修队列反查 workflow 行（队列 completed 终态联动用）。"""
        return self._deserialize(self._db.one(
            "SELECT * FROM workflows WHERE refine_queue_id = ?", (queue_id,)))

    def _update(self, workflow_id: str, **cols) -> None:
        sets = ", ".join(f"{k} = ?" for k in cols)
        self._db.run(
            f"UPDATE workflows SET {sets}, updated_at = ? WHERE workflow_id = ?",
            (*cols.values(), now_iso(), workflow_id))

    def set_state(self, workflow_id: str, state: str) -> None:
        self._update(workflow_id, state=state)

    def set_crest_execution(self, workflow_id: str, execution_id: int) -> None:
        self._update(workflow_id, crest_execution_id=execution_id)

    def set_refine_queue(self, workflow_id: str, queue_id: str | None) -> None:
        self._update(workflow_id, refine_queue_id=queue_id)

    def set_refine_pending(self, workflow_id: str, pending: bool) -> None:
        self._update(workflow_id, refine_queue_pending=1 if pending else 0)
