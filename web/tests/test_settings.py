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


# ---------------- 枚举值域校验（C1，update_check_interval 四档） ----------------

def test_put_enum_valid_accepted():
    """合法枚举值（daily）→ 200 且值反映（含 range.enum 结构回显）。"""
    r = client.put("/api/v1/settings",
                   json={"values": {"update_check_interval": "daily"}})
    assert r.status_code == 200
    runtime = {m["key"]: m["value"] for m in r.json()["runtime"]}
    assert runtime["update_check_interval"] == "daily"
    item = next(m for m in r.json()["runtime"]
                if m["key"] == "update_check_interval")
    assert item["range"] == {"enum": ["daily", "weekly", "monthly", "never"]}
    assert_contract_schema(spec, "PUT", "/settings", 200, r.json())


def test_put_enum_miss_classified_as_type():
    """字符串不落枚举值域（hourly）→ 422 且 reason=type（不扩词表二）。"""
    r = client.put("/api/v1/settings",
                   json={"values": {"update_check_interval": "hourly"}})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "SETTING_VALUE_INVALID"
    errors = body["error"]["details"]["errors"]
    assert any(item["key"] == "update_check_interval" and item["reason"] == "type"
               for item in errors)


def test_put_enum_wrong_value_type_rejected():
    """非 string 值（integer）→ 422 且 reason=type（类型检查先于值域）。"""
    r = client.put("/api/v1/settings",
                   json={"values": {"update_check_interval": 1}})
    assert r.status_code == 422
    errors = r.json()["error"]["details"]["errors"]
    assert any(item["key"] == "update_check_interval" and item["reason"] == "type"
               for item in errors)


def test_runtime_defaults_include_update_check_interval():
    """运行级参数表含 update_check_interval 且默认 weekly（B1 落点回归）。"""
    r = client.get("/api/v1/settings")
    assert r.status_code == 200
    item = next(m for m in r.json()["runtime"]
                if m["key"] == "update_check_interval")
    assert item["value"] == "weekly"
    assert item["value_type"] == "string"
    assert item["effect"] == "immediate"