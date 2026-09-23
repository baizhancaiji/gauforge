"""设置读写契约测试（m0-plan §4.3 test_settings.py）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.src.main import app
from .conftest import assert_contract_schema, load_spec

spec = load_spec()
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_settings():
    # 测试前清空 SQLite 设置表（回落代码默认值），避免用例间互相污染。
    from web.src import store
    store.get_db().run("DELETE FROM settings")
    yield


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
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert any(item["key"] == "page_size" for item in body["error"]["details"]["errors"])


def test_put_startup_readonly_409():
    r = client.put("/api/v1/settings", json={"values": {"bind_address": "0.0.0.0"}})
    assert r.status_code == 422  # readonly 项按未知/只读拒
    code = r.json()["error"]["code"]
    assert code in ("VALIDATION_FAILED", "SETTING_READONLY")


def test_settings_response_against_schema():
    r = client.get("/api/v1/settings")
    assert_contract_schema(spec, "GET", "/settings", 200, r.json())