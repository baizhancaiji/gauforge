"""分析域服务（M3 B3，m3-plan §4.6/§2.1/§2.3）：analysis.json 读取、惰性
重建、分块响应与 workspace-out 只读分析。

- 可见性：仅 succeeded 可读（非 succeeded 一律 409 ANALYSIS_UNAVAILABLE）；
- 惰性重建（§8 决策点 2 定稿）：analysis.json 缺失/损坏时经 finalize 解析步
  补跑一次（幂等），仍失败方报 409（run 目录缺失等）；
- 块可见性由 Result.blocks 驱动：false 的块请求 422 ANALYSIS_PARSE_FAILED
  （无频率任务请求 frequencies 等）；
- 响应预算：收敛端点 >2MB 时按步均匀抽稀并置 downsampled=true（§2.3；
  金标准样本不触发）；
- workspace-out：resolve 后子孙校验 + 后缀白名单 {.out,.log}，越界/缺失/
  不可解析分别 400/404/422；不落库、不写 result_ref（§2.3 路径守卫）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import config
from ..errors import err, not_found
from ..engine import finalize
from ..parse import results as results_parse
from ..store import executions

_RESPONSE_BUDGET = 2 * 1024 * 1024  # 单端点响应预算（§2.3）
_OUT_SUFFIXES = (".out", ".log")


def _terminal_succeeded(execution_id: int) -> dict:
    """历史终态行且 succeeded（其余 409：非 succeeded 条目请求分析）。"""
    row = executions().get(execution_id)
    if row is None or row["state"] not in ("succeeded", "failed", "skipped"):
        raise not_found("history", execution_id)
    if row["state"] != "succeeded":
        raise err("ANALYSIS_UNAVAILABLE",
                  "非 succeeded 条目不可分析（仅正常结束进入解析管道）",
                  {"state": row["state"]}, http=409)
    return row


def _run_dir(execution_id: int) -> Path:
    return config.HOME_DIR / "run" / str(execution_id)


def _load_analysis(execution_id: int) -> dict:
    """读 analysis.json；缺失/损坏时惰性重建一次再读，仍无则 409。"""
    run_d = _run_dir(execution_id)
    path = run_d / finalize.ANALYSIS_NAME
    payload = _read_json(path)
    if payload is None:
        finalize.write_analysis(run_d)  # 补跑一次（幂等；失败留日志）
        payload = _read_json(path)
    if payload is None:
        raise err("ANALYSIS_UNAVAILABLE",
                  "analysis.json 缺失且重建失败（执行目录或输出不可得）",
                  {"execution_id": execution_id}, http=409)
    return payload


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _require_block(payload: dict, key: str) -> dict:
    """blocks 标志为 false 的块 422（数据不足）；块数据与标志不一致以
    标志为准（空形返回亦判不可用）。"""
    if not payload["result"]["blocks"].get(key):
        raise err("ANALYSIS_PARSE_FAILED",
                  "请求的分析块数据不足（该执行无此类数据）",
                  {"block": key,
                   "missing": payload["result"]["missing"]}, http=422)
    return payload[key]


def overview(execution_id: int) -> dict:
    """GET /history/{id}/analysis：Result 全集（含 degraded）。"""
    _terminal_succeeded(execution_id)
    return _load_analysis(execution_id)["result"]


def convergence(execution_id: int) -> dict:
    """GET /history/{id}/analysis/convergence：SCF 迹线+几何收敛+能量序列。"""
    _terminal_succeeded(execution_id)
    payload = _load_analysis(execution_id)
    return _fit_budget(_require_block(payload, "convergence"))


def frequencies(execution_id: int) -> dict:
    """GET /history/{id}/analysis/frequencies：频率表与红外强度。"""
    _terminal_succeeded(execution_id)
    return _require_block(_load_analysis(execution_id), "frequencies")


def orbitals(execution_id: int) -> dict:
    """GET /history/{id}/analysis/orbitals：轨道能量清单（不含系数）。"""
    _terminal_succeeded(execution_id)
    return _require_block(_load_analysis(execution_id), "orbitals")


# ---------------- workspace-out（工作区 .out/.log 只读分析） ----------------

def workspace_out(path_str: str) -> dict:
    """POST /analysis/workspace-out：四块合一负载（契约 WorkspaceOutAnalysis）。

    只读：绝不写工作区外（roadmap §2.4）；不落库、不写 result_ref。
    """
    target = _guarded_path(path_str)
    payload = results_parse.parse_output(
        target, timeout_s=results_parse.PARSE_TIMEOUT_S)
    result = payload["result"]
    if result["parse_error"] and result["parse_error"].startswith(
            results_parse.TIMEOUT_PREFIX):
        raise err("ANALYSIS_PARSE_FAILED", "解析超时",
                  {"path": path_str, "reason": "timeout",
                   "timeout_s": results_parse.PARSE_TIMEOUT_S}, http=422)
    if not any(result["blocks"].values()) and result["summary"]["natom"] == 0:
        raise err("ANALYSIS_PARSE_FAILED", "输出不可解析（无有效分析数据）",
                  {"path": path_str, "reason": "unparseable",
                   "parse_error": result["parse_error"]}, http=422)
    return {"overview": result,
            "convergence": payload["convergence"],
            "frequencies": payload["frequencies"],
            "orbitals": payload["orbitals"]}


def _guarded_path(path_str: str) -> Path:
    """路径守卫（§2.3）：resolve 后须为 workspace_root 子孙且后缀白名单。"""
    root = config.HOME_DIR.resolve()
    if not path_str or path_str.strip() in ("", "."):
        raise err("WORKSPACE_PATH_OUTSIDE", "路径为空",
                  {"path": path_str}, http=400)
    target = (config.HOME_DIR / path_str).resolve()
    if target != root and root not in target.parents:
        raise err("WORKSPACE_PATH_OUTSIDE", "路径越出工作区",
                  {"path": path_str}, http=400)
    if target.suffix.lower() not in _OUT_SUFFIXES:
        raise err("WORKSPACE_PATH_OUTSIDE",
                  "仅支持工作区内 .out/.log 输出文件",
                  {"path": path_str, "suffix": target.suffix}, http=400)
    if not target.is_file():
        raise not_found("workspace_file", path_str)
    return target


# ---------------- 收敛响应预算抽稀（§2.3） ----------------

def _fit_budget(conv: dict, budget: int = _RESPONSE_BUDGET) -> dict:
    """收敛负载超预算时按步均匀抽稀（scf/geo/energy 三序列同步保序，
    恒保留末点），置 downsampled=true。判据阈值数组极小、不抽。"""
    size = len(json.dumps(conv, ensure_ascii=False))
    if size <= budget:
        return conv
    steps = [len(conv.get(key) or [])
             for key in ("scf_trace", "geo_trace", "energy_series")]
    stride = 2
    while stride <= max(steps or [1]):
        thinned = {k: _thin(conv.get(k) or [], stride)
                   for k in ("scf_trace", "geo_trace", "energy_series")}
        cand = {**conv, **thinned, "downsampled": True}
        if len(json.dumps(cand, ensure_ascii=False)) <= budget:
            return cand
        stride *= 2
    return {**conv, "scf_trace": [], "geo_trace": [],
            "energy_series": (conv.get("energy_series") or [])[-1:],
            "downsampled": True}


def _thin(items: list, stride: int) -> list:
    """均匀抽稀：保序取 i%stride==0，恒保留末元素。"""
    if not items or stride <= 1:
        return items
    kept = [item for i, item in enumerate(items) if i % stride == 0]
    if items[-1] is not kept[-1]:
        kept.append(items[-1])
    return kept
