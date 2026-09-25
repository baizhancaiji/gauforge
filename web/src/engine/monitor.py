"""执行监控（m1-plan §4.3 B7；roadmap §2.3 监视器、§8.4）。

- ProcessSampler：psutil 定位 g16 进程树——cwd=run/<id>/ + 进程启动时间
  双重校验（防目录复用误采），CPU 取采样差值、内存树内 RSS 汇总
  （g16 依次派生 l*.exe 段进程）；
- StallDetector：停滞状态机（翻转才推）——超阈值无新优化步/SCF → 置位、
  恢复新进度 → 解除；冷启动宽限：last_progress_ts 初始取启动时刻；
  只提示不自动终止（红线，roadmap M1）；
- ExecutionMonitor：per-execution 聚合——采样节流（2s）、monitor_summary
  累计（cpu/mem 峰值、停滞告警次数与时长，仅 succeeded 条目落库）。

进度信号源：B8 增量解析产出后经 note_progress 喂入；本模块只认时间戳。
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

try:  # psutil 为 B7 起硬依赖，缺失时监控降级为缺席（不炸引擎线程）
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


class ProcessSampler:
    """进程树采样：cwd+启动时间双重校验，CPU 差值 / RSS 汇总。"""

    def __init__(self) -> None:
        self._prev_cpu: dict[int, float] = {}   # pid → 上次累计 cpu_time

    def locate(self, run_dir: Path, since: float | None) -> list:
        """定位根进程列表：cwd 匹配且 create_time ≥ since（宿主时钟秒）。

        容差 30s：run/<id>/ 目录按执行 id 唯一（AUTOINCREMENT 永不复用），
        不存在真实复用场景，宽窗口仅用于吸收「轮询观察 started_at 晚于
        进程 spawn」的时序偏差（S1 接管路径，GUI 走查实测）。
        """
        if psutil is None:
            return []
        roots = []
        for proc in psutil.process_iter(["pid", "cwd", "create_time"]):
            try:
                info = proc.info
                if info["cwd"] != str(run_dir):
                    continue
                if since is not None and (info["create_time"] or 0) < since - 30:
                    continue  # 双重校验：显著早于任务启动的进程不属本次执行
                roots.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied,
                    psutil.ZombieProcess):
                continue
        return roots

    def sample(self, run_dir: Path, since: float | None,
               elapsed: float) -> dict | None:
        """采样一次 → {"cpu_percent", "mem_rss_mb"}；未定位到进程返回 None。

        cpu_percent：树内各进程 cpu_time 差值之和 / 墙钟差 × 100（全机
        百分比语义）。mem_rss_mb：树内 RSS 汇总。
        """
        if psutil is None:
            return None
        roots = self.locate(run_dir, since)
        if not roots:
            self._prev_cpu.clear()
            return None
        tree: dict[int, object] = {}
        for r in roots:
            try:
                tree[r.pid] = r
                for c in r.children(recursive=True):
                    tree[c.pid] = c
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        total_cpu = 0.0
        seen: set[int] = set()
        for proc in list(tree.values()):
            try:
                t = proc.cpu_times()
                total = float(t.user) + float(t.system)
                prev = self._prev_cpu.get(proc.pid)
                if prev is not None:
                    total_cpu += max(0.0, total - prev)
                self._prev_cpu[proc.pid] = total
                seen.add(proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied,
                    psutil.ZombieProcess):
                continue
        # 消失进程的 prev 清理（防 pid 复用与字典无限增长）
        for pid in set(self._prev_cpu) - seen:
            self._prev_cpu.pop(pid, None)
        rss = 0.0
        for proc in tree.values():
            try:
                rss += float(proc.memory_info().rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied,
                    psutil.ZombieProcess):
                continue
        cpu_percent = total_cpu * 100.0 / max(elapsed, 0.5)
        return {"cpu_percent": round(cpu_percent, 2),
                "mem_rss_mb": round(rss / 1048576, 2)}


class StallDetector:
    """停滞状态机：翻转才推；同一停滞期置位/解除各一条。"""

    def __init__(self, threshold_minutes: float) -> None:
        self.threshold = float(threshold_minutes)
        self.last_progress_ts: str | None = None
        self.stalled = False
        self.since: str | None = None  # 当前停滞期起点（=最后进度时刻）
        self.last_flip_minutes = 0.0   # 解除翻转时携带的停滞期时长

    def note_start(self, ts: str) -> None:
        """执行启动（冷启动宽限起点）：无进度时以启动时刻为基准。"""
        if self.last_progress_ts is None:
            self.last_progress_ts = ts

    def note_progress(self, ts: str) -> None:
        self.last_progress_ts = ts

    def check(self, now_iso: str, has_progress: bool = False) -> bool | None:
        """周期判定 → True 置位 / False 解除 / None 无翻转。

        has_progress：本周期确认有新进度（B8 接入；推进基准并触发解除）。
        """
        if has_progress:
            self.last_progress_ts = now_iso
            if self.stalled:
                dur = self.stalled_minutes(now_iso)  # 先算时长再清状态
                self.stalled = False
                self.last_flip_minutes = dur
                self.since = None
                return False  # 解除
            return None
        if not self.stalled and self._expired(now_iso):
            self.stalled = True
            self.since = self.last_progress_ts  # 无进展的真实起点
            return True  # 置位
        return None

    def _expired(self, now_iso: str) -> bool:
        base = self.last_progress_ts
        if not base:
            return False
        return (_ts(now_iso) - _ts(base)).total_seconds() \
            >= self.threshold * 60

    def stalled_minutes(self, now_iso: str) -> float:
        """当前停滞期时长（分钟；非停滞期为 0）。"""
        if not self.stalled or not self.since:
            return 0.0
        return (_ts(now_iso) - _ts(self.since)).total_seconds() / 60


class ExecutionMonitor:
    """per-execution 聚合：2s 节流采样、峰值累计、停滞状态机。"""

    def __init__(self, threshold_minutes: float) -> None:
        self.threshold = float(threshold_minutes)
        self._sampler = ProcessSampler()
        self._state: dict[int, dict] = {}

    def _entry(self, execution_id: int) -> dict:
        return self._state.setdefault(execution_id, {
            "last_sample": 0.0, "started": None, "has_progress": False,
            "cpu_peak": 0.0, "mem_peak": 0.0,
            "stall_alerts": 0, "stall_total": 0.0,
            "stall": StallDetector(self.threshold)})

    def note_started(self, execution_id: int, ts: str) -> None:
        e = self._entry(execution_id)
        if e["started"] is None:
            e["started"] = ts
            e["stall"].note_start(ts)  # 冷启动宽限：基准=启动时刻

    def note_progress(self, execution_id: int, ts: str) -> None:
        """B8 增量解析产出新进度时调用：推进基准并在下一 step 解除停滞。"""
        e = self._entry(execution_id)
        e["stall"].note_progress(ts)
        e["has_progress"] = True

    def step(self, execution: dict, run_dir: Path, now_iso: str,
             *, min_interval: float = 2.0) -> tuple[dict | None, bool | None]:
        """采样一轮 → (execution.monitor 载荷 | None, stalled 翻转 | None)。

        采样瞬时失败（进程消失/不可读）→ 载荷 None，下一周期恢复；
        停滞判定独立于采样成败（sse.md §6 连续失败转停滞判定输入）。
        """
        st = self._entry(execution["id"])
        payload = None
        now_mono = time.monotonic()
        gap = now_mono - st["last_sample"]
        if gap >= min_interval:
            st["last_sample"] = now_mono
            since = None
            elapsed_s = 0.0
            if st["started"]:
                started_dt = _ts(st["started"])
                since = started_dt.timestamp()
                elapsed_s = max(0.0, (_ts(now_iso) - started_dt).total_seconds())
            sample = self._sampler.sample(run_dir, since, gap)
            if sample is not None:
                payload = {"execution_id": execution["id"],
                           "cpu_percent": sample["cpu_percent"],
                           "mem_rss_mb": sample["mem_rss_mb"],
                           "elapsed_s": elapsed_s, "ts": now_iso}
                st["cpu_peak"] = max(st["cpu_peak"], sample["cpu_percent"])
                st["mem_peak"] = max(st["mem_peak"], sample["mem_rss_mb"])
        flip = st["stall"].check(now_iso, has_progress=st.pop("has_progress",
                                                              False))
        if flip is True:
            st["stall_alerts"] += 1
        elif flip is False:  # 解除：累计本停滞期时长
            st["stall_total"] += st["stall"].last_flip_minutes
        return payload, flip

    def settle(self, execution_id: int, now_iso: str) -> None:
        """终态收尾：未解除的停滞期时长一并累计。"""
        st = self._state.get(execution_id)
        if st is not None and st["stall"].stalled:
            st["stall_total"] += st["stall"].stalled_minutes(now_iso)

    def summary(self, execution_id: int) -> dict:
        st = self._state.get(execution_id, {})
        return {"cpu_peak_percent": st.get("cpu_peak", 0.0),
                "mem_peak_mb": st.get("mem_peak", 0.0),
                "stall_alerts": st.get("stall_alerts", 0),
                "stall_total_minutes": round(st.get("stall_total", 0.0), 2)}

    def forget(self, execution_id: int) -> None:
        self._state.pop(execution_id, None)
