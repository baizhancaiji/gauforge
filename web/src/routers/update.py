"""update 域路由：更新检查/执行/代理通道四端点（v2.1.0 功能更新）。

路由薄层，逻辑全在 service（services/update.py）；apply 同步段（守卫+预检）
放线程池，受理后经事件循环调度后台下载流水线。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response
from urllib.parse import urlparse

from ..errors import err
from ..services import update as update_svc

router = APIRouter(tags=["update"])


def _status() -> dict:
    return update_svc.get_service().status()


@router.get("/update/status")
def get_update_status() -> dict:
    """最近检查结果与更新流程状态（页面恢复；启动恢复的 done/failed 相
    被本端点首次消费即删除 update-state 文件）。"""
    return _status()


@router.post("/update/check")
def check_update() -> dict:
    """触发一次检查（同步返回；只发现不安装；探测失败 502
    UPDATE_CHECK_FAILED，文案按 §3.5）。"""
    return update_svc.get_service().run_check()


@router.post("/update/apply")
async def apply_update(response: Response) -> dict:
    """触发更新（异步执行）：同步段守卫+预检，受理后后台下载流水线，
    进度经 SSE update.progress/update.phase 推送。

    受理（phase=downloading）→ 202；已最新幂等（up_to_date）→ 200。"""
    svc = update_svc.get_service()
    status = await asyncio.to_thread(svc.apply)
    if svc.pending is not None:  # 受理（202）：调度后台流水线
        asyncio.create_task(svc.run_pending())
    response.status_code = 202 if status["phase"] == "downloading" else 200
    return status


def _valid_proxy_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


@router.put("/update/proxy")
def set_update_proxy(payload: dict) -> dict:
    """设置代理通道（写部署目录 .update-proxy，即时生效；null=直连；
    与 update.sh 共用同一份配置，URL 原文落盘且无尾换行）。"""
    if "proxy" not in payload:
        raise err("INVALID_REQUEST", "缺少 proxy 字段", http=400)
    proxy = payload["proxy"]
    if proxy is not None and (
            not isinstance(proxy, str) or not _valid_proxy_url(proxy)):
        raise err("INVALID_REQUEST", "代理 URL 非法", {"field": "proxy"},
                  http=400)
    update_svc.write_proxy(proxy)
    return _status()
