#!/usr/bin/env python3
"""从 CHANGELOG.jsonl 生成人类可读的 CHANGELOG.md。

单一事实来源是 CHANGELOG.jsonl（append-only）；本脚本只做单向渲染，
禁止手工编辑 CHANGELOG.md——再次运行即可再生成，`--check` 校验两者一致
（不一致即退出码非零，可纳入提交前闸门）。

用法：
    uv run python scripts/gen_changelog_md.py            # 重新生成 CHANGELOG.md
    uv run python scripts/gen_changelog_md.py --check    # 只校验，不写文件
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JSONL_PATH = PROJECT_ROOT / "CHANGELOG.jsonl"
MD_PATH = PROJECT_ROOT / "CHANGELOG.md"

HEADER = "<!-- 本文件由 scripts/gen_changelog_md.py 从 CHANGELOG.jsonl 生成，勿手工编辑；再生成：uv run python scripts/gen_changelog_md.py -->\n\n# 变更日志\n\n"

# type -> 中文小节标题（按此顺序分组渲染，未出现的类型跳过）
TYPE_ORDER = [
    ("added", "新增"),
    ("changed", "变更"),
    ("fixed", "修复"),
    ("deprecated", "弃用"),
    ("removed", "移除"),
    ("security", "安全"),
]


def load_rows() -> list[dict]:
    rows = []
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(__import__("json").loads(line))
    return rows


def render_entry(change: dict) -> list[str]:
    scope = change.get("scope")
    prefix = f"【{scope}】" if scope else ""
    lines = [f"- {prefix}{change['summary']}"]
    if change.get("breaking"):
        lines[-1] += " **（破坏性变更）**"
        migration = change.get("migration")
        if migration:
            lines.append(f"  - 迁移指引：{migration}")
    return lines


def render_release(row: dict) -> str:
    if row.get("status") == "released":
        title = f"## v{row['version']}（{row['date']} 发布，{row['semver']}）"
    else:
        title = "## Unreleased（未发布）"

    parts = [title, ""]
    changes = row.get("changes", [])
    if not changes:
        parts += ["_暂无条目。_", ""]
        return "\n".join(parts)

    for type_key, type_label in TYPE_ORDER:
        group = [c for c in changes if c.get("type") == type_key]
        if not group:
            continue
        parts += [f"### {type_label}", ""]
        for change in group:
            parts += render_entry(change)
        parts.append("")
    return "\n".join(parts)


def render_markdown(rows: list[dict]) -> str:
    # jsonl 按发布顺序追加（旧→新），人类阅读习惯是新→旧，故倒序渲染
    sections = [render_release(row) for row in reversed(rows)]
    return HEADER + "\n".join(sections).rstrip() + "\n"


def main() -> int:
    check_only = "--check" in sys.argv[1:]
    markdown = render_markdown(load_rows())

    if check_only:
        if not MD_PATH.exists():
            print(f"check_changelog_md: FAIL — {MD_PATH.name} 不存在，请先生成")
            return 1
        if MD_PATH.read_text(encoding="utf-8") != markdown:
            print(f"check_changelog_md: FAIL — {MD_PATH.name} 与 CHANGELOG.jsonl 不一致，请重新生成")
            return 1
        print(f"check_changelog_md: OK — {MD_PATH.name} 与 CHANGELOG.jsonl 一致")
        return 0

    MD_PATH.write_text(markdown, encoding="utf-8")
    print(f"gen_changelog_md: 已生成 {MD_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
