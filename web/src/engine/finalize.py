"""终态文件管线（m1-plan §4.3 B9）：formchk、保全快照、过期清理。

- formchk：succeeded 后以 <g16_root>/formchk 将 chk 转 .fchk 留在
  run/<id>/；chk 路径取实际执行副本 Link0 %Chk（相对值相对 run/<id>/），
  无声明回落 input.chk（g16 无 %Chk 不产 chk，转换失败记日志不阻断）；
- 保全快照：非正常终止（failed，含程序报错/外部中断/手动停止）时
  run/<id>/ 顶层 chk/rwf 改名移入 protected/ 并落库 chk_snapshot
  （M1 落地保全，M4 断点续跑与 B10 重定向消费）；
- 清理：POST /history/cleanup 手动触发——仅删「正常结束（succeeded）且
  超保留期」的 run/<id>/ 顶层 .chk/.rwf，**永不触碰 .out/.log/输入**；
  protected/ 仅用户经文件系统手动清（m1-plan §8 决策点 11）。
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

_CHK_RE = re.compile(r"^%chk\s*=\s*(.+)$", re.IGNORECASE)
# 保全/清理作用的瞬态文件扩展（小写比对）；其余（.out/.log/输入）永不触碰
TRANSIENT_EXTS = (".chk", ".rwf")

_PROTECTED_DIR = "protected"

ANALYSIS_NAME = "analysis.json"
ANALYSIS_TIMEOUT_S = 60


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
    from ..parse import results as results_parse
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
    """非正常终止保全：run/<id>/ 顶层 chk/rwf 移入 protected/。

    返回 chk_snapshot：{"protected": 是否有文件被保全,
    "location": "protected" | None}（契约：正常结束/无可保全时 location
    为 null）。
    """
    if not run_dir.is_dir():
        return {"protected": False, "location": None}
    moved = 0
    for f in sorted(run_dir.iterdir()):
        if not f.is_file() or f.suffix.casefold() not in TRANSIENT_EXTS:
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


def cleanup_expired(entries: list[dict], run_root: Path,
                    retention_days: int, now: datetime) -> dict:
    """手动清理：仅删「succeeded 且 finished_at 超保留期」的 run/<id>/
    顶层 .chk/.rwf。protected/ 子目录与其余文件永不触碰。

    返回 {"checked", "removed_chk", "removed_rwf"}；checked = 检查的
    正常结束执行数（run 目录存在者）。
    """
    stats = {"checked": 0, "removed_chk": 0, "removed_rwf": 0}
    horizon = now - timedelta(days=retention_days)
    for row in entries:
        if row.get("state") != "succeeded":
            continue  # failed 的瞬态件由 protected/ 保全，不属清理范围
        run_d = run_root / str(row["id"])
        if not run_d.is_dir():
            continue
        stats["checked"] += 1
        finished = row.get("finished_at")
        if not finished or _iso(finished) > horizon:
            continue  # 未超保留期
        for f in sorted(run_d.iterdir()):
            if not f.is_file() or f.suffix.casefold() not in TRANSIENT_EXTS:
                continue
            f.unlink()
            if f.suffix.casefold() == ".chk":
                stats["removed_chk"] += 1
            else:
                stats["removed_rwf"] += 1
    return stats
