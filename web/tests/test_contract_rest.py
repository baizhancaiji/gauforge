"""REST 契约测试（m0-plan §4.3：参数化 §2.3 全表端点）。

- 用 TestClient 打真实端点；
- 状态码符合契约；
- 每个 JSON 响应体重用 openapi-core 校验是否匹配 openapi.yaml schema；
- 常见错误场景返回统一错误结构 {"error":{code,message,details}}。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.src import config
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


def test_queues_response_carries_member_ids():
    """契约 Queue.member_ids 必需：列表/详情均须聚合成员（回归：曾返回
    裸库行，队列页真实数据下 q.member_ids.length 直接崩）。"""
    from web.src.store import queues as queues_store, tasks as tasks_store
    qid = "QVIEW01"
    queues_store().create(qid, name="n1")
    a = tasks_store().create_candidate("a.gjf", "imported")
    b = tasks_store().create_candidate("b.gjf", "imported")
    tasks_store().enqueue(a, qid, 0)
    tasks_store().enqueue(b, qid, 1)
    rows = client.get("/api/v1/queues").json()
    row = next(r for r in rows if r["id"] == qid)
    assert row["member_ids"] == [a, b]
    one = client.get(f"/api/v1/queues/{qid}").json()
    assert one["member_ids"] == [a, b]
    assert_contract_schema(spec, "GET", "/api/v1/queues", 200, rows)


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


# ---------------- M2 契约回归（#12：PUT blocks / PATCH member_ids /
# 提交响应 normalized / 提交核验） ----------------

SAMPLE = ("%mem=1GB\n%nprocshared=4\n#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\n\n")


def _seed_candidate(tmp_path, monkeypatch) -> int:
    from web.src.services.candidates import import_files
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    (tmp_path / "inputs").mkdir()
    return import_files([("h2o.gjf", SAMPLE.encode("utf-8"))],
                        inputs_dir=tmp_path / "inputs")[0]["id"]


def test_put_blocks_response_against_schema(tmp_path, monkeypatch):
    cid = _seed_candidate(tmp_path, monkeypatch)
    r = client.put(f"/api/v1/candidates/{cid}/blocks/route",
                   json={"lines": ["#p hf/sto-3g opt"]})
    assert r.status_code == 200
    body = r.json()
    # InputPreview + warnings（拼写检查，非阻断）结构
    assert_contract_schema(spec, "PUT", "/candidates/{id}/blocks/{section}",
                           200, body)
    assert isinstance(body["warnings"], list)
    assert body["blocks"]["route"] == "#p hf/sto-3g opt"


def test_patch_queue_members_response_against_schema(tmp_path, monkeypatch):
    from web.src import config
    from web.src.store import queues as queues_store
    from web.src.store import tasks as tasks_store
    cid = _seed_candidate(tmp_path, monkeypatch)
    cid2 = cid + 1
    tasks_store().create_candidate("b.gjf", "imported")
    (tmp_path / "inputs" / str(cid2)).write_text(SAMPLE, encoding="utf-8")
    qid = "QM0001"
    queues_store().create(qid, name="q", skip_failed=False)
    tasks_store().enqueue(cid, qid, 0)
    tasks_store().enqueue(cid2, qid, 1)
    r = client.patch(f"/api/v1/queues/{qid}", json={"member_ids": [cid2, cid]})
    assert r.status_code == 200
    assert_contract_schema(spec, "PATCH", "/queues/{id}", 200, r.json())
    assert r.json()["member_ids"] == [cid2, cid]


def test_inline_submit_response_carries_normalized(tmp_path, monkeypatch):
    cid = _seed_candidate(tmp_path, monkeypatch)
    r = client.post(f"/api/v1/candidates/{cid}/submit")
    assert r.status_code == 200
    body = r.json()
    assert_contract_schema(spec, "POST", "/candidates/{id}/submit", 200, body)
    assert isinstance(body["normalized"], bool)  # 提交核验规范化标记


def test_queue_submit_response_carries_normalized(tmp_path, monkeypatch):
    from web.src import config
    from web.src.services import verify as verify_svc
    from web.src.store import queues as queues_store
    from web.src.store import tasks as tasks_store
    cid = _seed_candidate(tmp_path, monkeypatch)
    (tmp_path / "inputs" / str(cid)).write_text(
        SAMPLE.replace("\n", "\r\n"), encoding="utf-8")
    qid = "QS0001"
    queues_store().create(qid, name="q", skip_failed=False)
    tasks_store().enqueue(cid, qid, 0)
    r = client.post(f"/api/v1/queues/{qid}/submit")
    assert r.status_code == 200
    body = r.json()
    assert_contract_schema(spec, "POST", "/queues/{id}/submit", 200, body)
    assert body["normalized"] is True  # CRLF 副本经提交核验规范化
    assert verify_svc  # 核验入口存在（三路径接入断言之锚）


def _mk_member(tmp_path, monkeypatch, *, rollback: bool) -> int:
    """构造队列成员（rollback=True 同时置回退标记），返回任务 id。"""
    from web.src import config
    from web.src.store import queues as queues_store
    from web.src.store import tasks as tasks_store
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    (tmp_path / "inputs").mkdir(exist_ok=True)
    tid = tasks_store().create_candidate("m.gjf", "imported")
    (tmp_path / "inputs" / str(tid)).write_text(SAMPLE, encoding="utf-8")
    qid = f"QP{tid:04d}"
    queues_store().create(qid, name="q", skip_failed=False)
    tasks_store().enqueue(tid, qid, 0)
    if rollback:
        queues_store().update(qid, rollback_flag=True)
    return tid


def test_preview_and_input_readable_for_rollback_member(tmp_path, monkeypatch):
    """M2 跨形态守卫（契约 previewCandidate/getCandidateInput 描述）：
    失败回退队列成员可读预览与原文（分块编辑初始化 + CRLF 检出依赖）。"""
    tid = _mk_member(tmp_path, monkeypatch, rollback=True)
    r = client.get(f"/api/v1/candidates/{tid}/preview")
    assert r.status_code == 200
    assert r.json()["candidate_id"] == tid
    assert_contract_schema(spec, "GET", "/candidates/{id}/preview", 200,
                           r.json())
    r2 = client.get(f"/api/v1/candidates/{tid}/input")
    assert r2.status_code == 200
    assert "#p hf/sto-3g" in r2.text


def test_input_endpoint_returns_raw_crlf(tmp_path, monkeypatch):
    """GET input 返回原文行尾（CRLF 不转）：契约「供分块编辑初始化与
    CRLF 检出」依赖原始 \\r——read_text 通用换行模式会静默吞掉（D1
    走查实测缺陷：前端 CRLF 注记永不触发）。"""
    from web.src.store import tasks as tasks_store
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    (tmp_path / "inputs").mkdir(exist_ok=True)
    tid = tasks_store().create_candidate("crlf.gjf", "imported")
    (tmp_path / "inputs" / str(tid)).write_bytes(
        b"%chk=w.chk\r\n\r\n#p hf/sto-3g\r\n\r\nt\r\n\r\n0 1\r\nO\r\n\r\n")
    r = client.get(f"/api/v1/candidates/{tid}/input")
    assert r.status_code == 200
    assert "\r\n" in r.text


def test_preview_and_input_404_for_locked_member(tmp_path, monkeypatch):
    """新建未提交成员（非回退）不可读预览与原文——404 语义不变。"""
    tid = _mk_member(tmp_path, monkeypatch, rollback=False)
    assert client.get(
        f"/api/v1/candidates/{tid}/preview").status_code == 404
    assert client.get(f"/api/v1/candidates/{tid}/input").status_code == 404

# ============================= 更新域（v2.1.0）=============================

import httpx

from web.src.mock import get_state
from web.src.services import update as update_svc


@pytest.fixture()
def update_env(tmp_path, monkeypatch):
    """更新域隔离：独立部署目录（VERSION+bin/hq）、工作区（.update-proxy
    新位置）、服务单例复位、拉起/自退替换（不真 Popen、不真 SIGTERM）、
    不触真实网络。"""
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    (tmp_path / "VERSION").write_text("v2.0.0", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "hq").write_bytes(b"\x7fELF")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(config, "HOME_DIR", workspace)
    update_svc.reset_service()
    get_state().event_history.clear()
    monkeypatch.setattr(update_svc.UpdateService, "_popen",
                        staticmethod(lambda args, **kw: None))
    monkeypatch.setattr(update_svc.UpdateService, "_self_terminate",
                        staticmethod(lambda: None))
    yield tmp_path
    update_svc.reset_service()
    get_state().event_history.clear()


def _mock_release(monkeypatch, version=b"v2.1.1", version_exc=None,
                  sha_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/VERSION"):
            if version_exc is not None:
                raise version_exc
            return httpx.Response(200, content=version)
        if url.endswith(".sha256"):
            return httpx.Response(sha_status, content=f"{'0' * 64}  x\n".encode())
        return httpx.Response(200, content=b"PAYLOAD",
                              headers={"content-length": "7"})
    # 每次调用新建 client（_request 的 with 自收会 close 实例）。
    monkeypatch.setattr(update_svc, "_client",
                        lambda: httpx.Client(
                            transport=httpx.MockTransport(handler)))
    return handler


def test_update_status_fields_complete(update_env):
    r = client.get("/api/v1/update/status")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"current_version", "latest_version",
                         "last_checked_at", "phase", "message", "proxy",
                         "supported"}
    assert body["phase"] == "idle"
    assert body["supported"] is True  # 部署形态（update_env 伪造布局）
    assert body["proxy"] is None
    assert body["latest_version"] is None
    assert_contract_schema(spec, "GET", "/update/status", 200, body)


def test_update_status_source_form_unsupported(monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", config.PROJECT_ROOT)  # 源码形态
    update_svc.reset_service()
    try:
        r = client.get("/api/v1/update/status")
        assert r.status_code == 200
        assert r.json()["supported"] is False
        assert_contract_schema(spec, "GET", "/update/status", 200, r.json())
    finally:
        update_svc.reset_service()


def test_update_check_available(update_env, monkeypatch):
    _mock_release(monkeypatch, version=b"v2.1.1")
    r = client.post("/api/v1/update/check")
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == "available"
    assert body["latest_version"] == "v2.1.1"
    assert body["message"] == "发现新版本 v2.1.1！查看更新说明"
    assert_contract_schema(spec, "POST", "/update/check", 200, body)


def test_update_check_up_to_date(update_env, monkeypatch):
    _mock_release(monkeypatch, version=b"v2.0.0")
    r = client.post("/api/v1/update/check")
    assert r.status_code == 200
    assert r.json()["phase"] == "up_to_date"
    assert_contract_schema(spec, "POST", "/update/check", 200, r.json())


def test_update_check_failed_502(update_env, monkeypatch):
    _mock_release(monkeypatch, version_exc=httpx.ConnectTimeout("boom"))
    r = client.post("/api/v1/update/check")
    assert r.status_code == 502
    body = r.json()
    assert body["error"]["code"] == "UPDATE_CHECK_FAILED"
    assert body["error"]["message"] == "连接超时，请检查网络"
    assert_contract_schema(spec, "POST", "/update/check", 502, body)


def test_update_apply_unsupported_409(update_env):
    (update_env / "bin" / "hq").unlink()
    r = client.post("/api/v1/update/apply")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "UPDATE_UNSUPPORTED"
    assert_contract_schema(spec, "POST", "/update/apply", 409, r.json())


def test_update_apply_blocked_running_409(update_env):
    from web.src import store
    tid = store.tasks().create_candidate("running.gjf", "imported")
    store.executions().create(
        task_id=tid, filename="running.gjf",
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})
    r = client.post("/api/v1/update/apply")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "UPDATE_BLOCKED_RUNNING"
    assert r.json()["error"]["message"] == \
        "为保证运行稳定性，任务执行期间禁止更新"
    assert_contract_schema(spec, "POST", "/update/apply", 409, r.json())


def test_update_apply_precheck_sha_failed_502(update_env, monkeypatch):
    _mock_release(monkeypatch, sha_status=404)
    r = client.post("/api/v1/update/apply")
    assert r.status_code == 502
    body = r.json()
    assert body["error"]["code"] == "UPDATE_DOWNLOAD_FAILED"
    assert_contract_schema(spec, "POST", "/update/apply", 502, body)


def test_update_apply_precheck_check_failed_502(update_env, monkeypatch):
    _mock_release(monkeypatch, version_exc=httpx.ConnectError("down"))
    r = client.post("/api/v1/update/apply")
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "UPDATE_CHECK_FAILED"
    assert_contract_schema(spec, "POST", "/update/apply", 502, r.json())


def test_update_apply_accepted_202(update_env, monkeypatch):
    _mock_release(monkeypatch, version=b"v2.1.1")
    r = client.post("/api/v1/update/apply")
    assert r.status_code == 202
    body = r.json()
    assert body["phase"] == "downloading"
    assert body["latest_version"] == "v2.1.1"
    assert_contract_schema(spec, "POST", "/update/apply", 202, body)


def test_update_proxy_set_and_direct(update_env):
    r = client.put("/api/v1/update/proxy", json={"proxy": None})
    assert r.status_code == 200
    assert r.json()["proxy"] is None
    assert (update_env / "workspace" / ".update-proxy").read_bytes() == b""  # 直连=空文件
    assert_contract_schema(spec, "PUT", "/update/proxy", 200, r.json())

    r = client.put("/api/v1/update/proxy",
                   json={"proxy": "https://v4.gh-proxy.org"})
    assert r.status_code == 200
    assert r.json()["proxy"] == "https://v4.gh-proxy.org"
    assert (update_env / "workspace" / ".update-proxy").read_bytes() == \
        b"https://v4.gh-proxy.org"  # URL 原文、无尾换行
    assert_contract_schema(spec, "PUT", "/update/proxy", 200, r.json())


def test_update_proxy_invalid_400(update_env):
    for bad in ("not a url", "ftp://x.example", "https://"):
        r = client.put("/api/v1/update/proxy", json={"proxy": bad})
        assert r.status_code == 400, bad
        assert r.json()["error"]["code"] == "INVALID_REQUEST"
        assert_contract_schema(spec, "PUT", "/update/proxy", 400, r.json())
    r = client.put("/api/v1/update/proxy", json={})
    assert r.status_code == 400  # 缺 proxy 字段
    assert r.json()["error"]["code"] == "INVALID_REQUEST"
