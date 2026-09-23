"""REST 契约测试（m0-plan §4.3：参数化 §2.3 全表端点）。

- 用 TestClient 打真实端点；
- 状态码符合契约；
- 每个 JSON 响应体重用 openapi-core 校验是否匹配 openapi.yaml schema；
- 常见错误场景返回统一错误结构 {"error":{code,message,details}}。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.src.main import app
from .conftest import assert_contract_schema, load_spec

spec = load_spec()
client = TestClient(app)


# (method, path, [query]) —— 契约的 33 个操作中可无参数安全调用者。
# 分页/列表类端点契约 schema 校验体型；动作类用演示状态打一次成功+一次常见错误。
GOOD_GET: list[tuple[str, str, dict]] = [
    ("GET", "/api/v1/system/health", {}),
    ("GET", "/api/v1/settings", {}),
    ("GET", "/api/v1/candidates", {}),
    ("GET", "/api/v1/queues", {}),
    ("GET", "/api/v1/pending", {}),
    ("GET", "/api/v1/executions", {}),
    ("GET", "/api/v1/history", {}),
]


@pytest.mark.parametrize("method,path,query", GOOD_GET)
def test_get_endpoints_against_schema(method: str, path: str, query: dict) -> None:
    r = client.request(method, path, params=query)
    assert r.status_code == 200
    assert_contract_schema(spec, method, path, r.status_code, r.json(),
                           query=query)


def test_health():
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    for key in ("status", "version", "uptime_s"):
        assert key in r.json()


def test_pending_shape():
    r = client.get("/api/v1/pending")
    body = r.json()
    assert set(body["capacity"]) == {"limit", "occupied", "available"}
    assert "window_size" in body


def test_settings_two_groups():
    r = client.get("/api/v1/settings")
    body = r.json()
    assert set(body) == {"startup", "runtime"}
    assert all("key" in item and "editable" in item for item in body["runtime"])


def test_error_structure_not_found():
    r = client.get("/api/v1/candidates/999999")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "NOT_FOUND"


def test_error_structure_member_range():
    r = client.post("/api/v1/queues", json={
        "name": "q", "member_ids": [1], "skip_failed": False})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "QUEUE_MEMBER_RANGE"


def test_candidate_detail_against_schema(tmp_path):
    # M1 起候选走 store 数据源：用例内播种（契约校验不变，#14 全量切换）
    from web.src.services.candidates import import_files
    sample = (b"%mem=1GB\nnprocplaceholder\n\n#p hf/sto-3g\n\nt\n\n0 1\n"
              b"O\nH 1 0.96\nH 1 0.96 2 1.0\n").replace(b"nprocplaceholder",
                                                          b"%nprocshared=4")
    out = import_files([("h2o.gjf", sample)],
                       inputs_dir=tmp_path / "inputs")
    cid = out[0]["id"]
    r = client.get(f"/api/v1/candidates/{cid}")
    assert r.status_code == 200
    assert_contract_schema(spec, "GET", f"/candidates/{cid}",
                           r.status_code, r.json())


def test_404_for_missing_execution_schema():
    r = client.get("/api/v1/executions/999999")
    assert r.status_code == 404
    assert_contract_schema(spec, "GET", "/executions/{id}", r.status_code,
                           r.json())