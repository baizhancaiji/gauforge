"""seats 表 DAL（待执行席位有序表，m1-plan §2.2）。"""
from __future__ import annotations

from .db import Database, now_iso


class SeatsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, seat_id: int) -> dict | None:
        return self._db.one("SELECT * FROM seats WHERE seat_id = ?", (seat_id,))

    def list_by_position(self) -> list[dict]:
        return self._db.query("SELECT * FROM seats ORDER BY position")

    def count(self) -> int:
        row = self._db.one("SELECT COUNT(*) AS n FROM seats")
        return int(row["n"]) if row else 0

    def next_position(self) -> int:
        row = self._db.one("SELECT COALESCE(MAX(position), -1) AS p FROM seats")
        return int(row["p"]) + 1 if row else 0

    def append(self, *, kind: str, task_id: int | None = None,
               queue_id: str | None = None,
               position: int | None = None) -> int:
        """尾部追加（position 缺省 = 队尾）。"""
        pos = self.next_position() if position is None else position
        with self._db.tx() as conn:
            cur = conn.execute(
                "INSERT INTO seats (kind, task_id, queue_id, position, locked,"
                " created_at) VALUES (?, ?, ?, ?, 0, ?)",
                (kind, task_id, queue_id, pos, now_iso()))
            return int(cur.lastrowid)

    def remove(self, seat_id: int) -> None:
        self._db.run("DELETE FROM seats WHERE seat_id = ?", (seat_id,))

    def set_locked(self, seat_id: int, locked: bool) -> None:
        self._db.run("UPDATE seats SET locked = ? WHERE seat_id = ?",
                     (int(locked), seat_id))

    def reorder(self, seat_ids: list[int]) -> None:
        """按给定顺序整体重排 position（0..n-1，单事务原子）。"""
        with self._db.tx() as conn:
            for pos, sid in enumerate(seat_ids):
                conn.execute("UPDATE seats SET position = ? WHERE seat_id = ?",
                             (pos, sid))
