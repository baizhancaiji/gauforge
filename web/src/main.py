"""G16 Web 工作台 · FastAPI 应用工厂（B1/B5）。

- 挂载各域路由（system/settings/candidates/queues/pending/executions/history/events）。
- 静态挂载 web/frontend/dist（B5）。
- /openapi.json 直接回读落盘 yaml（SSOT，B2 契约生成链要求，见 m0-plan §4.2）。
- lifespan 启动 SSE fanout（B11 领域事件总线）；引擎开启时执行启动序列（B10）。
"""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .errors import ApiError
from .mock import get_state
from .sse import fanout_task  # type: ignore[attr-defined]
from .routers import (
    candidates,
    events,
    executions,
    history,
    pending,
    queues,
    settings,
    system,
    ui_prefs,
    update,
)


def build_app() -> FastAPI:
    app = FastAPI(title="G16 Web 工作台",
                  version=config.APP_VERSION,
                  docs_url="/docs",
                  openapi_url="/openapi.json")

    for r in (system, settings, candidates, queues, pending, executions,
              history, update, ui_prefs, events):
        app.include_router(r.router, prefix="/api/v1")

    # ---------- 契约 SSOT：/openapi.json 回读落盘 yaml ----------
    def _openapi_override() -> dict:
        doc = _load_contract()
        # info.version 动态覆盖（防再漂移，version-update-impl-plan §1.2-2）：
        # yaml 静态值保留为离线参考，运行时以版本单一事实来源为准
        # （APP_VERSION 剥 v 裸版本）。
        info = doc.get("info")
        if isinstance(info, dict):
            info["version"] = config.bare_version()
        return doc

    app.openapi = _openapi_override  # type: ignore[assignment]

    # ---------- 统一错误：契约裸 body {"error":{...}} ----------
    @app.exception_handler(ApiError)
    async def _api_error_handler(_req, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def _val_handler(_req, _exc: RequestValidationError) -> JSONResponse:
        # FastAPI 请求级校验也走统一结构（顶层 error，不包 detail）。
        return JSONResponse(status_code=422, content={"error": {
            "code": "VALIDATION_FAILED", "message": "字段级校验失败",
            "details": {"errors": []}}})

    # ---------- 静态前端 ----------
    dist = config.FRONTEND_DIST if config.FRONTEND_DIST.exists() else None
    manifest = None
    if dist is not None:
        app.mount("/", StaticFiles(directory=str(dist), html=True),
                  name="frontend")

    # ---------- 生命周期：事件 fanout（B11 领域事件总线）+ 引擎（B10） ----------
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        from .engine import startup

        state = get_state()
        tasks = [asyncio.create_task(fanout_task(state))]
        engine = None
        if config.ENGINE_ENABLED:  # 启动序列放线程池，不阻塞事件循环
            engine = await asyncio.to_thread(startup.start_engine)
        # 更新域（v2.1.0）：启动恢复 update-state/.update-check（§3.4）+
        # 自动检查调度（30s 轮询式；到点触发与启动补查同口径，只发现不安装）
        from .services import update as update_svc
        update_svc.get_service().recover_from_disk()
        scheduler = update_svc.AutoCheckScheduler()
        tasks.append(asyncio.create_task(scheduler.run()))
        yield
        scheduler.stop()
        for t in tasks:
            t.cancel()
        startup.shutdown_engine(engine)  # 摘运行时单例；不杀 HQ 进程

    app.router.lifespan_context = lifespan  # type: ignore[method-assign]

    return app


def _load_contract() -> dict:
    path = config.CONTRACT_PATH
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    # 契约缺失（常规测试不解耦场景）时回退框架自省，不炸启动。
    return _fallback_info()


def _fallback_info() -> dict:  # pragma: no cover
    return {"openapi": "3.0.3", "info": {"title": "G16 Web 工作台",
                                         "version": config.bare_version()},
            "paths": {}}


app = build_app()


def resolved_listen_port() -> int:
    """启动端口：SQLite 运行级设置（无记录回落代码默认值）。

    `python -m web.src.main` 启动时生效；listen_port 保存后下次重启生效。
    """
    from .store import settings as settings_store
    return int(settings_store().get("listen_port"))


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host=config.BIND_ADDR, port=resolved_listen_port())