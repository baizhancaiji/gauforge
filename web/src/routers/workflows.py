"""workflows 域路由（M4 B10/B11）：组合流提交与查询（契约 workflow 域）。

POST /workflows/conformer-refinement：一键组合流（前置检查序 503/409/422
见 services.workflows）；受理即返回（crest 任务已入待执行队列）。
GET /workflows/{id}：组合流单点（状态 + energy_summary 跨容器后端聚合，
C7 进度面板数据源）；GET /workflows?limit=20：列表（按 updated_at 倒序、
单点同形——页面刷新后找回组合流与 refine_queue_pending 提示回看的恢复
路径）。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..errors import not_found
from ..mock import get_state
from ..services import energy as energy_svc
from ..services import pending as pending_svc
from ..services import workflows as workflows_svc
from ..store import workflows as workflows_store

router = APIRouter(tags=["workflow"])


@router.post("/workflows/conformer-refinement")
def submit_conformer_refinement(payload: dict) -> dict:
    out = workflows_svc.submit_conformer_refinement(payload)
    get_state().emit("pending.snapshot", pending_svc.snapshot())
    # 响应契约 = openapi ConformerRefinementResponse 四字段（crest 任务 id
    # 与席位 id 供待执行面板定位；crest_execution_id 属 GET 单点，
    # 提交时点 crest 尚未派发、恒不存在）
    return {"workflow_id": out["workflow_id"], "state": out["state"],
            "crest_task_id": out["crest_task_id"], "seat_id": out["seat_id"]}


@router.get("/workflows")
def list_workflows(limit: int = 20) -> dict:
    limit = min(max(limit, 1), 100)
    return {"workflows": [energy_svc.workflow_view(r)
                          for r in workflows_store().list(limit)]}


@router.get("/workflows/{id}")
def get_workflow(id: str) -> dict:
    row = workflows_store().get(id)
    if row is None:
        raise not_found("workflow", id)
    return energy_svc.workflow_view(row)
