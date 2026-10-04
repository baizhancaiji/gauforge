"""终态文件管线（m1-plan §4.3 B9；清理边界 2026-10-04 修订定稿）：
formchk、保全快照、异常收尸、过期/全量清理。

- formchk：succeeded 后以 <g16_root>/formchk 将 chk 转 .fchk 留在
  run/<id>/；chk 路径取实际执行副本 Link0 %Chk（相对值相对 run/<id>/），
  无声明回落 input.chk（g16 无 %Chk 不产 chk，转换失败记日志不阻断）；
- 保全快照：非正常终止（failed，含程序报错/外部中断/手动停止）时
  run/<id>/ 顶层 chk 改名移入 protected/ 并落库 chk_snapshot
  （M1 落地保全，M4 断点续跑消费）——保全仅 chk（rwf 无续跑消费
  价值，不再纳入保全）；
- 收尸：异常终止时立即删除顶层 Gau-* 瞬态 scratch 与任意命名 .rwf
  （g16 异常死亡来不及自清的草稿件，不留垃圾）；protected/ 与
  .out/.log/输入永不触碰；
- 清理：POST /history/cleanup 手动触发，双档——expired（默认）仅删
  「正常结束（succeeded）且超保留期」的顶层 .chk；all（「清理所有」）
  无视保留期删所有 succeeded 顶层 .chk；两档均不触碰 failed 的保全
  chk（protected/），**永不触碰 .out/.log/输入**；protected/ 仅用户经
  文件系统手动清（m1-plan §8 决策点 11）。
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from ..parse import results as results_parse  # 常量单一来源（无循环依赖）

_CHK_RE = re.compile(r"^%chk\s*=\s*(.+)$", re.IGNORECASE)
# 保全边界：仅 chk（修订定稿：rwf/Gau-* 即终收尸，不再保全）
PROTECT_SUFFIX = ".chk"
# 收尸边界：Gau-<pid>.rwf/int/d2e/skr/inp 等 g16 瞬态 scratch + 任意命名
# .rwf；.out/.log/输入永不触碰
REAP_PREFIX = "gau-"
REAP_SUFFIX = ".rwf"

_PROTECTED_DIR = "protected"

ANALYSIS_NAME = "analysis.json"
# 解析超时预算与 workspace-out 同款 60s（单一来源：parse/results）
ANALYSIS_TIMEOUT_S = results_parse.PARSE_TIMEOUT_S


def write_analysis(run_dir: Path, *,
                   timeout_s: int = ANALYSIS_TIMEOUT_S) -> str | None:
    """M3 解析步（m3-plan §4.5 B2）：succeeded 后解析 input.log →
    run/<id>/analysis.json（临时文件+rename 原子写）。

    - 解析异常/超时由 parse_output 保底按 degraded 落地（不抛出），
      degraded 产物照常落盘（result_ref 置位口径 §2.1 含 degraded）；
    - 落盘失败（磁盘等 OSError）记日志返回 None，不阻断终态管线
      （沿用 formchk「失败不阻断」先例）；
    - 返回 result_ref 值："analysis.json"（落盘成功，含 degraded）| None。
    """
    try:
        payload = results_parse.parse_output(run_dir / "input.log",
                                             timeout_s=timeout_s)
    except Exception as exc:  # noqa: BLE001  parse_output 不抛出，防御兜底
        print(f"[finalize] analysis 解析异常：{exc}", file=sys.stderr)
        return None
    tmp = run_dir / (ANALYSIS_NAME + ".tmp")
    try:
        tmp.write_text(results_parse.dumps_compact(payload), encoding="utf-8")
        tmp.replace(run_dir / ANALYSIS_NAME)
    except OSError as exc:
        print(f"[finalize] analysis 落盘失败：{exc}", file=sys.stderr)
        return None
    return ANALYSIS_NAME


def _iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def resolve_chk(run_dir: Path) -> Path:
    """实际执行副本 input.gjf 的 Link0 %Chk → chk 路径。

    相对值相对 run/<id>/ 解析；无扩展名时 g16 自动追加 .chk
    （g16 手册规则，实测 run/<id>/ 产物旁证），此处对齐；
    无声明回落 input.chk（此时 g16 不产 chk，formchk 将因文件
    缺失失败并按「记日志不阻断」处理）。
    """
    try:
        text = (run_dir / "input.gjf").read_text(encoding="utf-8",
                                                 errors="replace")
    except OSError:
        return run_dir / "input.chk"
    for ln in text.splitlines():
        m = _CHK_RE.match(ln.strip())
        if m:
            raw = m.group(1).strip().strip('"').strip("'")
            p = Path(raw)
            if not p.is_absolute():
                p = run_dir / p
            return p if p.suffix else p.with_name(p.name + ".chk")
    return run_dir / "input.chk"


def make_fchk(run_dir: Path, g16_root: Path) -> Path | None:
    """succeeded 后 formchk：chk → run/<id>/input.fchk。

    chk 缺失/进程失败/非零退出均记日志返回 None，不阻断终态管线。
    """
    from .workspace import g16_env
    chk = resolve_chk(run_dir)
    if not chk.is_file():
        print(f"[finalize] formchk 跳过：chk 不存在 {chk}", file=sys.stderr)
        return None
    out = run_dir / "input.fchk"
    try:
        proc = subprocess.run(
            [str(g16_root / "formchk"), str(chk), str(out)],
            cwd=str(run_dir), env=g16_env(g16_root, run_dir),
            capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[finalize] formchk 失败：{exc}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip()[:200]
        print(f"[finalize] formchk 非零退出 {proc.returncode}：{tail}",
              file=sys.stderr)
        return None
    return out if out.is_file() else None


def protect_transient(run_dir: Path) -> dict:
    """非正常终止保全：run/<id>/ 顶层 chk 移入 protected/（仅 chk）。

    返回 chk_snapshot：{"protected": 是否有文件被保全,
    "location": "protected" | None}（契约：正常结束/无可保全时 location
    为 null）。
    """
    if not run_dir.is_dir():
        return {"protected": False, "location": None}
    moved = 0
    for f in sorted(run_dir.iterdir()):
        if not f.is_file() or f.suffix.casefold() != PROTECT_SUFFIX:
            continue
        prot = run_dir / _PROTECTED_DIR
        prot.mkdir(exist_ok=True)
        target = prot / f.name
        if target.exists():  # 防覆盖（同一执行不应重复保全，防御）
            target = prot / f"{f.stem}.1{f.suffix}"
        f.rename(target)
        moved += 1
    return {"protected": moved > 0,
            "location": _PROTECTED_DIR if moved else None}


def reap_scratch(run_dir: Path) -> int:
    """异常终止收尸：删除 run/<id>/ 顶层 Gau-* 瞬态 scratch 与任意命名
    .rwf，帮 g16 收尸不留垃圾。

    返回删除数；单个文件删除失败记日志继续（不阻断终态管线，沿用
    formchk「失败不阻断」先例）。protected/ 与 .out/.log/输入永不触碰。
    """
    if not run_dir.is_dir():
        return 0
    reaped = 0
    for f in sorted(run_dir.iterdir()):
        if not f.is_file():
            continue
        if not (f.name.casefold().startswith(REAP_PREFIX)
                or f.suffix.casefold() == REAP_SUFFIX):
            continue
        try:
            f.unlink()
        except OSError as exc:
            print(f"[finalize] 收尸失败：{f.name} {exc}", file=sys.stderr)
            continue
        reaped += 1
    return reaped


def _top_level_chk(run_d: Path) -> list[Path]:
    """run/<id>/ 顶层 .chk 文件清单（两档清理共用）。"""
    return [f for f in sorted(run_d.iterdir())
            if f.is_file() and f.suffix.casefold() == PROTECT_SUFFIX]


def reclaimable_files(run_d: Path, row: dict, retention_days: int,
                      now: datetime) -> list[Path]:
    """清理边界判定（单一实现，m3-plan §2.6）：succeeded 且 finished_at
    超保留期的 run/<id>/ 顶层 .chk 文件清单。

    cleanup_expired（「清理 chk」默认档）与 storage.usage（可清理量统计）
    共用，保证 reclaimable_bytes 与清理逻辑口径同源；failed 的保全快照
    （protected/）不在边界内（计 0），.out/.log/输入永不触碰。
    """
    if row.get("state") != "succeeded" or not run_d.is_dir():
        return []
    finished = row.get("finished_at")
    if not finished or _iso(finished) > now - timedelta(days=retention_days):
        return []
    return _top_level_chk(run_d)


def _sweep(entries: list[dict], run_root: Path,
           retention_days: int | None, now: datetime | None) -> dict:
    """清理动作（两档共用）：遍历 succeeded 执行删顶层 .chk。

    retention_days/now 非 None 为超期档（reclaimable_files 边界），
    None 为「清理所有」档（无视保留期）。
    """
    stats = {"checked": 0, "removed_chk": 0}
    for row in entries:
        run_d = run_root / str(row["id"])
        if row.get("state") != "succeeded" or not run_d.is_dir():
            continue  # failed 的 chk 由 protected/ 保全，不属清理范围
        stats["checked"] += 1
        files = (reclaimable_files(run_d, row, retention_days, now)
                 if retention_days is not None else _top_level_chk(run_d))
        for f in files:
            f.unlink()
            stats["removed_chk"] += 1
    return stats


def cleanup_expired(entries: list[dict], run_root: Path,
                    retention_days: int, now: datetime) -> dict:
    """「清理 chk」默认档：仅删「succeeded 且超保留期」的 run/<id>/
    顶层 .chk（边界判定见 reclaimable_files）。protected/ 子目录与
    其余文件永不触碰。

    返回 {"checked", "removed_chk"}；checked = 检查的正常结束执行数
    （run 目录存在者）。
    """
    return _sweep(entries, run_root, retention_days, now)


def cleanup_all(entries: list[dict], run_root: Path) -> dict:
    """「清理所有」档：无视保留期立即删所有 succeeded 执行的顶层 .chk；
    failed 的 chk（含 protected/ 保全）依旧保留。

    返回 {"checked", "removed_chk"}，口径同 cleanup_expired。
    """
    return _sweep(entries, run_root, None, None)
