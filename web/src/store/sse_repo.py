"""sse_seq 表 DAL（B11）：SSE 事件全局序号持久化（sse.md §5.1，m1-plan §2.2）。

服务重启后序号延续（不归零）：emit 每事件短事务自增落库，启动侧无需
显式加载（next() 以库内计数为准）。
"""
from __future__ import annotations

from .db import Database


class SseSeqRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def current(self) -> int:
        row = self._db.one("SELECT MAX(counter) AS c FROM sse_seq")
        return int(row["c"] or 0) if row is not None else 0

    def next(self) -> int:
        """分配下一序号（短事务自增，线程安全由单连接写锁保证）。"""
        with self._db.tx() as conn:
            conn.execute("UPDATE sse_seq SET counter = counter + 1")
            row = conn.execute("SELECT MAX(counter) AS c FROM sse_seq").fetchone()
            return int(row["c"])
