"""侧栏 HQ 连通性监控（m1-acceptance §1.3 遗留项真实化；sse.md §2 hq.status）。

引擎 tick 以 workers 列表探测 server 可达性（CLI/HTTP 双实现同语义）：
状态或 worker 在线数翻转才推 hq.status（稳态不重发）；system.snapshot
携带 hq 字段（off/down/up 三态）供重连快照重建侧栏基线。
"""
from __future__ import annotations

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.engine import runtime as engine_runtime
from web.src.services.snapshot import system_snapshot


def make_disp(gw: FakeGateway, rec: list) -> Dispatcher:
    return Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))


def hq_events(rec: list) -> list[dict]:
    return [d for e, d in rec if e == "hq.status"]


def test_first_tick_probes_up_and_emits_once():
    rec: list[tuple[str, dict]] = []
    disp = make_disp(FakeGateway(cpus=4), rec)
    disp.tick()
    assert disp.hq_state == "up" and disp.hq_workers_online == 1
    evs = hq_events(rec)
    assert len(evs) == 1
    assert evs[0]["state"] == "up" and evs[0]["workers_online"] == 1
    assert "ts" in evs[0]
    disp.tick()  # 稳态不重发
    assert len(hq_events(rec)) == 1


def test_worker_online_count_change_emits():
    rec: list[tuple[str, dict]] = []
    gw = FakeGateway(cpus=4)
    disp = make_disp(gw, rec)
    disp.tick()
    gw._workers[0]["online"] = False
    disp.tick()
    evs = hq_events(rec)
    assert len(evs) == 2
    assert evs[-1]["state"] == "up" and evs[-1]["workers_online"] == 0
    assert disp.hq_workers_online == 0


def test_server_lost_then_recovered_flips_down_up():
    rec: list[tuple[str, dict]] = []
    gw = FakeGateway(cpus=4)
    disp = make_disp(gw, rec)
    disp.tick()
    gw.fail_worker()  # HQ 不可达（workers 抛 GatewayError）
    disp.tick()
    assert disp.hq_state == "down" and disp.hq_workers_online == 0
    evs = hq_events(rec)
    assert evs[-1]["state"] == "down" and evs[-1]["workers_online"] == 0
    gw._unreachable = False
    disp.tick()
    assert disp.hq_state == "up"
    assert hq_events(rec)[-1]["state"] == "up"
    assert len(hq_events(rec)) == 3  # up → down → up 各一条


def test_snapshot_hq_off_when_engine_disabled():
    snap = system_snapshot(server_restarted=False)
    assert snap["hq"] == {"state": "off", "workers_online": 0}


def test_snapshot_hq_down_before_first_probe(monkeypatch):
    # 引擎开启但启动序列未完成（Dispatcher 未挂载）→ down（尚未连通）
    monkeypatch.setattr(config, "ENGINE_ENABLED", True)
    monkeypatch.setattr(engine_runtime, "_dispatcher", None)
    snap = system_snapshot(server_restarted=False)
    assert snap["hq"] == {"state": "down", "workers_online": 0}


def test_snapshot_hq_reads_dispatcher_probe(monkeypatch):
    rec: list[tuple[str, dict]] = []
    disp = make_disp(FakeGateway(cpus=4), rec)
    disp.tick()
    monkeypatch.setattr(engine_runtime, "_dispatcher", disp)
    snap = system_snapshot(server_restarted=False)
    assert snap["hq"] == {"state": "up", "workers_online": 1}
