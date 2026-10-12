"""组合流服务（M4 B10，m4-plan §2.3/§4.7）：一键「构象搜索 + top N 精修」。

提交流程（POST /workflows/conformer-refinement，前置检查顺序固定）：
① crest 可执行探测（缺失 503 CREST_EXECUTABLE_MISSING，显式不静默）→
② 在途席位满员（409 PENDING_CAPACITY_FULL，整体拒绝零副作用——不建
workflow 记录、不生成 crest 任务）→ ③ 来源候选形态（422
WORKFLOW_STATE_INVALID）与 top_n ∈ [2,10]（422 VALIDATION_FAILED）→
④ 生成 crest 任务（候选分子说明节坐标引导的 xyz，程序化生成）入待执行
队列（单任务席位）+ 建 workflow 行（state=crest_running）。

crest 终态钩子链（幂等，席位释放前执行、crest 离席为链尾——自动提交的
满员判定发生在 crest 仍占席期间，在途席位计数含 crest 自身席位）：
提取（锚文件判重）→ 构象数边界（<2 记 failed）→ 建精修队列（成员数
N=min(top_n, 实际构象数)，workflow 行判重不重建）→ 自动提交（满员保留
unsubmitted + refine_queue_pending=true，state 停 refining）。

恢复语义（§2.3）：提取产物落盘锚文件 crest_ensemble.json 于 crest 执行
目录（重入先查锚跳过提取）；启动对账 reconcile_workflows 扫非终态
workflow 行与既有证据比对、按幂等钩子重推未完成一步、不重建已存在实体。
"""
from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

from .. import config
from ..engine import crest as crest_mod
from ..engine.crest import CrestExtractError
from ..errors import err, not_found
from ..parse.blocks import parse_input, verify_and_normalize
from ..store import executions, queues, seats, settings, tasks, workflows
from ..store.db import now_iso
from .candidates import default_inputs_dir, resolve_title
from .dependencies import validate_queue_members
from . import verify as verify_svc

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_workflow_id() -> str:
    """短随机组合流 id（同队列 id 规约：对照全库查重、永不复用）。"""
    while True:
        wid = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if workflows().get(wid) is None:
            return wid


def _crest_root() -> Path:
    return Path(str(settings().get("crest_root"))).expanduser()


def _extract_molecule_block(text: str) -> tuple[str, list[str]]:
    """候选输入 → (电荷/多重度行, 坐标行列表)。

    节定位规则与 parse/blocks.parse_input 同源（Link0→route→title→
    电荷/多重度→坐标行至终止空行）。"""
    lines = text.replace("\r\n", "\n").split("\n")
    n = len(lines)
    i = 0
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    while i < n and lines[i].lstrip().startswith("%"):
        i += 1
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    while i < n and lines[i].lstrip().startswith("#"):
        while i < n and lines[i].strip():
            i += 1
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    while i < n and lines[i].strip():  # title 节
        i += 1
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    charge_mult = lines[i].strip() if i < n else "0 1"
    i += 1
    coords: list[str] = []
    while i < n and lines[i].strip():
        ln = lines[i].strip()
        if ln and not ln.startswith("!"):
            coords.append(ln)
        i += 1
    return charge_mult, coords


def _xyz_guide(coords: list[str], formula: str | None) -> str:
    """crest 引导 xyz（程序化生成，非通用编辑器）。"""
    head = f"{formula or 'conformer search'} crest guide"
    return f"{len(coords)}\n{head}\n" + "\n".join(
        " ".join(ln.split()) for ln in coords) + "\n"


def _refine_input(route: str, link0: list[str] | None, charge_mult: str,
                  coords: list[str], title: str) -> str:
    """精修成员输入程序化生成（模板坐标替换——M4 程序化输入生成的唯一
    场景；重组空行规约经 verify_and_normalize，roadmap §2.7 沿用）。"""
    lines = [f"%{ln.lstrip('%')}" if not ln.lstrip().startswith("%") else ln
             for ln in (link0 or [])]
    lines += ["# " + route.lstrip("# ").strip() if not route.lstrip().startswith("#")
              else route, "", title, "", charge_mult]
    lines += [" ".join(ln.split()) for ln in coords]
    return "\n".join(lines) + "\n"


def submit_conformer_refinement(payload: dict) -> dict:
    """POST /workflows/conformer-refinement：受理即返回（crest 任务已入
    待执行队列）。返回动作清单供路由层发事件。"""
    candidate_id = payload.get("candidate_id")
    crest_cfg = payload.get("crest") or {}
    template = payload.get("template") or {}
    if not isinstance(candidate_id, int) or not isinstance(crest_cfg, dict) \
            or not isinstance(template, dict):
        raise err("VALIDATION_FAILED", "请求体形态不合法",
                  {"fields": ["candidate_id", "crest", "template"]}, http=422)
    top_n = crest_cfg.get("top_n")
    nproc = crest_cfg.get("nproc")
    if not isinstance(top_n, int) or isinstance(top_n, bool) \
            or not (2 <= top_n <= 10):
        raise err("VALIDATION_FAILED", "top_n 须为 2–10 整数",
                  {"field": "top_n", "actual": top_n}, http=422)
    if not isinstance(nproc, int) or isinstance(nproc, bool) or nproc < 1:
        raise err("VALIDATION_FAILED", "nproc 须为正整数",
                  {"field": "nproc", "actual": nproc}, http=422)
    route = template.get("route")
    link0 = template.get("link0")
    if not route or not isinstance(route, str):
        raise err("VALIDATION_FAILED", "template.route 必填",
                  {"field": "route"}, http=422)
    if link0 is not None and (not isinstance(link0, list)
                              or not all(isinstance(x, str) for x in link0)):
        raise err("VALIDATION_FAILED", "template.link0 须为字符串数组",
                  {"field": "link0"}, http=422)
    # ① 可执行探测（显式不静默）
    crest_bin = crest_mod.crest_executable(_crest_root())
    if not crest_bin.is_file():
        raise err("CREST_EXECUTABLE_MISSING",
                  "crest 可执行不可用（crest_root 定位缺失）",
                  {"crest_root": str(_crest_root()),
                   "expected": str(crest_bin)}, http=503)
    # ② 在途席位满员（整体拒绝零副作用）
    limit = int(settings().get("pending_seat_limit"))
    if seats().count() >= limit:
        raise err("PENDING_CAPACITY_FULL", "在途席位满员",
                  {"limit": limit}, http=409)
    # ③ 来源候选形态
    cand = tasks().get(candidate_id)
    if cand is None or cand["form"] != "candidate":
        raise err("WORKFLOW_STATE_INVALID",
                  "来源候选不可用（已提交/已删除或非候选形态）",
                  {"candidate_id": candidate_id,
                   "form": cand["form"] if cand else None}, http=422)
    try:
        cand_text = (default_inputs_dir() / str(candidate_id)).read_text(
            encoding="utf-8")
        charge_mult, coords = _extract_molecule_block(cand_text)
        formula = parse_input(cand_text)["blocks"]["molecule"]["formula"]
    except (OSError, UnicodeDecodeError):
        raise err("WORKFLOW_STATE_INVALID", "候选输入副本不可读",
                  {"candidate_id": candidate_id}, http=422)
    if len(coords) < 1:
        raise err("WORKFLOW_STATE_INVALID", "候选分子说明节无坐标",
                  {"candidate_id": candidate_id}, http=422)

    # ④ 生成 crest 任务 + 建 workflow 行 + 入待执行队列
    wid = new_workflow_id()
    crest_tid = tasks().create_seat_task(f"crest-{candidate_id}.xyz")
    (default_inputs_dir() / str(crest_tid)).write_text(
        _xyz_guide(coords, formula), encoding="utf-8")
    tasks().set_crest_binding(crest_tid, wid, nproc)
    save_template(wid, route, link0)
    workflows().create(wid, source_candidate_id=candidate_id, top_n=top_n)
    sid = seats().append(kind="task", task_id=crest_tid)
    return {"workflow_id": wid, "state": "crest_running",
            "crest_task_id": crest_tid, "seat_id": sid}


def on_crest_terminal(dispatcher, execution_row: dict, state: str) -> None:
    """crest 终态钩子（幂等；dispatcher 终态管线在席位释放前调用）。

    succeeded：提取 → 建精修队列 → 自动提交；failed：workflow 记
    failed（不生成精修队列）。钩子链尾由调用方继续既有终态管线
    （crest 离席）。"""
    wf_id = None
    try:
        tid = execution_row["task_id"]
        task = tasks().get(tid)
        wf_id = (task or {}).get("workflow_id")
        if not wf_id:
            return
        wf = workflows().get(wf_id)
        if wf is None or wf["state"] != "crest_running":
            return  # 幂等：已推进/已终态
        workflows().set_crest_execution(wf_id, execution_row["id"])
        if state != "succeeded":
            workflows().set_state(wf_id, "failed")  # crest 原文可查
            return
        run_d = dispatcher._run_root / str(execution_row["id"])
        # ① 提取（锚判重：重入先查锚跳过提取）
        anchor = run_d / crest_mod.ANCHOR_NAME
        if anchor.is_file():
            ensemble = json.loads(anchor.read_text(encoding="utf-8"))
        else:
            try:
                ensemble = crest_mod.extract_ensemble(run_d)
            except CrestExtractError as exc:
                print(f"[workflow] {wf_id} 提取失败：{exc}", file=sys.stderr)
                workflows().set_state(wf_id, "failed")
                return
            anchor.write_text(json.dumps(ensemble, ensure_ascii=False),
                              encoding="utf-8")
        # ② 构象数边界
        if ensemble["n"] < 2:
            print(f"[workflow] {wf_id} 构象数不足（{ensemble['n']} < 2）",
                  file=sys.stderr)
            workflows().set_state(wf_id, "failed")
            return
        # ③④ 建精修队列 + 自动提交（幂等：refine_queue_id 判重）
        _build_and_submit_refine_queue(dispatcher, wf, ensemble)
    except Exception as exc:  # noqa: BLE001 — 钩子异常不阻断终态管线
        print(f"[workflow] {wf_id} 终态钩子异常：{exc}", file=sys.stderr)


def _build_and_submit_refine_queue(dispatcher, wf: dict,
                                   ensemble: dict) -> None:
    wid = wf["workflow_id"]
    if wf.get("refine_queue_id"):
        return  # 幂等：队列已存在（重启重推不重建）
    top_n = int(wf.get("top_n") or 2)
    n = min(top_n, ensemble["n"])
    template = _workflow_template(wid)
    cand_text = _candidate_text(wf["source_candidate_id"])
    charge_mult, _ = _extract_molecule_block(cand_text)
    title = resolve_title(wf["source_candidate_id"]) or "conformer refinement"
    qid = "R" + "".join(secrets.choice(ALPHABET) for _ in range(5))
    while queues().get(qid) is not None:
        qid = "R" + "".join(secrets.choice(ALPHABET) for _ in range(5))
    queues().create(qid, name=f"精修 {wid}", skip_failed=False)
    member_ids: list[int] = []
    for pos, conf in enumerate(ensemble["conformers"][:n]):
        text = _refine_input(template["route"], template.get("link0"),
                             charge_mult, conf["coords"],
                             f"{title} #{pos + 1}")
        tid = tasks().create_candidate(f"refine-{pos + 1:02d}.gjf",
                                       "imported")
        (default_inputs_dir() / str(tid)).write_text(text, encoding="utf-8")
        verify_svc.verify_and_store(tid)  # 程序化输入必过既有核验（不绕行）
        tasks().enqueue(tid, qid, pos)
        member_ids.append(tid)
    validate_queue_members(member_ids)  # 与提交核验链同源（防御）
    workflows().set_refine_queue(wid, qid)
    dispatcher._emit("queues.changed", {"action": "created", "queue_id": qid})
    # ④ 自动提交（crest 仍占席：满员判定含 crest 自身席位）
    limit = int(settings().get("pending_seat_limit"))
    workflows().set_state(wid, "refining")
    if seats().count() >= limit:
        workflows().set_refine_pending(wid, True)  # 保留 unsubmitted 待手动
        print(f"[workflow] {wid} 精修队列 {qid} 席位满员未自动提交",
              file=sys.stderr)
        dispatcher._emit("queues.changed", {"action": "updated",
                                            "queue_id": qid})
        return
    for m in tasks().list_queue_members(qid):
        verify_svc.verify_and_store(m["id"])
    queues().set_state(qid, "submitted")
    seats().append(kind="queue", queue_id=qid)
    dispatcher._emit("queue.status", {"queue_id": qid,
                                      "from": "unsubmitted", "to": "submitted"})
    dispatcher._emit("pending.snapshot", None)


def _workflow_template(wid: str) -> dict:
    """精修模板取回（提交时随 workflow 行留存于 crest 任务输入旁注？——
    M4 简化：模板为组合流载荷、终态钩子建队时需要；落 workflow 行旁路
    存储会加列，此处从候选输入重建 route/title 框架不可行（模板 route
    是用户载荷）——提交时模板存工作区文件 workflows/<wid>.template.json。"""
    path = config.HOME_DIR / "workflows" / f"{wid}.template.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def save_template(wid: str, route: str, link0: list[str] | None) -> None:
    """组合流模板落盘（终态钩子建队取用；随执行产物保留）。"""
    d = config.HOME_DIR / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{wid}.template.json").write_text(
        json.dumps({"route": route, "link0": link0}, ensure_ascii=False),
        encoding="utf-8")


def _candidate_text(candidate_id: int) -> str:
    return (default_inputs_dir() / str(candidate_id)).read_text(
        encoding="utf-8")


def reconcile_workflows(dispatcher) -> int:
    """启动对账 workflow 扫描（§2.3 恢复语义）：非终态行与既有证据比对，
    按幂等钩子重推未完成一步、不重建已存在实体。返回重推行数。"""
    pushed = 0
    for wf in workflows().list_open():
        if wf["state"] == "refining":
            # 崩溃窗口收口：_settle_queue_seat 在「队列 completed → workflow
            # completed」两写之间中断时，重启据此补记（终态判据=精修队列
            # 成功，m4-plan §2.3）；队列回退/放弃/删除期间维持 refining
            qid = wf.get("refine_queue_id")
            q = queues().get(qid) if qid else None
            if q is not None and q["state"] == "completed":
                workflows().set_state(wf["workflow_id"], "completed")
                pushed += 1
            continue
        crest_eid = wf.get("crest_execution_id")
        if crest_eid:
            row = executions().get(crest_eid)
        else:
            # 钩子在 set_crest_execution 前中断：经 crest 任务行反查执行
            trows = tasks().list_by_workflow(wf["workflow_id"])
            row = None
            for t in trows:
                exs = executions().list_by_task(t["id"])
                if exs:
                    row = exs[-1]
                    break
        if row is None or row["state"] == "running":
            continue  # crest 尚未派发/仍在跑：引擎自然推进
        if row["state"] == "succeeded":
            on_crest_terminal(dispatcher, row, "succeeded")
            pushed += 1
        elif row["state"] in ("failed", "skipped"):
            on_crest_terminal(dispatcher, row, row["state"])
            pushed += 1
    return pushed
