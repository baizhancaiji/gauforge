"""引擎运行时单例（B7）：stop 端点经此寻址 Dispatcher。

B10 将在应用工厂 lifespan 内创建并注入（HQ 进程管理 + 引擎线程启动）；
测试经 set_dispatcher 注入。"""
from __future__ import annotations

from .dispatcher import Dispatcher

_dispatcher: Dispatcher | None = None


def set_dispatcher(d: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = d


def get_dispatcher() -> Dispatcher | None:
    return _dispatcher
