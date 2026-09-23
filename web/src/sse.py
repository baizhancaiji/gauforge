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


# ---------------- mock 推流剧本（§3.7，六页联演） ----------------

def _seat_of_task(state: MockState, task_id: int) -> dict | None:
    """task_id 所在席位（成员匹配）；不在席返回 None。"""
    for seat in state.seats:
        if any(m["task_id"] == task_id for m in seat["members"]):
            return seat
    return None


async def _emit_pending(state: MockState) -> None:
    """席位变动后推 pending.snapshot（载荷同 GET /pending）。"""
    state.emit("pending.snapshot", state.pending())


async def _finish_execution(state: MockState, exc: dict,
                            queue_id: str | None, *,
                            remove_seat: bool = True) -> None:
    """收尾一条执行：终态事件 + 历史写入 +（可选）席位释放。

    队列席位须待全部成员完成后统一释放，故队列旅程传 remove_seat=False。
    """
    eid, tid = exc["id"], exc["task_id"]
    extra = {"queue_id": queue_id} if queue_id else {}
    state.emit("task.status", {"task_id": tid, "execution_id": eid,
                               **extra, "from": "running", "to": "succeeded",
                               "ts": _now_ts()})
    state.finish_execution(eid, "succeeded", None)
    state.emit("history.appended", {"execution_id": eid, "task_id": tid,
                                    "state": "succeeded", **extra,
                                    "ts": _now_ts()})
    if remove_seat:
        seat = _seat_of_task(state, tid)
        if seat is not None:
            state.seats.remove(seat)
            await _emit_pending(state)


async def _demo_queue_journey(state: MockState) -> None:
    """首轮队列旅程：种子队列席位 提交→执行→成员收尾→完成→席位释放。

    驱动 queue.status 全流转（队列页状态徽标）+ 成员派发/读数/入史
    （执行中/历史页联动）+ 席位释放（待执行页联动）。
    """
    seat = next((s for s in state.seats if s["kind"] == "queue"), None)
    q = next((x for x in state.queues
              if seat is not None and x["id"] == seat["queue_id"]), None)
    if seat is None or q is None or q["state"] != "unsubmitted":
        return
    q["state"] = "submitted"
    state.emit("queue.status", {"queue_id": q["id"], "from": "unsubmitted",
                                "to": "submitted", "ts": _now_ts()})
    await asyncio.sleep(0.6)
    q["state"] = "executing"
    state.emit("queue.status", {"queue_id": q["id"], "from": "submitted",
                                "to": "executing", "ts": _now_ts()})
    await _emit_pending(state)
    for m in seat["members"]:
        exc = state.add_execution(m["task_id"], m["filename"], q["id"])
        m["state"] = "running"
        state.emit("task.status", {"task_id": m["task_id"],
                                   "execution_id": exc["id"],
                                   "queue_id": q["id"],
                                   "from": "staged", "to": "running",
                                   "ts": _now_ts()})
        await _emit_pending(state)
        for i in range(1, 4):
            state.emit("execution.monitor", {
                "execution_id": exc["id"], "cpu_percent": 45 + i * 10,
                "mem_rss_mb": 400 + i * 30, "elapsed_s": i * 3,
                "ts": _now_ts()})
            state.emit("execution.progress", {
                "execution_id": exc["id"], "task_id": m["task_id"],
                "opt_step": i, "scf_cycle": i + 3, "converged": False,
                "last_line": f" Step number {i}", "ts": _now_ts()})
            await asyncio.sleep(0.4)
        await _finish_execution(state, exc, q["id"], remove_seat=False)
        await asyncio.sleep(0.3)
    q["state"] = "completed"
    q["finish_reason"] = "success"
    state.emit("queue.status", {"queue_id": q["id"], "from": "executing",
                                "to": "completed", "finish_reason": "success",
                                "ts": _now_ts()})
    if seat in state.seats:
        state.seats.remove(seat)
    await _emit_pending(state)


async def _demo_single_task(state: MockState) -> None:
    """单任务滚动旅程：收尾最旧腾席 → 新候选入席 → 派发 → 读数 → 停滞 → 成功。"""
    # a. 收尾最旧在跑执行：滚动腾出席位，席位容量守恒。
    if state.executions:
        oldest = state.executions[0]
        await _finish_execution(state, oldest, oldest.get("queue_id"))
    # b. 挑空闲候选（不在跑、不在席）；无则本轮跳过（容量守恒下极少发生）。
    busy = {e["task_id"] for e in state.executions}
    seated = {m["task_id"] for s in state.seats for m in s["members"]}
    cand = next((c for c in state.candidates
                 if c["id"] not in busy and c["id"] not in seated), None)
    if cand is None:
        return
    # c. 入席（等待区，pending.snapshot）→ 派发（staged→running）。
    state.seats.append({
        "seat_id": state.next_id(), "kind": "task", "task_id": cand["id"],
        "queue_id": None, "position": len(state.seats),
        "members": [{"task_id": cand["id"], "filename": cand["filename"],
                     "state": "staged"}], "locked": False})
    await _emit_pending(state)
    await asyncio.sleep(0.5)
    exc = state.add_execution(cand["id"], cand["filename"], None)
    seat = _seat_of_task(state, cand["id"])
    if seat is not None:
        seat["members"][0]["state"] = "running"
    state.emit("task.status", {"task_id": cand["id"], "execution_id": exc["id"],
                               "from": "staged", "to": "running",
                               "ts": _now_ts()})
    await _emit_pending(state)
    # d. 读数跳变（monitor 资源 + progress 步进；0.4s 节奏肉眼可见）。
    eid = exc["id"]
    for i in range(1, 6):
        state.emit("execution.monitor", {
            "execution_id": eid, "cpu_percent": 40 + i * 12,
            "mem_rss_mb": 380 + i * 25, "elapsed_s": i * 2,
            "ts": _now_ts()})
        await asyncio.sleep(0.4)
    for i in range(1, 6):
        state.emit("execution.progress", {
            "execution_id": eid, "task_id": cand["id"], "opt_step": i,
            "scf_cycle": i + 2, "converged": False,
            "last_line": f" Step number {i}", "ts": _now_ts()})
        await asyncio.sleep(0.4)
    # e. 停滞告警：置位 → 停滞期 → 新进度恢复触发解除（§3.7 stalled 演示）。
    state.emit("execution.stalled", {"execution_id": eid,
                                     "task_id": cand["id"], "stalled": True,
                                     "ts": _now_ts()})
    await asyncio.sleep(1.2)
    state.emit("execution.progress", {
        "execution_id": eid, "task_id": cand["id"], "opt_step": 6,
        "scf_cycle": 8, "converged": False,
        "last_line": " Step number 6", "ts": _now_ts()})
    state.emit("execution.stalled", {"execution_id": eid,
                                     "task_id": cand["id"], "stalled": False,
                                     "ts": _now_ts()})
    await asyncio.sleep(0.4)
    # f. 成功收尾 + 席位释放。
    await _finish_execution(state, exc, None)


async def mock_script_runner(state: MockState) -> None:
    """§3.7 mock 推流剧本：周期 30s，六页联演完整生命周期。

    M0 不做真实调度（派发/窗口补位属 M1），但把契约事件全集逐类推实：
    - 首轮队列旅程：种子队列 unsubmitted→submitted→executing→成员依次
      派发/读数/收尾 → completed(success) → 席位释放（queue.status 全流转）；
    - 后续单任务滚动旅程：收尾最旧执行腾席 → 新候选入席（pending.snapshot）
      → 派发（task.status staged→running）→ monitor/progress 读数跳变
      → execution.stalled 置位/解除 → succeeded → history.appended
      → 席位释放。
    读数间隔 0.4s（较契约 2s/1s 加速演示）；周期间隙由 system.heartbeat
    自然填充。
    """
    queue_demo_done = False
    last_tick = 0.0
    while True:
        await asyncio.sleep(0.5)
        now = asyncio.get_running_loop().time()
        if now - last_tick < 30:
            continue
        last_tick = now
        try:
            if not queue_demo_done:
                queue_demo_done = True
                await _demo_queue_journey(state)
            else:
                await _demo_single_task(state)
        except asyncio.CancelledError:
            return
        except Exception as e:  # pragma: no cover
            logger.warning("mock script: %s", e)
            await asyncio.sleep(2)