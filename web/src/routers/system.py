"""system 域路由：健康检查。"""
from __future__ import annotations

import time

from fastapi import APIRouter

from .. import config
from ..mock import get_state

router = APIRouter(tags=["system"])


@router.get("/system/health")
def get_system_health() -> dict:
    started = get_state().started_at
    return {
        "status": "ok",
        "version": config.APP_VERSION,
        "uptime_s": round(time.time() - started.timestamp(), 1),
    }