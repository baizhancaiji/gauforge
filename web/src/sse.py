"""SSE broker（m0-plan §3.4–§3.5）。

架构：
- REST 端点调用 ``MockState.emit()`` 仅同步记入 ``event_history``（重放窗口）。
- **全局 fanout 任务**（app lifespan 启动）轮询 event_history 的尾部新序号，
  经 broker 广播给各订阅者；新事件被 REST 端点的请求线程 emit 时触发广播。
  这样 REST 与 SSE 共享同一内存状态，无循环依赖。
- 每连接独立 asyncio.Queue，容量 256；溢出主动断开（走恢复语义）。
- 心跳定时推 ``system.heartbeat``。
- 重放：Last-Event-ID 在窗口（1024 条 / 5 分钟）内按序重放；否则推 ``system.snapshot``。

M0 单机单用户，一条流承载全部事件，不设 topic 订阅。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from sse_starlette.sse import ServerSentEvent

from .mock import MockState, get_state

logger = logging.getLogger(__name__)

QUEUE_CAPACITY = 256
WINDOW_MAX_EVENTS = 1024
WINDOW_MAX_SECONDS = 300  # 5 分钟，先到为准（§3.5）
HEARTBEAT_FALLBACK = 15.0


def _now_ts() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class SseBroker:
    """为每个连接派生独立有界队列；广播新事件；队满断开。"""

    def __init__(self) -> None:
        self._subscribers: dict[int, asyncio.Queue[ServerSentEvent]] = {}
        self._counter = 0

    def subscribe(self) -> int:
        self._counter += 1
        self._subscribers[self._counter] = asyncio.Queue(maxsize=QUEUE_CAPACITY)
        return self._counter

    def unsubscribe(self, sub_id: int) -> None:
        self._subscribers.pop(sub_id, None)

    async def broadcast(self, ev: dict) -> None:
        # ev["data"] 已是 JSON 字符串（emit 时序列化），勿二次编码。
        data = ev["data"] if isinstance(ev["data"], str) else \
            json.dumps(ev["data"], ensure_ascii=False)
        drop: list[int] = []
        for sub_id, q in self._subscribers.items():
            if q.full():
                drop.append(sub_id)  # 慢消费：断开，客户端重连取快照
                continue
            q.put_nowait(ServerSentEvent(id=str(ev["id"]),
                                         event=ev["event"], data=data))
        for sub_id in drop:
            self.unsubscribe(sub_id)

    async def deliver(self, sub_id: int, ev: dict) -> None:
        """向指定订阅者投递一帧；无关订阅是否队满（重放/快照场景）。"""
        q = self._subscribers.get(sub_id)
        if q is None:
            return
        data = ev["data"] if isinstance(ev["data"], str) else \
            json.dumps(ev["data"], ensure_ascii=False)
        q.put_nowait(ServerSentEvent(
            id=str(ev["id"]), event=ev["event"], data=data))


async def fanout_task(state: MockState) -> None:
    """把新 emitted 事件广播到所有订阅者；在 app 后台持续运行。"""
    last_seq = state.event_seq
    while True:
        await asyncio.sleep(0.02)
        history = state.event_history
        start = last_seq
        if history and start < len(history):
            for ev in history[start:]:
                await broker.broadcast(ev)
            last_seq = len(history)


def _window(state: MockState) -> list[dict]:
    events = list(state.event_history)
    cutoff = datetime.now(timezone.utc).timestamp() - WINDOW_MAX_SECONDS
    fresh = [ev for ev in events
             if (datetime.fromisoformat(ev["ts"]).timestamp() if ev.get("ts")
                 else 0) > cutoff]
    return fresh[-WINDOW_MAX_EVENTS:] if len(fresh) > WINDOW_MAX_EVENTS else fresh


async def event_stream(last_id: str | None = None) -> AsyncIterator[ServerSentEvent]:
    """SSE 端点生成器：注册 → 重放/快照 → 心跳 + 实时事件。"""
    sub_id = broker.subscribe()
    try:
        await _replay_or_snapshot(sub_id, last_id)
        state = get_state()
        while True:
            interval = float(state.get_runtime("sse_heartbeat_seconds")
                             or HEARTBEAT_FALLBACK)
            try:
                sse = await asyncio.wait_for(broker._subscribers[sub_id].get(),
                                             timeout=interval)
                yield sse
            except asyncio.TimeoutError:
                seq = state.event_seq
                yield ServerSentEvent(id=str(seq), event="system.heartbeat",
                                      data=json.dumps({"ts": _now_ts()}))
            except KeyError:
                return
    finally:
        broker.unsubscribe(sub_id)


async def _replay_or_snapshot(sub_id: int, last_id: str | None) -> None:
    state = get_state()
    window = _window(state)
    last_seq = int(last_id) if last_id and last_id.isdigit() else 0
    if last_id is not None and last_seq and last_seq < window[-1]["id"] \
            if window else last_id:
        for ev in window:
            if ev["id"] > last_seq:
                await broker.deliver(sub_id, ev)
        return
    # 超窗 / 缺 id / 首次连接：推全量快照重建基线。
    pend = state.pending()
    snapshot = {
        "pending": pend,
        "executions_running": [dict(e) for e in state.executions],
        "queues_summary": [{"id": q["id"], "state": q["state"],
                            "rollback_flag": q["rollback_flag"],
                            "rollback_count": q["rollback_count"]}
                           for q in state.queues],
        "server_restarted": last_id is not None,
    }
    await broker.deliver(sub_id, {
        "id": state.event_seq, "event": "system.snapshot", "data": snapshot,
        "ts": _now_ts()})


# 模块级单例（应用复用）。
broker = SseBroker()


async def mock_script_runner(state: MockState) -> None:
    """§3.7 mock 推流剧本；周期 30s 循环，数据与 REST mock 同源。

    事件经 state.emit() 记入窗口，由 fanout_task 广播给所有订阅者。
    """
    last_tick = 0
    while True:
        await asyncio.sleep(0.5)
        now = asyncio.get_running_loop().time()
        if now - last_tick < 30:
            continue
        last_tick = now
        try:
            if not state.executions:
                # 无运行中执行则新建一条演示执行（含任务映射），模拟派发。
                cand = (state.candidates or [None])[0]
                task_id = cand["id"] if cand else state.next_id()
                exc = state.add_execution(task_id, cand["filename"]
                                          if cand else "demo.gjf", None)
            else:
                exc = state.executions[0]
            eid, tid = exc["id"], exc["task_id"]
            for i in range(1, 6):
                state.emit("execution.monitor", {
                    "execution_id": eid, "cpu_percent": 40 + i * 12,
                    "mem_rss_mb": 380 + i * 25, "elapsed_s": i * 2,
                    "ts": _now_ts()})
                await asyncio.sleep(0.05)
            for i in range(1, 6):
                state.emit("execution.progress", {
                    "execution_id": eid, "task_id": tid, "opt_step": i,
                    "scf_cycle": i + 2, "converged": False,
                    "last_line": f" Step number {i}", "ts": _now_ts()})
                await asyncio.sleep(0.05)
            state.emit("task.status", {"task_id": tid, "execution_id": eid,
                                       "from": "running", "to": "succeeded",
                                       "ts": _now_ts()})
            state.finish_execution(eid, "succeeded", None)
            state.emit("history.appended", {"execution_id": eid, "task_id": tid,
                                            "state": "succeeded", "ts": _now_ts()})
            # 模拟队列完成事件由前端观看；无队列时跳过。
        except asyncio.CancelledError:
            return
        except Exception as e:  # pragma: no cover
            logger.warning("mock script: %s", e)
            await asyncio.sleep(2)