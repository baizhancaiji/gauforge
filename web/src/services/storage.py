"""空间占用统计与告警（M3.7 B12，m3-plan §2.6/§4.13）：纯拉取式只读统计。

- 定位：roadmap §7 开放事项 5① 裁决的替代面——只统计与警告，**绝不自动
  清理**；无定时器、无后台任务（历史页加载与 history.appended 后拉取）；
- total_bytes：工作区根（G16WEB_HOME）整树 apparent size——run/ 产物树、
  数据库及 hq 状态、inputs 等全部内容计入（目录条目计入 apparent size，
  与 du -sb <工作区根> 同口径，并发落盘下允许条目竞态容差）；运行中执行
  目录与无执行行的孤儿目录一并计入（全态一致）；
- entries[]：per-execution 明细（总量 + 可清理量），仍按 run/<id> 分桶，
  桶外内容仅计入总量、不产生明细；按 total_bytes 降序，默认截断前 50 条
  （truncated/total_entries 标注）；含运行中条目（reclaimable 恒 0）；
- reclaimable_bytes 与 M1 清理边界单一实现（finalize.reclaimable_files，
  含「仅 succeeded 且超保留期的顶层 chk/rwf」与「保全快照计 0」口径）；
- 只读：只 stat/遍历，不触碰、不移动任何文件；清理动作后统计即时反映；
- 统计为工作区根整树单遍历（每条目一次 stat，total 与明细一遍完成）+
  执行行一次全量缓存（C8 收敛，原 2× 遍历 + N+1 点查退役）；
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
    """GET /storage/usage 响应（契约 StorageUsage）。

    C8 单遍历收敛（§2.6 实现注记，2026-10-01 审核裁决）：工作区根整树
    os.walk 一遍、每条目恰一次 stat，run/<id> 顶层执行目录分桶累加
    （total 与 per-execution 明细一遍完成，桶外内容仅进总量）；执行行
    一次取全量缓存，替代原「2× 遍历 + N+1 点查」。口径（A-10 扩面）：
    total 与 du -sb <工作区根> 同口径（含 run/ 外的 db/hq 状态/inputs），
    运行中与孤儿目录全态一致。
    """
    now = now or datetime.fromisoformat(now_iso())
    home = config.HOME_DIR
    run_root = home / "run"
    retention = int(settings().get("chk_rwf_retention_days"))
    warn_gb = int(settings().get("disk_usage_warn_gb"))

    rows = {r["id"]: r for r in executions().list_all()}
    total = 0
    per_exec: dict[int, int] = {}
    if home.is_dir():
        try:
            total += home.stat().st_size  # 工作区根自身条目（du -sb 含根）
        except OSError:
            return {"total_bytes": 0, "threshold_bytes": warn_gb * 1024 ** 3,
                    "over": False, "entries": [], "total_entries": 0,
                    "truncated": False}
        for root, dirs, files in os.walk(home):
            root_p = Path(root)
            cur: int | None = None
            if root_p != run_root and root_p.is_relative_to(run_root):
                head = root_p.relative_to(run_root).parts[0]
                if head.isdigit() and int(head) in rows:
                    cur = int(head)
            for name in (*dirs, *files):
                try:
                    size = (root_p / name).stat().st_size
                except OSError:
                    continue  # 竞态消失的条目按 0 计
                total += size
                if cur is not None:
                    per_exec[cur] += size
                elif root_p == run_root and name.isdigit() \
                        and int(name) in rows:
                    # 顶层执行目录条目自身归各自桶（目录 inode 尺寸）
                    per_exec[int(name)] = per_exec.get(int(name), 0) + size

    entries = []
    for eid, size in per_exec.items():
        row = rows[eid]
        reclaimable = sum(f.stat().st_size
                          for f in finalize.reclaimable_files(
                              run_root / str(eid), row, retention, now))
        entries.append({"execution_id": eid, "task_id": row["task_id"],
                        "filename": row["filename"], "total_bytes": size,
                        "reclaimable_bytes": reclaimable})
    entries.sort(key=lambda e: e["total_bytes"], reverse=True)
    return {"total_bytes": total,
            "threshold_bytes": warn_gb * 1024 ** 3,
            "over": over_state(total, warn_gb),
            "entries": entries[:ENTRY_LIMIT],
            "total_entries": len(entries),
            "truncated": len(entries) > ENTRY_LIMIT}
