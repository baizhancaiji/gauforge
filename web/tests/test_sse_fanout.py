"""SSE fanout 回归（v2.0.0 实测缺陷）：重放窗口修剪后实时广播不得停摆。

根因：fanout 以「绝对累计已广播条数」对「固定容量（1024）event_history」做
增量判断——累计事件数超过窗口容量后 ``len(history) > broadcast_count`` 永假，
fanout 不报错不退出、静默停摆，其后所有实时事件服务端丢失（前端执行页
幽灵卡/读数冻结而心跳照常、无「连接中断」提示的根因）。
"""
from __future__ import annotations

import asyncio
import contextlib

from web.src.mock import MockState
from web.src.sse import broker, fanout_task


def test_fanout_survives_replay_window_trim():
    """累计发射 1100 条（> 重放窗口 1024）→ 订阅者全量按序送达。"""

    async def scenario() -> list[int]:
        state = MockState()
        sub = broker.subscribe()
        received: list[int] = []

        async def consume() -> None:
            while True:
                ev = await broker._subscribers[sub].get()
                received.append(int(ev.id))

        consumer = asyncio.create_task(consume())
        fan = asyncio.create_task(fanout_task(state))
        try:
            for i in range(1100):
                state.emit("execution.monitor",
                           {"execution_id": 1, "cpu_percent": 627.0,
                            "mem_rss_mb": 246.0, "elapsed_s": i,
                            "ts": "2026-09-29T01:02:51+08:00"})
                if i % 50 == 49:
                    await asyncio.sleep(0.02)  # 让出循环：fanout 全速跟进
            await asyncio.sleep(0.3)
        finally:
            for t in (fan, consumer):
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            broker.unsubscribe(sub)
        return received

    received = asyncio.run(scenario())
    assert len(received) == 1100  # 修复前：停在 1024，其后全部丢失
    assert received == sorted(received)  # 全局单调序
