"""tasks 表 DAL（候选/任务同表同 id，form 形态列，m1-plan §2.2）。"""
from __future__ import annotations

from .db import Database, now_iso


class TasksRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---------------- 查询 ----------------

    def get(self, task_id: int) -> dict | None:
        return self._db.one("SELECT * FROM tasks WHERE id = ?", (task_id,))

    def list_by_form(self, form: str) -> list[dict]:
        """默认 id 倒序（新在前，m0 决策点 3）。"""
        return self._db.query(
            "SELECT * FROM tasks WHERE form = ? ORDER BY id DESC", (form,))

    def list_queue_members(self, queue_id: str) -> list[dict]:
        """队列成员按 position 正序。"""
        return self._db.query(
            "SELECT * FROM tasks WHERE queue_id = ? ORDER BY position",
            (queue_id,))

    def count_by_form(self, form: str) -> int:
        row = self._db.one("SELECT COUNT(*) AS n FROM tasks WHERE form = ?", (form,))
        return int(row["n"]) if row else 0

    # ---------------- 写入 ----------------

    def create_candidate(self, filename: str, origin: str,
                         failure_note: str | None = None) -> int:
        ts = now_iso()
        with self._db.tx() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (filename, origin, failure_note, form,"
                " created_at, updated_at) VALUES (?, ?, ?, 'candidate', ?, ?)",
                (filename, origin, failure_note, ts, ts))
            return int(cur.lastrowid)

    def delete(self, task_id: int) -> None:
        self._db.run("DELETE FROM tasks WHERE id = ?", (task_id,))

    # ---------------- form 形态转换（对照 §2.1 状态机） ----------------

    def enqueue(self, task_id: int, queue_id: str, position: int) -> None:
        """candidate → queue_member（入队）。"""
        self._db.run(
            "UPDATE tasks SET form = 'queue_member', queue_id = ?, position = ?,"
            " updated_at = ? WHERE id = ?", (queue_id, position, now_iso(), task_id))

    def to_seat_task(self, task_id: int) -> None:
        """candidate →（行内提交）seat_task；finished →（重新排队）seat_task
        （沿用原 id）。脱离队列归属。"""
        self._db.run(
            "UPDATE tasks SET form = 'seat_task', queue_id = NULL, position = NULL,"
            " updated_at = ? WHERE id = ?", (now_iso(), task_id))

    def to_finished(self, task_id: int) -> None:
        """seat_task →（执行结束离席）finished。"""
        self._db.run(
            "UPDATE tasks SET form = 'finished', updated_at = ? WHERE id = ?",
            (now_iso(), task_id))

    def return_to_candidate(self, task_id: int, origin: str,
                            failure_note: str | None = None) -> None:
        """queue_member →（回退/移除退回）candidate：origin 分流
        returned_unrun / returned_failed(+note)。"""
        self._db.run(
            "UPDATE tasks SET form = 'candidate', queue_id = NULL, position = NULL,"
            " origin = ?, failure_note = ?, updated_at = ? WHERE id = ?",
            (origin, failure_note, now_iso(), task_id))

    def repack_queue(self, queue_id: str) -> None:
        """队列成员 position 重排为 0..n-1（成员移除后补位）。"""
        with self._db.tx() as conn:
            rows = conn.execute(
                "SELECT id FROM tasks WHERE queue_id = ? ORDER BY position, id",
                (queue_id,)).fetchall()
            for idx, row in enumerate(rows):
                conn.execute("UPDATE tasks SET position = ? WHERE id = ?",
                             (idx, row["id"]))
