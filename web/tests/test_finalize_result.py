"""Result 落库与 finalize 接线测试（M3 B2，m3-plan §4.5/§5 test_finalize_result）。

- Dispatcher 集成：succeeded 后 run/<id>/analysis.json 存在且 history 条目
  result_ref="analysis.json"（fake g16 输出非 G16 格式 → degraded 产物，
  置位口径 §2.1 含 degraded）；
- 解析注入失败（parse_output 抛出/落盘 OSError）→ result_ref=null 且
  终态落库与事件不受影响；
- 非 succeeded（failed）→ result_ref 恒 null、无 analysis.json；
- history API 透传：GET /history 条目 result_ref 与库内一致。

隔离：SQLite 走 conftest autouse；config.HOME_DIR 重定向用例级 tmp_path。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.engine import Dispatcher, FakeGateway, finalize
from web.src.store import executions, seats, settings, tasks
from web.src.parse import results as results_parse

SIMPLE = "%chk=w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


def seed_dispatch(disp: Dispatcher) -> tuple[int, object]:
    """派发一个单任务席位，返回 (eid, run 目录)。"""
    tid = tasks().create_candidate("h2o.gjf", "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(SIMPLE,
                                                       encoding="utf-8")
    seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)
    disp.advance()
    row = executions().list_by_state("running")[0]
    return row["id"], config.HOME_DIR / "run" / str(row["id"])


def run_to_succeeded(monkeypatch, payload: dict | None = None) -> tuple[int, object]:
    """驱动一次 succeeded 终态（可注入解析产物）。"""
    if payload is not None:
        monkeypatch.setattr(results_parse, "parse_output",
                            lambda *a, **k: payload)
    disp = Dispatcher(FakeGateway(cpus=8))
    eid, rd = seed_dispatch(disp)
    disp._gw.set_state("1", "finished")
    disp.tick()
    return eid, rd


# ---------------- succeeded：analysis.json + result_ref 置位 ----------------

def test_succeeded_writes_analysis_and_result_ref(home, monkeypatch):
    """fake g16 输出非 G16 格式 → degraded 产物照常落盘并置位（§2.1 口径）。"""
    eid, rd = run_to_succeeded(monkeypatch)
    analysis = rd / "analysis.json"
    assert analysis.is_file()
    payload = json.loads(analysis.read_text(encoding="utf-8"))
    assert payload["result"]["state"] == "degraded"  # fake 输出 ccopen 识别不了
    assert payload["result"]["parse_error"] is not None
    assert executions().get(eid)["result_ref"] == "analysis.json"
    # 原子写不留临时文件
    assert not (rd / "analysis.json.tmp").exists()


def test_succeeded_parsed_payload_result_ref(home, monkeypatch):
    """注入 parsed 产物：analysis.json 内容与置位一致。"""
    payload = results_parse.parse_output(
        config.G16_SAMPLES_DIR / "anion_BC1_393.out")
    eid, rd = run_to_succeeded(monkeypatch, payload=payload)
    on_disk = json.loads((rd / "analysis.json").read_text(encoding="utf-8"))
    assert on_disk["result"]["state"] == "parsed"
    assert on_disk["result"]["summary"]["freq_count"] == 39
    assert executions().get(eid)["result_ref"] == "analysis.json"


def test_history_api_carries_result_ref(home, monkeypatch):
    """GET /history 条目 result_ref 透传（entry_shape）。"""
    eid, _ = run_to_succeeded(monkeypatch)
    client = TestClient(__import__("web.src.main", fromlist=["app"]).app)
    body = client.get(f"/api/v1/history/{eid}").json()
    assert body["result_ref"] == "analysis.json"
    body_list = client.get("/api/v1/history").json()
    assert body_list["items"][0]["result_ref"] == "analysis.json"


# ---------------- 失败注入：降级不阻断终态 ----------------

def test_parse_failure_injection_keeps_terminal(home, monkeypatch):
    """解析注入抛出 → result_ref=null，终态落库不受影响（异常仅日志）。"""
    def _boom(*a, **k):
        raise RuntimeError("injected parse failure")

    monkeypatch.setattr(results_parse, "parse_output", _boom)
    eid, rd = run_to_succeeded(monkeypatch)
    e = executions().get(eid)
    assert e["state"] == "succeeded"          # 终态照常
    assert e["result_ref"] is None            # 置位失败恒 null
    assert not (rd / "analysis.json").exists()


def test_write_failure_injection_keeps_terminal(home, monkeypatch):
    """落盘失败注入（OSError）→ result_ref=null 且终态不受影响。"""
    eid = None

    def _write_fail(run_dir, **k):
        raise OSError("injected disk failure")

    monkeypatch.setattr(finalize, "write_analysis", _write_fail)
    disp = Dispatcher(FakeGateway(cpus=8))
    eid, rd = seed_dispatch(disp)
    disp._gw.set_state("1", "finished")
    disp.tick()
    e = executions().get(eid)
    assert e["state"] == "succeeded" and e["result_ref"] is None


def test_history_appended_still_emitted_on_parse_failure(home, monkeypatch):
    """解析异常不得影响 SSE history.appended 时序（事件照发）。"""
    from web.src.mock import get_state

    def _boom(*a, **k):
        raise RuntimeError("injected")

    monkeypatch.setattr(results_parse, "parse_output", _boom)
    disp = Dispatcher(FakeGateway(cpus=8))
    eid, _ = seed_dispatch(disp)
    disp._gw.set_state("1", "finished")
    disp.tick()
    events = [(ev["event"], json.loads(ev["data"]))
              for ev in get_state().event_history]
    appended = [d for name, d in events if name == "history.appended"
                and d.get("execution_id") == eid]
    assert appended and appended[0]["state"] == "succeeded"


# ---------------- 非 succeeded：result_ref 恒 null ----------------

def test_failed_has_null_result_ref(home):
    disp = Dispatcher(FakeGateway(cpus=8))
    eid, rd = seed_dispatch(disp)
    (rd / "w.chk").write_bytes(b"1")
    disp._gw.set_state("1", "failed")
    disp.tick()
    e = executions().get(eid)
    assert e["state"] == "failed"
    assert e["result_ref"] is None
    assert not (rd / "analysis.json").exists()


# ---------------- write_analysis 单元 ----------------

def test_write_analysis_missing_run_dir(tmp_path):
    """run 目录缺失（异常场景防御）：返回 None 不抛出。"""
    assert finalize.write_analysis(tmp_path / "run" / "404") is None


def test_write_analysis_degraded_payload_lands(home, monkeypatch):
    """degraded 产物落盘成功即返回置位值（B1 垃圾输入链路）。"""
    rd = home / "run" / "99"
    rd.mkdir(parents=True)
    (rd / "input.log").write_bytes(b"garbage not a g16 output")
    assert finalize.write_analysis(rd) == "analysis.json"
    payload = json.loads((rd / "analysis.json").read_text(encoding="utf-8"))
    assert payload["result"]["state"] == "degraded"
