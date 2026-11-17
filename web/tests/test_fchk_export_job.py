"""批量 fchk 导出作业测试（3.8.0 工具箱 B17，toolbox-plan §5
test_fchk_export_job）。

- 创建/分类：混合批次（succeeded 已有 fchk → reused / failed protected
  chk → 转换候选 → converted / skipped / 非终态 / 不存在 → missing）；
  已有 fchk 零子进程（哨兵）；创建时全缺 404；ids 值域 400；
- 单项失败继续：verdict≠ok 记 failed 不使作业失败，好条目照常转换出包；
- 总预算：注入低预算（monkeypatch 常量）→ 未处理候选记 missing、作业仍
  done（有 reused 条目时）；
- 取消：queued 即时生效 / running 当前条目结束后生效（已转 fchk 保留）/
  packing 条目写入间隙生效（PackCancelled 注入）；取消后 .part/ZIP 无
  残留；
- 并发与语义：同刻第二作业 409（details.active_job_id）；下载前 409、
  未知 404；TTL 到期惰性 expired 后 404 且 ZIP 删除（注入短 TTL）；
  重启（作业表清空 + purge 清扫）404 且 .part 残留被清扫；
- ZIP 形态：<stem>.fchk 平铺、同 stem 冲突组三位补零前缀、_导出说明.txt
  按 fchk 维度文案、testzip 完整、fchk 条目 ZIP_DEFLATED；打包期 fchk
  消失弃包重建按缺登记；
- scope=all 不含 fchk 零回归（out+chk 语义不变）。
"""
from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.engine import finalize
from web.src.services import fchk_export as svc
from web.src.services import history as history_svc
from web.src.store import executions, settings, tasks

client = TestClient(__import__("web.src.main", fromlist=["app"]).app)

FIXTURES = Path(__file__).parent / "fixtures" / "g16tools"
FCHK_GOOD = ('Gaussian, Inc.\n'
             ' Number of atoms                            I                3\n'
             ' Number of basis functions                  I               19\n'
             ' Alpha Orbital Energies                     R   N=          19\n')


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    (tmp_path / "export-tmp").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    svc._jobs.clear()  # 进程内作业表逐用例复位（「重启」语义的测试基底）
    return tmp_path


def make_tool(root: Path, name: str, script: str) -> Path:
    f = root / name
    f.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    f.chmod(0o755)
    return f


def install_convert_tools(root: Path, *,
                          mixed_verdict: bool = False) -> None:
    """健康 chkchk 回放 + 合法头 formchk（转换候选全链可用）。
    mixed_verdict=True 时按快照大小区分：<64B 视为损坏 chk 回放截断
    反例（verdict=unreadable → 条目级失败），否则健康（执行期 failed
    与 converted 并存的造数）。"""
    healthy = FIXTURES / "chkchk_healthy.txt"
    truncated = FIXTURES / "chkchk_unreadable_truncated.txt"
    if mixed_verdict:
        script = (f'if [ "$(stat -c%s "$1")" -lt 64 ]; then '
                  f'cat "{truncated}"; exit 134; fi\n'
                  f'cat "{healthy}"\nexit 0\n')
    else:
        script = f'cat "{healthy}"\nexit 0\n'
    make_tool(root, "chkchk", script)
    make_tool(root, "formchk",
              f'cat > "$2" <<\'EOF\'\n{FCHK_GOOD}EOF\n')


def install_corrupted_chkchk(root: Path) -> None:
    truncated = FIXTURES / "chkchk_unreadable_truncated.txt"
    make_tool(root, "chkchk", f'cat "{truncated}"\nexit 134\n')


def seed(*, state: str = "succeeded", filename: str = "h2o.gjf",
         with_fchk: bool = False, with_chk: bool = True,
         protected: bool = False, chk_bytes: bytes = b"fake-chk") -> int:
    tid = tasks().create_candidate(filename, "imported")
    eid = executions().create(
        task_id=tid, filename=filename,
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True, exist_ok=True)
    if with_chk:
        if protected:
            prot = run_d / "protected"
            prot.mkdir()
            (prot / "input.chk").write_bytes(chk_bytes)
        else:
            (run_d / "input.chk").write_bytes(chk_bytes)
    if with_fchk:
        (run_d / "input.fchk").write_text(FCHK_GOOD, encoding="utf-8")
    executions().finalize(execution_id=eid, state=state,
                          finished_at="2026-01-01T00:00:00+08:00")
    return eid


def wait_terminal(job_id: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = svc.get_job(job_id)
        if snap["state"] in ("done", "failed", "cancelled"):
            return snap
        time.sleep(0.02)
    raise AssertionError("作业未在时限内到达终态")


def wait_running(job_id: str, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if svc.get_job(job_id)["state"] == "running":
            return
        time.sleep(0.01)
    raise AssertionError("作业未进入 running")


# ---------------- 创建/分类 ----------------

def test_mixed_batch_classification(home):
    """混合批次：reused（已有 fchk）+ converted（failed protected chk）+
    missing（skipped/非终态/不存在）计数与 ZIP 条目正确。"""
    r_eid = seed(state="succeeded", filename="have.gjf", with_fchk=True,
                 with_chk=False)
    f_eid = seed(state="failed", filename="protect.gjf", protected=True)
    s_eid = seed(state="skipped", filename="skip.gjf", with_chk=False)
    tid = tasks().create_candidate("x.gjf", "imported")
    running = executions().create(
        task_id=tid, filename="x.gjf",
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})
    install_convert_tools(home / "g16")
    r = client.post("/api/v1/history/export/fchk",
                    json={"ids": [r_eid, f_eid, s_eid, running, 99999]})
    assert r.status_code == 202
    body = r.json()
    assert body["state"] == "queued" and body["total"] == 5
    snap = wait_terminal(body["job_id"])
    assert snap["state"] == "done"
    assert snap["reused"] == 1 and snap["converted"] == 1
    assert snap["missing"] == 3 and snap["failed"] == 0
    assert snap["processed"] == snap["reused"] + snap["converted"] \
        + snap["missing"] + snap["failed"]
    r2 = client.get(f"/api/v1/history/export/fchk/{body['job_id']}")
    assert r2.status_code == 200 and r2.json() == snap

    dl = client.get(
        f"/api/v1/history/export/fchk/{body['job_id']}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/zip")
    assert "filename=gauforge-fchk-" in dl.headers["content-disposition"]
    with zipfile.ZipFile(__import__("io").BytesIO(dl.content)) as zf:
        assert zf.testzip() is None
        names = sorted(zf.namelist())
        assert names == ["_导出说明.txt", "have.fchk", "protect.fchk"]
        assert zf.getinfo("have.fchk").compress_type == zipfile.ZIP_DEFLATED
        manifest = zf.read("_导出说明.txt").decode("utf-8")
        assert "以下选中条目无对应 fchk" in manifest
        assert "条目不存在或非终态" in manifest
        assert "未运行无执行产物" in manifest


def test_reused_only_zero_subprocess(home):
    """全 reused 批次：零子进程（formchk/chkchk 哨兵不被调用）秒级 done。"""
    sentinel = home / "tools-ran"
    e1 = seed(state="succeeded", filename="a.gjf", with_fchk=True,
              with_chk=False)
    e2 = seed(state="succeeded", filename="b.gjf", with_fchk=True,
              with_chk=False)
    make_tool(home / "g16", "chkchk", f'echo ran > "{sentinel}"\n')
    make_tool(home / "g16", "formchk", f'echo ran > "{sentinel}"\n')
    r = client.post("/api/v1/history/export/fchk", json={"ids": [e1, e2]})
    snap = wait_terminal(r.json()["job_id"])
    assert snap["state"] == "done"
    assert snap["reused"] == 2 and snap["converted"] == 0
    assert not sentinel.exists()  # 已有 fchk 零子进程


def test_create_rejected_400_and_404(home):
    """ids 值域 400（空/非正整数/bool/超 500）；创建时全缺 404
    （details.missing）。"""
    assert client.post("/api/v1/history/export/fchk",
                       json={"ids": []}).status_code == 400
    assert client.post("/api/v1/history/export/fchk",
                       json={"ids": [0]}).status_code == 400
    assert client.post("/api/v1/history/export/fchk",
                       json={"ids": [True]}).status_code == 400
    assert client.post("/api/v1/history/export/fchk",
                       json={"ids": list(range(1, 502))}).status_code == 400
    eid = seed(state="skipped", with_chk=False)
    r = client.post("/api/v1/history/export/fchk", json={"ids": [eid]})
    assert r.status_code == 404
    assert r.json()["error"]["details"]["missing"]


def test_concurrent_create_409(home):
    """同刻第二作业 409 TASK_STATE_CONFLICT（details.active_job_id）。"""
    slow_eid = seed(state="failed", protected=True, filename="slow.gjf")
    make_tool(home / "g16", "chkchk", "exit 0\n")
    make_tool(home / "g16", "formchk", "sleep 1\n")
    r1 = client.post("/api/v1/history/export/fchk", json={"ids": [slow_eid]})
    assert r1.status_code == 202
    r2 = client.post("/api/v1/history/export/fchk",
                     json={"ids": [slow_eid]})
    assert r2.status_code == 409
    assert r2.json()["error"]["details"]["active_job_id"] \
        == r1.json()["job_id"]
    wait_terminal(r1.json()["job_id"])


def test_item_failure_continues(home):
    """条目级失败不使作业失败：坏 chk 条目 failed 计数、好条目照常转换，
    ZIP 仅含成功条目且说明逐条登记。"""
    bad = seed(state="failed", filename="bad.gjf", protected=True,
               chk_bytes=b"tiny-corrupt")  # 执行期体检 verdict≠ok → failed
    good = seed(state="failed", filename="good.gjf", protected=True,
                chk_bytes=b"fake-chk" * 16)
    install_convert_tools(home / "g16", mixed_verdict=True)
    r = client.post("/api/v1/history/export/fchk", json={"ids": [bad, good]})
    snap = wait_terminal(r.json()["job_id"])
    assert snap["state"] == "done"
    assert snap["failed"] == 1 and snap["converted"] == 1
    dl = client.get(f"/api/v1/history/export/fchk/{r.json()['job_id']}"
                    "/download")
    with zipfile.ZipFile(__import__("io").BytesIO(dl.content)) as zf:
        assert zf.namelist() == ["good.fchk", "_导出说明.txt"]
        assert "chk 损坏/不完整" in zf.read("_导出说明.txt").decode()


# ---------------- 总预算 / 取消 / TTL / 重启 ----------------

def test_budget_exhausted_marks_missing(home, monkeypatch):
    """总预算耗尽：注入零预算 → 候选未启动记 missing「超出批量转换时间
    预算」、reused 条目照常出包、作业 done（非 failed）。"""
    monkeypatch.setattr(svc, "FCHK_BATCH_BUDGET_S", 0.0)
    r_eid = seed(state="succeeded", filename="have.gjf", with_fchk=True,
                 with_chk=False)
    cand = seed(state="failed", protected=True, filename="cand.gjf")
    install_convert_tools(home / "g16")
    r = client.post("/api/v1/history/export/fchk", json={"ids": [r_eid, cand]})
    snap = wait_terminal(r.json()["job_id"])
    assert snap["state"] == "done"
    assert snap["reused"] == 1 and snap["converted"] == 0
    assert snap["missing"] == 1
    dl = client.get(f"/api/v1/history/export/fchk/{r.json()['job_id']}"
                    "/download")
    with zipfile.ZipFile(__import__("io").BytesIO(dl.content)) as zf:
        assert "超出批量转换时间预算" in zf.read("_导出说明.txt").decode()


def test_cancel_queued_and_running(home):
    """取消：running 当前条目结束后生效（已转 fchk 保留、作业私有
    .part/ZIP 无残留）；终态后取消 409。"""
    cand = seed(state="failed", protected=True, filename="slow.gjf")
    make_tool(home / "g16", "chkchk", "exit 0\n")
    make_tool(home / "g16", "formchk",
              f'sleep 1\ncat > "$2" <<\'EOF\'\n{FCHK_GOOD}EOF\n')
    r = client.post("/api/v1/history/export/fchk", json={"ids": [cand]})
    job_id = r.json()["job_id"]
    wait_running(job_id)
    c = client.post(f"/api/v1/history/export/fchk/{job_id}/cancel")
    assert c.status_code == 202
    assert c.json()["state"] in ("running", "cancelled")
    snap = wait_terminal(job_id)
    assert snap["state"] == "cancelled"
    tmp_dir = config.HOME_DIR / config.EXPORT_TMP_SUBDIR
    assert not list(tmp_dir.glob("fchk-export-*"))  # 无 .part/ZIP 残留
    assert finalize.fchk_head_valid(
        config.HOME_DIR / "run" / str(cand) / "input.fchk")  # fchk 保留
    c2 = client.post(f"/api/v1/history/export/fchk/{job_id}/cancel")
    assert c2.status_code == 409  # 终态不可取消


def test_cancel_packing_gap(home, monkeypatch):
    """packing 条目写入间隙取消：PackCancelled 注入路径 → cancelled 且
    .part 清理。"""
    eid = seed(state="succeeded", filename="a.gjf", with_fchk=True,
               with_chk=False)
    real_pack = history_svc._pack_entries

    def packing_with_cancel(zf, entries, inner, missing, scope, **kwargs):
        kwargs["cancelled_check"] = lambda: True  # 注入条目间隙取消
        return real_pack(zf, entries, inner, missing, scope, **kwargs)

    monkeypatch.setattr(history_svc, "_pack_entries", packing_with_cancel)
    r = client.post("/api/v1/history/export/fchk", json={"ids": [eid]})
    job_id = r.json()["job_id"]
    snap = wait_terminal(job_id)
    assert snap["state"] == "cancelled"
    tmp_dir = config.HOME_DIR / config.EXPORT_TMP_SUBDIR
    assert not list(tmp_dir.glob("fchk-export-*"))


def test_download_gates_and_unknown(home):
    """下载前 409（未 done）、未知/非法形态 404（不可猜 id 不回退）。"""
    cand = seed(state="failed", protected=True, filename="slow.gjf")
    make_tool(home / "g16", "chkchk", "exit 0\n")
    make_tool(home / "g16", "formchk", "sleep 0.6\n")
    r = client.post("/api/v1/history/export/fchk", json={"ids": [cand]})
    job_id = r.json()["job_id"]
    dl = client.get(f"/api/v1/history/export/fchk/{job_id}/download")
    assert dl.status_code == 409  # 下载前未 done
    assert dl.json()["error"]["code"] == "TASK_STATE_CONFLICT"
    wait_terminal(job_id)
    assert client.get(
        "/api/v1/history/export/fchk/"
        "ffffffffffffffffffffffffffffffff").status_code == 404
    assert client.get(
        "/api/v1/history/export/fchk/..%2Fevil").status_code == 404


def test_ttl_expiry_lazy_sweep(home, monkeypatch):
    """TTL 到期惰性转 expired：状态/下载触发清扫，ZIP 删除、记录 404。"""
    monkeypatch.setattr(svc, "FCHK_EXPORT_TTL_S", 0.2)
    eid = seed(state="succeeded", filename="a.gjf", with_fchk=True,
               with_chk=False)
    job_id = client.post(
        "/api/v1/history/export/fchk", json={"ids": [eid]}).json()["job_id"]
    wait_terminal(job_id)
    tmp_dir = config.HOME_DIR / config.EXPORT_TMP_SUBDIR
    assert list(tmp_dir.glob("fchk-export-*.zip"))  # done 保留 ZIP
    time.sleep(0.3)
    assert client.get(
        f"/api/v1/history/export/fchk/{job_id}").status_code == 404
    assert client.get(
        f"/api/v1/history/export/fchk/{job_id}/download").status_code == 404
    assert not list(tmp_dir.glob("fchk-export-*.zip"))  # 清扫删除


def test_restart_clears_jobs_and_purge(home):
    """重启语义：作业表清空 → 作业 404；purge_export_tmp 扫 .part/.zip
    残留（fchk-export-* 两族形态）。"""
    eid = seed(state="succeeded", filename="a.gjf", with_fchk=True,
               with_chk=False)
    job_id = client.post(
        "/api/v1/history/export/fchk", json={"ids": [eid]}).json()["job_id"]
    wait_terminal(job_id)
    svc._jobs.clear()  # 模拟进程重启（作业表内存）
    assert client.get(
        f"/api/v1/history/export/fchk/{job_id}").status_code == 404
    tmp_dir = config.HOME_DIR / config.EXPORT_TMP_SUBDIR
    (tmp_dir / "fchk-export-dead.zip").write_bytes(b"x")
    (tmp_dir / "fchk-export-dead.zip.part").write_bytes(b"y")
    history_svc.purge_export_tmp()
    assert not list(tmp_dir.glob("fchk-export-*"))  # .part 与 ZIP 清扫


# ---------------- ZIP 形态 / 打包竞态 / scope 零回归 ----------------

def test_zip_conflict_prefix_and_rebuild(home, monkeypatch):
    """同 stem 冲突组三位补零前缀；打包期 fchk 消失弃包重建按缺登记。"""
    e1 = seed(state="succeeded", filename="same.gjf", with_fchk=True,
              with_chk=False)
    e2 = seed(state="succeeded", filename="same.gjf", with_fchk=True,
              with_chk=False)
    # 打包期把 e2 的 fchk 清走（采集已定位、写包前预检命中 → 按缺登记）
    real_valid = finalize.fchk_head_valid

    def vanish_once(path):
        ok = real_valid(path)
        if ok and path.parent.name == str(e2) or \
                (ok and str(e2) in str(path)):
            path.unlink()
        return ok

    r = client.post("/api/v1/history/export/fchk", json={"ids": [e1, e2]})
    job_id = r.json()["job_id"]
    wait_terminal(job_id)
    dl = client.get(f"/api/v1/history/export/fchk/{job_id}/download")
    with zipfile.ZipFile(__import__("io").BytesIO(dl.content)) as zf:
        names = sorted(zf.namelist())
        assert any(n.startswith(f"{e1:03d}-same.fchk") for n in names), names
        assert any(n.startswith(f"{e2:03d}-same.fchk") for n in names) \
            or "same.fchk" in names
        zf.testzip() is None


def test_scope_all_has_no_fchk(home):
    """scope=all 零回归：既有导出不含 fchk 条目（out+chk 语义不变）。"""
    eid = seed(state="succeeded", filename="h2o.gjf", with_fchk=True)
    (config.HOME_DIR / "run" / str(eid) / "input.log").write_bytes(b"LOG")
    result = history_svc.export_outputs([eid], "all")
    assert isinstance(result, Path)
    with zipfile.ZipFile(result) as zf:
        assert set(zf.namelist()) == {"h2o.out", "h2o.chk"}
        assert not any(n.endswith(".fchk") for n in zf.namelist())
