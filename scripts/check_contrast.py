#!/usr/bin/env python3
"""对比度实测闸门（m0-frontend-design §2.1/§7 / m1-review2-fix-plan D-04）。

按 WCAG 相对亮度公式实测 §2.1 对比度核算表全部组合（明暗两主题），
输出实测值供文档回填；任一组合 < 4.5:1 即退出码非零（零回退闸门）。

取数来源：web/frontend/src/styles/tokens.css（唯一事实来源）。
- 徽标响亮档 12% 底 = color-mix(in srgb, 状态色 12%, 透明) 叠于
  --bg-raised 之上，按 sRGB 通道线性混合（与 CSS color-mix 一致）；
- 安静档状态色直接对 --bg-raised 计算。

用法（项目根）：uv run python scripts/check_contrast.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOKENS_CSS = PROJECT_ROOT / "web/frontend/src/styles/tokens.css"

QUIET_STATES = ["staged", "succeeded", "skipped", "archived", "idle"]


def _parse_block(text: str, selector: str) -> dict[str, str]:
    m = re.search(re.escape(selector) + r"\s*\{", text)
    if not m:
        raise SystemExit(f"check_contrast: 未找到选择器 {selector}")
    depth = 0
    for i in range(m.end() - 1, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                block = text[m.end():i]
                break
    else:
        raise SystemExit(f"check_contrast: 选择器 {selector} 块未闭合")
    out: dict[str, str] = {}
    for vm in re.finditer(r"(--[\w-]+)\s*:\s*([^;{}]+);", block):
        out[vm.group(1)] = re.sub(r"\s+", "", vm.group(2))
    return out


def _hex(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _mix_over(fg: str, alpha: float, bg_rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """color-mix(in srgb, fg alpha%, transparent) 叠于 bg：sRGB 通道混合。"""
    f = _hex(fg)
    return tuple(a * alpha + (1 - alpha) * v for a, v in zip(f, bg_rgb, strict=True))


def _luminance(rgb: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(fg_rgb, bg_rgb) -> float:
    l1, l2 = sorted((_luminance(fg_rgb), _luminance(bg_rgb)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def main() -> int:
    text = TOKENS_CSS.read_text(encoding="utf-8")
    dark = _parse_block(text, ":root")
    light = _parse_block(text, 'html[data-theme="light"]')
    themes = {"暗色": dark, "亮色": light}

    rows: list[str] = []
    failures: list[str] = []

    def check(label: str, fg_var: str, bg_rgb, theme: str) -> float:
        fg_rgb = _hex(themes[theme][fg_var])
        r = _ratio(fg_rgb, bg_rgb)
        rows.append(f"{label:<34} {r:5.2f}:1")
        if r < 4.5:
            failures.append(f"{theme} {label} = {r:.3f} < 4.5")
        return r

    for theme, vars_ in themes.items():
        bg_base = _hex(vars_["--bg-base"])
        bg_raised = _hex(vars_["--bg-raised"])
        rows.append(f"—— {theme}（--bg-base / --bg-raised 底）——")
        check("text-primary / bg-base", "--text-primary", bg_base, theme)
        check("text-secondary / bg-base", "--text-secondary", bg_base, theme)
        check("text-faint / bg-base", "--text-faint", bg_base, theme)
        # 响亮档徽标：状态色 12% 底（chip-bg-alpha，亮色组继承暗色值）叠 --bg-raised
        alpha = float(vars_.get("--chip-bg-alpha") or dark["--chip-bg-alpha"])
        for state in ("running", "failed"):
            loud_bg = _mix_over(vars_[f"--state-{state}"], alpha, bg_raised)
            check(f"{state} 徽标文字 / 12% 底", f"--state-{state}", loud_bg, theme)
        # 安静档状态色直接对 --bg-raised
        quiet = {s: _ratio(_hex(vars_[f"--state-{s}"]), bg_raised)
                 for s in QUIET_STATES}
        lo = min(quiet, key=quiet.get)
        hi = max(quiet, key=quiet.get)
        rows.append(f"{'安静档状态色 / bg-raised（区间）':<34} "
                    f"{quiet[lo]:.2f}–{quiet[hi]:.2f}:1"
                    f"（{lo}–{hi}）")
        for s, r in quiet.items():
            if r < 4.5:
                failures.append(f"{theme} 安静档 {s} = {r:.3f} < 4.5")
        check("primary 按钮 ink / accent 底", "--accent-ink",
              _hex(vars_["--accent"]), theme)

    print("\n".join(rows))
    if failures:
        print("check_contrast: 不达标 —")
        for f in failures:
            print(f"  {f}")
        return 1
    print("check_contrast: OK — 全部组合 ≥ 4.5:1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
