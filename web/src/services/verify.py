"""提交前输入核验（M2 B6，m2-plan §2.5）。

所有进入待执行队列的提交动作（行内提交 / 队列提交与直接提交 / 历史重新
排队）统一在提交事务内、建席位之前调用：核验通过且规范化有变化时原子写
回 inputs/<id>（此后派发、哈希、历史输入均以规范副本为准），失败不写盘。
"""
from __future__ import annotations

import logging
import os

from ..errors import ApiError, err, not_found
from ..parse.blocks import parse_input, verify_and_normalize
from .candidates import default_inputs_dir

log = logging.getLogger(__name__)


def _mask(blocks: dict) -> dict:
    """结构自证掩码：附加节 terminator_blank 由空行规约统一置 True。"""
    masked = {**blocks,
              "additional_sections": [dict(s, terminator_blank=True)
                                      for s in blocks["additional_sections"]]}
    return masked


def verify_and_store(task_id: int) -> bool:
    """对 inputs/<id> 执行提交前核验，返回 normalized 标记。

    ①② 规范化有变化 → 原子写回；③ 解析失败 → 422 INPUT_PARSE_FAILED；
    ④ 多步 → 422 INPUT_MULTISTEP_UNSUPPORTED；规范化致结构变化 →
    500 拒绝（不落盘，m2-plan §9 风险 11 防线）。
    """
    path = default_inputs_dir() / str(task_id)
    try:
        text = path.read_bytes().decode("utf-8")
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
    if result["changed"]:
        before = parse_input(text)
        if _mask(before["blocks"]) != _mask(parsed["blocks"]):
            log.error("提交核验规范化致结构变化（拒绝落盘）：task=%s", task_id)
            raise ApiError("INTERNAL_ERROR", "服务端异常", http=500)
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(result["text"], encoding="utf-8")
        os.replace(tmp, path)
    return result["changed"]
