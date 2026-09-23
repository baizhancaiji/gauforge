"""文件名自然序排序键（roadmap M1.1）。

规则：文件名切分为 [字母|数字] 块序列；字母块 casefold 字典序、数字块数值序、
字母块先于数字块（A–Z 先于 0–9）；其余字符仅作分隔不参与键。
"""
from __future__ import annotations

import re

_TOKEN = re.compile(r"[A-Za-z]+|[0-9]+")


def natural_key(name: str) -> tuple:
    """文件名 → 可比较键（字母块 (0, 0, casefold)、数字块 (1, 数值, "")）。"""
    tokens: list[tuple] = []
    for m in _TOKEN.finditer(name):
        s = m.group()
        if s[0].isdigit():
            tokens.append((1, int(s), ""))
        else:
            tokens.append((0, 0, s.casefold()))
    return tuple(tokens)
