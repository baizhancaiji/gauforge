"""SSE 契约测试（m0-plan §4.3 test_contract_sse.py）。

直接驱动 web.src.sse.event_stream 生成器（asyncio.wait_for 超时收帧），
避免 TestClient 对无限流的阻塞；时序断言用轮询/超时，不用 sleep 死等（§4.3）。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from web.src.sse import broker, event_stream
from web.src.mock import MockState, get_state


@pytest.fixture(autouse=True)
def reset_broker():
    # 每用例清空订阅者与事件窗口，避免跨用例相互影响。
    broker._subscribers.clear()
    broker._counter = 0
    st = get_state()
    st.event_seq = 0
    st.event_history.clear()
    yield


async def _first_frame(last_id: str | None = None,
                       timeout: float = 2.0) -> dict:
    """异步接收一帧（有界队列模式），超时抛 TimeoutError。"""
    sub_id = broker.subscribe()
    try:
        queue = broker._subscribers[sub_id]
        # 把 event_stream 乏首帧编进循环：复用重放/快照/心跳逻辑。
        await _primed_replay(sub_id, last_id)
        q = asyncio.wait_for(queue.get(), timeout=timeout)
        sse = await q
        return {"id": sse.id, "event": sse.event, "data": sse.data}
    finally:
        broker.unsubscribe(sub_id)


async def _primed_replay(sub_id: int, last_id: str | None) -> None:
    """等价 event_stream 的进入步骤：注册后重放/快照（同步投递已入队）。"""
    import json as _j
    from web.src.sse import _replay_or_snapshot
    await _replay_or_snapshot(sub_id, last_id)


def _run(coro, timeout: float = 3.0):
    return asyncio.run(asyncio.wait_for(coro, timeout=timeout))


def test_first_frame_is_snapshot_with_valid_data():
    frame = _run(_first_frame(timeout=3.0))
    assert frame["event"] == "system.snapshot", "首帧（无 Last-Event-ID）应为快照"
    data = json.loads(frame["data"])
    # 快照载荷字段（sse.md §2 system.snapshot，hq 为侧栏 HQ 连接状态）。
    assert set(data) == {"pending", "executions_running", "queues_summary",
                         "hq", "server_restarted"}
    assert "id" in frame and frame["id"].isdigit()


def test_emit_propagates_as_frame_with_monotonic_id():
    st = get_state()
    st.emit("task.status", {"task_id": 1, "from": "staged", "to": "running",
                            "ts": "2026-09-23T00:00:00+08:00"})

    async def collect():
        sub_id = broker.subscribe()
        try:
            # fanout 由后台任务推送；这里直接调用广播路径模拟。
            await broker.broadcast(st.event_history[-1])
            sse = await asyncio.wait_for(broker._subscribers[sub_id].get(),
                                         timeout=1.0)
            return sse
        finally:
            broker.unsubscribe(sub_id)

    sse = _run(collect())
    assert sse.event == "task.status"
    assert sse.id == str(st.event_seq)
    payload = json.loads(sse.data)
    assert payload["task_id"] == 1
    assert "ts" in payload, "事件载荷应含 ts"


def test_replay_orders_past_events_by_last_event_id():
    st = get_state()
    for i in range(3):
        st.emit("execution.progress", {"execution_id": 1, "opt_step": i,
                                       "ts": "t"})
    # 用 Last-Event-ID=第一次的 id，应只重放之后的事件。
    first_id = str(st.event_history[0]["id"])

    async def replay():
        sub_id = broker.subscribe()
        try:
            from web.src.sse import _replay_or_snapshot
            await _replay_or_snapshot(sub_id, first_id)
            frames = []
            while not broker._subscribers[sub_id].empty():
                frames.append(await broker._subscribers[sub_id].get())
            return frames
        finally:
            broker.unsubscribe(sub_id)

    frames = _run(replay())
    assert frames, "重放至少一帧"
    # Last-Event-ID 大于窗口内全部 → 超窗走快照分支也返回帧；此处断言有序。
    ids = [int(f.id) for f in frames]
    assert ids == sorted(ids), "重放帧序号应有序"
    assert all(int(f.id) > int(first_id) for f in frames), \
        "重放帧序号应大于 Last-Event-ID"