"""空间占用统计与告警（M3.7 B12，m3-plan §2.6/§4.13）：纯拉取式只读统计。

- 定位：roadmap §7 开放事项 5① 裁决的替代面——只统计与警告，**绝不自动
  清理**；无定时器、无后台任务（历史页加载与 history.appended 后拉取）；
- total_bytes：run/ 下全部执行目录总占用（含输入/输出/scratch/chk/rwf/
  protected/cubes，目录条目计入 apparent size，与 du -sb 同口径）；
- entries[]：per-execution 明细（总量 + 可清理量），按 total_bytes 降序，
  默认截断前 50 条（truncated/total_entries 标注）；
- reclaimable_bytes 与 M1 清理边界单一实现（finalize.reclaimable_files，
  含「仅 succeeded 且超保留期的顶层 chk/rwf」与「保全快照计 0」口径）；
- 只读：只 stat/遍历，不触碰、不移动任何文件；清理动作后统计即时反映；
- 阈值：运行级设置 disk_usage_warn_gb（整数 GB，0=禁用，即时生效）；
  threshold_bytes > 0 且 total_bytes ≥ threshold_bytes ⇒ over=true。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .. import config
from ..engine import finalize
from ..store import executions, settings
from ..store.db import now_iso

ENTRY_LIMIT = 50  # entries 默认截断前 50 条（§2.6 定稿）


def over_state(total_bytes: int, warn_gb: int) -> bool:
    """阈值判定（单一实现）：threshold_bytes > 0 且 total_bytes ≥
    threshold_bytes ⇒ over=true；warn_gb=0 恒 false（禁用告警）。"""
    threshold_bytes = warn_gb * 1024 ** 3
    return threshold_bytes > 0 and total_bytes >= threshold_bytes


def usage(now: datetime | None = None) -> dict:
    """GET /storage/usage 响应（契约 StorageUsage）。"""
    now = now or datetime.fromisoformat(now_iso())
    run_root = config.HOME_DIR / "run"
    retention = int(settings().get("chk_rwf_retention_days"))
    warn_gb = int(settings().get("disk_usage_warn_gb"))

    rows = _terminal_rows()
    entries = []
    total_bytes = 0
    if run_root.is_dir():
        # run 根目录条目计入 total（du -sb run/ 同口径）
        try:
            total_bytes += os.stat(run_root).st_size
        except OSError:
            pass
    for row in rows:
        run_d = run_root / str(row["id"])
        if not run_d.is_dir():
            continue  # 无执行目录（skipped 等）不计入占用明细
        size = _dir_size(run_d)
        total_bytes += size
        reclaimable = sum(f.stat().st_size
                          for f in finalize.reclaimable_files(
                              run_d, row, retention, now))
        entries.append({"execution_id": row["id"], "task_id": row["task_id"],
                        "filename": row["filename"], "total_bytes": size,
                        "reclaimable_bytes": reclaimable})
    entries.sort(key=lambda e: e["total_bytes"], reverse=True)
    return {"total_bytes": total_bytes,
            "threshold_bytes": warn_gb * 1024 ** 3,
            "over": over_state(total_bytes, warn_gb),
            "entries": entries[:ENTRY_LIMIT],
            "total_entries": len(entries),
            "truncated": len(entries) > ENTRY_LIMIT}


def _terminal_rows() -> list[dict]:
    """全部终态行（三态合并；单机量级小，全量载入可忽略）。"""
    rows: list[dict] = []
    for state in ("succeeded", "failed", "skipped"):
        rows.extend(executions().list_by_state(state))
    return rows


def _dir_size(path: Path) -> int:
    """目录 apparent size（自身条目 + 递归文件/子目录，与 du -sb 同口径）；
    只读遍历，竞态消失的条目按 0 计。"""
    total = 0
    try:
        total += os.stat(path).st_size  # 目录自身条目（os.walk 不含根）
    except OSError:
        return 0
    for root, dirs, files in os.walk(path):
        for name in (*dirs, *files):
            try:
                total += os.stat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total
