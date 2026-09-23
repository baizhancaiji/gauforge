"""SQLite 持久化层（B1）：进程级单例 + 领域 DAL。

唯一 SQL 出口（AGENTS §2.2 写并发策略）；routers 不写 SQL。
测试经 set_db 注入内存/临时库。
"""
from __future__ import annotations

import threading

from .. import config
from .db import Database
from .executions_repo import ExecutionsRepo
from .migrations import run_migrations
from .queues_repo import QueuesRepo
from .seats_repo import SeatsRepo
from .settings_repo import SettingsRepo
from .tasks_repo import TasksRepo

__all__ = ["Database", "run_migrations", "get_db", "set_db", "reset_db",
           "SettingsRepo", "TasksRepo", "QueuesRepo", "SeatsRepo",
           "ExecutionsRepo"]

_db: Database | None = None
_lock = threading.Lock()


def get_db() -> Database:
    """惰性单例：<workspace>/g16web.db，首次访问自动迁移。"""
    global _db
    if _db is None:
        with _lock:
            if _db is None:
                _db = Database(config.HOME_DIR / "g16web.db")
                run_migrations(_db)
    return _db


def set_db(db: Database) -> None:
    """测试注入。"""
    global _db
    with _lock:
        _db = db


def reset_db() -> None:
    """测试清理：关闭并清除单例。"""
    global _db
    with _lock:
        if _db is not None:
            _db.close()
            _db = None


def settings() -> SettingsRepo:
    return SettingsRepo(get_db())


def tasks() -> TasksRepo:
    return TasksRepo(get_db())


def queues() -> QueuesRepo:
    return QueuesRepo(get_db())


def seats() -> SeatsRepo:
    return SeatsRepo(get_db())


def executions() -> ExecutionsRepo:
    return ExecutionsRepo(get_db())
