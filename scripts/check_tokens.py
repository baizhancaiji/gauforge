#!/usr/bin/env python3
"""设计令牌一致性闸门（m0-frontend-design §8 / m1-review2-fix-plan D-06）。

逐变量 diff 两处令牌定义，任一缺失或不一致即退出码非零：
- 唯一来源：web/frontend/src/styles/tokens.css（:root 暗色 + 明亮主题组）；
- 可视化样板：docs/plans/assets/m0-ui-preview.html（:root 由本文件再生成，
  机械校验，人工目检不替代）。

比较口径：变量名全等；值经归一化后全等（剔除全部空白、`.5` 补前导零），
因此排版差异（多行字体栈、空格）不构成 diff，仅实质值差异报错。

用法（项目根）：uv run python scripts/check_tokens.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TOKENS_CSS = PROJECT_ROOT / "web/frontend/src/styles/tokens.css"
PREVIEW_HTML = PROJECT_ROOT / "docs/plans/assets/m0-ui-preview.html"

# (块标签, tokens.css 内选择器, 样板内选择器)
_BLOCKS = [
    ("暗色 :root", ":root", ":root"),
    ("明亮 html[data-theme=light]", 'html[data-theme="light"]',
     'html[data-theme="light"]'),
]


def _extract_block(text: str, selector: str) -> str:
    """按选择器定位声明块并做花括号配对截取（值内无花括号，无需深匹配）。"""
    m = re.search(re.escape(selector) + r"\s*\{", text)
    if not m:
        raise SystemExit(f"check_tokens: 未找到选择器 {selector}")
    depth = 0
    for i in range(m.end() - 1, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[m.end():i]
    raise SystemExit(f"check_tokens: 选择器 {selector} 块未闭合")


def _parse_vars(block: str) -> dict[str, str]:
    """提取自定义属性 → 归一化值（剔空白、`.5` 补前导零）。"""
    out: dict[str, str] = {}
    for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;{}]+);", block):
        value = re.sub(r"\s+", "", m.group(2))
        value = re.sub(r"(?<![\w.])\.(\d)", r"0.\1", value)
        out[m.group(1)] = value
    return out


def main() -> int:
    tokens_text = TOKENS_CSS.read_text(encoding="utf-8")
    preview_text = PREVIEW_HTML.read_text(encoding="utf-8")
    problems: list[str] = []
    for label, sel_t, sel_p in _BLOCKS:
        tv = _parse_vars(_extract_block(tokens_text, sel_t))
        pv = _parse_vars(_extract_block(preview_text, sel_p))
        names = sorted(set(tv) | set(pv))
        for name in names:
            if name not in tv:
                problems.append(f"[{label}] {name} 仅样板有，tokens.css 缺失")
            elif name not in pv:
                problems.append(f"[{label}] {name} 仅 tokens.css 有，样板缺失")
            elif tv[name] != pv[name]:
                problems.append(
                    f"[{label}] {name} 值不一致: tokens={tv[name]} 样板={pv[name]}")
        print(f"{label}: tokens {len(tv)} 变量 / 样板 {len(pv)} 变量")
    if problems:
        print("check_tokens: 令牌 diff 非空 —")
        for p in problems:
            print(f"  {p}")
        return 1
    print("check_tokens: OK — 逐变量 diff 为空")
    return 0


if __name__ == "__main__":
    sys.exit(main())
