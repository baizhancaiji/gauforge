"""route 关键词字典加载（m2-plan B1）。

字典文件 web/src/parse/keywords.txt 由 scripts/extract_keywords.py 从
gaussian-kb 结构化知识库生成（纳入版本管理、可重生成）；进程内缓存一次，
缺失时降级为空集（拼写检查零警告）并记日志，不阻断保存。
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

DICT_PATH = Path(__file__).resolve().parent / "keywords.txt"

_cache: frozenset[str] | None = None


def load_keywords(path: Path | None = None, *,
                  refresh: bool = False) -> frozenset[str]:
    """读入关键词全集（小写）；缺失降级为空集。"""
    global _cache
    if _cache is not None and not refresh and path is None:
        return _cache
    target = path if path is not None else DICT_PATH
    try:
        words = frozenset(
            w for w in target.read_text(encoding="utf-8").splitlines() if w)
    except OSError:
        log.warning("关键词字典缺失（%s）：拼写检查降级为零警告", target)
        words = frozenset()
    if path is None:
        _cache = words
    return words
