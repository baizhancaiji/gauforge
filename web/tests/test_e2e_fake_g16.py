"""fake g16 端到端全链路（m1-plan §5 测试表 test_e2e_fake_g16）。

导入（真实 import_files）→ 席位提交 → 派发（真 CliGateway + 本地
server/worker）→ 增量解析 → 终态 → 历史；SSE 事件序按 §5 约定断言
（同 execution 内有序，跨 execution 不比较顺序）。

execution.monitor 为采样命中型事件（2s 节流 + 进程存活窗口），存在
先天非确定性：读数正确性由 test_monitor_stall 注入覆盖；此处仅断言
若命中则必落在 running 窗口内。
hq 不在 PATH 时跳过（§5：单测不依赖真 g16 环境，本链路依赖真 hq）。
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
from web.src.store import executions, seats, settings, tasks

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
