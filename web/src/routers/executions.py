"""executions 域路由：运行中执行列表/详情/停止（§2.3，B7 真实化）。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Response
from starlette import status

from ..errors import err, not_found
from ..store import executions, tasks

router = APIRouter(tags=["executions"])


def _attach_kind(rows: list[dict]) -> list[dict]:
    """kind 冗余注入（M4 C7 crest 行徽标数据源；契约 Execution.kind）。

    按 task_id 反查任务 kind，任务已删除缺省 g16；执行表不落列、响应时
    注入（与 filename 写入时冗余不同源，口径见 openapi Execution.kind）。
    """
    out = []
    for r in rows:
        t = tasks().get(r["task_id"])
        out.append({**r, "kind": (t or {}).get("kind") or "g16"})
    return out


@router.get("/executions")
def list_executions(state: str | None = None) -> list:
    rows = (executions().list_by_state(state)
            if state in ("running", "succeeded", "failed", "skipped")
            else None)
    if rows is None:
        # 无过滤：running 优先展示，其余按 id 倒序（运行视图语义）
        rows = executions().list_by_state("running")
        seen = {r["id"] for r in rows}
        for st in ("succeeded", "failed", "skipped"):
            for r in executions().list_by_state(st):
                if r["id"] not in seen:
                    rows.append(r)
                    seen.add(r["id"])
    return _attach_kind(rows)


@router.get("/executions/{id}")
def get_execution(id: int) -> dict:
    e = executions().get(id)
    if e is None:
        raise not_found("execution", id)
    return _attach_kind([e])[0]


@router.post("/executions/{id}/stop",
             status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def stop_execution(id: int) -> Response:
    from ..engine.runtime import get_dispatcher
    d = get_dispatcher()
    if d is None:
        raise err("INTERNAL_ERROR", "派发引擎未挂载",
                  http=status.HTTP_500_INTERNAL_SERVER_ERROR)
    d.stop_execution(id)  # 终态与席位释放由引擎差分管线驱动（§8.7 归因）
    return Response(status_code=status.HTTP_204_NO_CONTENT)
