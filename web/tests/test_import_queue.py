"""导入成队测试（B5，m2-plan §5 test_import_queue）。

覆盖：queue_from_folder 成队（2–10 边界）；越界（1/11）回落全部候选 +
回落原因；mode=files + true → 422；folder_name 缺失 → 422；事件序列
created ×N → moved_out ×N → queues.changed(created)。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .conftest import assert_contract_schema, load_spec
from web.src import config
from web.src.main import app
from web.src.mock import get_state
from web.src.store import queues, tasks

DATA = "%mem=1GB\n%nprocshared=4\n#p opt\n\nt{}\n\n0 1\nO 0 0 0\n\n"

client = TestClient(app)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch) -> Path:
    (tmp_path / "inputs").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


def _files(n: int) -> list[tuple[str, tuple[str, str, str]]]:
    return [("files", (f"t{i}.gjf", DATA.format(i), "text/plain"))
            for i in range(n)]


def _post(n: int, **data: str):
    return client.post("/api/v1/candidates", files=_files(n), data=data)


def _events() -> list[tuple[str, dict]]:
    import json
    return [(e["event"], json.loads(e["data"]))
            for e in get_state().event_history]


# ---------------- 成队（2–10 边界） ----------------

def test_import_queue_created_with_folder_name():
    r = _post(3, mode="folder", queue_from_folder="true",
              folder_name="我的文件夹")
    assert r.status_code == 201
    body = r.json()
    assert body["queue"]["name"] == "我的文件夹"
    qid = body["queue"]["queue_id"]
    q = queues().get(qid)
    assert q["state"] == "unsubmitted"
    assert bool(q["skip_failed"]) is False  # 默认不跳过
    ids = [i["id"] for i in body["files"]]
    assert [m["id"] for m in tasks().list_queue_members(qid)] == ids
    assert tasks().count_by_form("candidate") == 0  # 入队者移出候选


def test_boundary_two_and_ten_form_queue():
    for n in (2, 10):
        r = _post(n, mode="folder", queue_from_folder="true",
                  folder_name=f"q{n}")
        assert r.status_code == 201
        assert r.json()["queue"] is not None
        assert r.json()["queue_fallback_reason"] is None


# ---------------- 越界回落 ----------------

def test_boundary_eleven_falls_back_with_reason():
    r = _post(11, mode="folder", queue_from_folder="true",
              folder_name="big")
    assert r.status_code == 201
    body = r.json()
    assert body["queue"] is None
    assert body["queue_fallback_reason"] is not None
    assert "11" in body["queue_fallback_reason"]  # 明示回落原因
    assert len(body["files"]) == 11
    assert tasks().count_by_form("candidate") == 11  # 回落全部生成候选
    assert len(queues().list()) == 0


def test_single_file_falls_back():
    r = _post(1, mode="folder", queue_from_folder="true",
              folder_name="solo")
    body = r.json()
    assert body["queue"] is None
    assert body["queue_fallback_reason"] is not None
    assert tasks().count_by_form("candidate") == 1


def test_flag_without_folder_mode_rejected_422():
    r = _post(3, mode="files", queue_from_folder="true",
              folder_name="x")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"
    assert tasks().count_by_form("candidate") == 0


def test_flag_without_folder_name_rejected_422():
    r = _post(3, mode="folder", queue_from_folder="true")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_plain_folder_import_unaffected():
    r = _post(3, mode="folder")  # 不勾选：纯导入
    body = r.json()
    assert body["queue"] is None
    assert body["queue_fallback_reason"] is None
    assert tasks().count_by_form("candidate") == 3


# ---------------- 事件序列 ----------------

def test_event_sequence_created_moved_out_queue_created():
    get_state().event_history.clear()  # 事件窗口为进程级单例：先清空本用例断言段
    _post(3, mode="folder", queue_from_folder="true", folder_name="eq")
    events = _events()
    assert [(e, d.get("action")) for e, d in events] == (
        [("candidates.changed", "created")] * 3
        + [("candidates.changed", "moved_out")] * 3
        + [("queues.changed", "created")])  # sse.md §3 顺序，不省略 moved_out


# ---------------- 契约零漂移 ----------------

def test_response_matches_contract():
    r = _post(3, mode="folder", queue_from_folder="true", folder_name="cq")
    spec = load_spec()
    assert_contract_schema(spec, "POST", "/candidates", 201, r.json())
    r2 = _post(11, mode="folder", queue_from_folder="true", folder_name="cb")
    assert_contract_schema(spec, "POST", "/candidates", 201, r2.json())
