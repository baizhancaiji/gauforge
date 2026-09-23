"""引擎运行时单例（B7/B10）：stop 端点经此寻址 Dispatcher。

应用工厂 lifespan 经 engine/startup.start_engine 创建并注入；
测试经 set_dispatcher 注入（或直接持有实例）。"""
from __future__ import annotations

from .dispatcher import Dispatcher

_dispatcher: Dispatcher | None = None


def set_dispatcher(d: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = d


def get_dispatcher() -> Dispatcher | None:
    return _dispatcher
