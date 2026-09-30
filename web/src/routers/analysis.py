"""analysis 域路由（M3 B3）：历史详情分析四端点 + workspace-out 只读分析。

纯拉取型（无新增 SSE 事件，sse.md §2 M3 注记）；全部只读或幂等派生。
storage 域（GET /storage/usage）随 B12 单独装配。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..errors import err
from ..services import analysis as analysis_svc

router = APIRouter(tags=["history"])


@router.get("/history/{id}/analysis")
def get_analysis_overview(id: int) -> dict:
    return analysis_svc.overview(id)


@router.get("/history/{id}/analysis/convergence")
def get_analysis_convergence(id: int) -> dict:
    return analysis_svc.convergence(id)


@router.get("/history/{id}/analysis/frequencies")
def get_analysis_frequencies(id: int) -> dict:
    return analysis_svc.frequencies(id)


@router.get("/history/{id}/analysis/orbitals")
def get_analysis_orbitals(id: int) -> dict:
    return analysis_svc.orbitals(id)


@router.post("/analysis/workspace-out")
def analyze_workspace_out(payload: dict) -> dict:
    path = payload.get("path")
    if not isinstance(path, str):
        raise err("INVALID_REQUEST", "path 须为字符串（工作区内相对路径）",
                  http=400)
    return analysis_svc.workspace_out(path)
