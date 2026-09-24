"""system.snapshot 载荷构建（sse.md §2；B10 对账与 B11 重连恢复共用）。

数据源为真实 store（pending 全量/在跑执行/队列摘要）；列表型资源
（候选/历史分页）不入快照，客户端按通知事件重拉 REST。
"""
from __future__ import annotations


def system_snapshot(*, server_restarted: bool) -> dict:
    from ..store import executions, queues
    from .pending import snapshot as pending_snapshot
    return {
        "pending": pending_snapshot(),
        "executions_running": executions().list_by_state("running"),
        "queues_summary": [{"id": q["id"], "state": q["state"],
                            "rollback_flag": q["rollback_flag"],
                            "rollback_count": q["rollback_count"]}
                           for q in queues().list()],
        "server_restarted": server_restarted,
    }
