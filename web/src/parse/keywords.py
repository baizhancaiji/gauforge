"""route 关键词字典加载与拼写检查（m2-plan B1/B2）。

字典文件 web/src/parse/keywords.txt 由 scripts/extract_keywords.py 从
gaussian-kb 结构化知识库生成（纳入版本管理、可重生成）；进程内缓存一次，
缺失时降级为空集（拼写检查零警告）并记日志，不阻断保存。
"""
from __future__ import annotations

import difflib
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

DICT_PATH = Path(__file__).resolve().parent / "keywords.txt"

# route token 切分：#、/ 与空白（m2-plan §2.1；大小写不敏感匹配）
_TOKEN_SPLIT = re.compile(r"[/\s#]+")

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


def check_route_spelling(route_text: str, *, cutoff: float = 0.8,
                         dictionary: frozenset[str] | None = None) -> list[dict]:
    """route 节关键词拼写检查（非阻断，m2-plan §2.1 定稿）。

    警告条件：token 未命中字典且与某词条编辑距离接近
    （difflib.get_close_matches cutoff=0.80）→ kind=keyword_spell +
    首个近邻 suggestion；纯新词（无近邻）不警告——方法学与基组不在字典，
    「未收录即警告」会使检查失效。line 为 route 节内行号（1 起）。
    """
    words = dictionary if dictionary is not None else load_keywords()
    if not words or not route_text:
        return []
    ordered = sorted(words)  # 排序保证近邻并列时结果确定
    out: list[dict] = []
    for line_no, line in enumerate(route_text.split("\n"), start=1):
        for tok in _TOKEN_SPLIT.split(line):
            word = tok.casefold()
            if not word or word in words:
                continue
            near = difflib.get_close_matches(word, ordered, n=1, cutoff=cutoff)
            if near:
                out.append({"line": line_no, "keyword": tok,
                            "kind": "keyword_spell", "suggestion": near[0]})
    return out
