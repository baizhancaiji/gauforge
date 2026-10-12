"""能量表汇总与聚合（M4 B11，m4-plan §2.3/§4.8）。

- 队列端点（GET /queues/{id}/energy-summary）：队列成员恒 g16（crest 不
  入队），每行取 B1 解析（run/<eid>/analysis.json）末次 SCF 双单位能量；
- workflow 聚合（GET /workflows/{id} 的 energy_summary）：crest 行
  （ensemble 最低构象能量，source=ensemble）+ 精修队列 g16 行跨容器
  后端聚合（前端不拼两段数据）；精修队列被放弃/删除时队列行按缺失成员
  处理、crest 结果仍可查（workflow 停留 refining）；
- relative_kJ_mol 零点 = **该查询范围内最低能量**：部分完成态新增更低
  能量行时已展示行随零点整体改写——接受该漂移（语义自洽，前端对相对列
  标注「随完成进度重算」）；无能量行 relative 为 null；
- hartree→eV 换算与 B1 同源（cclib convertor，parse/results._eV_to_hartree
  的逆换算）；hartree→kJ/mol 换算单点 = engine.crest.HARTREE_KJ_MOL
  （1 Eh = 2625.4996 kJ/mol，单测断言物理基准）。
"""
from __future__ import annotations

import json
from pathlib import Path

from ..engine.crest import HARTREE_KJ_MOL
from ..parse.results import _eV_to_hartree
from ..store import executions, queues, tasks, workflows
from .candidates import resolve_title
from .dependencies import run_dir

ANALYSIS_NAME = "analysis.json"


def _hartree_to_eV(value_h: float) -> float:
    """hartree → eV（B1 cclib convertor 同源逆换算：value_h /
    _eV_to_hartree(1.0)）。"""
    return value_h / _eV_to_hartree(1.0)


def _latest_analysis(task_id: int) -> tuple[dict | None, dict | None]:
    """任务最近成功执行的解析概览（analysis.json summary）与其执行行。

    无 succeeded 执行 / 解析缺失 → (None, 最近终态执行行或 None)。"""
    exs = executions().list_by_task(task_id)
    latest = exs[-1] if exs else None
    for e in reversed([e for e in exs if e["state"] == "succeeded"]):
        path = run_dir(e["id"]) / ANALYSIS_NAME
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            return data, e
    return None, latest


def _g16_row(task_row: dict) -> dict:
    """g16 成员能量行（B1 解析末次 SCF，hartree/eV 双单位同源）。"""
    analysis, latest = _latest_analysis(task_row["id"])
    summary = (analysis or {}).get("summary") or {}
    state = latest["state"] if latest else "staged"
    eh = summary.get("scf_energy_hartree")
    # eV 透传 B1 双单位原值（与解析层同源，不二次换算）；kJ/mol 由
    # HARTREE_KJ_MOL 单点计算（B11 单位换算单点）
    row = {"task_id": task_row["id"], "kind": "g16", "state": state,
           "method": summary.get("method"),
           "energy_hartree": eh,
           "energy_eV": summary.get("scf_energy_eV"),
           "relative_kJ_mol": None,
           "source": "analysis" if eh is not None else "none"}
    return row


def _crest_row(wf: dict) -> dict | None:
    """crest 能量行（ensemble 最低构象代表；source=ensemble）。

    锚文件缺失回落 crest_conformers.xyz 提取；产物缺失（crest 失败/
    构象数不足）返回 None（行缺席，workflow 状态本身承载失败语义）。"""
    crest_eid = wf.get("crest_execution_id")
    if not crest_eid:
        return None
    run_d = run_dir(crest_eid)
    ensemble = None
    anchor = run_d / "crest_ensemble.json"
    if anchor.is_file():
        try:
            ensemble = json.loads(anchor.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ensemble = None
    if ensemble is None:
        from ..engine.crest import extract_ensemble
        try:
            ensemble = extract_ensemble(run_d)
        except Exception:  # noqa: BLE001 — 产物缺失行缺席，不炸端点
            return None
    conformers = ensemble.get("conformers") or []
    if not conformers:
        return None
    best = min(conformers, key=lambda c: c["energy_hartree"])
    eh = float(best["energy_hartree"])
    execution = executions().get(crest_eid)
    return {"task_id": (executions().get(crest_eid) or {}).get("task_id"),
            "kind": "crest",
            "state": execution["state"] if execution else "failed",
            "method": None,
            "energy_hartree": eh, "energy_eV": _hartree_to_eV(eh),
            "relative_kJ_mol": None, "source": "ensemble"}


def _apply_zero_point(rows: list[dict]) -> list[dict]:
    """零点计算：该查询范围内最低能量 → relative_kJ_mol（最低行=0）。

    部分完成态零点随行集重算（B11 断言：零点恒为当前行集最低值）。"""
    values = [r["energy_hartree"] for r in rows
              if r.get("energy_hartree") is not None]
    if not values:
        return rows
    emin = min(values)
    for r in rows:
        if r.get("energy_hartree") is not None:
            r["relative_kJ_mol"] = round(
                (r["energy_hartree"] - emin) * HARTREE_KJ_MOL, 6)
    return rows


def queue_energy_summary(queue_id: str) -> dict:
    """GET /queues/{id}/energy-summary：队列维度能量表（成员恒 g16）。"""
    q = queues().get(queue_id)
    if q is None:
        from ..errors import not_found
        raise not_found("queue", queue_id)
    rows = [_g16_row(t) for t in tasks().list_queue_members(queue_id)]
    return {"rows": _apply_zero_point(rows)}


def workflow_energy_summary(wf: dict) -> dict:
    """workflow energy_summary 跨容器聚合：crest 行 + 精修队列 g16 行。

    精修队列缺失/被删除/放弃 → 仅 crest 行（crest 结果仍可查）。"""
    rows: list[dict] = []
    crest = _crest_row(wf)
    if crest is not None:
        rows.append(crest)
    qid = wf.get("refine_queue_id")
    if qid and queues().get(qid) is not None:
        rows += [_g16_row(t) for t in tasks().list_queue_members(qid)]
    return {"rows": _apply_zero_point(rows)}


def workflow_view(row: dict) -> dict:
    """契约 Workflow 视图（单点与列表项同形；energy_summary 后端聚合）。"""
    data = dict(row)
    data["energy_summary"] = workflow_energy_summary(row)
    return data
