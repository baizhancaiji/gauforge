"""校验进度管理两文件（零回退闸门脚本，见 docs/references/changelog-spec.md §1.8）。

用法：uv run python scripts/validate_progress.py
校验内容：
  1. CHANGELOG.jsonl 逐行为合法 JSON，字段与取值符合 schema；
  2. 恰好存在一个 unreleased 行且位于末行；
  3. progress.json 为合法 JSON 且字段齐全，unreleased 与 CHANGELOG 一致。
失败输出问题清单并以非零码退出。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.jsonl"
PROGRESS = ROOT / "progress.json"

CHANGE_TYPES = {"added", "changed", "deprecated", "removed", "fixed", "security"}
PROGRESS_FIELDS = [
    "updated",
    "latest_released_version",
    "unreleased",
    "in_progress",
    "next_steps",
    "known_issues",
    "context",
]


def validate_changelog(errors: list[str]) -> list[dict]:
    rows: list[dict] = []
    lines = [ln for ln in CHANGELOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
    seen_versions: set[object] = set()
    for i, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"CHANGELOG.jsonl 第 {i} 行非法 JSON: {exc}")
            continue
        if not isinstance(row, dict):
            errors.append(f"CHANGELOG.jsonl 第 {i} 行不是 JSON 对象")
            continue
        status = row.get("status")
        if status not in {"unreleased", "released"}:
            errors.append(f"CHANGELOG.jsonl 第 {i} 行 status 非法: {status!r}")
        version = row.get("version")
        if status == "unreleased" and version is not None:
            errors.append(f"CHANGELOG.jsonl 第 {i} 行 unreleased 行 version 应为 null")
        if status == "released" and not isinstance(version, str):
            errors.append(f"CHANGELOG.jsonl 第 {i} 行 released 行缺少 version")
        if version is not None:
            if version in seen_versions:
                errors.append(f"CHANGELOG.jsonl 第 {i} 行 version 重复: {version}")
            seen_versions.add(version)
        for j, change in enumerate(row.get("changes", [])):
            if change.get("type") not in CHANGE_TYPES:
                errors.append(f"CHANGELOG.jsonl 第 {i} 行 changes[{j}] type 非法: {change.get('type')!r}")
            if change.get("breaking") and not change.get("migration"):
                errors.append(f"CHANGELOG.jsonl 第 {i} 行 changes[{j}] breaking=true 但缺 migration")
        rows.append(row)

    unreleased = [r for r in rows if r.get("status") == "unreleased"]
    if len(unreleased) != 1:
        errors.append(f"应恰好存在一个 unreleased 行，实际 {len(unreleased)} 个")
    elif rows and rows[-1].get("status") != "unreleased":
        errors.append("unreleased 行必须位于文件末尾")
    return rows


def validate_progress(errors: list[str], changelog_rows: list[dict]) -> None:
    try:
        progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"progress.json 非法 JSON: {exc}")
        return
    for field in PROGRESS_FIELDS:
        if field not in progress:
            errors.append(f"progress.json 缺字段: {field}")
    in_progress = progress.get("in_progress")
    if in_progress is not None and (
            not isinstance(in_progress, dict)
            or set(in_progress) != {"task", "note"}
            or not all(isinstance(v, str) and v for v in in_progress.values())):
        errors.append(
            'progress.json 的 in_progress 应为 null 或 {"task","note"}'
            "（均为非空字符串）")
    if not isinstance(progress.get("unreleased"), list):
        errors.append("progress.json 的 unreleased 应为数组")
        return
    changelog_unreleased = [r for r in changelog_rows if r.get("status") == "unreleased"]
    if changelog_unreleased:
        expected = changelog_unreleased[-1].get("changes", [])
        if progress["unreleased"] != expected:
            errors.append("progress.json 的 unreleased 与 CHANGELOG.jsonl 当前 unreleased 行不一致")


def main() -> int:
    errors: list[str] = []
    if not CHANGELOG.is_file():
        errors.append(f"缺少 {CHANGELOG.name}")
        rows: list[dict] = []
    else:
        rows = validate_changelog(errors)
    if not PROGRESS.is_file():
        errors.append(f"缺少 {PROGRESS.name}")
    else:
        validate_progress(errors, rows)

    if errors:
        for err in errors:
            print(f"[FAIL] {err}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
