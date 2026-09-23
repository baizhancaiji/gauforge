"""派发引擎（B6）：序列展开/窗口推进/停等/补位/终态与失败分流。

Dispatcher 为唯一入口；workspace 物化与 g16 环境构建；fake.py 供测试。
"""
from .dispatcher import Dispatcher
from .fake import FakeGateway

__all__ = ["Dispatcher", "FakeGateway"]
