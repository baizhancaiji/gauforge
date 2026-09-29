"""SSE broker（m0-plan §3.4–§3.5；B11 事件总线真实化）。

架构：
- 事件唯一来源为**领域事件总线**：引擎/路由在真实业务动作点调用
  ``MockState.emit()`` 记入重放窗口（id 取 sse_seq 持久计数，每事件落库）。
- **全局 fanout 任务**（app lifespan 启动）按已广播条数轮询 event_history
  增量，经 broker 广播给各订阅者；REST 与引擎共用同一事件通路，无循环依赖。
- 每连接独立 asyncio.Queue，容量 256；溢出主动断开（走恢复语义）。
- 心跳定时推 ``system.heartbeat``。
- 重放：Last-Event-ID 在窗口（1024 条 / 5 分钟）内按序重放；否则推
  ``system.snapshot``（真实 store 数据，services.snapshot.system_snapshot）。

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

    async def deliver(self, sub_id: int, ev: dict) -> bool:
        """向指定订阅者投递一帧（重放/快照场景）。

        队满（重放差量超过 256 有界队列等）时断开该订阅并返回 False，
        客户端按退避重连后走恢复语义补齐（契约 §3.5）。
        """
        q = self._subscribers.get(sub_id)
        if q is None:
            return True
        data = ev["data"] if isinstance(ev["data"], str) else \
            json.dumps(ev["data"], ensure_ascii=False)
        try:
            q.put_nowait(ServerSentEvent(
                id=str(ev["id"]), event=ev["event"], data=data))
        except asyncio.QueueFull:
            self.unsubscribe(sub_id)
            return False
        return True


async def fanout_task(state: MockState) -> None:
    """把新 emitted 事件广播到所有订阅者；在 app 后台持续运行。

    以**事件 id** 为增量基准（持久单调、不受重放窗口修剪影响）：每轮只
    广播 id 大于上次已广播的事件。不得以「已广播条数」对固定容量列表做
    差量——event_history 超 1024 条即修剪，绝对计数会令 ``len(history) >
    broadcast_count`` 永假而静默停摆（v2.0.0 实测：实时事件全丢、心跳照常、
    连接看似正常，执行页幽灵卡与读数冻结的根因）。
    """
    last_id = 0
    while True:
        await asyncio.sleep(0.02)
        for ev in state.event_history:
            if ev["id"] > last_id:
                await broker.broadcast(ev)
                last_id = ev["id"]


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
    """订阅进入步骤（契约 §3.5 三分支）。

    - Last-Event-ID 落在重放窗口内（窗口最旧 id ≤ last_seq）→ 按序重放差量
      （last_seq 已最新时重放为空集，静默续流）；
    - 缺失 / 超窗（含服务重启清窗）→ 推 system.snapshot 全量重建
      （带 Last-Event-ID 的超窗场景 server_restarted=true）；
    - 投递中队满 → 断开该订阅，客户端重连走恢复语义。
    """
    state = get_state()
    window = _window(state)
    last_seq: int | None = None
    if last_id and last_id.isdigit():
        last_seq = int(last_id)
    # 仅当 last_seq 落在窗口内才重放；只查上界会把超窗旧 id 误入重放分支，
    # 静默丢失窗口之前的更早事件（违反「超窗 → snapshot」语义）。
    if last_seq is not None and window and window[0]["id"] <= last_seq:
        for ev in window:
            if ev["id"] > last_seq:
                if not await broker.deliver(sub_id, ev):
                    return
        return
    # 超窗 / 缺 id / 首次连接：推全量快照重建基线（B11 起取真实 store 数据）。
    from .services.snapshot import system_snapshot
    snapshot = system_snapshot(server_restarted=last_id is not None)
    await broker.deliver(sub_id, {
        "id": state.event_seq, "event": "system.snapshot", "data": snapshot,
        "ts": _now_ts()})


# 模块级单例（应用复用）。
broker = SseBroker()
