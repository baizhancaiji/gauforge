"""重启对账（m1-plan §4.3 B10、§2.4 五场景矩阵）。

启动序列（§2.4）：加载 SQLite 全量状态 → 确保 HQ server/worker 存活
（engine/startup）→ Gateway 拉取 HQ job 全量 → 对本地 state='running'
的执行记录按 hq_job_id 逐条对照：

| 场景 | 判定 | 处置 |
|---|---|---|
| S1 g16web 重启，HQ 活着、job 在跑 | job 非终态且非重跑 | 接管：started_at 缺失则回填；监视器按库内 started_at 重新播种（进程树重定位/位点重扫由 monitor/progress 首轮 catch-up 自然完成），不落历史 |
| S2 重启期间 job 已终态 | job ∈ 终态映射表 | 幂等冻结：按 §8.7 归因映射落历史，monitor_summary 置空（监视器内存态已丢失） |
| S3 WSL2 整体重启，journal 恢复重跑 | job 非终态且重跑特征成立 | run/<id>/ 存在 chk → 取消语义下保全（chk/rwf 入 protected/）、原执行归因 external_interrupt 落历史、以新执行目录**原样重提交**（重定向，防 g16 重写 %CHK；断点续跑注入属 M4）；无 chk → 接管跟踪重跑（结局即原执行结局） |
| S4 HQ server 丢失 / journal 缺失 | 本地 running 无对应 job（含无 hq_job_id 的僵尸行） | 归因 external_interrupt 落历史（chk 若在则保全），终态管线照常（席位释放/队列分流） |
| S5 worker 失联自动重试 | job 中途失联又 Running | 不中途落历史（与 S1 同为接管），仅最终终态入历史 |

S3 重跑特征（§2.4 ③，H4 实测结论）：① job 状态回退 waiting 且本地已有
started_at（journal 恢复后任务回退 waiting、worker 重连后从头重跑）——
对账时点即可判定；② 进程 create_time 显著晚于本地 started_at
（> RERUN_TOLERANCE_S）——回 running 后的佐证；③ server 本次生命周期
被重新 spawn 且本地 started_at 早于 server spawn（GUI 走查实测加固：
worker 快速重连时 ①② 可被对账时点双双错过，③ 由 server spawn 时刻
给出确定性判定）。任一成立即 S3。

对账完成发 system.snapshot(server_restarted=true) 供前端全量重建。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from . import finalize
from .dispatcher import HQ_TERMINAL_MAP, Dispatcher, _mem_mib
from .monitor import psutil
from .workspace import materialize
from ..store import executions, queues, seats, settings, tasks
from ..store.db import now_iso

RERUN_TOLERANCE_S = 120.0  # 进程 create_time 晚于本地 started_at 的判定容差


def detect_rerun(execution: dict, run_dir: Path, *,
                 tolerance_s: float = RERUN_TOLERANCE_S) -> bool:
    """S3 重跑特征默认探测（create_time 佐证，§2.4 ③特征②）。

    定位 cwd=run_dir 的进程，取最早 create_time；显著晚于本地
    started_at → 重跑。定位不到进程（尚未被 worker 重启）或无
    started_at 记录 → 不判定——waiting 回退特征（§2.4 ③特征①）
    由 Reconciler 在对账时点先行判定，不走本探测。
    """
    if psutil is None:
        return False
    started = execution.get("started_at")
    if not started:
        return False
    try:
        base = datetime.fromisoformat(started).timestamp()
    except ValueError:
        return False
    earliest: float | None = None
    for proc in psutil.process_iter(["pid", "cwd", "create_time"]):
        try:
            if proc.info["cwd"] != str(run_dir):
                continue
            ct = float(proc.info["create_time"] or 0.0)
            earliest = ct if earliest is None else min(earliest, ct)
        except (psutil.NoSuchProcess, psutil.AccessDenied,
                psutil.ZombieProcess):
            continue
    if earliest is None:
        return False
    return earliest - base > tolerance_s


def has_chk(run_dir: Path) -> bool:
    """run/<id>/ 顶层是否存在 chk（S3 重定向判据；rwf 不参与判定）。"""
    if not run_dir.is_dir():
        return False
    return any(f.is_file() and f.suffix.casefold() == ".chk"
               for f in run_dir.iterdir())


class Reconciler:
    """§2.4 五场景对账器：经 Dispatcher 复用终态管线（归因/席位/队列分流）。"""

    def __init__(self, dispatcher: Dispatcher) -> None:
        self._d = dispatcher

    def run(self) -> dict:
        """全量对账一轮；HQ 不可达时 GatewayError 上抛（调用方重试）。"""
        jobs = {int(j["id"]): j for j in self._d._gw.jobs()}
        summary: dict[str, list[int]] = {"takeover": [], "terminal": [],
                                         "redirect": [], "lost": []}
        for row in executions().list_by_state("running"):
            jid = row.get("hq_job_id")
            job = jobs.get(int(jid)) if jid is not None else None
            if job is None:
                summary["lost"].append(row["id"])
                self._s4_external_interrupt(row)
            elif job["state"] in HQ_TERMINAL_MAP:
                summary["terminal"].append(row["id"])
                self._s2_settle(row, job["state"])
            else:  # running / waiting：在跑或待启动
                run_d = self._d._run_root / str(row["id"])
                # S3 判据（§2.4 ③）：① job 状态回退 waiting 且本地曾 running；
                # ② create_time 佐证（已回 running 者）；③ server 本次生命
                # 周期被重新 spawn 且本地 started_at 早于 server spawn——
                # journal 恢复重跑的确定性证据（前两者可能被对账时点错过：
                # GUI 走查实测 worker 快速重连时 waiting 相位与进程证据均缺席）。
                spawn_ts = self._d.server_spawn_ts
                rerun = (spawn_ts is not None
                         and bool(row.get("started_at"))
                         and row["started_at"] < spawn_ts) \
                    or (job["state"] == "waiting"
                        and bool(row.get("started_at"))) \
                    or self._d._rerun_probe(row, run_d)
                if rerun:
                    if has_chk(run_d) and self._seat_holds(row):
                        summary["redirect"].append(row["id"])
                        self._s3_redirect(row)
                        continue
                    # S5 重试识别 / S3 无 chk：接管不误判，不中途落历史
                summary["takeover"].append(row["id"])
                self._takeover(row, job)
        self._emit_snapshot()
        return summary

    # ---------------- 各场景处置 ----------------

    def _takeover(self, row: dict, job: dict) -> None:
        """S1/S5：接管在跑执行；started_at 缺失且 job 已在跑时回填。"""
        started = row.get("started_at")
        if not started and job["state"] == "running":
            started = now_iso()
            executions().set_started_at(row["id"], started)
        self._d._monitor.note_started(row["id"], started or now_iso())

    def _s2_settle(self, row: dict, hq_state: str) -> None:
        """S2：按终态映射补齐历史（monitor_summary 置空）。"""
        self._d._on_terminal(row, *HQ_TERMINAL_MAP[hq_state],
                             monitor_summary=None)

    def _s4_external_interrupt(self, row: dict) -> None:
        """S4：无对应 job → 外部中断落历史（终态管线照常）。"""
        self._d._on_terminal(row, "failed", "external_interrupt",
                             monitor_summary=None)

    def _s3_redirect(self, row: dict) -> None:
        """S3：chk 保全 → 原执行归因外部中断 → 新执行目录原样重提交。"""
        d = self._d
        run_d = d._run_root / str(row["id"])
        snap = finalize.protect_transient(run_d)
        # 原执行冻结但不离席（release=False：席位/队列由新执行延续）
        d._on_terminal(row, "failed", "external_interrupt",
                       monitor_summary=None, chk_snapshot=snap, release=False)
        self._resubmit(row, run_d)

    def _resubmit(self, row: dict, old_run_d: Path) -> None:
        """以 run/<旧id>/input.gjf 实际执行副本原样重提交（新执行目录）。"""
        d = self._d
        try:
            text = (old_run_d / "input.gjf").read_text(
                encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[reconcile] S3 重定向失败：执行副本不可读 {exc}",
                  file=sys.stderr)
            return
        g16_root = Path(str(settings().get("g16_root"))).expanduser()
        resources = row.get("resources") or {}
        eid2 = executions().create(
            task_id=row["task_id"], filename=row["filename"],
            resources=resources, queue_id=row.get("queue_id"),
            input_hash=row.get("input_hash"), state="running")
        try:
            run_d2, _ = materialize(d._run_root, eid2, text, g16_root)
            nproc = int((resources.get("nproc") or {}).get("value") or 0)
            job_id = d._gw.submit(
                [str(g16_root / "g16"), "input.gjf"], cwd=str(run_d2),
                name=row["filename"],
                resources={"cpus": nproc,
                           "mem_mib": _mem_mib((resources.get("mem_gb")
                                                or {}).get("value") or 0)},
                time_limit_s=self._task_time_limit(row["task_id"]))
        except Exception as exc:  # 提交/物化失败：回收新行，原执行已落历史
            executions().delete(eid2)
            print(f"[reconcile] S3 重定向提交失败（执行 {eid2} 已回收）：{exc}",
                  file=sys.stderr)
            return
        executions().update_hq_job_id(eid2, int(job_id))
        d._monitor.note_started(eid2, now_iso())
        extra = ({"queue_id": row["queue_id"]}
                 if row.get("queue_id") else {})
        d._emit("task.status",
                {"task_id": row["task_id"], "execution_id": eid2, **extra,
                 "from": "staged", "to": "running", "ts": now_iso()})

    @staticmethod
    def _task_time_limit(task_id: int) -> int:
        t = tasks().get(task_id)
        return int(t.get("time_limit_s") or 0) if t else 0

    # ---------------- 辅助 ----------------

    def _seat_holds(self, row: dict) -> bool:
        """任务仍占席（单任务席位在席，或队列席位且仍为队列成员）。"""
        tid, qid = row["task_id"], row.get("queue_id")
        for s in seats().list_by_position():
            if s["kind"] == "task" and s["task_id"] == tid:
                return True
            if s["kind"] == "queue" and qid and s["queue_id"] == qid \
                    and any(m["id"] == tid
                            for m in tasks().list_queue_members(qid)):
                return True
        return False

    def _emit_snapshot(self) -> None:
        """对账完成：system.snapshot(server_restarted=true) 全量重建基线。"""
        from ..services.snapshot import system_snapshot
        self._d._emit("system.snapshot", system_snapshot(server_restarted=True))
