"""跨重启读数恢复（m1-acceptance §1.3 长寿命标签页遗留项 A 项；sse.md §2）。

- system.snapshot 的 executions_running 行附带引擎已掌握的 progress 字段
  （未探测过的执行不附带）——覆盖跨重启重连标签页与运行中新开页面；
- S1 接管后首读快进吞历史行但补发一条 execution.progress（每执行至多
  一条），重连窗口之外的事件流路径同样即时恢复。
"""
from __future__ import annotations

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.engine import runtime as engine_runtime
from web.src.engine.progress import ProgressTracker
from web.src.services.snapshot import system_snapshot
from web.src.store import executions, seats, tasks

SIMPLE = "%chk=w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"
STEP1 = " Step number %d out of a maximum of   5\n"
CYCLE1 = " Cycle %d  Pass 1  IDiag 1:\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    from web.src.store import settings as settings_repo
    settings_repo().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


def make_disp(gw, rec) -> Dispatcher:
    d = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    d._progress = ProgressTracker(window_s=0)  # 测试内免 1s 窗口
    return d


def seed_running(rec, log_text: str, home) -> tuple[Dispatcher, int]:
    """播种在跑执行并预写日志（真实派发路径），返回 (disp, eid)。"""
    disp = make_disp(FakeGateway(cpus=8), rec)
    tid = add_input(SIMPLE)
    seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)
    disp.advance()
    eid = executions().list_by_state("running")[0]["id"]
    log = home / "run" / str(eid) / "input.log"
    log.write_text(log_text, encoding="utf-8")
    return disp, eid


def add_input(text: str, name: str = "h2o.gjf") -> int:
    tid = tasks().create_candidate(name, "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(text, encoding="utf-8")
    return tid


def test_snapshot_rows_carry_progress_after_restart(home, monkeypatch):
    rec1: list[tuple[str, dict]] = []
    disp1, eid = seed_running(rec1, STEP1 % 3 + CYCLE1 % 4, home)
    disp1.tick()  # 重启前：首读快进 + 补发，引擎掌握进度状态

    # 模拟 g16web 重启（S1）：新 Dispatcher = 全新内存态
    rec2: list[tuple[str, dict]] = []
    disp2 = make_disp(FakeGateway(cpus=8), rec2)
    disp2._reconciled = True  # 聚焦进度路径，绕开对账
    monkeypatch.setattr(engine_runtime, "_dispatcher", disp2)

    # 引擎首 tick 前连接：快照尚无 progress（尚未探测日志）
    snap = system_snapshot(server_restarted=True)
    row = next(e for e in snap["executions_running"] if e["id"] == eid)
    assert "progress" not in row

    disp2.tick()  # 首读快进 → 补发一条 + 掌握状态

    # 快照路径：progress 随 executions_running 恢复（无需新日志行）
    snap = system_snapshot(server_restarted=True)
    row = next(e for e in snap["executions_running"] if e["id"] == eid)
    assert row["progress"]["opt_step"] == 3
    assert row["progress"]["scf_cycle"] == 4

    # 事件流路径：快进补发恰好一条，稳态不重发
    prog = [d for e, d in rec2 if e == "execution.progress"]
    assert len(prog) == 1
    assert prog[0]["opt_step"] == 3 and prog[0]["scf_cycle"] == 4
    disp2.tick()
    assert len([d for e, d in rec2 if e == "execution.progress"]) == 1


def test_snapshot_without_engine_has_plain_rows(home, monkeypatch):
    rec1: list[tuple[str, dict]] = []
    disp1, eid = seed_running(rec1, STEP1 % 1, home)
    disp1.tick()
    # 无引擎挂载（引擎关闭/测试解耦场景）：行不带 progress，键集不变
    monkeypatch.setattr(engine_runtime, "_dispatcher", None)
    snap = system_snapshot(server_restarted=False)
    row = next(e for e in snap["executions_running"] if e["id"] == eid)
    assert "progress" not in row
