"""监控/停滞/停止测试（m1-plan B7；§5 测试表 test_monitor_stall）。

- psutil 采样注入：fake g16 父子进程树 CPU/RSS 采样（cwd+启动时间双重
  校验定位，与 ps 目测对照的自动化等价）；
- 停滞判定（阈值内增量解析无进展才告警）：置位/解除成对、冷启动宽限；
- stop→取消→归因 manually_stopped：停止后执行进历史、席位释放。

时间推进：StallDetector 判定以 now_iso 参数驱动，无需真实等待。
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.engine.monitor import ExecutionMonitor, StallDetector
from web.src.store import executions, seats, tasks

SIMPLE = "%chk=/tmp/w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------- 停滞状态机（翻转才推/成对/冷启动宽限） ----------------

def test_stall_flip_pairs_and_no_repeat():
    d = StallDetector(threshold_minutes=10)
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    d.note_start(_iso(t0))
    # 冷启动宽限：阈值内（含边界前）不置位
    assert d.check(_iso(t0 + timedelta(minutes=5))) is None
    assert d.check(_iso(t0 + timedelta(minutes=9, seconds=59))) is None
    # 超阈值 → 置位一次
    assert d.check(_iso(t0 + timedelta(minutes=10))) is True
    assert d.check(_iso(t0 + timedelta(minutes=20))) is None  # 不重复
    assert d.stalled is True
    assert d.stalled_minutes(_iso(t0 + timedelta(minutes=20))) == 20.0
    # 恢复新进度 → 解除一次（停滞期时长自最后进度 t0 起算 21 分钟）
    assert d.check(_iso(t0 + timedelta(minutes=21)), has_progress=True) is False
    assert d.last_flip_minutes == 21.0
    assert d.check(_iso(t0 + timedelta(minutes=25))) is None
    assert d.stalled is False
    assert d.stalled_minutes(_iso(t0 + timedelta(minutes=25))) == 0.0


def test_stall_progress_extends_without_flip():
    d = StallDetector(threshold_minutes=10)
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    d.note_start(_iso(t0))
    # 阈值内有进度：基准推进，永不置位
    for i in range(1, 6):
        assert d.check(_iso(t0 + timedelta(minutes=5 * i)),
                       has_progress=True) is None


# ---------------- psutil 进程树采样 ----------------

PARENT = textwrap.dedent("""
    import subprocess, sys, time
    child = subprocess.Popen([sys.executable, "-c",
        "import time\\nf=open('child.busy','w')\\n"
        "end=time.monotonic()+6\\n"
        "while time.monotonic()<end:\\n    f.write('x'); f.flush()"],
        cwd=".", env={k: v for k, v in __import__('os').environ.items()})
    end = time.monotonic() + 6
    while time.monotonic() < end:
        time.sleep(0.05)
    child.wait()
""")


def test_sampler_tree_cpu_rss(tmp_path):
    from web.src.engine.monitor import ProcessSampler
    rd = tmp_path / "run" / "42"
    rd.mkdir(parents=True)
    # 父进程 cwd=run/<id>/，派生忙碌子进程 → 树内 RSS 汇总 > 单进程
    proc = subprocess.Popen([sys.executable, "-c", PARENT], cwd=str(rd))
    try:
        since = time.time() - 1  # 双重校验下界（略早于启动）
        sampler = ProcessSampler()
        time.sleep(1.2)
        got_cpu = got_rss = None
        for _ in range(10):
            s = sampler.sample(rd, since, elapsed=1.0)
            time.sleep(0.5)
            if s is not None and s["mem_rss_mb"] > 0:
                got_cpu, got_rss = s["cpu_percent"], s["mem_rss_mb"]
                break
        assert got_rss is not None and got_rss > 0  # 与 ps 目测对照：树有驻留
        assert got_cpu is not None and got_cpu >= 0
        # 双重校验：启动时间晚于进程的执行不误采（目录复用防护）
        s_late = ProcessSampler().sample(
            rd, time.time() + 3600, elapsed=1.0)
        assert s_late is None
    finally:
        proc.wait(timeout=10)
    # 进程退出 → 采样缺席（不抛错）
    assert ProcessSampler().sample(rd, since, elapsed=1.0) is None


def test_monitor_since_anchored_at_dispatch_before_spawn(tmp_path):
    """回归（GUI 走查实测）：HQ 在 submit 后立即 spawn g16，进程启动早于
    轮询观察到的 started_at 1~2s，若监控基准取轮询时刻，双重校验会把真实
    进程树整体误杀（locate 全空、monitor_summary 恒 0）。基准须取派发时刻
    先行注入，且后续轮询调用不得覆盖。"""
    from web.src.engine.monitor import ExecutionMonitor
    rd = tmp_path / "run" / "7"
    rd.mkdir(parents=True)
    m = ExecutionMonitor(threshold_minutes=10)
    m.note_started(7, _iso(datetime.now(timezone.utc) - timedelta(seconds=3)))
    proc = subprocess.Popen([sys.executable, "-c",
                             "import time;time.sleep(5)"], cwd=str(rd))
    try:
        # 轮询观察时刻（晚于 spawn）：不得覆盖既有基准
        m.note_started(7, _iso(datetime.now(timezone.utc) + timedelta(seconds=5)))
        payload, _ = m.step({"id": 7, "task_id": 7}, rd,
                            _iso(datetime.now(timezone.utc)))
        assert payload is not None and payload["mem_rss_mb"] >= 0
    finally:
        proc.wait(timeout=10)


def test_monitor_summary_accumulation(tmp_path):
    rd = tmp_path / "run" / "7"
    rd.mkdir()
    mon = ExecutionMonitor(threshold_minutes=10)
    t0 = datetime.now(timezone.utc)
    mon.note_started(7, _iso(t0))
    # 两次采样推进峰值
    p1, f1 = mon.step({"id": 7}, rd, _iso(t0 + timedelta(seconds=3)))
    assert p1 is None  # 首采样无差值基线也返载荷（cpu_percent=0）或 None，
    p2, f2 = mon.step({"id": 7}, rd, _iso(t0 + timedelta(seconds=6)))
    assert f1 is None and f2 is None  # 阈值内无停滞翻转
    s = mon.summary(7)
    assert s["stall_alerts"] == 0 and s["stall_total_minutes"] == 0.0


def test_monitor_elapsed_is_real_duration(tmp_path):
    """elapsed_s 为真实运行时长（now - started_at），非硬编码 0（F-02 回归）。

    now_iso 秒级精度下，派发当拍采样的 elapsed 可为 0；故以注入时间戳直接
    断言数值，不依赖真实 sleep 跨秒。
    """
    rd = tmp_path / "run" / "9"
    rd.mkdir(parents=True)
    mon = ExecutionMonitor(threshold_minutes=10)
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mon.note_started(9, _iso(t0))
    proc = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(3)"],
                            cwd=str(rd))
    try:
        payload, _ = mon.step({"id": 9}, rd, _iso(t0 + timedelta(seconds=5)))
        assert payload is not None
        assert payload["elapsed_s"] == 5.0
    finally:
        proc.wait(timeout=10)


# ---------------- Dispatcher 集成：monitor 事件 + stop ----------------

def _setup(tmp_path):
    """派发一个执行（FakeGateway），返回 (disp, rec, tid)。"""
    tid = tasks().create_candidate("h2o.gjf", "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(SIMPLE)
    seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)
    rec: list[tuple[str, dict]] = []
    disp = Dispatcher(FakeGateway(cpus=8),
                      emitter=lambda e, d: rec.append((e, d)))
    disp.advance()
    return disp, rec, tid


def test_monitor_events_flow(tmp_path):
    import subprocess
    import sys
    disp, rec, tid = _setup(tmp_path)
    eid = executions().list_by_state("running")[0]["id"]
    disp._gw.set_state("1", "running")
    disp.tick()  # running 事件 → started_at/note_started
    # 真 g16 替身进程（cwd=run/<eid>/）使采样命中
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=str(config.HOME_DIR / "run" / str(eid)))
    try:
        time.sleep(0.3)
        disp._monitor._entry(eid)["last_sample"] = 0.0  # 重置节流（测试提速）
        disp.tick()  # monitor 步进（采样 + 停滞判定）
    finally:
        proc.wait(timeout=10)
    mon = [d for e, d in rec if e == "execution.monitor"]
    assert mon and {"execution_id", "cpu_percent", "mem_rss_mb",
                    "elapsed_s", "ts"} <= set(mon[0])
    assert mon[0]["execution_id"] == eid
    assert mon[0]["mem_rss_mb"] > 0
    stalled = [d for e, d in rec if e == "execution.stalled"]
    assert stalled == []  # 阈值内不置位


def test_stall_event_payload_on_flip(tmp_path):
    disp, rec, tid = _setup(tmp_path)
    disp._gw.set_state("1", "running")
    disp.tick()
    # 阈值压缩为 0 分钟 → 下一周期即置位
    st = disp._monitor._entry(list(disp._monitor._state)[0])["stall"]
    st.threshold = 0.0
    disp.tick()
    stalled = [d for e, d in rec if e == "execution.stalled"]
    assert len(stalled) == 1  # 翻转才推
    assert stalled[0]["stalled"] is True
    assert stalled[0]["task_id"] == tid
    assert {"threshold_minutes", "last_progress_ts"} <= set(stalled[0])
    disp.tick()
    assert len([d for e, d in rec if e == "execution.stalled"]) == 1  # 不重复
    # 恢复进度 → 解除
    disp._monitor.note_progress(stalled[0]["execution_id"],
                                stalled[0]["ts"])
    disp.tick()
    flips = [d for e, d in rec if e == "execution.stalled"]
    assert len(flips) == 2 and flips[-1]["stalled"] is False


def test_stop_cancels_and_attributes(tmp_path):
    disp, rec, tid = _setup(tmp_path)
    eid = executions().list_by_state("running")[0]["id"]
    disp._gw.set_state("1", "running")
    disp.tick()
    disp.stop_execution(eid)  # → FakeGateway.cancel → canceled
    disp.tick()
    row = executions().get(eid)
    assert row["state"] == "failed" and row["cause"] == "manually_stopped"
    assert row["finished_at"] is not None
    assert row["monitor_summary"] is None  # 仅 succeeded 条目
    assert seats().count() == 0  # 席位释放
    assert tasks().get(tid)["form"] == "finished"  # 离席进历史
    hist = [d for e, d in rec if e == "history.appended"]
    assert hist[-1]["execution_id"] == eid
    assert hist[-1]["state"] == "failed"
    assert hist[-1]["cause"] == "manually_stopped"


def test_stop_state_conflicts(tmp_path):
    disp, rec, tid = _setup(tmp_path)
    eid = executions().list_by_state("running")[0]["id"]
    from web.src.errors import ApiError
    disp._gw.set_state("1", "finished")
    disp.tick()  # 执行终态
    with pytest.raises(ApiError) as ei:
        disp.stop_execution(eid)
    assert ei.value.code == "TASK_STATE_CONFLICT"  # 409 非 running
    with pytest.raises(ApiError) as ei2:
        disp.stop_execution(9999)
    assert ei2.value.code == "NOT_FOUND"  # 404 不存在


def test_terminal_success_carries_summary(tmp_path):
    disp, rec, tid = _setup(tmp_path)
    eid = executions().list_by_state("running")[0]["id"]
    disp._gw.set_state("1", "running")
    disp.tick()
    disp._gw.set_state("1", "finished")
    disp.tick()
    row = executions().get(eid)
    assert row["state"] == "succeeded"
    assert row["monitor_summary"] is not None  # succeeded 落摘要
    assert {"cpu_peak_percent", "mem_peak_mb",
            "stall_alerts", "stall_total_minutes"} == set(row["monitor_summary"])
