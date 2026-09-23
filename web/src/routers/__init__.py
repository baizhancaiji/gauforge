"""routers 包：聚合各域路由，供 main.py 挂载。"""
from . import candidates, executions, history, pending, queues, settings, system

# events 路由在事件域单独装配（依赖 sse broker）。