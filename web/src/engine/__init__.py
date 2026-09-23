"""派发引擎（B6/B7/B8）：序列展开/窗口推进/停等/补位/终态与失败分流。

Dispatcher 为唯一入口；workspace 物化与 g16 环境构建；monitor 监控与
停滞检测；progress 增量解析；fake.py 供测试。
"""
from .dispatcher import Dispatcher
from .fake import FakeGateway
from .progress import ProgressTracker

__all__ = ["Dispatcher", "FakeGateway", "ProgressTracker"]
