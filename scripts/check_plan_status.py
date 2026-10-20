"""校验实施计划文档状态回填（零回退闸门脚本，AGENTS.md §5.2 第 2 步）。

用法：uv run python scripts/check_plan_status.py [计划文档路径...]
  不带参数：扫描 docs/plans/*-plan.md 全部计划文档（发布前必跑形态）；
  带参数：对显式列出的计划文档做定点校验。
校验内容：
  1. 目标文件存在；
  2. 文件头部引用块含「状态：」行，状态值取自「状态：」起至首个句号止
    （状态行跨行折行时按引用块拼接后解析）；
  3. 状态值须为终态：包含「已实施并验收」；「已执行完毕」同认终态
    （修复清单类历史文档的既定口径，如 m1-review2-fix-plan.md）；
  4. 未回填状态（「执行计划」「实施计划定稿」「待执行」「待实施」
    「部分实施」等）与缺失状态行均判失败。
失败输出问题清单并以非零码退出。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANS_DIR = ROOT / "docs" / "plans"
PLAN_GLOB = "*-plan.md"
FINAL_MARKS = ("已实施并验收", "已执行完毕")
STATUS_KEY = "状态："
HEADER_SCAN_LINES = 40  # 状态行位于文件头部引用块内


def extract_status(text: str) -> str | None:
    """取头部连续引用块拼接后，「状态：」至首个句号的状态值；找不到返回 None。"""
    blockquote: list[str] = []
    for line in text.splitlines()[:HEADER_SCAN_LINES]:
        stripped = line.strip()
        if stripped.startswith(">"):
            blockquote.append(stripped.lstrip(">").strip())
        elif blockquote:
            break  # 头部引用块结束
    joined = " ".join(fragment for fragment in blockquote if fragment)
    idx = joined.find(STATUS_KEY)
    if idx < 0:
        return None
    segment = joined[idx + len(STATUS_KEY):]
    end = segment.find("。")
    return segment[:end] if end >= 0 else segment


def display_path(path: Path) -> Path:
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def main() -> int:
    args = sys.argv[1:]
    if args:
        targets = [Path(arg) for arg in args]
    elif PLANS_DIR.is_dir():
        targets = sorted(PLANS_DIR.glob(PLAN_GLOB))
    else:
        targets = []
    if not targets:
        print(f"[FAIL] 未找到任何计划文档（{PLANS_DIR / PLAN_GLOB}），"
              "目录缺失或 glob 失效", file=sys.stderr)
        return 1

    errors: list[str] = []
    for path in targets:
        label = display_path(path)
        if not path.is_file():
            errors.append(f"{label}: 文件不存在")
            continue
        status = extract_status(path.read_text(encoding="utf-8"))
        if status is None:
            errors.append(f"{label}: 头部未找到「{STATUS_KEY}」行")
            continue
        if not any(mark in status for mark in FINAL_MARKS):
            shown = status[:40] + ("…" if len(status) > 40 else "")
            errors.append(f"{label}: 状态未回填为终态（当前「{shown}」）")

    if errors:
        for err in errors:
            print(f"[FAIL] {err}", file=sys.stderr)
        print(f"共检查 {len(targets)} 份计划文档，{len(errors)} 项未通过；"
              "发布前必须全部回填（AGENTS.md §5.2 第 2 步）", file=sys.stderr)
        return 1
    print(f"OK — {len(targets)} 份计划文档状态均已回填为终态")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
