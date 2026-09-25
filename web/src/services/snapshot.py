"""system.snapshot 载荷构建（sse.md §2；B10 对账与 B11 重连恢复共用）。

数据源为真实 store（pending 全量/在跑执行/队列摘要）；列表型资源
（候选/历史分页）不入快照，客户端按通知事件重拉 REST。
"""
from __future__ import annotations


def system_snapshot(*, server_restarted: bool) -> dict:
    from ..engine.runtime import get_dispatcher, hq_status
    from ..store import executions, queues
    from .pending import snapshot as pending_snapshot
    running = executions().list_by_state("running")
    # 进度状态随快照恢复（sse.md §2）：引擎已探测过该执行日志时附带
    # progress 字段——覆盖跨重启重连的标签页与运行中新开页面两条路径；
    # monitor 属采样态不随快照携带（重连后 ≤2s 重建）。
    dispatcher = get_dispatcher()
    if dispatcher is not None:
        for row in running:
            facts = dispatcher.progress_state(row["id"])
            if facts:
                row["progress"] = facts
    return {
        "pending": pending_snapshot(),
        "executions_running": running,
        "queues_summary": [{"id": q["id"], "state": q["state"],
                            "rollback_flag": q["rollback_flag"],
                            "rollback_count": q["rollback_count"]}
                           for q in queues().list()],
        "hq": hq_status(),
        "server_restarted": server_restarted,
    }
