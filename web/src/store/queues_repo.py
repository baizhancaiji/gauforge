"""queues 表 DAL（m1-plan §2.2；成员经 tasks.queue_id+position 表达）。"""
from __future__ import annotations

from .db import Database, now_iso


class QueuesRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, queue_id: str) -> dict | None:
        row = self._db.one("SELECT * FROM queues WHERE id = ?", (queue_id,))
        if row is not None and isinstance(row.get("last_failure"), str):
            import json
            row["last_failure"] = json.loads(row["last_failure"])
        return row

    def list(self) -> list[dict]:
        """默认 id 倒序（新在前）。"""
        return self._db.query("SELECT * FROM queues ORDER BY id DESC")

    def create(self, queue_id: str, *, name: str,
               skip_failed: bool = False) -> None:
        ts = now_iso()
        self._db.run(
            "INSERT INTO queues (id, name, skip_failed, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (queue_id, name, int(skip_failed), ts, ts))

    def delete(self, queue_id: str) -> None:
        self._db.run("DELETE FROM queues WHERE id = ?", (queue_id,))

    def set_state(self, queue_id: str, state: str) -> None:
        self._db.run(
            "UPDATE queues SET state = ?, updated_at = ? WHERE id = ?",
            (state, now_iso(), queue_id))

    def update(self, queue_id: str, **fields: object) -> None:
        """白名单字段更新（name/skip_failed/rollback_flag/rollback_count/
        last_failure/finish_reason）。"""
        allowed = {"name", "skip_failed", "rollback_flag", "rollback_count",
                   "last_failure", "finish_reason"}
        keys = [k for k in fields if k in allowed]
        if not keys:
            return
        import json
        sets, params = [], []
        for k in keys:
            v = fields[k]
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            elif isinstance(v, bool):
                v = int(v)
            sets.append(f"{k} = ?")
            params.append(v)
        sets.append("updated_at = ?")
        params.extend([now_iso(), queue_id])
        self._db.run(f"UPDATE queues SET {', '.join(sets)} WHERE id = ?", tuple(params))
