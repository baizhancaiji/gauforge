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


def hq_status() -> dict:
    """侧栏 HQ 连通性快照（hq.status 事件与 system.snapshot 同一口径）。

    引擎未启用 → off（演示模式无 HQ）；已挂载但尚未探测（启动初期）或
    引擎挂载失败 → down；tick 探测可达 → up（附在线 worker 数）。
    """
    d = get_dispatcher()
    if d is not None and d.hq_state is not None:
        return {"state": d.hq_state, "workers_online": d.hq_workers_online}
    from .. import config
    if not config.ENGINE_ENABLED:
        return {"state": "off", "workers_online": 0}
    return {"state": "down", "workers_online": 0}
