"""UI 偏好持久化测试（GET/PUT /ui-preferences，视图偏好域）。

覆盖：repo 层读写与重启一致（重开连接）；路由层合并 upsert、键白名单/
值域整批校验（all-or-nothing）、契约 schema 校验；响应只含已持久化键。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.src.main import app
from web.src.store import Database, run_migrations
from web.src.store.ui_prefs_repo import UiPrefsRepo
from .conftest import assert_contract_schema, load_spec

spec = load_spec()
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_ui_prefs():
    # 测试前清空 ui_prefs 表，避免用例间互相污染。
    from web.src import store
    store.get_db().run("DELETE FROM ui_prefs")
    yield
    store.get_db().run("DELETE FROM ui_prefs")


def test_repo_roundtrip_persists(tmp_path):
    """写库后重开新连接（模拟重启）读值一致。"""
    d1 = Database(tmp_path / "p.db")
    run_migrations(d1)
    r1 = UiPrefsRepo(d1)
    assert r1.all() == {}
    r1.set("queues.sort", "name_asc")
    r1.set("history.sort", "finished_desc")
    d1.close()

    d2 = Database(tmp_path / "p.db")
    run_migrations(d2)
    r2 = UiPrefsRepo(d2)
    assert r2.all() == {"queues.sort": "name_asc",
                        "history.sort": "finished_desc"}
    d2.close()


def test_repo_set_overwrites():
    from web.src import store
    repo = store.ui_prefs()
    repo.set("queues.sort", "name_desc")
    repo.set("queues.sort", "default")  # 同键覆盖
    assert repo.all() == {"queues.sort": "default"}


def test_get_empty_returns_empty_map():
    r = client.get("/api/v1/ui-preferences")
    assert r.status_code == 200
    assert r.json() == {"prefs": {}}
    assert_contract_schema(spec, "GET", "/ui-preferences", 200, r.json())


def test_put_merge_upsert_and_full_return():
    r1 = client.put("/api/v1/ui-preferences",
                    json={"prefs": {"queues.sort": "name_asc"}})
    assert r1.status_code == 200
    assert r1.json() == {"prefs": {"queues.sort": "name_asc"}}
    assert_contract_schema(spec, "PUT", "/ui-preferences", 200, r1.json())

    # 合并语义：只更新出现的键，未提及键保留
    r2 = client.put("/api/v1/ui-preferences",
                    json={"prefs": {"history.sort": "filename_desc"}})
    assert r2.json() == {"prefs": {"queues.sort": "name_asc",
                                   "history.sort": "filename_desc"}}
    assert_contract_schema(spec, "PUT", "/ui-preferences", 200, r2.json())


def test_put_unknown_key_400():
    r = client.put("/api/v1/ui-preferences",
                   json={"prefs": {"nope.sort": "default"}})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["details"]["errors"] == [
        {"key": "nope.sort", "reason": "unknown_key"}]


def test_put_out_of_enum_400():
    r = client.put("/api/v1/ui-preferences",
                   json={"prefs": {"queues.sort": "size_asc"}})
    assert r.status_code == 400
    errors = r.json()["error"]["details"]["errors"]
    assert errors == [{"key": "queues.sort", "reason": "enum"}]


def test_put_non_string_value_400():
    r = client.put("/api/v1/ui-preferences",
                   json={"prefs": {"history.sort": 3}})
    assert r.status_code == 400
    errors = r.json()["error"]["details"]["errors"]
    assert errors == [{"key": "history.sort", "reason": "enum"}]


def test_put_all_or_nothing():
    """整批校验先于应用：任一非法则全批不写入。"""
    client.put("/api/v1/ui-preferences",
               json={"prefs": {"queues.sort": "name_asc"}})
    r = client.put("/api/v1/ui-preferences",
                   json={"prefs": {"history.sort": "finished_asc",
                                   "archive.sort": "bogus"}})
    assert r.status_code == 400
    # 合法项也未写入
    assert client.get("/api/v1/ui-preferences").json() == \
        {"prefs": {"queues.sort": "name_asc"}}


def test_put_empty_prefs_noop():
    r = client.put("/api/v1/ui-preferences", json={"prefs": {}})
    assert r.status_code == 200
    assert r.json() == {"prefs": {}}


def test_missing_prefs_field_422():
    r = client.put("/api/v1/ui-preferences", json={"values": {}})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"
