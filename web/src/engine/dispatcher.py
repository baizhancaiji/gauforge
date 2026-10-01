"""派发引擎（m1-plan §4.3 B6；roadmap §2.1 派发原则、§2.3 派发引擎与执行流水线）。

核心循环「事件驱动 + 状态推进」（引擎为后台线程，B10 挂启动序列）：

1. 执行序列展开：seats 按 position → 单任务席位取自身、队列席位展开为
   当前成员序列（tasks.position），单任务与队列成员平权扁平化；
2. 并行窗口推进：自序列头按序取未终态任务直到窗口满（在跑数 =
   parallel_window）或序列尽——只有在真正要派发下一任务时才取其信息
   （输入哈希、Link0 解析均在该时点）；
   ① 哈希跳过：存在 succeeded 执行且当前输入哈希 == 该次 input_hash
     → 沿用既有结果不建执行记录（成员状态保持 succeeded）；
   ② Link0 解析补齐：%NProcShared/%Mem 缺失按设置缺省注入；
   ③ 声明资源停等：声明 > 空闲（worker 总资源 − 在跑声明值之和）→
     窗口停在该任务等待释放，不越位取其后小任务（队头阻塞显式接受）；
   ④⑤ 物化 run/<id>/ → Gateway.submit（资源双账第二账：cpus/mem_mib
     随任务提交 HQ）→ 回填 hq_job_id → task.status(staged→running)。
3. 任务结束补位：poll_events 差分发现终态 → 终态映射（finished→succeeded、
   failed→failed(program_error)、canceled→failed(manually_stopped)）→
   失败分流（§2.1）→ 席位释放 → 补位（保序）。

失败分流：未勾跳过——出错成员记 failed、未启动成员即时 skipped
(predecessor_failed)、在跑成员任其跑完、队列即刻回退未提交
(abort_on_failure)；勾选跳过——继续取未启动成员，全部结束时按
finished_with_failures 处理；手动停止——在跑成员全部被 stop，
未执行成员 skipped(queue_manually_stopped) + 整队回退
(manually_stopped)；全部成功 → completed(success)。

队列席位待全部成员完成后统一释放；失败回退后队列状态不再变动，
仅在跑成员收尾结束后释放席位。窗口之外的一切在真正执行前都可能被修改
（提交时的顺序不构成承诺）。
"""
from __future__ import annotations

import sys
import threading
import time
import traceback
from pathlib import Path

from .. import config
from ..hq.gateway import Gateway, GatewayError
from ..store import executions, queues, seats, settings, tasks
from ..store.db import now_iso
from . import finalize, workspace
from .monitor import ExecutionMonitor
from .progress import ProgressTracker

# HQ job 终态 → (TaskState, FailureCause)（§8.7 归因映射：程序报错/手动停止）
HQ_TERMINAL_MAP = {
    "finished": ("succeeded", None),
    "failed": ("failed", "program_error"),
    "canceled": ("failed", "manually_stopped"),
}

_SUMMARY_AUTO = object()  # monitor_summary/chk_snapshot 缺省：按既有管线取值


def _mem_mib(gb: float) -> int:
    return int(round(float(gb) * 1024))


def _declared(execution: dict) -> tuple[int, int]:
    """执行记录 Link0 声明值 → (cpus, mem_mib)，停等记账用。"""
    res = execution.get("resources") or {}
    nproc = int((res.get("nproc") or {}).get("value") or 0)
    mem_gb = (res.get("mem_gb") or {}).get("value") or 0
    return nproc, _mem_mib(mem_gb)


class Dispatcher:
    def __init__(self, gateway: Gateway, *, emitter=None,
                 run_root: Path | None = None,
                 monitor: ExecutionMonitor | None = None,
                 rerun_probe=None) -> None:
        self._gw = gateway
        self._emit = emitter if emitter is not None else self._mock_emit
        self._run_root = run_root if run_root is not None \
            else config.HOME_DIR / "run"
        self._monitor = monitor if monitor is not None else ExecutionMonitor(
            float(settings().get("stall_threshold_minutes")))
        self._progress = ProgressTracker()
        if rerun_probe is not None:
            self._rerun_probe = rerun_probe
        else:  # 延迟导入：reconcile 反向复用本模块（避免模块级环）
            from .reconcile import detect_rerun
            self._rerun_probe = detect_rerun
        self._reconciled = False  # 启动对账闩：成功一次后不再重复（B10）
        # HQ server 本次生命周期被重新 spawn 的时刻（startup 接线；
        # None=复用存活实例）。S3 对账判据③：server 比 job 新 ⇒ journal
        # 恢复重跑（确定性，不受对账时点竞态影响）。
        self.server_spawn_ts: str | None = None
        # 侧栏 HQ 连通性（hq.status，sse.md §2 契约增量）：None=尚未探测
        # （首 tick 定初值）；workers_online 为探测到的在线 worker 数。
        self.hq_state: str | None = None
        self.hq_workers_online = 0
        # 队列执行周期水位：qid → (基准 updated_at, 周期起点最大执行 id)，
        # 供 _executed_this_cycle 以 id 判定周期归属（秒级时间戳同秒竞态规避）
        self._cycle_watermark: dict[str, tuple[str, int]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------- 事件发射（B11 真实化前经 mock 记入重放窗口） ----------------

    @staticmethod
    def _mock_emit(event: str, data: dict) -> None:
        from ..mock import get_state
        get_state().emit(event, data)

    # ---------------- 执行序列展开 ----------------

    def expand_sequence(self) -> list[dict]:
        """seats 按 position 展开为扁平执行序列。

        条目：{"seat_id", "kind", "task_id", "queue_id", "filename"}；
        队列席位展开为当前成员序列（派发当下最新值，窗口外可随时修改）。
        """
        seq: list[dict] = []
        for s in seats().list_by_position():
            if s["kind"] == "task":
                row = tasks().get(s["task_id"])
                if row is not None:
                    seq.append({"seat_id": s["seat_id"], "kind": "task",
                                "task_id": row["id"], "queue_id": None,
                                "filename": row["filename"]})
            else:
                for m in tasks().list_queue_members(s["queue_id"]):
                    seq.append({"seat_id": s["seat_id"], "kind": "queue",
                                "task_id": m["id"],
                                "queue_id": s["queue_id"],
                                "filename": m["filename"]})
        return seq

    # ---------------- 窗口推进 ----------------

    def advance(self) -> None:
        """自序列头按序推进并行窗口（哈希跳过/停等/物化/提交/回填）。"""
        window = int(settings().get("parallel_window"))
        # 停滞阈值逐 tick 跟随设置（新任务生效）：新建监测 entry 用当前值，
        # 已在跑 entry 的检测器保有创建时刻阈值，不追溯。
        self._monitor.threshold = float(settings().get("stall_threshold_minutes"))
        running = executions().list_by_state("running")
        if len(running) >= window:
            return
        try:
            workers = self._gw.workers()
        except GatewayError:
            return  # HQ 不可达：全部停等
        total_cpus = sum(int(w.get("cpus") or 0) for w in workers
                         if w.get("online"))
        total_mem = sum(int(w.get("mem_mib") or 0) for w in workers
                        if w.get("online"))
        claimed_cpus = sum(_declared(e)[0] for e in running)
        claimed_mem = sum(_declared(e)[1] for e in running)
        running_task_ids = {e["task_id"] for e in running}

        for item in self.expand_sequence():
            if len(running) >= window:
                break
            if item["task_id"] in running_task_ids:
                continue  # 同任务不重复派发（防御）
            task = tasks().get(item["task_id"])
            if task is None:
                continue
            if item["queue_id"] is not None:
                q = queues().get(item["queue_id"])
                # 队列仅 submitted/executing 可派发：回退（unsubmitted）或已完成
                # （completed）后席位残余成员不再派发（席位待在跑收尾释放）
                if q is None or q["state"] not in ("submitted", "executing"):
                    continue
                self._refresh_cycle_watermark(q)
                # 本周期已有执行记录者不重复派发（failed/succeeded 终态成员）
                if self._executed_this_cycle(task["id"], q):
                    continue
            inputs = self._inputs_path(task["id"])
            if not inputs.is_file():
                continue  # 输入副本缺失：不可派发（导入目录异常，防御跳过）
            text = inputs.read_text(encoding="utf-8", errors="replace")
            resolved = workspace.resolve_link0(
                text, int(settings().get("link0_default_nproc")),
                float(settings().get("link0_default_mem_gb")))
            input_hash = workspace.content_hash(resolved["completed_text"])

            # ① 哈希跳过：上次成功且输入哈希一致 → 沿用结果，序列越过
            if self._hash_skip(task["id"], input_hash):
                if item["kind"] == "task":
                    self._release_seat_task(task["id"])
                continue

            # ③ 声明资源停等：窗口停在该任务，不越位（mem 维度仅当 worker 上报）
            nproc = int(resolved["nproc"]["value"])
            mem = _mem_mib(resolved["mem_gb"]["value"])
            if nproc > total_cpus - claimed_cpus:
                break
            if total_mem and mem > total_mem - claimed_mem:
                break

            eid = self._dispatch(item, task, resolved, input_hash)
            running.append(executions().get(eid))  # type: ignore[arg-type]
            claimed_cpus += nproc
            claimed_mem += mem

    def _hash_skip(self, task_id: int, input_hash: str) -> bool:
        return any(e["state"] == "succeeded" and e["input_hash"] == input_hash
                   for e in executions().list_by_task(task_id))

    def _executed_this_cycle(self, task_id: int, queue: dict) -> bool:
        """本执行周期内是否已有执行记录。

        周期归属以「执行 id 水位」判定（advance 观察 submitted 态时以当下
        最大执行 id 为周期起点，见 _refresh_cycle_watermark）：时间戳为
        秒级 ISO，同秒内跨周期时 `>=` 比较会把上一周期记录误判为本周期
        （m2-plan §5 e2e 实测：周期 1 全部执行与周期 2 提交同秒 → 周期 2
        永不派发）。无水位（未观察到 submitted）时回退时间基准。"""
        mark = self._cycle_watermark.get(queue["id"])
        if mark is not None:
            return any(e["id"] > mark[1]
                       for e in executions().list_by_task(task_id))
        base = queue.get("updated_at") or ""
        return any((e.get("submitted_at") or "") >= base
                   for e in executions().list_by_task(task_id))

    def _refresh_cycle_watermark(self, queue: dict) -> None:
        """观察 submitted 态且基准变化（新一次提交）时重置周期水位。

        回退不重置 updated_at（见 _queue_rollback），故 updated_at 变化
        即新周期提交。"""
        qid = queue["id"]
        mark = self._cycle_watermark.get(qid)
        if queue["state"] == "submitted" \
                and (mark is None or mark[0] != queue["updated_at"]):
            self._cycle_watermark[qid] = (queue["updated_at"],
                                          executions().max_id())

    def _member_has_result(self, task_id: int) -> bool:
        """成员最近执行终态为 succeeded（哈希跳过沿用既有结果，视为已结算：
        §7.1 #5「无新执行记录、状态保持 succeeded」，失败分流不再改标
        skipped，席位结算不再视为未启动）。"""
        exs = executions().list_by_task(task_id)
        return bool(exs) and exs[-1]["state"] == "succeeded"

    def _inputs_path(self, task_id: int) -> Path:
        from ..services.candidates import default_inputs_dir
        return default_inputs_dir() / str(task_id)

    # ---------------- 派发 ----------------

    def _dispatch(self, item: dict, task: dict, resolved: dict,
                  input_hash: str) -> int:
        """④⑤ 建执行记录 → 物化 → 提交 → 回填 hq_job_id → 事件。"""
        if item["queue_id"]:
            self._queue_enter_executing(item["queue_id"])
        resources = {"nproc": resolved["nproc"], "mem_gb": resolved["mem_gb"]}
        eid = executions().create(
            task_id=task["id"], filename=task["filename"],
            resources=resources, queue_id=item["queue_id"],
            input_hash=input_hash)
        g16_root = Path(str(settings().get("g16_root"))).expanduser()
        try:
            run_d, env = workspace.materialize(
                self._run_root, eid, resolved["completed_text"], g16_root)
        except Exception:
            executions().delete(eid)  # 补偿：不留僵尸 running 行
            raise
        mem = _mem_mib(resolved["mem_gb"]["value"])
        # 监控双重校验基准：须取派发时刻（早于 HQ spawn）——轮询观察到的
        # started_at 晚于进程启动 1~2s，据此过滤会把真实 g16 进程树整体
        # 误杀（GUI 走查实测 monitor_summary 恒 0 的根因）。
        self._monitor.note_started(eid, now_iso())
        job_id = self._gw.submit(
            [str(g16_root / "g16"), "input.gjf"], cwd=str(run_d),
            name=task["filename"], env=env,
            resources={"cpus": int(resolved["nproc"]["value"]),
                       "mem_mib": mem},
            time_limit_s=int(task.get("time_limit_s") or 0))
        executions().update_hq_job_id(eid, int(job_id))
        self._emit("task.status",
                   {"task_id": task["id"], "execution_id": eid,
                    **({"queue_id": item["queue_id"]} if item["queue_id"] else {}),
                    "from": "staged", "to": "running", "ts": now_iso()})
        return eid

    def _queue_enter_executing(self, queue_id: str) -> None:
        q = queues().get(queue_id)
        if q is not None and q["state"] == "submitted":
            queues().set_state(queue_id, "executing")
            self._emit("queue.status",
                       {"queue_id": queue_id, "from": "submitted",
                        "to": "executing", "ts": now_iso()})

    # ---------------- 终态处理与失败分流 ----------------

    def tick(self) -> None:
        """一轮状态推进：HQ 连通性探测 → 消费 Gateway 事件（终态）→ 窗口推进补位。"""
        # 探测须先于 poll_events：HQ 失联时后者抛 GatewayError 提前返回，
        # 状态翻转推送不能被短路漏掉
        self._hq_status_step()
        try:
            events = self._gw.poll_events()
        except GatewayError:
            return  # HQ 不可达：本周期跳过
        for ev in events:
            if ev.get("type") != "job_state":
                continue
            mapping = HQ_TERMINAL_MAP.get(ev.get("state") or "")
            if mapping is None:
                if ev.get("state") == "running":
                    self._note_running(int(ev["job_id"]))
                continue
            row = self._find_running(int(ev["job_id"]))
            if row is not None:
                self._on_terminal(row, *mapping)
        self._progress_step()
        self._monitor_step()
        self.advance()

    def _hq_status_step(self) -> None:
        """侧栏 HQ 连通性监控（m1-acceptance §1.3 遗留项真实化）。

        以 workers 列表探测 server 可达性（CLI/HTTP 双实现同语义，随 tick
        2s 周期），状态或 worker 在线数变化才推 hq.status——稳态不重发，
        引擎未启用时无 Dispatcher、仅快照携带 hq: off。
        """
        try:
            online = sum(1 for w in self._gw.workers() if w.get("online"))
            state = "up"
        except GatewayError:
            online, state = 0, "down"
        if state == self.hq_state and online == self.hq_workers_online:
            return
        self.hq_state, self.hq_workers_online = state, online
        self._emit("hq.status",
                   {"state": state, "workers_online": online,
                    "ts": now_iso()})

    def progress_state(self, execution_id: int) -> dict | None:
        """快照恢复用：该执行当前已掌握的进度状态（未探测返回 None）。"""
        return self._progress.state(execution_id)

    def _find_running(self, job_id: int) -> dict | None:
        for e in executions().list_by_state("running"):
            if e.get("hq_job_id") == job_id:
                return e
        return None

    def _note_running(self, job_id: int) -> None:
        row = self._find_running(job_id)
        if row is not None and not row.get("started_at"):
            executions().set_started_at(row["id"], now_iso())
            self._monitor.note_started(row["id"], now_iso())

    def _on_terminal(self, execution: dict, state: str, cause: str | None, *,
                     monitor_summary=_SUMMARY_AUTO,
                     chk_snapshot=_SUMMARY_AUTO,
                     release: bool = True) -> None:
        """终态冻结管线。

        - monitor_summary/chk_snapshot 显式传参时覆盖既有取值（B10 对账：
          S2 监视器态丢失 → 置空；S3 已先行保全 → 直接落库）；
        - release=False 跳过席位释放与队列分流（S3 重定向：席位由新执行延续）。
        """
        eid, tid = execution["id"], execution["task_id"]
        run_d = self._run_root / str(eid)
        snap = chk_snapshot
        result_ref: str | None = None
        if state == "succeeded":
            # ② formchk：失败记日志不阻断（finalize.make_fchk）
            g16_root = Path(str(settings().get("g16_root"))).expanduser()
            finalize.make_fchk(run_d, g16_root)
            # ②' M3 解析步（m3-plan §4.5 B2）：input.log → analysis.json，
            #    degraded 亦落盘置位；落盘失败 result_ref=null 不阻断
            try:
                result_ref = finalize.write_analysis(run_d)
            except Exception as exc:  # noqa: BLE001  硬保证：不阻断终态
                print(f"[finalize] analysis 步异常：{exc}", file=sys.stderr)
                result_ref = None
        elif state == "failed" and snap is _SUMMARY_AUTO:
            # ③ 保全快照：非正常终止 chk/rwf 移入 protected/
            snap = finalize.protect_transient(run_d)
        if monitor_summary is _SUMMARY_AUTO:
            monitor_summary = self._monitor.summary(eid) \
                if state == "succeeded" else None
        self._monitor.settle(eid, now_iso())
        executions().finalize(execution_id=eid, state=state,
                              finished_at=now_iso(), cause=cause,
                              monitor_summary=monitor_summary,
                              chk_snapshot=None if snap is _SUMMARY_AUTO
                              else snap,
                              result_ref=result_ref)
        self._monitor.forget(eid)
        self._progress.forget(eid)
        extra = ({"queue_id": execution["queue_id"]}
                 if execution.get("queue_id") else {})
        self._emit("task.status",
                   {"task_id": tid, "execution_id": eid, **extra,
                    "from": "running", "to": state, "cause": cause,
                    "ts": now_iso()})
        self._emit("history.appended",
                   {"execution_id": eid, "task_id": tid,
                    "state": state, **extra, "cause": cause,
                    "ts": now_iso()})
        if not release:
            return  # S3 重定向：席位/队列不动，由新执行延续
        if state == "failed" and execution.get("queue_id"):
            self._handle_queue_failure(execution, cause)
        # 席位释放：单任务终态即离席；队列待全部成员终态后统一释放
        if execution.get("queue_id"):
            self._settle_queue_seat(execution["queue_id"])
        else:
            self._release_seat_task(tid)

    # ---- 失败分流（§2.1：未勾跳过即时回退；勾选跳过跑完全队再结算） ----

    def _handle_queue_failure(self, execution: dict,
                              cause: str | None) -> None:
        qid = execution["queue_id"]
        q = queues().get(qid)
        if q is None or q["state"] != "executing":
            return  # 已回退/已结算：不重复分流
        members = tasks().list_queue_members(qid)
        running_ids = {e["task_id"] for e in executions().list_by_state("running")}
        if cause == "manually_stopped":
            # 手动停止（§2.3）：未执行成员即时 skipped(queue_manually_stopped)
            # + 整队回退；在跑成员已被一并 stop，其终态事件到达时队列已
            # unsubmitted，本分支天然幂等不再分流
            for m in members:
                if self._member_settled(m, running_ids, q):
                    continue
                self._mark_skipped(m, qid, "queue_manually_stopped")
            self._queue_rollback(q, "manually_stopped",
                                 [(execution["task_id"], "failed", cause)])
            return
        if not q["skip_failed"]:
            for m in members:
                if self._member_settled(m, running_ids, q):
                    continue  # 在跑任其跑完；本周期已执行者/既有成功者不动
                self._mark_skipped(m, qid, "predecessor_failed")
            self._queue_rollback(q, "abort_on_failure",
                                 [(execution["task_id"], "failed", cause)])
        # 勾选跳过：继续取未启动成员（advance 补位自然完成）

    def _member_settled(self, member: dict, running_ids: set[int],
                        queue: dict) -> bool:
        """失败分流中「不动」的成员：在跑、本周期已执行、或既有成功结果
        （哈希跳过沿用——不误标 skipped，m2-plan §7.1 第 5 条）。"""
        return (member["id"] in running_ids
                or self._executed_this_cycle(member["id"], queue)
                or self._member_has_result(member["id"]))

    def _mark_skipped(self, member: dict, queue_id: str, cause: str) -> None:
        """未启动成员即时 skipped：终态行直接落库（无执行过程）。"""
        eid = executions().create(
            task_id=member["id"], filename=member["filename"],
            resources={"nproc": {"value": 0, "defaulted": False},
                       "mem_gb": {"value": 0, "defaulted": False}},
            queue_id=queue_id, state="skipped")
        executions().finalize(execution_id=eid, state="skipped",
                              finished_at=now_iso(), cause=cause)
        self._emit("task.status",
                   {"task_id": member["id"], "execution_id": eid,
                    "queue_id": queue_id, "from": "staged", "to": "skipped",
                    "cause": cause, "ts": now_iso()})
        self._emit("history.appended",
                   {"execution_id": eid, "task_id": member["id"],
                    "queue_id": queue_id, "state": "skipped",
                    "cause": cause, "ts": now_iso()})

    def _queue_rollback(self, queue: dict, reason: str,
                        failures: list[tuple[int, str, str | None]]) -> None:
        """队列失败回退：记 finish_reason/last_failure/回退标记 → unsubmitted。

        不重置 updated_at（周期基准=进入 submitted/executing 时点）：
        本周期已建 skipped/failed 记录须仍被 _executed_this_cycle 判为
        「本周期已执行」，席位结算 undone 判定才收敛。"""
        qid = queue["id"]
        count = int(queue.get("rollback_count") or 0) + 1
        queues().update(qid, bump_updated=False, finish_reason=reason,
                        rollback_flag=True, rollback_count=count,
                        last_failure={"finish_reason": reason,
                                      "failure_positions": [f[0] for f in failures],
                                      "members": [{"task_id": f[0],
                                                   "state": f[1],
                                                   "cause": f[2]}
                                                  for f in failures]})
        queues().set_state(qid, "unsubmitted", bump_updated=False)
        self._emit("queue.status",
                   {"queue_id": qid, "from": "executing", "to": "unsubmitted",
                    "finish_reason": reason,
                    "failure_positions": [f[0] for f in failures],
                    "rollback_count": count, "ts": now_iso()})
        # sse.md §3「任务失败」行：回退伴随 queues.changed（updated）
        self._emit("queues.changed", {"action": "updated", "queue_id": qid})

    # ---- 席位释放 ----

    def _release_seat_task(self, task_id: int) -> None:
        for s in seats().list_by_position():
            if s["kind"] == "task" and s["task_id"] == task_id:
                tasks().to_finished(task_id)
                seats().remove(s["seat_id"])
                self._emit_pending_snapshot()
                return

    def _settle_queue_seat(self, queue_id: str) -> None:
        """队列席位：全部成员终态后释放并结算队列。"""
        q = queues().get(queue_id)
        if q is None:
            return
        members = tasks().list_queue_members(queue_id)
        if any(m["id"] in {e["task_id"] for e in executions().list_by_state("running")}
               for m in members):
            return  # 仍有在跑成员：席位保留
        seat = next((s for s in seats().list_by_position()
                     if s["kind"] == "queue" and s["queue_id"] == queue_id), None)
        undone = [m for m in members
                  if not (self._executed_this_cycle(m["id"], q)
                          or self._member_has_result(m["id"]))]
        if undone:
            return  # 尚有本周期未启动成员：skip_failed 继续派发中
        states = {m["id"]: executions().list_by_task(m["id"])[-1]["state"]
                  for m in members}
        if q["state"] == "executing":
            if all(v == "succeeded" for v in states.values()):
                queues().update(queue_id, finish_reason="success",
                                last_failure=None)
                queues().set_state(queue_id, "completed")
                self._emit("queue.status",
                           {"queue_id": queue_id, "from": "executing",
                            "to": "completed", "finish_reason": "success",
                            "ts": now_iso()})
            else:
                failures = [(m["id"], states[m["id"]],
                             executions().list_by_task(m["id"])[-1]["cause"])
                            for m in members if states[m["id"]] != "succeeded"]
                self._queue_rollback(q, "finished_with_failures", failures)
        if seat is not None:
            seats().remove(seat["seat_id"])
            self._emit_pending_snapshot()

    def _progress_step(self) -> None:
        """增量解析一轮（B8）：tail run/<id>/input.log → execution.progress。

        新进度同时喂入 monitor.note_progress（停滞基准推进；置于
        _monitor_step 之前，同周期即可解除停滞）。"""
        for e in executions().list_by_state("running"):
            facts = self._progress.step(
                e["id"], self._run_root / str(e["id"]) / "input.log")
            if facts is None:
                continue
            self._monitor.note_progress(e["id"], now_iso())
            self._emit("execution.progress",
                       {"execution_id": e["id"], "task_id": e["task_id"],
                        **facts, "ts": now_iso()})

    def _monitor_step(self) -> None:
        """对全部在跑执行采样：execution.monitor（2s 节流）+ 停滞翻转。"""
        for e in executions().list_by_state("running"):
            payload, flip = self._monitor.step(
                e, self._run_root / str(e["id"]), now_iso())
            if payload is not None:
                self._emit("execution.monitor", payload)
            if flip is not None:
                stall = self._monitor._entry(e["id"])["stall"]
                self._emit("execution.stalled",
                           {"execution_id": e["id"], "task_id": e["task_id"],
                            "stalled": flip, "threshold_minutes":
                                self._monitor.threshold,
                            "last_progress_ts": stall.last_progress_ts,
                            "ts": now_iso()})

    def stop_execution(self, execution_id: int) -> None:
        """手动停止（§8.7）：Gateway.cancel → HQ Canceled → 差分终态
        failed(manually_stopped) → 席位释放走既有终态管线。"""
        row = executions().get(execution_id)
        if row is None:
            from ..errors import not_found
            raise not_found("execution", execution_id)
        if row["state"] != "running":
            from ..errors import err
            raise err("TASK_STATE_CONFLICT", "仅运行中执行可停止",
                      {"state": row["state"]}, http=409)
        if not row.get("hq_job_id"):
            from ..errors import err
            raise err("TASK_STATE_CONFLICT", "执行尚无 HQ 作业引用",
                      {"execution_id": execution_id}, http=409)
        self._gw.cancel(str(row["hq_job_id"]))

    def _emit_pending_snapshot(self) -> None:
        from ..services.pending import snapshot
        self._emit("pending.snapshot", snapshot())

    # ---------------- 重启对账（B10，编排见 reconcile.Reconciler） ----------------

    def reconcile(self) -> dict:
        """启动对账（§2.4 五场景）：HQ job 实态 ↔ 本地 running 执行对照。

        幂等闩：成功一次后跳过（重复调用返回 {}）；HQ 不可达时
        GatewayError 上抛（启动序列与引擎线程均会重试至成功）。
        """
        if self._reconciled:
            return {}
        from .reconcile import Reconciler  # 延迟导入（避免模块级环）
        summary = Reconciler(self).run()
        self._reconciled = True
        return summary

    # ---------------- 线程循环（B10 挂启动序列） ----------------

    def start(self, interval: float = 2.0) -> None:
        """启动后台推进线程（周期 tick；阻塞调用不占 async loop）。"""
        self._interval = interval
        self._thread = threading.Thread(target=self._loop, name="dispatcher",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self._reconciled:
                    try:
                        self.reconcile()
                    except GatewayError:
                        pass  # HQ 未就绪：下周期重试对账
                self.tick()
            except Exception:  # 引擎线程不因单轮异常死亡
                traceback.print_exc()
            self._stop.wait(getattr(self, "_interval", 2.0))
