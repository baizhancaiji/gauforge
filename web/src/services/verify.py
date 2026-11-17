"""提交前输入核验（M2 B6，m2-plan §2.5；3.8.0 工具箱 B14 增 testrt 步）。

所有进入待执行队列的提交动作（行内提交 / 队列提交与直接提交 / 历史重新
排队）统一在提交事务内、建席位之前调用：核验通过且规范化有变化时原子写
回 inputs/<id>（此后派发、哈希、历史输入均以规范副本为准），失败不写盘。

B14 testrt 权威校验（toolbox-plan §2.3）：结构解析校验之后、规范化写回
之前（testrt 只见单步输入——多步已被 422 INPUT_MULTISTEP_UNSUPPORTED
拒绝），校验顺序 = 结构 → route 语法 → 落盘。三支判定：退出 0 通过；
非 0 + QPErr 锚点 → 422 ROUTE_SYNTAX_INVALID（message 以「route 语法
错误：」起始并入报错原文首段截 300 字符，details.route_errors 截 2000
字符 + exit_code——前端只渲染 error.message，并入后拼错关键词与出错
位置在既有提示位直接可见）；其余（可执行缺失 / OSError 启动失败 / 非
零退出无 QPErr / 超时 / @file 包含形态）→ fail-open 降级，warnings 通道
追加非阻断黄警 route_check_skipped（显式不静默——降级可见，五类原因
中文短语内嵌为断言锚点）。送检预处理：引号感知截断行内 ! 注释（! 行内
注释与 @file 是 M2 认定的官方合法形态，testrt 实测 134 + QPErr——不截
断/不分流则合法输入被 422 误拒，§0.5 实测）+ 多行合并单行（A6 核验项 1
实测 testrt 接受合并单行）+ @file/@file/N 分流（不调 testrt，探测前完
成）。调用范式：独立临时目录（testrt 报错即 SIGABRT + core dump 落
cwd——临时目录隔离为硬约束，§9 风险 1）+ g16_env + 列表参数 + 120s
超时。与 B3 拼写警分层互补：离线黄警先行（编辑期实时反馈）、testrt
提交时权威阻断（派发前拦截），语义互不替代。
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from ..errors import ApiError, err, not_found
from ..engine.workspace import g16_env, resolve_link0
from ..parse.blocks import parse_input, split_lines, verify_and_normalize
from ..parse.keywords import tokenize_route
from ..parse.link0_rules import PER_CORE_MEM_GB_FLOOR
from ..store import settings
from .candidates import default_inputs_dir, file_warnings

log = logging.getLogger(__name__)

ROUTE_CHECK_TIMEOUT_S = 120
_QPERR_ANCHOR = "QPErr"
_QPERR_MESSAGE_SPAN = 300   # message 并入报错原文首段截断（§2.3）
_ROUTE_ERRORS_SPAN = 2000   # details.route_errors 原文截断（§2.3）

# 降级五类原因（中文短语内嵌 message、作断言锚点，不透出内部枚举值）
_REASON_UNAVAILABLE = "testrt 工具缺失"
_REASON_STARTUP = "调用失败"
_REASON_TIMEOUT = "校验超时"
_REASON_ABNORMAL = "异常退出"
_REASON_INCLUDE = "包含文件写法"

_REASON_NOTES = {
    _REASON_INCLUDE: "route 含 @file 包含文件写法（官方合法形态，testrt "
                     "不支持该形态），按既有离线拼写检查放行",
    _REASON_UNAVAILABLE: "g16_root 下未探测到 testrt 可执行（发行不完整），"
                         "按既有离线拼写检查放行",
    _REASON_STARTUP: "testrt 进程启动失败，按既有离线拼写检查放行",
    _REASON_TIMEOUT: f"testrt 校验超时（>{ROUTE_CHECK_TIMEOUT_S}s），"
                     "按既有离线拼写检查放行",
    _REASON_ABNORMAL: "testrt 异常退出且无语法报错输出，"
                      "按既有离线拼写检查放行",
}


def _mask(blocks: dict) -> dict:
    """结构自证掩码：附加节 terminator_blank 由空行规约统一置 True。"""
    masked = {**blocks,
              "additional_sections": [dict(s, terminator_blank=True)
                                      for s in blocks["additional_sections"]]}
    return masked


def _testrt_path() -> Path:
    """testrt 可执行定位（<g16_root>/testrt）。

    独立函数缝：conftest 受控注入点（B14——全部提交路径用例经此缝指向
    假 testrt，测试一律不真调 ~/g16）。"""
    root = Path(str(settings().get("g16_root"))).expanduser()
    return root / "testrt"


def _strip_inline_comments(route_text: str) -> str:
    """引号感知截断行内 ! 注释并合并单行：逐行扫描，双/单引号外首个
    `!` 起截断（引号内 ! 保留——External="RunTink Amber" 不拆词，A6
    核验项 1 实测引号值原样送检 exit 0）；非空行 strip 后单空格连接
    （多行合并单行，testrt 接受——核验项 1 实测留痕）。"""
    out: list[str] = []
    for raw in route_text.splitlines():
        buf: list[str] = []
        quote: str | None = None
        for ch in raw:
            if quote is not None:
                buf.append(ch)
                if ch == quote:
                    quote = None
            elif ch in ("\"", "'"):
                quote = ch
                buf.append(ch)
            elif ch == "!":
                break  # 行内注释起点（引号外）
            else:
                buf.append(ch)
        line = "".join(buf).strip()
        if line:
            out.append(line)
    return " ".join(out)


def _route_skipped_warning(line: int, reason: str,
                           task_id: int | None = None) -> dict:
    """降级黄警构造器（纯函数，B14）——warnings 通道 route_check_skipped，
    Warning schema 形状零变更（required [line, keyword, kind, message]）。
    message 以「route 语法校验跳过（<原因>）：」起始接中文说明（不透出
    内部枚举值）；line = route 节起始行号（route 缺失已先走 parse_errors
    422，恒可得）。"""
    return {"line": line, "keyword": "", "kind": "route_check_skipped",
            "message": f"route 语法校验跳过（{reason}）："
                       f"{_REASON_NOTES[reason]}",
            **({"task_id": task_id} if task_id is not None else {})}


def _check_route(route_text: str, route_line: int,
                 task_id: int) -> list[dict]:
    """testrt 权威校验（B14 三支判定）。返回降级支追加的 warnings
    （阻断支直接 raise 422）；fail-open 恒不阻断提交。"""
    single = _strip_inline_comments(route_text)
    # @file / @file/N 包含形态分流：官方合法形态（test_block_save.py
    # 零警断言）实测 testrt 134 + QPErr——不调 testrt、探测前完成
    if any(tok.startswith("@") for _, tok in tokenize_route(single)):
        return [_route_skipped_warning(route_line, _REASON_INCLUDE, task_id)]
    testrt = _testrt_path()
    if not (testrt.is_file() and os.access(testrt, os.X_OK)):
        return [_route_skipped_warning(route_line, _REASON_UNAVAILABLE,
                                       task_id)]
    with tempfile.TemporaryDirectory(prefix="hq-testrt-") as td:
        try:
            proc = subprocess.run(
                [str(testrt), single], cwd=td,
                env=g16_env(Path(str(settings().get("g16_root")))
                            .expanduser(), Path(td)),
                capture_output=True, timeout=ROUTE_CHECK_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return [_route_skipped_warning(route_line, _REASON_TIMEOUT,
                                           task_id)]
        except OSError:
            return [_route_skipped_warning(route_line, _REASON_STARTUP,
                                           task_id)]
    stdout = proc.stdout.decode(errors="replace")
    if proc.returncode == 0:
        return []  # 支 1：通过（不回显 link 展开序列——对用户无操作价值）
    if _QPERR_ANCHOR in stdout:  # 支 2：route 语法错，派发前权威阻断
        idx = stdout.find(_QPERR_ANCHOR)
        first = " ".join(stdout[idx:].split())[:_QPERR_MESSAGE_SPAN]
        raise err("ROUTE_SYNTAX_INVALID",
                  f"route 语法错误：{first}",
                  {"task_id": task_id,
                   "route_errors": stdout[:_ROUTE_ERRORS_SPAN],
                   "exit_code": proc.returncode}, http=422)
    # 支 3：非零退出但无 QPErr（异常终止形态）→ fail-open 降级
    return [_route_skipped_warning(route_line, _REASON_ABNORMAL, task_id)]


def _route_start_line(lines: list[str]) -> int:
    """route 节起始行号（1 起；首个 # 起始行——route 缺失已先走
    parse_errors 422，恒可得）。"""
    for i, ln in enumerate(lines, start=1):
        if ln.lstrip().startswith("#"):
            return i
    return 1  # 防御（不可达：parse_errors 已拦 route 缺失）


# ---------------- 每核内存下限黄警（3.8.0 工具箱 B16，§2.4） ----------------

def _mem_floor_warning(line: int, mem_gb: float, cores: int,
                       task_id: int | None = None) -> dict:
    """每核内存下限黄警构造器（纯函数，B16）——warnings 通道
    mem_below_per_core_floor（与组合流模板保存闸错误 reason 同名——
    同一规则两域承载；组合流保存闸阻断、提交链非阻断黄警）。Warning
    schema 必填字段钉死：keyword="%mem"、line = %mem 声明行绝对行号
    （无 %mem 声明取 Link0 区首行，无 Link0 取 1——避免 line=0 前端
    渲染 L0）。message 携带核算内存值/核数/下限并指引工具箱 freqmem
    精确校验入口。"""
    return {"line": line, "keyword": "%mem",
            "kind": "mem_below_per_core_floor",
            "message": f"每核内存低于下限：声明 {mem_gb:g}GB / {cores} 核"
                       f"（下限 {cores * PER_CORE_MEM_GB_FLOOR:g}GB/核，"
                       f"按每线程需求合计）。提交不阻断；freq 任务精确"
                       f"内存需求请用工具箱 freqmem 校验",
            **({"task_id": task_id} if task_id is not None else {})}


def _mem_decl_line(lines: list[str]) -> int:
    """%mem 声明行绝对行号（1 起）；无 %mem 声明取 Link0 区首行，
    无 Link0 取 1（§2.4 必填字段钉死口径）。"""
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1  # 前导空行跳过（Link0 区起点）
    if start >= len(lines) or not lines[start].lstrip().startswith("%"):
        return 1  # 无 Link0
    for i in range(start, len(lines)):
        if not lines[i].lstrip().startswith("%"):
            break  # Link0 区结束
        if lines[i].strip().casefold().startswith("%mem="):
            return i + 1
    return start + 1  # Link0 区首行（无 %mem 声明）


def _check_mem_floor(text: str, task_id: int) -> list[dict]:
    """提交链每核内存下限黄警（B16）：resolve_link0 记账值（声明优先、
    缺省回落——与 dispatcher 注入实况一致）做纯算术校验，mem × 核数
    失衡即追加非阻断黄警（fail-open 恒不阻断）。相等不触发（严格小于）。
    纯算术零子进程零 g16 依赖（hermetic，§9——g16_root 空目录不影响
    触发）。"""
    resolved = resolve_link0(text,
                             int(settings().get("link0_default_nproc")),
                             float(settings().get("link0_default_mem_gb")))
    mem_gb = float(resolved["mem_gb"]["value"])
    cores = int(resolved["nproc"]["value"])
    if cores <= 0 or mem_gb >= cores * PER_CORE_MEM_GB_FLOOR:
        return []  # 相等不触发（严格小于）；防御 cores 非正
    return [_mem_floor_warning(_mem_decl_line(split_lines(text)),
                               mem_gb, cores, task_id)]


def verify_and_store(task_id: int) -> dict:
    """对 inputs/<id> 执行提交前核验（G1 改造），返回
    {"normalized": bool, "warnings": list}。

    ①② 规范化有变化 → 原子写回；③ 解析失败 → 422 INPUT_PARSE_FAILED；
    ④ 多步 → 422 INPUT_MULTISTEP_UNSUPPORTED；规范化致结构变化 →
    500 拒绝（不落盘，m2-plan §9 风险 11 防线）。warnings 为规范化后文本
    的非阻断警告（拼写/重复关键字 B3 + testrt 降级黄警 B14——不改变任何
    阻断语义）。调用方须知：返回值为 dict（恒真值）——真值判断一律取
    ["normalized"]。
    """
    path = default_inputs_dir() / str(task_id)
    try:
        # utf-8-sig 统一读取口径（§2.7 项 6，审查整改 R2）：磁盘副本带 BOM
        # 时解析与规范化写回均不含 BOM
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        raise not_found("input", task_id)
    result = verify_and_normalize(text)
    parsed = parse_input(result["text"])
    if parsed["multistep"]:  # ④ 多步兜底（导入已拒，历史遗留兜底）
        raise err("INPUT_MULTISTEP_UNSUPPORTED",
                  "多步任务（--Link1--）不支持", {"task_id": task_id}, http=422)
    if parsed["parse_errors"]:  # ③ 解析校验
        first = parsed["parse_errors"][0]
        raise err("INPUT_PARSE_FAILED", "输入解析失败，拒绝提交",
                  {"task_id": task_id, "section": first["section"],
                   "line": first["line"],
                   "parse_errors": parsed["parse_errors"]}, http=422)
    lines = split_lines(result["text"])
    warnings = file_warnings(parsed, parsed["blocks"]["route"], lines)
    warnings += _check_mem_floor(result["text"], task_id)  # B16 每核下限
    warnings += _check_route(parsed["blocks"]["route"],
                             _route_start_line(lines), task_id)  # B14 testrt
    if result["changed"]:
        before = parse_input(text)
        if _mask(before["blocks"]) != _mask(parsed["blocks"]):
            log.error("提交核验规范化致结构变化（拒绝落盘）：task=%s", task_id)
            raise ApiError("INTERNAL_ERROR", "服务端异常", http=500)
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(result["text"], encoding="utf-8")
        os.replace(tmp, path)
    return {"normalized": result["changed"], "warnings": warnings}
