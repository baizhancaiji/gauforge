"""引擎启动序列（m1-plan §4.3 B10；§2.4 启动序列）。

顺序：确保 HQ server/worker 存活（B4 进程管理）→ 创建 Gateway 与
Dispatcher → 启动对账（reconcile.Reconciler 五场景）→ 挂载运行时单例
（stop 端点可达）→ 启动引擎后台线程。

容错：HQ 进程确保/对账失败仅告警降级——引擎照常挂载（tick 内停等），
watchdog 周期重试 server、引擎线程下周期重试对账。g16web 自身退出
**不杀** HQ 进程（§8.7：g16web 死亡不影响在跑计算）。
"""
from __future__ import annotations

import sys

from . import runtime
from .dispatcher import Dispatcher
from ..hq.gateway import Gateway, GatewayError
from ..hq.process import HqProcessManager


def start_engine(*, gateway: Gateway | None = None,
                 process_manager: HqProcessManager | None = None
                 ) -> Dispatcher:
    """执行启动序列并返回已挂载的 Dispatcher（测试可注入双依赖）。"""
    from .. import config

    pm = process_manager
    if pm is None:
        pm = HqProcessManager(config.hq_bin(), config.HOME_DIR)
    if gateway is None:
        from ..hq.cli_gateway import CliGateway
        gateway = CliGateway(pm.hq_path, str(pm.server_dir))
    try:
        pm.start()
        pm.ensure_worker()
    except GatewayError as exc:
        print(f"[startup] HQ 进程确保失败（watchdog 将重试）：{exc}",
              file=sys.stderr)

    d = Dispatcher(gateway)
    try:
        d.reconcile()
    except GatewayError as exc:
        print(f"[startup] 启动对账未完成（引擎线程将重试）：{exc}",
              file=sys.stderr)
    runtime.set_dispatcher(d)
    d.start()
    return d


def shutdown_engine(d: Dispatcher | None) -> None:
    """停引擎线程并摘除运行时单例（不动 HQ 进程）。"""
    if d is not None:
        d.stop()
    runtime.set_dispatcher(None)
