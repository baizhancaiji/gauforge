"""system 域路由：健康检查与服务重启。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Response

from .. import config
from ..mock import get_state
from ..services import restart as restart_svc

router = APIRouter(tags=["system"])


@router.get("/system/health")
def get_system_health() -> dict:
    started = get_state().started_at
    return {
        "status": "ok",
        "version": config.APP_VERSION,
        "uptime_s": round(time.time() - started.timestamp(), 1),
    }


@router.post("/system/restart")
async def restart_system(response: Response) -> dict:
    """触发服务重启（异步；前端二次确认后调用）：更新流程互斥守卫 →
    detached 拉起重启脚本（快照原启动上下文）→ 202 先行，响应 flush 后
    延迟 SIGTERM 优雅自退，脚本按快照复原拉回并探活（不杀 HQ，§8.7）。"""
    restart_svc.guard()
    restart_svc.launch_script()
    restart_svc.schedule_self_terminate()
    response.status_code = 202
    return {"status": "restarting", "message": restart_svc.MSG_ACCEPTED}