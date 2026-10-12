"""workflows 域路由（M4 B10）：组合流提交（契约 workflow 域）。

POST /workflows/conformer-refinement：一键组合流（前置检查序 503/409/422
见 services.workflows）；受理即返回（crest 任务已入待执行队列），前端由此
取得 id 打开进度面板（GET 查询端点随 B11）。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..mock import get_state
from ..services import pending as pending_svc
from ..services import workflows as workflows_svc

router = APIRouter(tags=["workflow"])


@router.post("/workflows/conformer-refinement")
def submit_conformer_refinement(payload: dict) -> dict:
    out = workflows_svc.submit_conformer_refinement(payload)
    get_state().emit("pending.snapshot", pending_svc.snapshot())
    return {"workflow_id": out["workflow_id"], "state": out["state"]}
