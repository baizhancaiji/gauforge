"""executions 域路由：运行中执行列表/详情/停止（§2.3，M0 mock）。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Response

from ..errors import NOT_FOUND, err
from ..mock import get_state
from starlette import status

router = APIRouter(tags=["executions"])


@router.get("/executions")
def list_executions(state: str | None = None) -> list:
    items = [dict(e) for e in get_state().executions]
    if state:
        items = [e for e in items if e["state"] == state]
    return items


@router.get("/executions/{id}")
def get_execution(id: int) -> dict:
    e = get_state().get_execution(id)
    if e is None:
        raise NOT_FOUND("execution", id)
    return dict(e)


@router.post("/executions/{id}/stop",
             status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def stop_execution(id: int) -> Response:
    state = get_state()
    e = state.get_execution(id)
    if e is None:
        raise NOT_FOUND("execution", id)
    if e["state"] != "running":
        raise err("TASK_STATE_CONFLICT", "仅运行中执行可停止",
                  {"state": e["state"]}, http=409)
    state.finish_execution(id, "failed", "manually_stopped")
    state.emit("task.status", {"task_id": e["task_id"], "execution_id": id,
                               "from": "running", "to": "failed",
                               "cause": "manually_stopped"})
    state.emit("history.appended", {"execution_id": id,
                                    "task_id": e["task_id"], "state": "failed",
                                    "cause": "manually_stopped"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)