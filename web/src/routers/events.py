"""SSE 事件流路由（契约 docs/api/sse.md）。"""
from __future__ import annotations

from fastapi import APIRouter, Request, Header
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from ..sse import event_stream

router = APIRouter(tags=["system"])


@router.get("/events")
async def sse_events(request: Request,
                     last_event_id: str | None = Header(default=None,
                                                        alias="Last-Event-ID")) \
        -> EventSourceResponse:
    return EventSourceResponse(
        event_stream(last_id=last_event_id),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        ping=9999,  # 心跳由应用帧承载；禁用 sse-starlette 默认 ping
    )