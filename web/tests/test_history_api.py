"""历史端点测试（m1-plan §4.3 B9；契约 #29-32 与 HistoryEntry 形状）。

- 列表：终态行分页 / state、queue_id、archived 过滤 / 非法 state 400；
- 详情：HistoryEntry 形状（派生 wall_time_s、chk_snapshot 缺省、result_ref
  占位 null），running 行按不存在处理 404；
- input/output：run/<id>/ 实际执行副本、skipped 回落任务副本、download
  导出头；
- archive：204 + archived 过滤联动（#29）；
- requeue：成功沿用原 id 建席 / succeeded 409 / 队列成员 409 / 满员 409
  （#30），事件 pending.snapshot 由路由层发；
- return-candidate：三来源分流 + 内容源回落 + 新 id（#31），事件
  candidates.changed(created)；
- cleanup：仅清 succeeded 超期顶层 chk/rwf，统计契约（#32）。

隔离：conftest autouse 隔离 SQLite；home fixture 重定向 config.HOME_DIR
（inputs/ 与 run/ 均不触真实工作区）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.main import app
from web.src.mock import get_state
from web.src.store import executions, queues, seats, settings, tasks
from web.src.store.db import now_iso

from .conftest import assert_contract_schema, load_spec

spec = load_spec()
client = TestClient(app)

INPUT_TEXT = "%chk=w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"
RUN_INPUT_TEXT = "%chk=w.chk\n\n#p HF/6-31G(d)\n\n运行副本\n\n0 1\nO 0 0 0\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """触盘面（inputs/、run/）重定向到 tmp_path（API 层读 config.HOME_DIR）。"""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


def seed_terminal(state: str, *, cause: str | None = None,
                  filename: str = "h2o.gjf", queue_id: str | None = None,
                  member: bool = False, finished_at: str | None = None,
                  with_run: bool = False) -> tuple[int, int]:
    """播种一条终态执行，返回 (eid, tid)。

    member=True：任务挂入队列（form=queue_member，不置 finished）；
    with_run=True：建 run/<eid>/ 并写 input.gjf / input.log（执行副本）。
    """
    tid = tasks().create_candidate(filename, "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(INPUT_TEXT,
                                                       encoding="utf-8")
    if member:
        queues().create(queue_id or "q1", name="t", skip_failed=False)
        tasks().enqueue(tid, queue_id or "q1", 0)
    eid = executions().create(
        task_id=tid, filename=filename, queue_id=queue_id,
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})
    if state != "skipped":  # skipped 无运行过程：无 started_at
        started = (datetime.now().astimezone()
                   - timedelta(seconds=10)).isoformat(timespec="seconds")
        executions().set_started_at(eid, started)
    executions().finalize(execution_id=eid, state=state,
                          finished_at=finished_at or now_iso(), cause=cause)
    if not member:
        tasks().to_finished(tid)
    if with_run:
        rd = config.HOME_DIR / "run" / str(eid)
        rd.mkdir(parents=True)
        (rd / "input.gjf").write_text(RUN_INPUT_TEXT, encoding="utf-8")
        (rd / "input.log").write_text(" Gaussian log\n", encoding="utf-8")
    return eid, tid


def seed_running() -> int:
    """播种一条 running 执行（FK 需真实任务行），返回 eid。"""
    tid = tasks().create_candidate("ghost.gjf", "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(INPUT_TEXT,
                                                       encoding="utf-8")
    return executions().create(
        task_id=tid, filename="ghost.gjf",
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})


def last_event(name: str) -> dict | None:
    hits = [e for e in get_state().event_history if e["event"] == name]
    return json.loads(hits[-1]["data"]) if hits else None


# ---------------- 列表与过滤 ----------------

def test_list_history_empty_and_schema():
    r = client.get("/api/v1/history")
    assert r.status_code == 200
    body = r.json()
    assert body == {"items": [], "page": 1,
                    "page_size": body["page_size"], "total": 0}
    assert_contract_schema(spec, "GET", "/history", 200, body)


def test_list_history_terminal_only(home):
    eid, _ = seed_terminal("succeeded", with_run=True)
    seed_running()
    body = client.get("/api/v1/history").json()
    assert [it["id"] for it in body["items"]] == [eid]
    assert_contract_schema(spec, "GET", "/history", 200, body)


def test_list_history_filters(home):
    s, _ = seed_terminal("succeeded")
    f, _ = seed_terminal("failed", cause="program_error")
    k, _ = seed_terminal("skipped", with_run=True)
    body = client.get("/api/v1/history", params={"state": "failed"}).json()
    assert [it["id"] for it in body["items"]] == [f]
    assert body["items"][0]["cause"] == "program_error"
    body = client.get("/api/v1/history",
                      params={"state": "succeeded", "page_size": 10}).json()
    assert [it["id"] for it in body["items"]] == [s]
    # 分页：id 倒序，page_size=2 取前两页头
    body = client.get("/api/v1/history", params={"page_size": 2}).json()
    assert body["total"] == 3 and len(body["items"]) == 2
    assert [it["id"] for it in body["items"]] == [k, f]


def test_list_history_invalid_state_400():
    r = client.get("/api/v1/history", params={"state": "running"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


# ---------------- 详情 ----------------

def test_history_detail_shape(home):
    eid, _ = seed_terminal("succeeded", with_run=True)
    r = client.get(f"/api/v1/history/{eid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == eid and body["state"] == "succeeded"
    assert body["finished_at"] and body["cause"] is None
    assert body["wall_time_s"] > 0  # started_at→finished_at 派生
    assert body["chk_snapshot"] == {"protected": False, "location": None}
    assert body["archived"] is False and body["result_ref"] is None
    assert_contract_schema(spec, "GET", "/history/{id}", 200, body)


def test_history_detail_running_is_404(home):
    eid = seed_running()
    r = client.get(f"/api/v1/history/{eid}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert_contract_schema(spec, "GET", "/history/{id}", 404, r.json())


def test_history_detail_unknown_404():
    r = client.get("/api/v1/history/999999")
    assert r.status_code == 404


# ---------------- input / output 视图 ----------------

def test_history_input_from_run_copy(home):
    eid, _ = seed_terminal("succeeded", with_run=True)
    r = client.get(f"/api/v1/history/{eid}/input")
    assert r.status_code == 200
    assert r.text == RUN_INPUT_TEXT  # 实际执行副本优先


def test_history_input_fallback_task_copy(home):
    eid, _ = seed_terminal("skipped", cause="predecessor_failed")
    r = client.get(f"/api/v1/history/{eid}/input")
    assert r.status_code == 200
    assert r.text == INPUT_TEXT  # 无执行目录 → 回落任务输入副本


def test_history_output_and_download_header(home):
    eid, _ = seed_terminal("succeeded", with_run=True)
    r = client.get(f"/api/v1/history/{eid}/output")
    assert r.status_code == 200 and "Gaussian log" in r.text
    r = client.get(f"/api/v1/history/{eid}/output",
                   params={"download": "true"})
    assert r.status_code == 200
    assert r.headers["Content-Disposition"] == \
        "attachment; filename*=UTF-8''h2o.log"


def test_history_output_missing_404(home):
    eid, _ = seed_terminal("failed", cause="program_error")
    r = client.get(f"/api/v1/history/{eid}/output")
    assert r.status_code == 404


# ---------------- archive（#29） ----------------

def test_archive_204_and_filter(home):
    eid, _ = seed_terminal("succeeded")
    r = client.post(f"/api/v1/history/{eid}/archive")
    assert r.status_code == 204 and r.content == b""
    assert client.get(f"/api/v1/history/{eid}").json()["archived"] is True
    assert client.get("/api/v1/history",
                      params={"archived": "true"}).json()["total"] == 1
    assert client.get("/api/v1/history",
                      params={"archived": "false"}).json()["total"] == 0
    assert client.post("/api/v1/history/999999/archive").status_code == 404


# ---------------- requeue（#30） ----------------

def test_requeue_failed_reuses_task_id(home):
    eid, tid = seed_terminal("failed", cause="program_error")
    r = client.post(f"/api/v1/history/{eid}/requeue")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"seat_id", "task_id"}
    assert body["task_id"] == tid
    assert_contract_schema(spec, "POST", "/history/{id}/requeue", 200, body)
    assert seats().count() == 1  # 沿用原任务 id 建席
    assert tasks().get(tid)["form"] == "seat_task"
    ev = last_event("pending.snapshot")
    assert ev and ev["seats"][0]["task_id"] == tid  # 路由层发事件


def test_requeue_skipped_ok(home):
    eid, tid = seed_terminal("skipped", cause="predecessor_failed")
    r = client.post(f"/api/v1/history/{eid}/requeue")
    assert r.status_code == 200 and r.json()["task_id"] == tid


def test_requeue_succeeded_409(home):
    eid, _ = seed_terminal("succeeded")
    r = client.post(f"/api/v1/history/{eid}/requeue")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "TASK_STATE_CONFLICT"
    assert_contract_schema(spec, "POST", "/history/{id}/requeue", 409,
                           r.json())


def test_requeue_queue_member_409(home):
    eid, _ = seed_terminal("failed", cause="program_error", member=True,
                           queue_id="q1")
    r = client.post(f"/api/v1/history/{eid}/requeue")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "TASK_STATE_CONFLICT"
    assert seats().count() == 0  # 未建席


def test_requeue_capacity_full_409(home):
    settings().set("pending_seat_limit", 1)
    other = tasks().create_candidate("filler.gjf", "imported")
    (config.HOME_DIR / "inputs" / str(other)).write_text(INPUT_TEXT,
                                                         encoding="utf-8")
    seats().append(kind="task", task_id=other)
    tasks().to_seat_task(other)
    eid, _ = seed_terminal("failed", cause="program_error")
    r = client.post(f"/api/v1/history/{eid}/requeue")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PENDING_CAPACITY_FULL"


def test_requeue_unknown_404():
    assert client.post("/api/v1/history/999999/requeue").status_code == 404


# ---------------- return-candidate（#31） ----------------

def test_return_candidate_from_failed(home):
    eid, tid = seed_terminal("failed", cause="program_error", with_run=True)
    r = client.post(f"/api/v1/history/{eid}/return-candidate")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] != tid  # 新 id
    assert body["origin"] == "returned_failed"
    assert body["failure_note"] == "program_error"  # failed 附归因
    assert body["filename"] == "h2o.gjf" and body["title"] is not None
    assert_contract_schema(spec, "POST", "/history/{id}/return-candidate",
                           201, body)
    # 内容源 = run/<id>/ 实际执行副本
    assert (config.HOME_DIR / "inputs" / str(body["id"])
            ).read_text(encoding="utf-8") == RUN_INPUT_TEXT
    ev = last_event("candidates.changed")
    assert ev == {"action": "created", "candidate_id": body["id"]}
    # 原任务形态不受影响（退回新建，不迁移）
    assert tasks().get(tid)["form"] == "finished"


def test_return_candidate_origin_by_state(home):
    s, _ = seed_terminal("succeeded")
    k, _ = seed_terminal("skipped", cause="predecessor_failed")
    body_s = client.post(f"/api/v1/history/{s}/return-candidate").json()
    body_k = client.post(f"/api/v1/history/{k}/return-candidate").json()
    assert body_s["origin"] == "returned_succeeded"
    assert body_s["failure_note"] is None
    assert body_k["origin"] == "returned_unrun"


def test_return_candidate_content_fallback(home):
    eid, _ = seed_terminal("skipped", cause="predecessor_failed")
    body = client.post(f"/api/v1/history/{eid}/return-candidate").json()
    assert (config.HOME_DIR / "inputs" / str(body["id"])
            ).read_text(encoding="utf-8") == INPUT_TEXT  # 回落任务副本


def test_return_candidate_running_404(home):
    eid = seed_running()
    assert client.post(
        f"/api/v1/history/{eid}/return-candidate").status_code == 404


# ---------------- cleanup（#32） ----------------

def test_cleanup_endpoint_stats_and_scope(home):
    old = (datetime.now().astimezone()
           - timedelta(days=30)).isoformat(timespec="seconds")
    exp, _ = seed_terminal("succeeded", finished_at=old, with_run=True)
    frs, _ = seed_terminal("succeeded", with_run=True)  # 未超期
    seed_terminal("failed", cause="program_error", with_run=True)
    seed_terminal("skipped", cause="predecessor_failed")
    # expired：顶层瞬态件 + protected/ + .out/.log/输入
    rd = config.HOME_DIR / "run" / str(exp)
    (rd / "input.chk").write_bytes(b"c")
    (rd / "input.rwf").write_bytes(b"r")
    (rd / "input.out").write_bytes(b"o")
    (rd / "protected").mkdir()
    (rd / "protected" / "keep.chk").write_bytes(b"k")
    rd2 = config.HOME_DIR / "run" / str(frs)
    (rd2 / "input.chk").write_bytes(b"c")
    r = client.post("/api/v1/history/cleanup")
    assert r.status_code == 200
    stats = r.json()
    assert stats == {"checked": 2, "removed_chk": 1, "removed_rwf": 1}
    assert not (rd / "input.chk").exists() and not (rd / "input.rwf").exists()
    assert (rd / "input.out").is_file()  # .out 永不触碰
    assert (rd / "input.log").is_file() and (rd / "input.gjf").is_file()
    assert (rd / "protected" / "keep.chk").is_file()  # protected/ 不触碰
    assert (rd2 / "input.chk").is_file()  # 未超期不动


# ---------------- 排序（openapi HistorySort；跨页全局有序） ----------------

def _seed_three_out_of_order() -> None:
    """播种三行：提交序 = w10, h2, a9（id 1..3），完成时间乱序（h2 最晚）。"""
    seed_terminal("succeeded", filename="w10.gjf",
                  finished_at="2026-01-02T00:00:00+00:00")
    seed_terminal("succeeded", filename="h2.gjf",
                  finished_at="2026-03-01T00:00:00+00:00")
    seed_terminal("succeeded", filename="a9.gjf",
                  finished_at="2026-01-01T00:00:00+00:00")


def _list_sort(sort: str | None = None, **kw) -> list[str]:
    params: dict = {"page_size": 50}
    if sort is not None:
        params["sort"] = sort
    params.update(kw)
    r = client.get("/api/v1/history", params=params)
    assert r.status_code == 200
    return [e["filename"] for e in r.json()["items"]]


def test_history_default_sort_is_submitted_desc(home):
    _seed_three_out_of_order()
    # 默认 = 提交时间倒序（id 逆序），与排序参数上线前行为一致
    assert _list_sort(None) == ["a9.gjf", "h2.gjf", "w10.gjf"]
    assert _list_sort("submitted_desc") == ["a9.gjf", "h2.gjf", "w10.gjf"]


def test_history_sort_by_finished_time(home):
    _seed_three_out_of_order()
    assert _list_sort("finished_desc") == ["h2.gjf", "w10.gjf", "a9.gjf"]
    assert _list_sort("finished_asc") == ["a9.gjf", "w10.gjf", "h2.gjf"]


def test_history_sort_by_filename_natural(home):
    _seed_three_out_of_order()
    assert _list_sort("filename_asc") == ["a9.gjf", "h2.gjf", "w10.gjf"]
    assert _list_sort("filename_desc") == ["w10.gjf", "h2.gjf", "a9.gjf"]


def test_history_sort_cross_page_and_ties(home):
    _seed_three_out_of_order()
    # 跨页拼接 = 全量序（切片在排序后）
    p1 = _list_sort("finished_desc", page=1, page_size=2)
    p2 = _list_sort("finished_desc", page=2, page_size=2)
    assert p1 + p2 == ["h2.gjf", "w10.gjf", "a9.gjf"]
    # 完成时间并列（两行同 finished_at）：稳定排序保持提交倒序（新者在前）
    seed_terminal("succeeded", filename="t1.gjf",
                  finished_at="2026-03-01T00:00:00+00:00")  # 与 h2 同秒
    assert _list_sort("finished_desc")[:2] == ["t1.gjf", "h2.gjf"]


def test_history_sort_invalid_value_400(home):
    r = client.get("/api/v1/history", params={"sort": "name_desc"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"
