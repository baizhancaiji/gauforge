"""SQLite 单连接 + 全局写锁 + 短事务（m1-plan §2.2 写并发策略）。

- FastAPI async 与引擎后台线程共用一个连接：threading.RLock 串行化全部
  访问（单连接下读写都持锁，避免并发 cursor 串话）；事务用显式
  BEGIN IMMEDIATE 保证短事务语义。
- PRAGMA：WAL（崩溃安全；内存库跳过）、foreign_keys=ON、busy_timeout=5000。
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

Params = tuple | list | dict


def now_iso() -> str:
    """UTC ISO 8601（契约 date-time）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path) -> None:
        self._lock = threading.RLock()
        uri = isinstance(path, str) and path.startswith("file:")
        if not uri and not str(path) == ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False,
                                     timeout=5.0, uri=uri,
                                     isolation_level=None)  # 显式事务
        self._conn.row_factory = sqlite3.Row
        self._is_memory = (uri and "mode=memory" in str(path)) or str(path) == ":memory:"
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        if not self._is_memory:
            self._conn.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """写短事务（锁内 BEGIN IMMEDIATE ... COMMIT/ROLLBACK）。"""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def run(self, sql: str, params: Params = ()) -> None:
        with self.tx() as conn:
            conn.execute(sql, params)

    def query(self, sql: str, params: Params = ()) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def one(self, sql: str, params: Params = ()) -> dict | None:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    def script(self, sql: str) -> None:
        """多语句脚本（executescript 有隐式提交语义，不走 tx）。

        仅供迁移使用：脚本自身须幂等（IF NOT EXISTS）以容忍半途崩溃。
        """
        with self._lock:
            self._conn.executescript(sql)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
