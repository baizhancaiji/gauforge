"""storage 域路由（M3.7 B12）：空间占用统计与阈值告警（只读、拉取式）。"""
from __future__ import annotations

from fastapi import APIRouter

from ..services import storage as storage_svc

router = APIRouter(tags=["storage"])


@router.get("/storage/usage")
def get_storage_usage() -> dict:
    return storage_svc.usage()
