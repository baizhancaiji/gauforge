"""fake g16 端到端全链路（m1-plan §5 测试表 test_e2e_fake_g16）。

导入（真实 import_files）→ 席位提交 → 派发（真 CliGateway + 本地
server/worker）→ 增量解析 → 终态 → 历史；SSE 事件序按 §5 约定断言
（同 execution 内有序，跨 execution 不比较顺序）。

execution.monitor 为采样命中型事件（2s 节流 + 进程存活窗口），存在
先天非确定性：读数正确性由 test_monitor_stall 注入覆盖；此处仅断言
若命中则必落在 running 窗口内。
hq 不在 PATH 时跳过（§5：单测不依赖真 g16 环境，本链路依赖真 hq）。
提交前检查清单要求 hq 产物存在（AGENTS §6.1）：skip 是本机未构建时的
降级路径，不视为闸门通过的依据；通过数须与实际执行数核对。
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher
from web.src.hq.cli_gateway import CliGateway
from web.src.hq.process import HqProcessManager
from web.src.services.candidates import import_files
from web.src.store import executions, queues, seats, settings, tasks

HQ = shutil.which("hq")

SIMPLE = "%chk=/tmp/w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """触盘面整体隔离到 tmp_path。"""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


@pytest.mark.skipif(HQ is None, reason="hq 不在 PATH")
def test_e2e_fake_g16_pipeline(tmp_path, monkeypatch):
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    shutil.copy(Path(__file__).parent / "fake_g16.py", fakebin / "g16")
    settings().set("g16_root", str(fakebin))
    settings().set("link0_default_nproc", 1)
    monkeypatch.setenv("G16_FAKE", "sleep=0.5;steps=2")  # worker 继承

    # 导入（真实导入路径：校验 + 拷贝入库，与源文件独立）
    created = import_files([("h2o.gjf", SIMPLE.encode("utf-8"))])
    tid = created[0]["id"]
    assert (tmp_path / "inputs" / str(tid)).is_file()
    # 行内提交 → 待执行席位
    seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)

    ws = tmp_path / "hqws"
    mgr = HqProcessManager(HQ, ws)
    mgr.start()
    mgr.ensure_worker(cpus=1)
    records: list[tuple[str, dict]] = []
    disp = Dispatcher(CliGateway(HQ, str(mgr.server_dir)),
                      emitter=lambda e, d: records.append((e, d)))
    try:
        deadline = time.monotonic() + 60
        rows: list[dict] = []
        while time.monotonic() < deadline:
            disp.tick()
            rows = executions().list_by_task(tid)
            if rows and rows[-1]["state"] != "running":
                break
            time.sleep(0.2)
        assert rows, "派发未发生"
        eid = rows[-1]["id"]
        e = executions().get(eid)
        assert e["state"] == "succeeded", e

        # 全链路产物：物化结构与 g16 输出（input.gjf → 同名 .log）
        rd = tmp_path / "run" / str(eid)
        assert (rd / "input.gjf").is_file()
        assert (rd / "input.log").is_file()

        # SSE 事件序（sse.md §3 推送时机表，同 execution 内有序）
        evs = records

        def idx_of(ev_name, pred):
            return next(i for i, (ev, d) in enumerate(evs)
                        if ev == ev_name and pred(d))

        i_run = idx_of("task.status", lambda d: d.get("execution_id") == eid
                       and d.get("to") == "running")
        i_ok = idx_of("task.status", lambda d: d.get("execution_id") == eid
                      and d.get("to") == "succeeded")
        i_hist = idx_of("history.appended",
                        lambda d: d.get("execution_id") == eid)
        # 状态机：staged→running → running→succeeded → 入史
        sts = [(d["from"], d["to"]) for ev, d in evs
               if ev == "task.status" and d.get("execution_id") == eid]
        assert sts == [("staged", "running"), ("running", "succeeded")]
        assert i_run < i_ok < i_hist
        # 增量解析：进度事件落在 running 窗口内且至少一条（合并窗口后推最新）
        prog = [i for i, (ev, d) in enumerate(evs)
                if ev == "execution.progress" and d.get("execution_id") == eid]
        assert prog, "应至少产出一条 execution.progress"
        assert all(i_run < i < i_ok for i in prog)
        # 监控事件（若采样命中）同样只在 running 窗口内
        mon = [i for i, (ev, d) in enumerate(evs)
               if ev == "execution.monitor" and d.get("execution_id") == eid]
        assert all(i_run < i < i_ok for i in mon)
        # 终态收尾：席位释放快照为末条事件，席位清空
        assert evs[-1][0] == "pending.snapshot"
        assert seats().count() == 0
    finally:
        mgr.stop()


# ---------------- §2.1 判据③：经 HttpGateway 的完整闭环（真实 HTTP 桥） ----------------

def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_e2e_http_gateway_pipeline(tmp_path, monkeypatch):
    """g16web 引擎经 HttpGateway 完成「提交 → 事件接收 → 终态落历史」一次
    完整闭环：真实 server（--http-port）+ worker + fake g16（HQ 桥接验收
    判据③，m1-plan §2.1）。"""
    from web.src.hq.http_gateway import HttpGateway

    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    shutil.copy(Path(__file__).parent / "fake_g16.py", fakebin / "g16")
    settings().set("g16_root", str(fakebin))
    settings().set("link0_default_nproc", 1)
    monkeypatch.setenv("G16_FAKE", "sleep=0.3;steps=2")

    import_files([("h2o.gjf", SIMPLE.encode("utf-8"))])
    tid = tasks().list_by_form("candidate")[0]["id"]
    seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)

    port = _free_port()
    # HTTP 桥仅存在于仓库构建产物（PATH 上游 hq 无 --http-port）
    hq_bin = Path(__file__).resolve().parents[2] / "target" / "release" / "hq"
    if not hq_bin.is_file():
        pytest.skip("仓库构建 hq 缺失（cargo build --release 未运行）")
    mgr = HqProcessManager(str(hq_bin), tmp_path / "hqws", http_port=port)
    mgr.start()
    mgr.ensure_worker(cpus=1)
    gw = HttpGateway(f"http://127.0.0.1:{port}")
    records: list[tuple[str, dict]] = []
    disp = Dispatcher(gw, emitter=lambda e, d: records.append((e, d)))
    try:
        deadline = time.monotonic() + 60
        rows: list[dict] = []
        while time.monotonic() < deadline:
            disp.tick()  # 事件经 HTTP /jobs 拉取 + SSE 线程差分
            rows = executions().list_by_task(tid)
            if rows and rows[-1]["state"] != "running":
                break
            time.sleep(0.2)
        e = executions().get(rows[-1]["id"])
        assert e["state"] == "succeeded", e
        # 事件接收：SSE 线程消费到的 job_state 被引擎差分为终态管线
        evs = records
        sts = [(d["from"], d["to"]) for ev, d in evs
               if ev == "task.status" and d.get("execution_id") == e["id"]]
        assert sts == [("staged", "running"), ("running", "succeeded")]
        assert any(ev == "history.appended" and d.get("execution_id") == e["id"]
                   for ev, d in evs)
        # 席位释放
        assert seats().count() == 0
    finally:
        gw.close()
        mgr.stop()


# ---------------- §7.1 第 7 条：队列 skip_failed=true 分支端到端（真实派发链路） ----------------

FAILING = SIMPLE + "! FAKE: exit=1\n"  # 成员 1 经输入内嵌覆盖 fake g16 退出码


def test_e2e_queue_skip_failed_continues(tmp_path, monkeypatch):
    """§7.1 第 7 条 skip_failed=true 分支端到端：队列两成员经真实 CliGateway
    + HQ + fake g16 全链路——成员 1 非零退出（program_error），成员 2 继续
    派发并成功。判别断言：skip_failed=false 分支下成员 2 会被即时 skipped、
    不产生执行记录（test_failure_semantics 锁定），此处断言其真实跑完；
    队列收尾按失败结局回退（与 test_queue_skip_failed_continues 引擎语义
    一致，本用例复核其在真实栈成立）。"""
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    shutil.copy(Path(__file__).parent / "fake_g16.py", fakebin / "g16")
    settings().set("g16_root", str(fakebin))
    settings().set("link0_default_nproc", 1)
    monkeypatch.setenv("G16_FAKE", "sleep=0.3;steps=2")  # worker 继承；exit 由成员 1 输入内嵌覆盖

    m1 = import_files([("fail.gjf", FAILING.encode("utf-8"))])[0]["id"]
    m2 = import_files([("ok.gjf", SIMPLE.encode("utf-8"))])[0]["id"]

    qid = f"q{int(time.monotonic_ns() % 100000):05d}"
    queues().create(qid, name="t", skip_failed=True)
    tasks().enqueue(m1, qid, 0)
    tasks().enqueue(m2, qid, 1)
    queues().set_state(qid, "submitted")  # 提交动作（append_queue 同语义）
    seats().append(kind="queue", queue_id=qid)

    # HTTP 桥仅存在于仓库构建产物（PATH 上游 hq 无本项目改造）
    hq_bin = Path(__file__).resolve().parents[2] / "target" / "release" / "hq"
    if not hq_bin.is_file():
        pytest.skip("仓库构建 hq 缺失（cargo build --release 未运行）")
    mgr = HqProcessManager(str(hq_bin), tmp_path / "hqws")
    mgr.start()
    mgr.ensure_worker(cpus=1)
    records: list[tuple[str, dict]] = []
    disp = Dispatcher(CliGateway(str(hq_bin), str(mgr.server_dir)),
                      emitter=lambda e, d: records.append((e, d)))
    try:
        deadline = time.monotonic() + 90
        q: dict = {}
        while time.monotonic() < deadline:
            disp.tick()
            q = queues().get(qid)
            if q["state"] in ("unsubmitted", "completed"):
                break
            time.sleep(0.2)
        # 成员 1：真实非零退出 → failed + program_error（§8.7 归因映射）
        e1 = executions().list_by_task(m1)[-1]
        assert e1["state"] == "failed" and e1["cause"] == "program_error", e1
        # 成员 2：skip_failed=true → 继续真实派发并成功
        e2 = executions().list_by_task(m2)[-1]
        assert e2["state"] == "succeeded", e2
        # 队列收尾：全部结束时按失败结局回退，席位释放
        assert q["state"] == "unsubmitted", q
        assert q["finish_reason"] == "finished_with_failures", q
        assert q["rollback_count"] == 1, q
        assert seats().count() == 0
        # 事件序（同 execution 内有序）：两成员各自走到终态并入史
        sts1 = [(d["from"], d["to"]) for ev, d in records
                if ev == "task.status" and d.get("task_id") == m1]
        assert sts1[-1] == ("running", "failed"), sts1
        sts2 = [(d["from"], d["to"]) for ev, d in records
                if ev == "task.status" and d.get("task_id") == m2]
        assert sts2 == [("staged", "running"), ("running", "succeeded")], sts2
        assert any(ev == "history.appended" and d.get("task_id") == m2
                   for ev, d in records)
    finally:
        mgr.stop()
