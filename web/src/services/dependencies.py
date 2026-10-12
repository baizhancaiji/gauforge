"""Link0 符号引用解析与依赖 DAG 静态校验（M4 B6，m4-plan §2.1）。

依赖单一真相：成员依赖由其 Link0 `%Chk=`/`%OldChk=` 的符号引用**自动推导**
（引用即依赖），无独立 depends_on 字段。文法两形态（A4 契约定稿）：

- `@task:<id>` —— 同队列成员任务 id（`%Chk=` 续用与 `%OldChk=` 只读接续
  两形态均产生对 `<id>` 的依赖边）；限定队列成员间使用，单任务席位载体
  （行内提交/历史重新排队）一律拒绝。
- `@exec:<eid>` —— 断点续跑专用，指向单条终态执行的历史 chk 资产、不受
  同队列限制；仅由 resume 动作生成的新任务携带，队列成员载体拒绝。

校验时机（全部在写操作事务内、先于席位创建）：
- 队列创建 / PATCH（member_ids 变更）/ 队列提交：validate_queue_members
  —— crest 不入队、@exec 载体拒绝、移除被依赖成员拒绝、可达、无环、
  溯源 chk 存在性；
- 行内提交 / 历史重新排队（单任务席位）：validate_single_seat_input
  —— @task: 拒绝、@exec 三点校验（存在/终态/chk 溯源）。

错误码（契约全集）：DEPENDENCY_CYCLE / DEPENDENCY_UNREACHABLE /
CHK_SOURCE_MISSING / INVALID_MEMBERS（crest 组队复用）。
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from ..errors import err
from ..store import executions, tasks
from .candidates import default_inputs_dir

_TERMINAL = ("succeeded", "failed", "skipped")
_EXEC_UNITS = {"s": "执行", "t": "任务"}

# Link0 关键字 → 引用载体（大小写不敏感；与 workspace.resolve_link0 同
# 解析规则：前导空行/!注释后的连续 % 行，其后无空行要求）
_REF_KEYS = {"chk": "chk", "oldchk": "oldchk"}


def inputs_path(task_id: int) -> Path:
    return default_inputs_dir() / str(task_id)


def parse_link0_refs(text: str) -> list[dict]:
    """解析 Link0 区符号引用。

    返回 [{"line": 行号(1 起), "keyword": "chk|oldchk",
           "kind": "task|exec|malformed", "target": int|None, "raw": 原值}]。
    非符号值（普通路径）不产生条目；`@` 开头但文法不完整（缺形态前缀、
    目标非正整数）记 kind=malformed——校验层按不可达拒绝（文法残缺
    即引用不可达语义，不另设码）。
    """
    lines = text.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    refs: list[dict] = []
    while i < n and lines[i].lstrip().startswith("%"):
        body = lines[i].strip().lstrip("%")
        key, _, val = body.partition("=")
        kind_key = _REF_KEYS.get(key.strip().casefold())
        raw = val.strip()
        if kind_key and raw.startswith("@"):
            ref: dict = {"line": i + 1, "keyword": kind_key,
                         "kind": "malformed", "target": None, "raw": raw}
            form, _, num = raw[1:].partition(":")
            form = form.strip().casefold()
            if form in ("task", "exec") and num.strip().isdigit() \
                    and int(num) > 0:
                ref["kind"] = form
                ref["target"] = int(num)
            refs.append(ref)
        i += 1
    return refs


def run_dir(execution_id: int) -> Path:
    return Path(config.HOME_DIR) / "run" / str(execution_id)


def latest_succeeded(task_id: int) -> dict | None:
    """任务最近一次成功执行（chk 溯源单一真相，m4-plan §2.1：

    @task:X 的 chk 来源 = X 最近一次 succeeded 执行的 run/<eid>/input.chk；
    B7 物化器与静态校验共用本定位。哈希跳过沿用的执行即该次成功执行
    （派发时哈希匹配项；静态校验时点以最近成功执行为溯源判定对象）。
    """
    exs = [e for e in executions().list_by_task(task_id)
           if e["state"] == "succeeded"]
    return exs[-1] if exs else None


def execution_chk_asset(execution_id: int) -> Path | None:
    """执行条目的 chk 资产定位（B9 续跑取数两条路径的公共判据）：

    ① 保全 chk：run/<eid>/protected/ 下任意 .chk（非正常终止保全）；
    ② 正常执行 chk：run/<eid>/input.chk（M1 清理边界保留期内）。
    两处皆无 → None（无续跑/溯源资产）。
    """
    d = run_dir(execution_id)
    prot = d / "protected"
    if prot.is_dir():
        for f in sorted(prot.iterdir()):
            if f.is_file() and f.suffix.casefold() == ".chk":
                return f
    top = d / "input.chk"
    return top if top.is_file() else None


def _err_unreachable(message: str, details: dict) -> None:
    raise err("DEPENDENCY_UNREACHABLE", message, details, http=422)


def _validate_exec_ref(ref: dict, task_id: int) -> None:
    """@exec 三点校验：执行存在、已终态、chk 溯源存在（§2.1 载体约束）。"""
    eid = ref["target"]
    row = executions().get(eid)
    if row is None or row["state"] not in _TERMINAL:
        _err_unreachable(
            f"@exec:{eid} 引用的执行不存在或未到终态",
            {"task_id": task_id, "line": ref["line"],
             "ref": f"@exec:{eid}"})
    if execution_chk_asset(eid) is None:
        raise err("CHK_SOURCE_MISSING",
                  f"@exec:{eid} 引用的执行无 chk 资产（已清理或从未产生）",
                  {"task_id": task_id, "line": ref["line"],
                   "execution_id": eid}, http=422)


def validate_single_seat_input(task_id: int) -> None:
    """单任务席位载体校验（行内提交 / 历史重新排队，§2.1）。

    @task: 一律拒绝（限队列成员间——原输入含引用者经「重新排队」将被此
    校验拒绝，引导先重建队列）；@exec 须过三点校验（resume 新建任务经
    此载体入队）。
    """
    try:
        text = inputs_path(task_id).read_text(encoding="utf-8",
                                               errors="replace")
    except OSError:
        return  # 输入不可读由提交核验链（verify_and_store）先行拒绝
    for ref in parse_link0_refs(text):
        if ref["kind"] == "task" or ref["kind"] == "malformed":
            _err_unreachable(
                "符号引用 @task:<id> 限队列成员间使用，单任务载体不支持"
                "（请组建队列提交）",
                {"task_id": task_id, "line": ref["line"], "ref": ref["raw"]})
        _validate_exec_ref(ref, task_id)


def _member_refs(member_ids: list[int]) -> dict[int, list[dict]]:
    """逐成员解析输入符号引用（输入不可读按无引用——提交路径由核验链
    拒绝；创建/PATCH 载体不在此重复核验结构）。"""
    out: dict[int, list[dict]] = {}
    for tid in member_ids:
        try:
            text = inputs_path(tid).read_text(encoding="utf-8",
                                               errors="replace")
        except OSError:
            text = ""
        out[tid] = parse_link0_refs(text)
    return out


def member_dependencies(member_ids: list[int]) -> dict[int, list[int]]:
    """成员 → 直接前驱集合（@task: 引用推导，不校验合法性；B8 窗口守卫
    与失败联动传递的数据源）。malformed/指向成员集之外的目标不计入
    （合法性问题由校验函数负责）。"""
    deps: dict[int, list[int]] = {}
    for tid, refs in _member_refs(member_ids).items():
        deps[tid] = sorted({r["target"] for r in refs
                            if r["kind"] == "task"
                            and r["target"] in member_ids})
    return deps


def validate_queue_members(member_ids: list[int], *,
                           removed_ids: list[int] | None = None) -> None:
    """队列成员集 DAG 静态校验（创建 / PATCH / 提交三时点共用）。

    ① crest 任务不入队（422 INVALID_MEMBERS，details 注明 crest 任务
    不可组队）；② 队列成员携带 @exec / 文法残缺引用拒绝（@exec 为
    resume 专用，不入队载体）；③ PATCH 移除被依赖成员拒绝（details
    注明被谁依赖，提示先解除下游引用）；④ 可达——@task:id 须为本成员集
    现存成员（跨队列/悬引用/自引用同码 DEPENDENCY_UNREACHABLE）；
    ⑤ 依赖图无环（含自环，DEPENDENCY_CYCLE，details 携带环路径）；
    ⑥ 溯源 chk 存在性——上游已有成功执行但其 chk 已被清理 →
    CHK_SOURCE_MISSING（details 注明缺失的执行 id，提示重跑上游恢复）。
    """
    rows = {t["id"]: t for t in (tasks().get(t) for t in member_ids)
            if t is not None}
    # ① crest 不入队
    crest = [tid for tid in member_ids
             if rows.get(tid, {}).get("kind", "g16") == "crest"]
    if crest:
        raise err("INVALID_MEMBERS",
                  "crest 任务不可组队（组合流 crest 恒单任务席位）",
                  {"task_ids": crest}, http=422)
    refs_by = _member_refs(member_ids)
    # ② 载体与文法：队列成员禁 @exec；malformed 按不可达
    for tid, refs in refs_by.items():
        for ref in refs:
            if ref["kind"] == "exec":
                _err_unreachable(
                    "@exec:<执行id> 为断点续跑专用文法，不可入队",
                    {"task_id": tid, "line": ref["line"],
                     "ref": ref["raw"]})
            if ref["kind"] == "malformed":
                _err_unreachable(
                    f"符号引用文法不完整：{ref['raw']}",
                    {"task_id": tid, "line": ref["line"], "ref": ref["raw"]})
    member_set = set(member_ids)
    # ③ 移除被依赖成员（PATCH 场景）
    if removed_ids:
        removed_set = set(removed_ids)
        for tid, refs in refs_by.items():
            if tid in removed_set:
                continue
            hit = sorted({r["target"] for r in refs
                          if r["kind"] == "task"
                          and r["target"] in removed_set})
            if hit:
                _err_unreachable(
                    "成员被下游依赖，不可移除（先解除下游引用再操作）",
                    {"removed": sorted(removed_set),
                     "depended_by": tid, "targets": hit})
    # ④ 可达 + ⑤ 无环（邻接表仅收合法 task 引用；自引用=自环归 CYCLE）
    deps: dict[int, list[int]] = {}
    for tid, refs in refs_by.items():
        edges: list[int] = []
        for ref in refs:
            if ref["kind"] != "task":
                continue
            if ref["target"] == tid:
                raise err("DEPENDENCY_CYCLE", "任务链依赖成环（自引用）",
                          {"cycle": [tid, tid]}, http=422)
            if ref["target"] not in member_set:
                _err_unreachable(
                    f"@task:{ref['target']} 不是本队列现存成员"
                    "（跨队列引用或引用已移除成员）",
                    {"task_id": tid, "line": ref["line"],
                     "ref": f"@task:{ref['target']}"})
            edges.append(ref["target"])
        deps[tid] = edges
    _assert_acyclic(deps)
    # ⑥ 溯源 chk 存在性（§2.1：上游无成功执行=依赖满足时必然有产出，
    # 放行；已有成功执行但 chk 已清理 → 明知物化必败的提交拒绝）
    for tid in member_ids:
        for ref in refs_by[tid]:
            if ref["kind"] != "task":
                continue
            src = latest_succeeded(ref["target"])
            if src is not None and (run_dir(src["id"]) / "input.chk") \
                    .is_file() is False:
                raise err(
                    "CHK_SOURCE_MISSING",
                    f"上游任务 {ref['target']} 最近成功执行（#{src['id']}）"
                    "的 chk 已被清理，物化必然失败（重跑上游恢复 chk 来源）",
                    {"task_id": tid, "line": ref["line"],
                     "upstream_task_id": ref["target"],
                     "execution_id": src["id"]}, http=422)


def _assert_acyclic(deps: dict[int, list[int]]) -> None:
    """依赖图无环判定（DFS 三色）；成环 422 DEPENDENCY_CYCLE，
    details 携带环路径成员序列。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in deps}
    stack: list[int] = []

    def visit(tid: int) -> None:
        color[tid] = GRAY
        stack.append(tid)
        for nxt in deps.get(tid, []):
            if color.get(nxt, BLACK) == GRAY:
                cycle = stack[stack.index(nxt):] + [nxt]
                raise err("DEPENDENCY_CYCLE",
                          "任务链依赖成环：" + "→".join(
                              f"#{t}" for t in cycle),
                          {"cycle": cycle}, http=422)
            if color.get(nxt, BLACK) == WHITE:
                visit(nxt)
        stack.pop()
        color[tid] = BLACK

    for tid in deps:
        if color[tid] == WHITE:
            visit(tid)
