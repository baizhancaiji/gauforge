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

    def list_by_task(self, task_id: int) -> list[dict]:
        """任务全部执行记录（id 正序，最近在后）。"""
        rows = self._db.query(
            "SELECT * FROM executions WHERE task_id = ? ORDER BY id", (task_id,))
        return [self._deserialize(r) for r in rows]  # type: ignore[misc]

    def create(self, *, task_id: int, filename: str, resources: dict,
               queue_id: str | None = None, input_hash: str | None = None,
               hq_job_id: int | None = None,
               submitted_at: str | None = None,
               state: str = "running") -> int:
        """创建执行记录（默认 state=running；staged 由席位表达不建行）。

        state 直落：B6 失败分流 skipped 终态行即时落库（无运行过程）。"""
        with self._db.tx() as conn:
            cur = conn.execute(
                "INSERT INTO executions (task_id, queue_id, state, submitted_at,"
                " input_hash, resources, hq_job_id, filename)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, queue_id, state, submitted_at or now_iso(), input_hash,
                 json.dumps(resources, ensure_ascii=False), hq_job_id, filename))
            return int(cur.lastrowid)

    def set_started_at(self, execution_id: int, started_at: str) -> None:
        """running 时补启动时间（roadmap §2.6 字段生命周期）。"""
        self._db.run("UPDATE executions SET started_at = ? WHERE id = ?",
                     (started_at, execution_id))

    def delete(self, execution_id: int) -> None:
        """终态前删除（仅引擎派发失败补偿用：物化失败回收刚建的 running 行）。"""
        self._db.run("DELETE FROM executions WHERE id = ?", (execution_id,))

    def update_hq_job_id(self, execution_id: int, hq_job_id: int | None) -> None:
        self._db.run("UPDATE executions SET hq_job_id = ? WHERE id = ?",
                     (hq_job_id, execution_id))

    def finalize(self, *, execution_id: int, state: str, finished_at: str,
                 cause: str | None = None,
                 monitor_summary: dict | None = None,
                 chk_snapshot: dict | None = None) -> None:
        """终态冻结（B9 管线调用；冻结后仅 archived 可变）。

        chk_snapshot：非正常终止保全快照 {protected, location}（仅 failed）。
        """
        self._db.run(
            "UPDATE executions SET state = ?, finished_at = ?, cause = ?,"
            " monitor_summary = ?, chk_snapshot = ? WHERE id = ?",
            (state, finished_at, cause,
             json.dumps(monitor_summary, ensure_ascii=False)
             if monitor_summary is not None else None,
             json.dumps(chk_snapshot, ensure_ascii=False)
             if chk_snapshot is not None else None,
             execution_id))

    def set_archived(self, execution_id: int) -> None:
        """归档（冻结后唯一可变标记，仅历史端点可达的终态行）。"""
        self._db.run("UPDATE executions SET archived = 1 WHERE id = ?",
                     (execution_id,))

    def list_terminal(self, *, state: str | None = None,
                      queue_id: str | None = None, archived: bool | None = None,
                      page: int = 1, page_size: int = 50) -> tuple[list[dict], int]:
        """终态条目分页（历史列表）：(items, total)，id 倒序。"""
        conds = ["state IN ('succeeded','failed','skipped')"]
        params: list[object] = []
        if state is not None:
            conds.append("state = ?")
            params.append(state)
        if queue_id is not None:
            conds.append("queue_id = ?")
            params.append(queue_id)
        if archived is not None:
            conds.append("archived = ?")
            params.append(1 if archived else 0)
        where = " AND ".join(conds)
        total_row = self._db.one(
            f"SELECT COUNT(*) AS n FROM executions WHERE {where}", tuple(params))
        total = int(total_row["n"]) if total_row else 0
        rows = self._db.query(
            f"SELECT * FROM executions WHERE {where} ORDER BY id DESC"
            " LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size))
        return [self._deserialize(r) for r in rows], total
