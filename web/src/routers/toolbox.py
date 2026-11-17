"""toolbox 域路由（3.8.0 工具箱 B15）：freqmem 校验 / 历史带入预填 /
溶剂速查表（「对象=独立工具」落位新路由，toolbox-plan §2.6）。

纯拉取/计算型（无 SSE 事件，sse.md 3.8.0 零变更注记）。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..services import toolbox as toolbox_svc

router = APIRouter(tags=["toolbox"])


@router.post("/toolbox/freqmem")
def check_freqmem(payload: dict) -> dict:
    """内存估算校验（白名单/值域 422、锚点判定、对照 verdict 总量口径）。"""
    return toolbox_svc.freqmem_check(payload)


@router.get("/toolbox/freqmem-prefill")
def get_freqmem_prefill(execution_id: int) -> dict:
    """历史带入预填（仅 succeeded；非终态 404、终态非 succeeded 409）。"""
    return toolbox_svc.freqmem_prefill(execution_id)


@router.get("/toolbox/solvents")
def list_solvents() -> dict:
    """溶剂速查表（懒加载 + 进程内缓存；184 条全量返回不分页）。"""
    return toolbox_svc.solvents_list()
