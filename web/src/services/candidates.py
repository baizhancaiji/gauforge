"""候选领域服务（B3）：导入 / 剔除 / title 实时解析 / 分块编辑保存（M2 B2）。

- 导入即拷贝：inputs/<id> 按候选 id 存输入副本，与源文件彻底独立
  （roadmap §2.4）；原文落盘不转换换行（CRLF 保留）。
- 整批原子（m1-plan §8 决策点 2）：全部文件校验通过才建行+拷贝；任一失败
  422 + details 逐文件，不产生部分导入。
- title 不落库：展示时实时解析注入（roadmap §2.6 ①），文件缺失/解码失败
  /解析失败回落 null。
- 重复导入同一文件 → 两条候选不同 id（roadmap §2.4）；同名且内容哈希一致
  时结果带 duplicate 提示（m1-plan §5 测试表「哈希+内容双校验」：同名 +
  同 sha256）。
- 分块编辑保存（m2-plan §2.1 流水①–⑤）：形态守卫 → 逐节校验（阻断 422）
  → 区间替换重组（不做换行转换）→ round-trip 自证（不一致 500 拒绝落盘）
  → 原子写；全程持全局写锁。编辑入口仅候选与失败回退队列（2026-09-26 裁决）。

mode=folder 与 files 服务端语义相同：文件清单由前端给定，后端不做服务端
目录扫描（路径边界 roadmap §2.4）。
"""
from __future__ import annotations

import copy
import hashlib
import logging
import os
import re
from pathlib import Path

from .. import config
from ..engine.workspace import _cpu_list_count
from ..errors import ApiError, err, not_found, validation_failed
from ..parse.blocks import (is_editable_section, parse_charge_tokens,
                            parse_input, reassemble, scan_spans, split_lines)
from ..parse.keywords import check_route_duplicates, check_route_spelling
from ..parse.link0_rules import (LINE_LENGTH_CAP, MEM_VALUE_RE,
                                 _NO_EQ_DIRECTIVES, directive_head)
from ..store import executions, get_db, tasks

log = logging.getLogger(__name__)

SUPPORTED_EXTS = (".gjf", ".com")
_File = tuple[str, bytes]  # (filename, 原始字节)


def default_inputs_dir() -> Path:
    return config.HOME_DIR / "inputs"


def _basename(filename: str) -> str:
    return Path(filename).name


def _route_warnings(route_text: str, lines: list[str]) -> list[dict]:
    """route 非阻断警告全集（G1/G2）：拼写近邻 + 重复关键字，行号为全文件
    绝对行号（route 起始行换算）。"""
    span = scan_spans(lines).get("route")
    offset = span[0] if span else 0
    return (check_route_spelling(route_text, line_offset=offset)
            + check_route_duplicates(route_text, line_offset=offset))


def file_warnings(parsed: dict, route_text: str, lines: list[str]) -> list[dict]:
    """全文件非阻断警告全集（G0/G1/G2/G5 统一口径）：parse_input 产出
    （分子说明/变量区 EOF、Link 0 值域与指令、title 禁用字符、原子标签、
    多组电荷对）+ route 拼写/重复（parse_input 不产拼写通道）。公共 API
    （审查整改 R5：预览路由跨模块消费，去私有名）。"""
    return parsed["warnings"] + _route_warnings(route_text, lines)


def _validate_one(filename: str, data: bytes) -> dict:
    """单文件校验（G1 改造）：始终返回 {"error": dict|None, "warnings": list}。

    error 为 None 表示校验通过；warnings 为非阻断提示（全文件警告，
    file_warnings 统一口径），仅在通过时非空可携带（失败条目不带
    warnings——422 details.errors[] 无该字段）。解码用 utf-8-sig：检测到
    UTF-8 BOM 时剥离 BOM 字节后落盘（G5 项 6，静默行为）。"""
    name = _basename(filename)
    if not name:
        return {"error": {"filename": filename, "reason": "INVALID_FILENAME",
                          "message": "文件名为空"}, "warnings": []}
    if Path(name).suffix.casefold() not in SUPPORTED_EXTS:
        return {"error": {"filename": name, "reason": "UNSUPPORTED_EXTENSION",
                          "message": "仅支持 .gjf/.com（不区分大小写）"},
                "warnings": []}
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {"error": {"filename": name, "reason": "INVALID_ENCODING",
                          "message": "非 UTF-8 文本"}, "warnings": []}
    stripped = data[len(b"\xef\xbb\xbf"):] if data.startswith(b"\xef\xbb\xbf") \
        else data  # 其余字节原样保留（CRLF 不转），仅剥离 BOM 字节
    r = parse_input(text)
    if r["multistep"]:
        return {"error": {"filename": name,
                          "reason": "INPUT_MULTISTEP_UNSUPPORTED",
                          "message": "多步任务（--Link1--）不支持"},
                "warnings": []}
    if r["parse_errors"]:
        first = r["parse_errors"][0]
        return {"error": {"filename": name, "reason": "INPUT_PARSE_FAILED",
                          "message": f"解析失败：{first['message']}"
                                     f"（第 {first['line']} 行）",
                          "parse_errors": r["parse_errors"]},
                "warnings": []}
    return {"error": None, "bom_stripped": stripped is not data,
            "data": stripped,
            "warnings": file_warnings(r, r["blocks"]["route"],
                                       split_lines(text))}


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_duplicate(name: str, data_hash: str, inputs_dir: Path) -> bool:
    """同名且已存副本内容哈希一致 → 重复提示（哈希+内容双校验）。"""
    for row in tasks().list_by_form("candidate"):
        if row["filename"] != name:
            continue
        try:
            stored = (inputs_dir / str(row["id"])).read_bytes()
        except OSError:
            continue
        if _content_hash(stored) == data_hash:
            return True
    return False


def import_files(files: list[_File], *, mode: str = "files",
                 inputs_dir: Path | None = None) -> list[dict]:
    """整批导入：校验全部通过才建行+拷贝；任一失败抛 422（details 逐文件）。

    返回 CandidateCreate.files 条目 [{"id", "filename", "duplicate",
    "warnings"}]；duplicate 为契约之外的提示字段（§5 测试表语义）；warnings
    为该文件 route 的非阻断警告（G1，仅成功条目携带，失败 422 不返回）。
    """
    if mode not in ("files", "folder"):
        raise validation_failed([{"field": "mode",
                                  "reason": "must_be_files_or_folder"}])
    if not files:
        raise validation_failed([{"field": "files", "reason": "empty"}])
    ind = inputs_dir if inputs_dir is not None else default_inputs_dir()

    results = [_validate_one(fn, data) for fn, data in files]
    errors = [r["error"] for r in results if r["error"]]
    if errors:
        raise validation_failed(errors)
    warnings_by_file = [r["warnings"] for r in results]
    # BOM 剥离后的落盘字节（G5 项 6：哈希与落盘以剥离后副本为准）
    stored_by_file = [r["data"] for r in results]

    ind.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    created: list[tuple[int, Path]] = []
    try:
        for (fn, _raw), warns, stored in zip(files, warnings_by_file,
                                             stored_by_file):
            name = _basename(fn)
            dup = _is_duplicate(name, _content_hash(stored), ind)
            tid = tasks().create_candidate(name, "imported")
            path = ind / str(tid)
            path.write_bytes(stored)  # 原文落盘（BOM 已剥离），CRLF 不转
            created.append((tid, path))
            out.append({"id": tid, "filename": name, "duplicate": dup,
                        "warnings": warns})
    except Exception:
        # 补偿回滚：兑现整批原子（磁盘故障等运行期异常也不留半批）
        for tid, path in created:
            path.unlink(missing_ok=True)
            tasks().delete(tid)
        raise
    return out


def import_folder_as_queue(files: list[_File], *, mode: str,
                           folder_name: str,
                           inputs_dir: Path | None = None,
                           ) -> tuple[list[dict], dict | None, str | None]:
    """导入成队（m2-plan §2.3 契约增量）：复用 import_files 整批导入后按
    受支持文件数 2–10 判定成队或回落。

    返回 (files 条目, queue {queue_id,name}|None, queue_fallback_reason|None)；
    成队 = 导入落候选 → 候选转换入队；越界 = 拒绝成队、回落全部生成候选。
    """
    out = import_files(files, mode=mode, inputs_dir=inputs_dir)
    n = len(out)
    if 2 <= n <= 10:
        from .queues import create_queue_from_candidates  # 延迟导入防环
        qid = create_queue_from_candidates(folder_name,
                                           [item["id"] for item in out])
        return out, {"queue_id": qid, "name": folder_name}, None
    reason = (f"受支持文件 {n} 个，超出队列成员上限 10" if n > 10
              else f"受支持文件 {n} 个，少于队列成员下限 2")
    return out, None, reason


def delete_candidate(task_id: int, inputs_dir: Path | None = None) -> None:
    """剔除候选：删 inputs/<id> 与记录（删除任务实体唯一入口）。

    仅 candidate 形态可删（roadmap §2.4）；其余形态按不存在处理。
    携带执行记录的候选（停止回退后删除队列等路径误退回的历史遗留）
    不删行——executions.task_id 外键约束下删行必失败，且先删文件会留下
    文件已失、行仍可见的幽灵候选；转 finished 离开候选列表，任务实体
    归历史所有（同删除队列「已执行成员只留历史」，roadmap §2.4）。
    """
    ind = inputs_dir if inputs_dir is not None else default_inputs_dir()
    row = tasks().get(task_id)
    if row is None or row["form"] != "candidate":
        raise not_found("candidate", task_id)
    if executions().list_by_task(task_id):
        tasks().detach_finished(task_id)
        return
    tasks().delete(task_id)
    (ind / str(task_id)).unlink(missing_ok=True)


def resolve_title(task_id: int, inputs_dir: Path | None = None) -> str | None:
    """实时解析 title（不落库）：文件缺失/解码失败/缺节 → None。

    读取统一 utf-8-sig（§2.7 项 6，审查整改 R2）：磁盘副本带 BOM 时解析
    口径与导入/提交一致。"""
    ind = inputs_dir if inputs_dir is not None else default_inputs_dir()
    try:
        text = (ind / str(task_id)).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return parse_input(text)["blocks"]["title"]


def copy_execution_input(execution_id: int, task_id: int,
                         inputs_dir: Path | None = None) -> bytes:
    """以 run/<执行id>/input.gjf 实际执行副本为源读取输入（缺失回落任务
    输入副本，skipped 等无执行目录者）。

    历史退回候选与队列移除分流（m2-plan §2.2）共用同一复制源语义
    （§9 风险 5：不另写复制逻辑）。
    """
    src = config.HOME_DIR / "run" / str(execution_id) / "input.gjf"
    if not src.is_file():
        src = (inputs_dir if inputs_dir is not None
               else default_inputs_dir()) / str(task_id)
    return src.read_bytes()


# ---------------- 分块编辑保存（M2 B2，m2-plan §2.1） ----------------

def _verr(section: str, line: int, reason: str, message: str) -> dict:
    return {"field": section, "line": line, "reason": reason,
            "message": message}


def _validate_section(section: str, content: list[str]) -> None:
    """逐节格式校验（阻断 422，m2-plan §2.1 校验表；B4 值域与 G5 同源口径：
    %mem 值域收紧并要求 >0、单行 ≤500、无等号官方指令合法）。"""
    errors: list[dict] = []
    if section == "link0":
        for k, ln in enumerate(content, 1):
            body = ln.strip()
            head, val = directive_head(body)
            # 无等号官方指令（%save/%kjob l502 2 等）合法放行
            if not body.startswith("%") or (
                    "=" not in body and head not in _NO_EQ_DIRECTIVES):
                errors.append(_verr(section, k, "must_be_key_value",
                                    "%行应为 %Key=Value 或官方无等号指令形态"))
                continue
            if len(body) > LINE_LENGTH_CAP:
                errors.append(_verr(section, k, "link0_line_too_long",
                                    f"Link 0 单行超长（官方上限 "
                                    f"{LINE_LENGTH_CAP} 字符）"))
                continue
            key_cf = head
            if not val.strip() and "=" in body:
                errors.append(_verr(section, k, "empty_value",
                                    "值不可为空"))
            elif key_cf.startswith("nproc"):
                try:
                    positive = int(val.strip()) > 0
                except ValueError:
                    positive = False
                if not positive:
                    errors.append(_verr(section, k, "nproc_not_positive_int",
                                        "%nprocshared 值须为正整数"))
            elif key_cf == "mem":
                m = MEM_VALUE_RE.match(val.split(",")[0].strip())
                num_ok = m is not None and float(
                    re.match(r"^\d+(?:\.\d+)?", val).group()) > 0
                if not num_ok:
                    errors.append(_verr(section, k, "mem_value_invalid",
                                        "%mem 值须为正数（可选单位 "
                                        "KB/MB/GB/TB/KW/MW/GW/TW）"))
            elif key_cf == "cpu" and _cpu_list_count(val) is None:
                errors.append(_verr(section, k, "cpu_list_invalid",
                                    "%cpu 值须为处理器列表"
                                    "（如 0,1,2 / 0-5 / 0-5/2）"))
    elif section == "route":
        if not content[0].lstrip().startswith("#"):
            errors.append(_verr(section, 1, "route_must_start_with_hash",
                                "route 首行须以 # 开头"))
        for k, ln in enumerate(content, 1):
            if k > 1 and ln.lstrip().startswith("%"):
                # G3 情形 1：分块保存通道同步阻断（reason 按端点词表）
                errors.append(_verr(section, k, "route_line_link0_forbidden",
                                    "Link 0 命令必须位于 route 节之前"
                                    "（% 行不得出现在 route 节内）"))
            if not ln.strip():
                errors.append(_verr(section, k, "blank_line_in_route",
                                    "route 节内不得出现空行（空行即节终止）"))
    elif section == "title":
        if len(content) > 5:
            errors.append(_verr(section, 1, "title_too_long",
                                "title 至多 5 行"))
        for k, ln in enumerate(content, 1):
            if ln.lstrip().startswith("%"):
                # G3 情形 2：分块保存通道同步阻断（reason 按端点词表）
                errors.append(_verr(section, k, "link0_misplaced",
                                    "疑似 Link 0 命令错置于 title 节"
                                    "（% 命令必须位于 route 节之前）"))
            bad = any(c in ln for c in "@#!–_\\") or any(
                ord(c) < 32 for c in ln)
            if bad:
                errors.append(_verr(section, k, "title_forbidden_char",
                                    "title 不得含 @ # ! – _ \\ 与控制字符"))
    elif section == "charge_mult":
        if len(content) != 1:
            errors.append(_verr(section, 1, "must_be_single_line",
                                "电荷/多重度恰为一行"))
        else:
            # G5 项 1：多组电荷-多重度对同口径（偶数个整数；首组 mult ≥1、
            # 后续组 mult≠0；负多重度官方仅 Guess=Fragment，宽容放行）。
            # 分词单点 parse_charge_tokens（审查整改 R3：斜杠/en-dash 分隔
            # 与 parse_input 同口径，自由格式分隔符无法解析才阻断）
            toks = parse_charge_tokens(content[0])
            nums: list[int] = []
            ok = bool(toks) and len(toks) % 2 == 0
            if ok:
                try:
                    nums = [int(t) for t in toks]
                except ValueError:
                    ok = False
            if ok:
                for g in range(0, len(nums), 2):
                    if (g == 0 and nums[g + 1] < 1) or \
                            (g > 0 and nums[g + 1] == 0):
                        ok = False
            if not ok:
                errors.append(_verr(section, 1, "must_be_integer_pairs",
                                    "应为电荷-多重度整数对（首组多重度为正"
                                    "整数，后续组多重度不得为 0）"))
    # additional-<n>：自由文本，无阻断校验
    if errors:
        raise validation_failed(errors)


def _guard_editable(row: dict, task_id: int, section: str | None = None) -> None:
    """形态守卫（m2-plan §2.1 守卫矩阵；编辑入口仅候选与失败回退队列）。

    M4 C5 增口：unsubmitted 队列成员限 link0 节可写（队列编辑框
    「接续前置 chk」写 %oldchk 依赖行，DAG 校验读输入）；其余节仍锁定。
    """
    form = row["form"]
    if form == "candidate":
        return
    if form == "queue_member":
        q = get_queue_row(row["queue_id"])
        if q is not None and q["state"] == "unsubmitted":
            if bool(q.get("rollback_flag")):
                return  # 失败回退队列成员：队列编辑框内分块编辑（全节）
            if section == "link0":
                return  # C5 依赖行写入（勾选辅助生成的唯一节口）
        raise err("QUEUE_MEMBER_LOCKED",
                  "队列成员内容锁定（编辑入口仅候选与失败回退队列；"
                  "unsubmitted 队列成员限 link0 依赖行）",
                  {"task_id": task_id,
                   "queue_state": q["state"] if q else None}, http=409)
    if form == "seat_task":
        raise err("TASK_IN_FLIGHT", "任务在途，内容锁定",
                  {"task_id": task_id}, http=409)
    if form == "finished":
        raise err("TASK_FINISHED", "终态条目不可变",
                  {"task_id": task_id}, http=409)
    raise err("TASK_STATE_CONFLICT", "任务形态不可编辑",
              {"form": form}, http=409)


def get_queue_row(queue_id: str) -> dict | None:
    """队列行读取（守卫用；独立小函数避免环形导入 routers）。"""
    from ..store import queues
    return queues().get(queue_id)


def _expected_blocks(blocks: dict, section: str,
                     content: list[str]) -> dict:
    """保存后应有的分块结构（round-trip 自证基准；归一化口径与 parse_input
    一致——link0/title/附加节 strip、route 仅 rstrip、电荷行规约两整数）。"""
    expected = copy.deepcopy(blocks)
    if section == "link0":
        expected["link0"]["lines"] = [ln.strip() for ln in content]
        low = [ln.casefold() for ln in expected["link0"]["lines"]]
        expected["link0"]["missing"] = [
            nm for nm, pats in (("NProcShared", ("%nproc", "%cpu")),
                                ("Mem", ("%mem",)))
            if not any(p in ln for ln in low for p in pats)]
    elif section == "route":
        expected["route"] = "\n".join(ln.rstrip() for ln in content)
    elif section == "title":
        expected["title"] = "\n".join(ln.strip() for ln in content)
    elif section == "charge_mult":
        cm = content[0].strip()
        # G5 多组对同口径：偶数个整数全组规范化（空格分隔），否则原样；
        # 分词单点 parse_charge_tokens（审查整改 R3，与 parse_input 一致）
        parts = parse_charge_tokens(cm)
        try:
            nums = [int(t) for t in parts]
            if len(nums) % 2 == 0 and nums:
                expected["charge_mult"] = " ".join(str(v) for v in nums)
            else:
                expected["charge_mult"] = cm
        except ValueError:
            expected["charge_mult"] = cm
    else:  # additional-<n>
        idx = int(section.split("-", 1)[1])
        expected["additional_sections"][idx] = {
            "lines": [ln.strip() for ln in content], "terminator_blank": True}
    return expected


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_block(task_id: int, section: str, lines: list[str], *,
               inputs_dir: Path | None = None) -> dict:
    """分块编辑保存（m2-plan §2.1 流水①–⑤；读-改-写全程持全局写锁）。

    返回新 InputPreview + warnings[]（拼写检查，非阻断）；
    重组后重解析与预期结构不一致 → 500 拒绝落盘（宁可保存失败不写坏输入）。
    """
    if not is_editable_section(section):
        raise err("INVALID_REQUEST",
                  "molecule 节不可编辑" if section == "molecule" else "未知分节",
                  {"section": section}, http=400)
    ind = inputs_dir if inputs_dir is not None else default_inputs_dir()
    with get_db().exclusive():
        row = tasks().get(task_id)
        if row is None:
            raise not_found("candidate", task_id)
        _guard_editable(row, task_id, section)
        path = ind / str(task_id)
        try:
            # 字节读入后解码（read_text 通用换行模式会吞 CRLF——编辑不转换行尾）；
            # utf-8-sig 统一读取口径（§2.7 项 6，审查整改 R2：带 BOM 磁盘
            # 副本 scan_spans 的 %/# 判定不被 \ufeff 前缀破坏）
            text = path.read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError):
            raise not_found("input", task_id)

        content = list(lines)
        while content and not content[0].strip():  # 节内容不含边界空行
            content.pop(0)
        while content and not content[-1].strip():
            content.pop()
        if not content:
            raise validation_failed(
                [_verr(section, 1, "empty_section", "分节内容不可为空")])
        _validate_section(section, content)  # ① 逐节校验（阻断）

        try:
            new_text = reassemble(text, section, content)  # ② 区间替换重组
        except KeyError:
            raise err("INVALID_REQUEST", "文件中不存在该分节",
                      {"section": section}, http=400)

        before = parse_input(text)
        expected = _expected_blocks(before["blocks"], section, content)
        if parse_input(new_text)["blocks"] != expected:  # ③ round-trip 自证
            log.error("分块保存 round-trip 不一致（拒绝落盘）：task=%s section=%s",
                      task_id, section)
            raise ApiError("INTERNAL_ERROR", "服务端异常",
                           http=500)

        _atomic_write_text(path, new_text)  # ④ 原子写
        after = parse_input(new_text)
        filename = row["filename"]
    # ⑤ 非阻断警告全集（G0/G1/G2/G5 五通道统一口径）：parse_input 产出 +
    # route 拼写/重复，行号全文件绝对（file_warnings 单点）
    warnings = file_warnings(after, after["blocks"]["route"],
                              split_lines(new_text))
    return {"candidate_id": task_id, "filename": filename,
            "blocks": after["blocks"], "parse_errors": after["parse_errors"],
            "warnings": warnings}
