"""G16 Web 工作台 · FastAPI 应用工厂（B1/B5）。

- 挂载各域路由（system/settings/candidates/queues/pending/executions/history/events）。
- 静态挂载 web/frontend/dist（B5）。
- /openapi.json 直接回读落盘 yaml（SSOT，B2 契约生成链要求，见 m0-plan §4.2）。
- lifespan 启动 mock 剧本后台任务与 SSE fanout。
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
from .sse import fanout_task, mock_script_runner  # type: ignore[attr-defined]
from .routers import (
    candidates,
    events,
    executions,
    history,
    pending,
    queues,
    settings,
    system,
)

_VERSION = "0.1.0"


def build_app() -> FastAPI:
    app = FastAPI(title="G16 Web 工作台",
                  version=_VERSION,
                  docs_url="/docs",
                  openapi_url="/openapi.json")

    for r in (system, settings, candidates, queues, pending, executions,
              history, events):
        app.include_router(r.router, prefix="/api/v1")

    # ---------- 契约 SSOT：/openapi.json 回读落盘 yaml ----------
    def _openapi_override() -> dict:
        return _load_contract()

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

    # ---------- 生命周期：mock 剧本 + SSTO fanout ----------
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        state = get_state()
        tasks = [
            asyncio.create_task(fanout_task(state)),
            asyncio.create_task(mock_script_runner(state)),
        ]
        yield
        for t in tasks:
            t.cancel()

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
                                         "version": _VERSION}, "paths": {}}


app = build_app()