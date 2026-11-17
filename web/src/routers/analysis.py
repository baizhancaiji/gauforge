"""analysis 域路由（M3 B3）：历史详情分析四端点 + workspace-out 只读分析。

纯拉取型（无新增 SSE 事件，sse.md §2 M3 注记）；全部只读或幂等派生。
storage 域（GET /storage/usage）随 B12 单独装配。
3.8.0 工具箱 B12 增 chk 工具三端点（chkchk 体检/手动转换/fchk 下载，
「对象=执行产物」落位本路由，toolbox-plan §2.6）。
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Response
from fastapi.responses import FileResponse

from ..errors import err
from ..services import analysis as analysis_svc
from ..services import chktools as chktools_svc
from ..services import cube as cube_svc

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


@router.post("/history/{id}/analysis/cube")
def generate_cube(id: int, payload: dict) -> dict:
    """生成 cube（幂等；白名单/上界越界 422、生成失败 502、cubegen 缺失 503）。"""
    return cube_svc.generate(id, payload.get("kind"),
                             payload.get("orbital"), payload.get("npts"))


@router.get("/history/{id}/analysis/cube/{cube_id}")
def download_cube(id: int, cube_id: str) -> Response:
    return Response(content=cube_svc.load(id, cube_id),
                    media_type="chemical/x-cube")


@router.post("/history/{id}/analysis/chkchk")
def check_chk(id: int) -> dict:
    """chk 体检（三态 verdict + 最小锚点提取 + raw 透传；损坏是有效结论
    恒 200，进程层失败 502/503）。"""
    return chktools_svc.run_chkchk(id)


@router.post("/history/{id}/analysis/fchk")
def convert_fchk(id: int) -> dict:
    """手动转换为 fchk（幂等优先 + 前置体检闸；502/503 映射在服务层
    领域异常）。"""
    fchk, generated = chktools_svc.ensure_fchk(id)
    return {"generated": generated, "fchk": fchk.name}


@router.get("/history/{id}/analysis/fchk")
def download_fchk(id: int) -> Response:
    """fchk 下载（FileResponse 流式发送，大 fchk 不整文件入内存；
    RFC 5987 双文件名在服务层拼装）。"""
    path, headers = chktools_svc.fchk_download(id)
    return FileResponse(path, media_type="application/octet-stream",
                        headers=headers)


@router.post("/analysis/workspace-out")
def analyze_workspace_out(payload: dict) -> dict:
    path = payload.get("path")
    if not isinstance(path, str):
        raise err("INVALID_REQUEST", "path 须为字符串（工作区内相对路径）",
                  http=400)
    return analysis_svc.workspace_out(path)
