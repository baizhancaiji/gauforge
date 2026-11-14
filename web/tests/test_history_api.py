"""历史端点测试（m1-plan §4.3 B9；契约 #29-32 与 HistoryEntry 形状）。

- 列表：终态行分页 / state、queue_id、archived 过滤 / 非法 state 400；
- 详情：HistoryEntry 形状（派生 wall_time_s、chk_snapshot 缺省、result_ref
  占位 null），running 行按不存在处理 404；
- input/output：run/<id>/ 实际执行副本、skipped 回落任务副本、download
  导出头（.out 正规扩展命名）；
- export：批量导出 ZIP（<stem>.out 命名与 id 前缀冲突消解、缺失容错与
  包内说明、全部无输出 404、请求体校验 400）；
- archive：204 + archived 过滤联动（#29）；
- requeue：成功沿用原 id 建席 / succeeded 409 / 队列成员 409 / 满员 409
  （#30），事件 pending.snapshot 由路由层发；
- return-candidate：三来源分流 + 内容源回落 + 新 id（#31），事件
  candidates.changed(created)；
- cleanup：双档（expired 超期 / all 无视保留期）仅清 succeeded 顶层 chk，
  统计契约与非法 scope 400（#32）。

隔离：conftest autouse 隔离 SQLite；home fixture 重定向 config.HOME_DIR
（inputs/ 与 run/ 均不触真实工作区）。
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

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


def test_history_and_executions_carry_kind(home):
    """kind 冗余注入（M4 C7 crest 行徽标数据源）：历史与运行视图按任务
    反查透传（crest 任务徽标 / g16 缺省）。FK 约束下执行行必对应现存
    任务，「任务已删除」缺省分支为防御路径（_attach_kind/entry_shape
    内 or g16 兜底），不在 FK 可达面。"""
    eid, tid = seed_terminal("succeeded")
    # g16 任务：kind 恒注入缺省值
    body = client.get("/api/v1/history").json()
    assert body["items"][0]["kind"] == "g16"
    r = client.get("/api/v1/executions", params={"state": "succeeded"})
    assert r.json()[0]["kind"] == "g16"
    # crest 任务：set_crest_binding 置 kind 后两视图均透传 crest
    tasks().set_crest_binding(tid, "WFTEST1", 4)
    body = client.get("/api/v1/history").json()
    assert body["items"][0]["kind"] == "crest"
    r = client.get("/api/v1/executions", params={"state": "succeeded"})
    assert r.json()[0]["kind"] == "crest"
    assert client.get(f"/api/v1/executions/{eid}").json()["kind"] == "crest"
    assert_contract_schema(spec, "GET", "/history", 200, body)


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
        "attachment; filename*=UTF-8''h2o.out"


def test_history_output_missing_404(home):
    eid, _ = seed_terminal("failed", cause="program_error")
    r = client.get(f"/api/v1/history/{eid}/output")
    assert r.status_code == 404


# ---------------- export（批量导出 ZIP，openapi /history/export） ----------------

def test_history_export_zip_out_naming(home):
    """<stem>.out 命名；无同名冲突不加前缀。"""
    eid, _ = seed_terminal("succeeded", with_run=True)
    r = client.post("/api/v1/history/export", json={"ids": [eid]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    assert "attachment" in r.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o.out"]
    assert zf.read("h2o.out") == b" Gaussian log\n"


def test_history_export_same_task_collision_id_prefix(home):
    """同任务多次执行（同名 stem）→ 冲突组全部加三位补零 id 前缀。"""
    e1, _ = seed_terminal("succeeded", with_run=True)
    e2, _ = seed_terminal("succeeded", with_run=True)  # 同名 h2o.gjf
    other, _ = seed_terminal("succeeded", filename="nh3.gjf", with_run=True)
    r = client.post("/api/v1/history/export", json={"ids": [e1, e2, other]})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(zf.namelist()) == \
        sorted([f"{e1:03d}-h2o.out", f"{e2:03d}-h2o.out", "nh3.out"])
    # 重复 id 去重保序：只导一份（去重后无冲突，不加前缀）
    r = client.post("/api/v1/history/export", json={"ids": [e1, e1]})
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o.out"]


def test_history_export_missing_manifest_and_all_missing_404(home):
    """无输出条目跳过并在包内 _导出说明.txt 登记；全部无输出 404。"""
    ok, _ = seed_terminal("succeeded", with_run=True)
    skip, _ = seed_terminal("skipped", cause="predecessor_failed")  # 无 run 目录
    gone, _ = seed_terminal("succeeded")  # run 目录缺失
    r = client.post("/api/v1/history/export", json={"ids": [ok, skip, gone]})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o.out", "_导出说明.txt"]
    note = zf.read("_导出说明.txt").decode("utf-8")
    assert f"执行 {skip}：无输出文件" in note
    assert f"执行 {gone}：无输出文件" in note
    r = client.post("/api/v1/history/export", json={"ids": [skip, gone]})
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert len(body["error"]["details"]["missing"]) == 2


def test_history_export_nonterminal_treated_missing_404(home):
    """running 行（非终态）按无输出处理，全部如此时 404。"""
    eid = seed_running()
    r = client.post("/api/v1/history/export", json={"ids": [eid]})
    assert r.status_code == 404


def test_history_export_bad_body_400():
    for body in ({}, {"ids": []}, {"ids": ["a"]}, {"ids": [0]},
                 {"ids": [True]}, {"ids": [1.5]}, {"ids": None}):
        r = client.post("/api/v1/history/export", json=body)
        assert r.status_code == 400, body
        assert r.json()["error"]["code"] == "INVALID_REQUEST"


# ---------------- export scope 扩展（chk/全部；chk-export 计划 T2） ----------------

def _write_run_chk(eid: int, name: str = "w.chk",
                   content: bytes = b"CHK-DATA") -> None:
    """在 run/<eid>/ 下落一个 chk 文件（默认名对齐 RUN_INPUT_TEXT 的
    %chk=w.chk，resolve_chk 声明定位口径）。"""
    d = config.HOME_DIR / "run" / str(eid)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(content)


def test_history_export_chk_scope_succeeded_asset(home):
    """succeeded 保留期内：执行副本 %chk= 声明定位的自有 chk 入包。"""
    eid, _ = seed_terminal("succeeded", with_run=True)
    _write_run_chk(eid, content=b"CHK-BYTES-1")
    r = client.post("/api/v1/history/export",
                    json={"ids": [eid], "scope": "chk"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    assert re.fullmatch(r"attachment; filename=gauforge-outputs-\d{8}-\d{6}\.zip",
                        r.headers["content-disposition"])
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o.chk"]
    assert zf.read("h2o.chk") == b"CHK-BYTES-1"
    assert zf.testzip() is None


def test_history_export_chk_failed_protected_asset(home):
    """failed：protected/ 保全 chk 优先于顶层 chk 入包。"""
    eid, _ = seed_terminal("failed", cause="program_error", with_run=True)
    prot = config.HOME_DIR / "run" / str(eid) / "protected"
    prot.mkdir()
    (prot / "keep.chk").write_bytes(b"PROTECTED")
    _write_run_chk(eid)  # 顶层同名位也有 chk：判据 ① 保全优先
    r = client.post("/api/v1/history/export",
                    json={"ids": [eid], "scope": "chk"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o.chk"]
    assert zf.read("h2o.chk") == b"PROTECTED"


def test_history_export_chk_skipped_manifest_and_404(home):
    """skipped 未启动无 chk：多项时说明登记；chk scope 全缺 404。"""
    ok, _ = seed_terminal("succeeded", with_run=True)
    _write_run_chk(ok)
    skip, _ = seed_terminal("skipped", cause="predecessor_failed")
    r = client.post("/api/v1/history/export",
                    json={"ids": [ok, skip], "scope": "chk"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o.chk", "_导出说明.txt"]
    note = zf.read("_导出说明.txt").decode("utf-8")
    assert f"执行 {skip}：无 chk（任务未启动）" in note
    r = client.post("/api/v1/history/export",
                    json={"ids": [skip], "scope": "chk"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert len(r.json()["error"]["details"]["missing"]) == 1


def test_history_export_chk_cleaned_manifest_and_404(home):
    """succeeded 但 chk 已清理（顶层无 chk 资产）：多项时说明登记；全缺 404。"""
    ok, _ = seed_terminal("succeeded", with_run=True)
    _write_run_chk(ok)
    cleaned, _ = seed_terminal("succeeded", filename="nh3.gjf", with_run=True)
    r = client.post("/api/v1/history/export",
                    json={"ids": [ok, cleaned], "scope": "chk"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o.chk", "_导出说明.txt"]
    note = zf.read("_导出说明.txt").decode("utf-8")
    assert f"执行 {cleaned}：无 chk 资产（已清理或从未产生）" in note
    r = client.post("/api/v1/history/export",
                    json={"ids": [cleaned], "scope": "chk"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_history_export_invalid_scope_400():
    """scope 非法值（非 out/chk/all）→ 400 INVALID_REQUEST
    （test_cleanup_invalid_scope_400 同型）。"""
    for scope in ("bogus", "", "OUT", None, 1):
        r = client.post("/api/v1/history/export",
                        json={"ids": [1], "scope": scope})
        assert r.status_code == 400, scope
        assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_history_export_scope_all_both_files_manifest_merged(home):
    """scope=all：同执行 .out+.chk 两条目同 stem 不加前缀；skipped 缺失
    说明按执行合并登记一条；包内平铺无子目录条目。"""
    ok, _ = seed_terminal("succeeded", with_run=True)
    _write_run_chk(ok, content=b"ALL-CHK")
    skip, _ = seed_terminal("skipped", cause="predecessor_failed")
    r = client.post("/api/v1/history/export",
                    json={"ids": [ok, skip], "scope": "all"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert sorted(names) == ["_导出说明.txt", "h2o.chk", "h2o.out"]
    assert not any("/" in n for n in names)  # 平铺：ZIP 根无子目录条目
    assert zf.read("h2o.chk") == b"ALL-CHK"
    note = zf.read("_导出说明.txt").decode("utf-8")
    assert f"执行 {skip}：无输出文件（任务未产生输出或已清理），" \
        f"无 chk（任务未启动）" in note
    assert "无 chk 资产（" not in note  # skipped 不按已清理/未产生口径登记


def test_history_export_scope_all_collision_prefix_by_ext(home):
    """scope=all 冲突组按 (stem, 扩展) 分组：out 与 chk 各自成组、全加前缀；
    无冲突组（nh3）不加。"""
    e1, _ = seed_terminal("succeeded", with_run=True)
    e2, _ = seed_terminal("succeeded", with_run=True)  # 同名 h2o.gjf
    other, _ = seed_terminal("succeeded", filename="nh3.gjf", with_run=True)
    for e in (e1, e2, other):
        _write_run_chk(e)
    r = client.post("/api/v1/history/export",
                    json={"ids": [e1, e2, other], "scope": "all"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(zf.namelist()) == sorted(
        [f"{e1:03d}-h2o.out", f"{e2:03d}-h2o.out",
         f"{e1:03d}-h2o.chk", f"{e2:03d}-h2o.chk",
         "nh3.out", "nh3.chk"])


def test_history_export_chk_reuse_materialized_dep_is_own(home):
    """续用形态：执行副本被物化为 %chk=dep-<X>.chk，其 dep-<X>.chk 即本任务
    自有 chk，按判据天然选中入包（不加 dep-* 过滤）。"""
    eid, _ = seed_terminal("succeeded", with_run=True)
    rd = config.HOME_DIR / "run" / str(eid)
    (rd / "input.gjf").write_text(
        "%chk=dep-3.chk\n\n#p HF/6-31G(d)\n\n运行副本\n\n0 1\nO 0 0 0\n",
        encoding="utf-8")
    (rd / "dep-3.chk").write_bytes(b"OWN-CHK")
    r = client.post("/api/v1/history/export",
                    json={"ids": [eid], "scope": "chk"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o.chk"]
    assert zf.read("h2o.chk") == b"OWN-CHK"


def test_history_export_chk_readonly_dep_not_exported(home):
    """只读接续形态：%oldchk=dep-<X>.chk 为上游参考副本，未声明自有 %chk
    时无自有 chk → dep-* 不入包、说明登记；单独导出 404。"""
    ok, _ = seed_terminal("succeeded", with_run=True)
    _write_run_chk(ok)
    ro, _ = seed_terminal("succeeded", filename="nh3.gjf", with_run=True)
    rd = config.HOME_DIR / "run" / str(ro)
    (rd / "input.gjf").write_text(  # 只 %oldchk，无自有 %chk 声明
        "%oldchk=dep-3.chk\n\n#p HF/6-31G(d)\n\n接续\n\n0 1\nN 0 0 0\n",
        encoding="utf-8")
    (rd / "dep-3.chk").write_bytes(b"UPSTREAM")
    r = client.post("/api/v1/history/export",
                    json={"ids": [ok, ro], "scope": "chk"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert sorted(names) == ["_导出说明.txt", "h2o.chk"]
    assert "dep-3.chk" not in names
    assert f"执行 {ro}：无 chk 资产（已清理或从未产生）" in \
        zf.read("_导出说明.txt").decode("utf-8")
    r = client.post("/api/v1/history/export",
                    json={"ids": [ro], "scope": "chk"})
    assert r.status_code == 404


def test_history_export_chk_entry_stored_out_deflated(home):
    """chk 条目 ZIP_STORED（二进制压缩无收益）、.out 条目 ZIP_DEFLATED。"""
    eid, _ = seed_terminal("succeeded", with_run=True)
    _write_run_chk(eid)
    r = client.post("/api/v1/history/export",
                    json={"ids": [eid], "scope": "all"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.getinfo("h2o.chk").compress_type == zipfile.ZIP_STORED
    assert zf.getinfo("h2o.out").compress_type == zipfile.ZIP_DEFLATED


def test_history_export_chk_tmpfile_lifecycle(home):
    """scope=chk 走临时文件：服务层返回 HOME_DIR/tmp 下 export-*.zip 路径、
    包过 testzip；HTTP 响应结束后 BackgroundTask 已删临时文件。"""
    from web.src.services import history as history_svc
    eid, _ = seed_terminal("succeeded", with_run=True)
    _write_run_chk(eid, content=b"BIG-CHK" * 1024)
    tmp_dir = config.HOME_DIR / "tmp"
    assert not tmp_dir.exists()  # scope=out 路径不触 tmp
    r = client.post("/api/v1/history/export",
                    json={"ids": [eid], "scope": "out"})
    assert r.status_code == 200 and not tmp_dir.exists()
    result = history_svc.export_outputs([eid], "chk")
    assert isinstance(result, Path)
    assert result.parent == tmp_dir
    assert result.name.startswith("export-") and result.suffix == ".zip"
    zf = zipfile.ZipFile(result)
    assert zf.testzip() is None and zf.namelist() == ["h2o.chk"]
    zf.close()
    result.unlink()  # 服务层直调产物手动清，免干扰后续断言
    r = client.post("/api/v1/history/export",
                    json={"ids": [eid], "scope": "chk"})
    assert r.status_code == 200
    assert list(tmp_dir.iterdir()) == []  # BackgroundTask 用后即删


def test_history_export_purge_tmp_startup(home):
    """启动清扫：HOME_DIR/tmp 下 export-*.zip 残留清掉、其他文件不动。"""
    from web.src.services import history as history_svc
    tmp_dir = config.HOME_DIR / "tmp"
    tmp_dir.mkdir(parents=True)
    stale = tmp_dir / "export-20261114-000000.zip"
    stale.write_bytes(b"stale")
    keep = tmp_dir / "unrelated.txt"
    keep.write_text("keep", encoding="utf-8")
    history_svc.purge_export_tmp()
    assert not stale.exists()
    assert keep.exists()


def test_history_export_scope_out_explicit_memory_path(home):
    """显式 scope=out 与缺省同走内存路径（判据 1：内存路径未动）。"""
    eid, _ = seed_terminal("succeeded", with_run=True)
    r = client.post("/api/v1/history/export",
                    json={"ids": [eid], "scope": "out"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o.out"]
    assert zf.read("h2o.out") == b" Gaussian log\n"


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
    # M2 起响应含提交核验规范化标记（SubmitResponse 契约增量）
    assert set(body) == {"seat_id", "task_id", "normalized", "warnings"}
    assert body["task_id"] == tid
    assert isinstance(body["normalized"], bool)
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
    # 执行副本携带物化明文依赖行与用户明文行（γ 场景）：
    # 回退候选剥离 dep 行、明文行保留（oldchk-duplicate-write-fix-plan §2.3）
    (config.HOME_DIR / "run" / str(eid) / "input.gjf").write_text(
        RUN_INPUT_TEXT.replace(
            "%chk=w.chk\n",
            "%chk=w.chk\n%oldchk=D1_DgpC_Monomer_Opt.chk\n"
            "%oldchk=dep-exec-42.chk\n"),
        encoding="utf-8")
    r = client.post(f"/api/v1/history/{eid}/return-candidate")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] != tid  # 新 id
    assert body["origin"] == "returned_failed"
    assert body["failure_note"] == "program_error"  # failed 附归因
    assert body["filename"] == "h2o.gjf" and body["title"] is not None
    assert_contract_schema(spec, "POST", "/history/{id}/return-candidate",
                           201, body)
    # 内容源 = run/<id>/ 实际执行副本（dep 明文行剥离、用户明文行保留）
    assert (config.HOME_DIR / "inputs" / str(body["id"])
            ).read_text(encoding="utf-8") == RUN_INPUT_TEXT.replace(
        "%chk=w.chk\n", "%chk=w.chk\n%oldchk=D1_DgpC_Monomer_Opt.chk\n")
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
    # expired：顶层 .chk + rwf + protected/ + .out/.log/输入
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
    assert stats == {"checked": 2, "removed_chk": 1}
    assert not (rd / "input.chk").exists()
    assert (rd / "input.rwf").is_file()  # rwf 不属清理（异常终止时收尸）
    assert (rd / "input.out").is_file()  # .out 永不触碰
    assert (rd / "input.log").is_file() and (rd / "input.gjf").is_file()
    assert (rd / "protected" / "keep.chk").is_file()  # protected/ 不触碰
    assert (rd2 / "input.chk").is_file()  # 未超期不动


def test_cleanup_scope_all_ignores_retention(home):
    """「清理所有」档：无视保留期清所有 succeeded 顶层 .chk；
    failed 的 chk（含 protected/）依旧保留。"""
    old = (datetime.now().astimezone()
           - timedelta(days=30)).isoformat(timespec="seconds")
    exp, _ = seed_terminal("succeeded", finished_at=old, with_run=True)
    frs, _ = seed_terminal("succeeded", with_run=True)
    fail, _ = seed_terminal("failed", cause="program_error", with_run=True)
    rd = config.HOME_DIR / "run" / str(exp)
    (rd / "input.chk").write_bytes(b"c")
    rd2 = config.HOME_DIR / "run" / str(frs)
    (rd2 / "input.chk").write_bytes(b"c")
    rd3 = config.HOME_DIR / "run" / str(fail)
    (rd3 / "stray.chk").write_bytes(b"c")
    (rd3 / "protected").mkdir()
    (rd3 / "protected" / "s.chk").write_bytes(b"s")
    r = client.post("/api/v1/history/cleanup?scope=all")
    assert r.status_code == 200
    assert r.json() == {"checked": 2, "removed_chk": 2}
    assert not (rd / "input.chk").exists() and not (rd2 / "input.chk").exists()
    assert (rd3 / "stray.chk").is_file()  # failed 的 chk 保留
    assert (rd3 / "protected" / "s.chk").is_file()


def test_cleanup_invalid_scope_400(home):
    seed_terminal("succeeded", with_run=True)
    r = client.post("/api/v1/history/cleanup?scope=bogus")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


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
