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
from ..parse.blocks import is_editable_section, parse_input, reassemble
from ..parse.keywords import check_route_spelling
from ..store import get_db, tasks

log = logging.getLogger(__name__)

SUPPORTED_EXTS = (".gjf", ".com")
_File = tuple[str, bytes]  # (filename, 原始字节)

# %Mem 值：数值 + 可选单位后缀（G16 手册核查，m2-plan 决策点 7：缺省单位
# 为 8 字节字（MW 量纲），可选 KB/MB/GB/TB/KW/MW/GW/TW，无空格；类型错才 422）
_MEM_VALUE_RE = re.compile(r"^\d+(?:\.\d+)?(?:KB|MB|GB|TB|KW|MW|GW|TW|W|B)?$",
                           re.IGNORECASE)


def default_inputs_dir() -> Path:
    return config.HOME_DIR / "inputs"


def _basename(filename: str) -> str:
    return Path(filename).name


def _validate_one(filename: str, data: bytes) -> dict | None:
    """单文件校验：通过返回 None；否则返回逐文件错误条目。"""
    name = _basename(filename)
    if not name:
        return {"filename": filename, "reason": "INVALID_FILENAME",
                "message": "文件名为空"}
    if Path(name).suffix.casefold() not in SUPPORTED_EXTS:
        return {"filename": name, "reason": "UNSUPPORTED_EXTENSION",
                "message": "仅支持 .gjf/.com（不区分大小写）"}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"filename": name, "reason": "INVALID_ENCODING",
                "message": "非 UTF-8 文本"}
    r = parse_input(text)
    if r["multistep"]:
        return {"filename": name, "reason": "INPUT_MULTISTEP_UNSUPPORTED",
                "message": "多步任务（--Link1--）不支持"}
    if r["parse_errors"]:
        first = r["parse_errors"][0]
        return {"filename": name, "reason": "INPUT_PARSE_FAILED",
                "message": f"解析失败：{first['message']}（第 {first['line']} 行）",
                "parse_errors": r["parse_errors"]}
    return None


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

    返回 CandidateCreate.files 条目 [{"id", "filename", "duplicate"}]；
    duplicate 为契约之外的提示字段（§5 测试表语义）。
    """
    if mode not in ("files", "folder"):
        raise validation_failed([{"field": "mode",
                                  "reason": "must_be_files_or_folder"}])
    if not files:
        raise validation_failed([{"field": "files", "reason": "empty"}])
    ind = inputs_dir if inputs_dir is not None else default_inputs_dir()

    errors = [e for e in (_validate_one(fn, data) for fn, data in files) if e]
    if errors:
        raise validation_failed(errors)

    ind.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    created: list[tuple[int, Path]] = []
    try:
        for fn, data in files:
            name = _basename(fn)
            dup = _is_duplicate(name, _content_hash(data), ind)
            tid = tasks().create_candidate(name, "imported")
            path = ind / str(tid)
            path.write_bytes(data)  # 原文落盘，CRLF 不转
            created.append((tid, path))
            out.append({"id": tid, "filename": name, "duplicate": dup})
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
    """
    ind = inputs_dir if inputs_dir is not None else default_inputs_dir()
    row = tasks().get(task_id)
    if row is None or row["form"] != "candidate":
        raise not_found("candidate", task_id)
    (ind / str(task_id)).unlink(missing_ok=True)
    tasks().delete(task_id)


def resolve_title(task_id: int, inputs_dir: Path | None = None) -> str | None:
    """实时解析 title（不落库）：文件缺失/解码失败/缺节 → None。"""
    ind = inputs_dir if inputs_dir is not None else default_inputs_dir()
    try:
        text = (ind / str(task_id)).read_text(encoding="utf-8")
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
    """逐节格式校验（阻断 422，m2-plan §2.1 校验表）。"""
    errors: list[dict] = []
    if section == "link0":
        for k, ln in enumerate(content, 1):
            body = ln.strip()
            if not body.startswith("%") or "=" not in body:
                errors.append(_verr(section, k, "must_be_key_value",
                                    "%行应为 %Key=Value 形态"))
                continue
            key, _, val = body.lstrip("%").partition("=")
            key_cf = key.strip().casefold()
            if not val.strip():
                errors.append(_verr(section, k, "empty_value",
                                    "值不可为空"))
            elif key_cf.startswith("nproc"):
                try:
                    positive = int(val.strip()) > 0
                except ValueError:
                    positive = False
                if not positive:
                    errors.append(_verr(section, k, "nproc_not_positive_int",
                                        "%NProcShared 值须为正整数"))
            elif key_cf == "mem" and not _MEM_VALUE_RE.match(val.strip()):
                errors.append(_verr(section, k, "mem_value_invalid",
                                    "%Mem 值须为数值（可选单位 KB/MB/GB/TB/KW/MW/GW/TW）"))
            elif key_cf == "cpu" and _cpu_list_count(val) is None:
                errors.append(_verr(section, k, "cpu_list_invalid",
                                    "%CPU 值须为处理器列表（如 0,1,2 / 0-5）"))
    elif section == "route":
        if not content[0].lstrip().startswith("#"):
            errors.append(_verr(section, 1, "route_must_start_with_hash",
                                "route 首行须以 # 开头"))
        for k, ln in enumerate(content, 1):
            if not ln.strip():
                errors.append(_verr(section, k, "blank_line_in_route",
                                    "route 节内不得出现空行（空行即节终止）"))
    elif section == "title":
        if len(content) > 5:
            errors.append(_verr(section, 1, "title_too_long",
                                "title 至多 5 行"))
        for k, ln in enumerate(content, 1):
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
            toks = content[0].replace(",", " ").split()
            if len(toks) != 2:
                errors.append(_verr(section, 1, "must_be_two_integers",
                                    "应为电荷与多重度两个整数"))
            else:
                try:
                    ok = int(toks[1]) > 0
                    int(toks[0])
                except ValueError:
                    ok = False
                if not ok:
                    errors.append(_verr(section, 1, "must_be_two_integers",
                                        "电荷为整数、多重度须为正整数"))
    # additional-<n>：自由文本，无阻断校验
    if errors:
        raise validation_failed(errors)


def _guard_editable(row: dict, task_id: int) -> None:
    """形态守卫（m2-plan §2.1 守卫矩阵；编辑入口仅候选与失败回退队列）。"""
    form = row["form"]
    if form == "candidate":
        return
    if form == "queue_member":
        q = get_queue_row(row["queue_id"])
        if q is not None and q["state"] == "unsubmitted" \
                and bool(q.get("rollback_flag")):
            return  # 失败回退队列成员：队列编辑框内分块编辑
        raise err("QUEUE_MEMBER_LOCKED",
                  "队列成员内容锁定（编辑入口仅候选与失败回退队列）",
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
        parts = cm.replace(",", " ").split()
        try:
            expected["charge_mult"] = f"{int(parts[0])} {int(parts[1])}"
        except (IndexError, ValueError):
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
        _guard_editable(row, task_id)
        path = ind / str(task_id)
        try:
            # 字节读入后解码（read_text 通用换行模式会吞 CRLF——编辑不转换行尾）
            text = path.read_bytes().decode("utf-8")
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
    warnings = check_route_spelling(after["blocks"]["route"])  # ⑤ 拼写检查
    return {"candidate_id": task_id, "filename": filename,
            "blocks": after["blocks"], "parse_errors": after["parse_errors"],
            "warnings": warnings}
