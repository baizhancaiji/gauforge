"""断点续跑（M4 B9，m4-plan §2.2/§4.6）。

两段式：`POST /history/{id}/resume/preview`（无副作用、恒 200——
ineligible 以 eligible=false + reason 表达）→ 前端弹窗 →
`POST /history/{id}/resume`（确认；幂等重探，ineligible 422
RESUME_NOT_ELIGIBLE、满员 409 PENDING_CAPACITY_FULL）。

探针取数两条路径（与物化器同源，engine.materialize.execution_chk_asset）：
① chk_snapshot.location=protected 的保全 chk；② 无保全但该任务存在
成功执行记录者取最近成功执行的 input.chk；两者皆无 ⇒ ineligible
（no_resume_asset）。

注入矩阵（route 判定复用 M0 输入分块解析器取 route 节文本，token 化
大小写不敏感；§2.2 规则）：
- 含 Opt（一切变体，Opt+Freq 并存归优化行）→ 优化行：Link0 追加
  `%OldChk=@exec:<原执行id>` + route 的 opt 项改写为 `Opt=Restart`
  （原选项保留——G16 Opt=Restart 语义：整个 route 仅 Opt 关键字与其
  原选项 + Restart）；
- 不含 Opt 但含 Freq → freq 行：无注入、回落原样重跑（弹窗明示；
  经 resume 链路新建任务保留 resumed_from 关联）；
- 其余 → 单点行：Link0 追加 `%OldChk=@exec` + route 追加 `Guess=Read`；
- route 缺失/不可解析 → ineligible（unknown_kind）。

 ineligible 原因五态：no_resume_asset / chk_corrupted / probe_timeout /
unknown_kind / chained_ref（输入含 @task: 链内引用——注入前置检测，
先于 chk 资产判定）。任务身份：resume 新建任务（新 task id + 注入改写
后输入副本），两层关联——输入层 %OldChk=@exec 符号引用（物化链技术
关联，随 B7 派发钩子物化）+ 记录层 resumed_from（派发创建执行记录时
写入）；原历史条目数据零变更（「已续跑」经 resumed_by 派生只读）。
"""
from __future__ import annotations

import difflib

from pathlib import Path

from ..engine.materialize import execution_chk_asset, probe_chk
from ..errors import err, not_found
from ..parse.blocks import parse_input
from ..services.dependencies import (
    inputs_path,
    parse_link0_refs,
    validate_single_seat_input,
)
from ..store import executions, seats, settings, tasks
from ..store.db import now_iso
from .candidates import default_inputs_dir
from . import verify as verify_svc

_INELIGIBLE_REASONS = ("no_resume_asset", "chk_corrupted", "probe_timeout",
                       "unknown_kind", "chained_ref")


def _load_source_row(execution_id: int) -> dict:
    """续跑源历史条目（终态；入口=failed/skipped——§2.2 续跑=从断点恢复，
    succeeded 条目无断点、其重跑诉求由历史页「重新排队」承载，后端显式
    拒绝（404 无续跑入口）；skipped/归档条目不提供续跑入口——前端不展示
    动作，后端 preview 按无资产态处理、confirm 显式拒绝）。"""
    row = executions().get(execution_id)
    if row is None or row["state"] not in ("failed", "skipped"):
        raise not_found("history", execution_id)
    return row


def _source_text(row: dict) -> str:
    """原任务输入文本（任务输入副本，符号形式）。"""
    return inputs_path(row["task_id"]).read_text(encoding="utf-8",
                                                  errors="replace")


def _route_kind(text: str) -> str | None:
    """route 任务类型判定（§2.2）：opt / freq / scf / None（不可解析）。

    route 节经 parse_input 分块提取；token 化（= , 空格拆分）大小写
    不敏感匹配——Opt=Restart/opt freq/Freq=Read 等一切变体归并，
    NoFreq 不误判（token 精确等值）。"""
    try:
        parsed = parse_input(text)
    except Exception:  # noqa: BLE001 — 解析异常按类型不明处理
        return None
    route = (parsed.get("blocks") or {}).get("route") or ""
    tokens = set()
    for tok in route.lower().replace("=", " ").replace(",", " ").split():
        tokens.add(tok)
    if "opt" in tokens:
        return "opt"
    if "freq" in tokens:
        return "freq"
    if route.strip():
        return "scf"
    return None


def _opt_restart_token(tok: str) -> str:
    """opt 项改写保留原子选项（§2.2 注入矩阵「Opt=Restart + 原选项」）：

    opt → Opt=Restart；opt=X → Opt=(Restart,X)；opt=(a,b) →
    Opt=(Restart,a,b)。已含 Restart 项不重复注入（选项大小写不敏感
    比对）；裸括号形态 Opt(...) 与取值形态 opt=... 同视；括号残缺按
    裸 opt 处理（语义变化在弹窗 diff 可见）。"""
    inner = ""
    if "(" in tok and ")" in tok:
        inner = tok[tok.index("(") + 1:tok.rindex(")")]
    elif "=" in tok:
        inner = tok.partition("=")[2].strip()
    items = [s.strip() for s in inner.split(",") if s.strip()]
    if not any(s.lower() == "restart" for s in items):
        items.insert(0, "Restart")
    if items == ["Restart"]:
        return "Opt=Restart"
    return "Opt=(" + ",".join(items) + ")"


def _rewrite_route_line(route_line: str, kind: str) -> str:
    """route 行注入改写（优化行=opt 项改 Opt=Restart 并保留原选项；
    单点行=追加 Guess=Read；freq 行不改写）。"""
    if kind == "opt":
        tokens = route_line.split()
        out = []
        for tok in tokens:
            head = tok.lower().split("=", 1)[0].split("/", 1)[0]
            out.append(_opt_restart_token(tok) if head == "opt" else tok)
        return " ".join(out)
    if kind == "scf":
        stripped = route_line.rstrip()
        if "guess" in stripped.lower():
            return stripped
        return stripped + " Guess=Read"
    return route_line


def _apply_injections(text: str, kind: str, source_eid: int) -> tuple[
        str, list[dict]]:
    """按注入矩阵改写输入文本。返回 (改写后文本, 注入清单)。"""
    lines = text.replace("\r\n", "\n").split("\n")
    injections: list[dict] = []
    # Link0 区定位（与 workspace.resolve_link0 同规则）
    i, n = 0, len(lines)
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    start = i
    while i < n and lines[i].lstrip().startswith("%"):
        i += 1
    if kind in ("opt", "scf"):
        lines.insert(i, f"%OldChk=@exec:{source_eid}")
        injections.append({"type": "link0_append",
                           "link0_lines": [f"%OldChk=@exec:{source_eid}"],
                           "route_lines": None})
    # route 行改写：首条 # 开头行
    for j, ln in enumerate(lines):
        if ln.lstrip().startswith("#"):
            if kind == "opt":
                lines[j] = _rewrite_route_line(ln, "opt")
                injections.append({"type": "route_rewrite",
                                   "link0_lines": None,
                                   "route_lines": [lines[j]]})
            elif kind == "scf":
                lines[j] = _rewrite_route_line(ln, "scf")
                injections.append({"type": "route_append",
                                   "link0_lines": None,
                                   "route_lines": [lines[j]]})
            break
    return "\n".join(lines), injections


def _evaluate(row: dict, g16_root) -> dict:
    """续跑资格判定链（preview 与 confirm 幂等重探共用）。

    返回 {"eligible", "reason", "probe", "task_kind",
          "injections", "input_diff", "text"}（text 仅 eligible 时为
    注入改写后文本；ineligible 时为 None）。
    """
    result: dict = {"eligible": False, "reason": None, "probe": None,
                    "task_kind": None, "injections": None,
                    "input_diff": None, "text": None}
    if row.get("archived"):
        result["reason"] = "no_resume_asset"  # 归档封存：不提供续跑入口
        result["probe"] = {"formchk_ok": False, "reason": "archived"}
        return result
    try:
        text = _source_text(row)
    except OSError:
        result["reason"] = "no_resume_asset"
        return result
    # 注入前置检测（§3.3：链内引用先于 chk 资产判定）
    if any(r["kind"] == "task" for r in parse_link0_refs(text)):
        result["reason"] = "chained_ref"
        return result
    # 资产取数（两条路径：protected 保全 → 保留期 input.chk）
    chk = execution_chk_asset(row["id"])
    if chk is None:
        result["reason"] = "no_resume_asset"
        return result
    ok, reason = probe_chk(chk, g16_root)
    result["probe"] = {"formchk_ok": ok, "reason": reason}
    if not ok:
        result["reason"] = reason  # chk_corrupted / probe_timeout
        return result
    kind = _route_kind(text)
    result["task_kind"] = kind
    if kind is None:
        result["reason"] = "unknown_kind"
        return result
    new_text, injections = _apply_injections(text, kind, row["id"])
    diff = "\n".join(difflib.unified_diff(
        text.split("\n"), new_text.split("\n"),
        fromfile=f"run/{row['id']}/input", tofile="resume", lineterm=""))
    result.update({"eligible": True, "reason": None,
                   "injections": injections, "input_diff": diff,
                   "text": new_text})
    return result


def preview(execution_id: int) -> dict:
    """POST /history/{id}/resume/preview：无副作用、恒 200。"""
    row = _load_source_row(execution_id)
    g16_root = _g16_root()
    out = _evaluate(row, g16_root)
    return {"eligible": out["eligible"], "reason": out["reason"],
            "probe": out["probe"], "task_kind": out["task_kind"],
            "injections": out["injections"],
            "input_diff": out["input_diff"]}


def confirm(execution_id: int) -> dict:
    """POST /history/{id}/resume：幂等重探 → 新建任务入待执行队列。

    资产缺失或探针失败按 422 RESUME_NOT_ELIGIBLE（details 注明原因）；
    入队满员 409 PENDING_CAPACITY_FULL（与普通提交同待遇、不设特权
    通道）；freq 回落原样重跑同经本端点（保留 resumed_from 关联）。
    """
    row = _load_source_row(execution_id)
    g16_root = _g16_root()
    out = _evaluate(row, g16_root)
    if not out["eligible"]:
        raise err("RESUME_NOT_ELIGIBLE", "该条目不可从断点续跑",
                  {"reason": out["reason"]}, http=422)
    limit = int(settings().get("pending_seat_limit"))
    if seats().count() >= limit:
        raise err("PENDING_CAPACITY_FULL", "在途席位满员",
                  {"limit": limit}, http=409)
    # 新建任务：输入副本 = 注入改写后文本（新 task id，不经候选）；
    # 任务级续跑关联（派发建行时转移到执行记录 resumed_from）
    new_tid = tasks().create_seat_task(
        row["filename"],
        resume_of={"task_id": row["task_id"], "execution_id": row["id"]})
    path = default_inputs_dir() / str(new_tid)
    path.write_text(out["text"], encoding="utf-8")
    # 既有提交核验链（规范化 + B6 载体校验：@exec 三点已被 _evaluate
    # 重探保证，此处对改写文本再过解析校验）
    verify_svc.verify_and_store(new_tid)
    validate_single_seat_input(new_tid)
    sid = seats().append(kind="task", task_id=new_tid)
    return {"task_id": new_tid, "seat_id": sid,
            "execution_id": row["id"], "task_kind": out["task_kind"]}


def _g16_root() -> Path:
    return Path(str(settings().get("g16_root"))).expanduser()
