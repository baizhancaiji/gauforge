"""设置读写契约测试（m0-plan §4.3 test_settings.py）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.src.main import app
from web.src.mock import get_state
from .conftest import assert_contract_schema, load_spec

spec = load_spec()
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_settings():
    # 测试前清空 SQLite 设置表（回落代码默认值），避免用例间互相污染。
    from web.src import store
    store.get_db().run("DELETE FROM settings")
    get_state().event_history.clear()
    yield
    get_state().event_history.clear()


def _runtime_keys():
    return [m["key"] for m in
            client.get("/api/v1/settings").json()["runtime"]]


def test_put_valid_value_reflects():
    r = client.put("/api/v1/settings", json={"values": {"page_size": 100}})
    assert r.status_code == 200
    runtime = {m["key"]: m["value"] for m in r.json()["runtime"]}
    assert runtime["page_size"] == 100
    assert_contract_schema(spec, "PUT", "/settings", 200, r.json())


def test_put_out_of_range_422_with_details():
    r = client.put("/api/v1/settings", json={"values": {"page_size": 99999}})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "SETTING_VALUE_INVALID"
    errors = body["error"]["details"]["errors"]
    assert any(item["key"] == "page_size" and item["reason"] == "range"
               for item in errors)


def test_put_startup_readonly_409():
    r = client.put("/api/v1/settings", json={"values": {"bind_address": "0.0.0.0"}})
    assert r.status_code == 409  # readonly 项整批 409（§2.6 决策点 10）
    assert r.json()["error"]["code"] == "SETTING_READONLY"


def test_settings_response_against_schema():
    r = client.get("/api/v1/settings")
    assert_contract_schema(spec, "GET", "/settings", 200, r.json())


def _events(name: str) -> list[dict]:
    import json
    out = []
    for e in get_state().event_history:
        if e["event"] == name:
            e = {**e, "data": json.loads(e["data"])
                 if isinstance(e["data"], str) else e["data"]}
            out.append(e)
    return out


def test_put_window_emits_pending_snapshot():
    """改并行窗口 → 补发 pending.snapshot（前端 WINDOW 读数即时刷新）。"""
    r = client.put("/api/v1/settings", json={"values": {"parallel_window": 4}})
    assert r.status_code == 200
    snaps = _events("pending.snapshot")
    assert len(snaps) == 1
    assert snaps[0]["data"]["window_size"] == 4
    assert [e["event"] for e in get_state().event_history] == \
        ["settings.updated", "pending.snapshot"]


def test_put_seat_limit_raise_no_squeeze_still_snapshots():
    """上限调大（无席位可挤）→ 仍补发 pending.snapshot（旧实现漏发，
    待执行页 OCCUPIED 上限滞留旧值直至刷新页面）。"""
    r = client.put("/api/v1/settings", json={"values": {"pending_seat_limit": 5}})
    assert r.status_code == 200
    snaps = _events("pending.snapshot")
    assert len(snaps) == 1
    assert snaps[0]["data"]["capacity"]["limit"] == 5


def test_put_unrelated_key_skips_pending_snapshot():
    """改动不触及待执行快照字段（page_size）→ 不发 pending.snapshot。"""
    r = client.put("/api/v1/settings", json={"values": {"page_size": 80}})
    assert r.status_code == 200
    assert _events("pending.snapshot") == []