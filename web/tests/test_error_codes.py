"""错误码全集一致性闸门（B7，m2-plan §2.6/§5 test_error_codes）。

- 静态：web/src 全部 err("…")/ApiError("…") 码 ⊆ openapi.yaml 文件头全集
  （29 码，SSOT 载体；v2.1.0 更新域增补 5 码 + M3 波 A1 分析/存储域 5 码），
  私有码零残留；
- 行为：席位/设置/导入域替换项逐条断言（§2.6 映射表）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .conftest import load_spec
from web.src import config
from web.src.errors import ApiError
from web.src.services import pending
from web.src.store import executions, queues, seats, tasks

# openapi.yaml 文件头错误码全集（29 码，SSOT；与契约文件头同步维护）
CONTRACT_CODES = {
    "INVALID_REQUEST", "NOT_FOUND", "VALIDATION_FAILED", "INTERNAL_ERROR",
    "QUEUE_MEMBER_RANGE", "QUEUE_STATE_CONFLICT", "PENDING_CAPACITY_FULL",
    "SEAT_WINDOW_LOCKED", "TASK_STATE_CONFLICT", "QUEUE_MEMBER_FLOOR",
    "QUEUE_MEMBER_LOCKED", "TASK_EXECUTED_IMMUTABLE", "INPUT_PARSE_FAILED",
    "INPUT_MULTISTEP_UNSUPPORTED", "SETTING_VALUE_INVALID",
    "SETTING_READONLY", "INVALID_MEMBERS", "TASK_IN_FLIGHT", "TASK_FINISHED",
    "UPDATE_BLOCKED_RUNNING", "UPDATE_IN_PROGRESS", "UPDATE_UNSUPPORTED",
    "UPDATE_CHECK_FAILED", "UPDATE_DOWNLOAD_FAILED",
    "ANALYSIS_UNAVAILABLE", "ANALYSIS_PARSE_FAILED",
    "WORKSPACE_PATH_OUTSIDE", "CUBE_GENERATION_FAILED",
    "CUBE_EXECUTABLE_MISSING",
}
RETIRED_CODES = ("SEAT_MEMBER_LAST", "SEAT_MEMBER_EXECUTED")

_ERR_RE = re.compile(r'\b(?:err|ApiError)\(\s*"([A-Z][A-Z0-9_]+)"')


def test_contract_carrier_lists_full_set():
    """契约载体文件头清单与本地全集一致（防两处漂移）。"""
    header = config.CONTRACT_PATH.read_text(encoding="utf-8")
    missing = [c for c in sorted(CONTRACT_CODES) if f"- {c} —" not in header]
    assert missing == []


def test_impl_codes_subset_of_contract():
    """实现错误码集合 ⊆ 契约载体全集（含辅助函数固定产物三码）。"""
    found: set[str] = set()
    for path in (config.PROJECT_ROOT / "web" / "src").rglob("*.py"):
        found |= set(_ERR_RE.findall(path.read_text(encoding="utf-8")))
    found |= {"NOT_FOUND", "VALIDATION_FAILED", "INTERNAL_ERROR"}  # errors.py 辅助
    assert found <= CONTRACT_CODES, f"越界错误码：{sorted(found - CONTRACT_CODES)}"


def test_retired_private_codes_absent():
    """退役私有码在实现/测试/前端零残留（闸门文件自身豁免：需引用字面量）。"""
    self_name = Path(__file__).name
    roots = [config.PROJECT_ROOT / "web" / "src",
             config.PROJECT_ROOT / "web" / "tests",
             config.PROJECT_ROOT / "web" / "frontend" / "src"]
    for root in roots:
        for path in root.rglob("*"):
            if path.name == self_name:
                continue
            if path.suffix not in (".py", ".ts", ".vue"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for code in RETIRED_CODES:
                assert code not in text, f"{path} 残留退役码 {code}"
            assert '"PARSE_FAILED"' not in text, \
                f"{path} 残留旧导入 reason PARSE_FAILED（应 INPUT_PARSE_FAILED）"


# ---------------- 行为断言（§2.6 映射表替换项） ----------------

@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)


def _cand(name: str) -> int:
    return tasks().create_candidate(name, "imported")


def _queue(qid: str, n: int) -> tuple[str, list[int]]:
    queues().create(qid, name=qid)
    ids = []
    for i in range(n):
        tid = tasks().create_candidate(f"{qid}-m{i}.gjf", "imported")
        tasks().enqueue(tid, qid, i)
        ids.append(tid)
    return qid, ids


def test_seat_floor_uses_queue_member_floor():
    """席位内移除下限 409 QUEUE_MEMBER_FLOOR（替换 SEAT_MEMBER_LAST）。"""
    qid, ids = _queue("qa", 2)
    sid = pending.append_queue(qid)
    pending.remove_member(sid, ids[1])  # 移至剩 1：放行
    with pytest.raises(ApiError) as ei:
        pending.remove_member(sid, ids[0])
    assert ei.value.body()["error"]["code"] == "QUEUE_MEMBER_FLOOR"


def test_seat_executed_removal_uses_task_executed_immutable():
    """席位内已执行成员不可移除 409 TASK_EXECUTED_IMMUTABLE
    （替换 SEAT_MEMBER_EXECUTED）。"""
    qid, ids = _queue("qb", 2)
    sid = pending.append_queue(qid)
    eid = executions().create(
        task_id=ids[0], filename="x.gjf", queue_id=qid,
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at="2026-01-01T00:00:00+08:00")
    with pytest.raises(ApiError) as ei:
        pending.remove_member(sid, ids[0])
    assert ei.value.body()["error"]["code"] == "TASK_EXECUTED_IMMUTABLE"


def test_settings_domain_codes():
    """设置域：readonly → 409 SETTING_READONLY；越界/类型 → 422
    SETTING_VALUE_INVALID（details.errors 保留逐项 reason：range/type）。"""
    client = TestClient(__import__("web.src.main", fromlist=["app"]).app)
    r = client.put("/api/v1/settings",
                   json={"values": {"bind_address": "0.0.0.0"}})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "SETTING_READONLY"
    assert any(f["reason"] == "readonly"
               for f in r.json()["error"]["details"]["errors"])

    r = client.put("/api/v1/settings", json={"values": {"page_size": 99999}})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SETTING_VALUE_INVALID"
    assert any(f["reason"] == "range"
               for f in r.json()["error"]["details"]["errors"])

    r = client.put("/api/v1/settings",
                   json={"values": {"page_size": "50"}})  # 类型错
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SETTING_VALUE_INVALID"
    assert any(f["reason"] == "type"
               for f in r.json()["error"]["details"]["errors"])

    r = client.put("/api/v1/settings",
                   json={"values": {"nope": 1}})  # 未知 key
    assert r.status_code == 422
    assert any(f["reason"] == "unknown_setting"
               for f in r.json()["error"]["details"]["errors"])


def test_import_parse_reason_aligned():
    """导入解析失败 per-file reason 与顶层码同名 INPUT_PARSE_FAILED。"""
    from web.src.services.candidates import import_files
    with pytest.raises(ApiError) as ei:
        import_files([("bad.gjf", b"no route marker\n\n0 1\nO\nH\n")])
    entries = ei.value.body()["error"]["details"]["errors"]
    assert entries[0]["reason"] == "INPUT_PARSE_FAILED"


# 前端按错误码分支的允许集（其余码走 error.message 逐字透传）：
# - PENDING_CAPACITY_FULL：提交满员的定制引导（m0 实测口径）
# - SEAT_WINDOW_LOCKED：席位窗口内移除的定制提示（M1 待执行页）
# - ANALYSIS_UNAVAILABLE / ANALYSIS_PARSE_FAILED：分析区不可用原因与
#   块缺失文案（M3 C2 分析视图，§7.1-3 的 409/422 语义 UI 承载）
# - CUBE_GENERATION_FAILED / CUBE_EXECUTABLE_MISSING：502/503 文案区分
#   「生成失败」与「cubegen 不可用」（M3 C4 轨道面板，§4.12 失败态）
# - WORKSPACE_PATH_OUTSIDE：工作区路径守卫三态同码的定制拒绝文案
#   （M3 C2 workspace .out 入口，§2.3 语义 UI 承载）
FRONTEND_CODE_BRANCHES = {
    "PENDING_CAPACITY_FULL",
    "SEAT_WINDOW_LOCKED",
    "ANALYSIS_UNAVAILABLE",
    "ANALYSIS_PARSE_FAILED",
    "CUBE_GENERATION_FAILED",
    "CUBE_EXECUTABLE_MISSING",
    "WORKSPACE_PATH_OUTSIDE",
}


def test_frontend_branches_only_on_capacity_full():
    """前端按码分支 ⊆ 允许集（新增分支须在此登记，防文案双写漂移）。"""
    fe = config.PROJECT_ROOT / "web" / "frontend" / "src"
    branch_re = re.compile(r'["\']([A-Z][A-Z0-9_]+)["\']')
    hits: set[str] = set()
    for path in fe.rglob("*"):
        if path.suffix not in (".ts", ".vue"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"(?:code|===|!==)\s*[^\n]*", text):
            hits |= {c for c in branch_re.findall(m.group(0))
                     if c in CONTRACT_CODES}
    assert hits <= FRONTEND_CODE_BRANCHES, sorted(hits)


def test_spec_loads_without_error():
    load_spec()  # 契约文件本身可加载（载体健全性）
