"""空间占用统计测试（M3.7 B12，m3-plan §4.13/§5 test_storage_usage）。

- 统计对照实测 du -sb 一致（含 protected/cubes 等子目录、目录条目 apparent size）；
- 全态口径：运行中执行与孤儿目录计入 total（du -sb run/ 全态一致）；
- per-execution 聚合与降序、entries 默认截断前 50 条（truncated/total_entries）；
- reclaimable 口径：仅 succeeded 且超保留期的顶层 chk/rwf；未超期 0；
  failed 保全快照计 0（与 M1 清理边界单一实现）；
- 阈值判定：超阈 over=true、阈值 0 恒 false、阈值即时生效；
- 手动清理后统计即时反映；千级执行目录基准 P95 < 2s。
"""
from __future__ import annotations

import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from web.src import config
from web.src.engine import finalize
from web.src.services import storage as storage_svc
from web.src.store import executions, settings, tasks
from .conftest import assert_contract_schema, load_spec

spec = load_spec()
client = TestClient(__import__("web.src.main", fromlist=["app"]).app)

OLD = (datetime.now().astimezone()
       - timedelta(days=30)).isoformat(timespec="seconds")
FRESH = datetime.now().astimezone().isoformat(timespec="seconds")


def seed_exec(state: str, finished_at: str, filename: str = "h2o.gjf") -> int:
    tid = tasks().create_candidate(filename, "imported")
    eid = executions().create(task_id=tid, filename=filename,
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1.0, "defaulted": True}})
    executions().finalize(execution_id=eid, state=state,
                          finished_at=finished_at)
    return eid


def touch(run_root: Path, eid: int, rel: str, size: int) -> None:
    f = run_root / str(eid) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x" * size)


def test_usage_matches_du(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    e1 = seed_exec("succeeded", OLD)
    e2 = seed_exec("failed", OLD)
    touch(tmp_path / "run", e1, "input.log", 5000)
    touch(tmp_path / "run", e1, "input.chk", 3000)
    touch(tmp_path / "run", e1, "protected/keep.chk", 700)
    touch(tmp_path / "run", e1, "cubes/abc.cube", 1200)
    touch(tmp_path / "run", e2, "input.log", 800)
    touch(tmp_path / "run", e2, "protected/snap.chk", 400)
    out = storage_svc.usage()
    du = subprocess.run(["du", "-sb", str(tmp_path / "run")],
                        capture_output=True, text=True, check=True)
    assert out["total_bytes"] == int(du.stdout.split()[0])
    by_id = {e["execution_id"]: e for e in out["entries"]}
    du_e1 = subprocess.run(["du", "-sb", str(tmp_path / "run" / str(e1))],
                           capture_output=True, text=True, check=True)
    assert by_id[e1]["total_bytes"] == int(du_e1.stdout.split()[0])
    # 可清理量：succeeded 超保留期的顶层 chk（3000）；protected/ 与 failed 计 0
    assert by_id[e1]["reclaimable_bytes"] == 3000
    assert by_id[e2]["reclaimable_bytes"] == 0


def test_running_and_orphan_dirs_counted(tmp_path, monkeypatch):
    """全态口径：运行中执行与孤儿目录计入 total（du -sb run/ 全态一致）；
    运行中条目进明细（reclaimable 恒 0），孤儿目录仅计总量不进明细。"""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    tid = tasks().create_candidate("run.gjf", "imported")
    eid = executions().create(task_id=tid, filename="run.gjf",
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1.0, "defaulted": True}})
    touch(tmp_path / "run", eid, "input.log", 4000)
    orphan = tmp_path / "run" / "424242"  # 无执行行的孤儿目录
    (orphan / "scratch.d").mkdir(parents=True)
    (orphan / "scratch.d" / "tmp.dat").write_bytes(b"x" * 900)
    (tmp_path / "run" / "lost+found").write_bytes(b"y" * 7)  # 非目录杂项
    out = storage_svc.usage()
    du = subprocess.run(["du", "-sb", str(tmp_path / "run")],
                        capture_output=True, text=True, check=True)
    assert out["total_bytes"] == int(du.stdout.split()[0])
    assert [e["execution_id"] for e in out["entries"]] == [eid]
    assert out["entries"][0]["reclaimable_bytes"] == 0  # 运行中不可清理
    assert out["total_entries"] == 1
    assert out["total_bytes"] > out["entries"][0]["total_bytes"]  # 孤儿计入总量


def test_entries_sorted_and_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    sizes = [10, 500, 300, 100]
    eids = [seed_exec("succeeded", FRESH) for _ in sizes]
    for eid, size in zip(eids, sizes):
        touch(tmp_path / "run", eid, "input.log", size)
    out = storage_svc.usage()
    totals = [e["total_bytes"] for e in out["entries"]]
    assert totals == sorted(totals, reverse=True)
    assert out["truncated"] is False
    assert out["total_entries"] == len(sizes)

    # 超 50 条 → 截断标注
    for i in range(55):
        eid = seed_exec("succeeded", FRESH)
        touch(tmp_path / "run", eid, "input.log", i)
    out = storage_svc.usage()
    assert len(out["entries"]) == 50
    assert out["total_entries"] == 59
    assert out["truncated"] is True
    assert out["entries"][0]["execution_id"] == eids[1]  # 500B 最大占用居首


def test_threshold_semantics(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    eid = seed_exec("succeeded", FRESH)
    touch(tmp_path / "run", eid, "input.log", 4096)
    # 默认阈值 50GB：未超
    assert storage_svc.usage()["over"] is False
    # 阈值 0 = 禁用：恒 false
    settings().set("disk_usage_warn_gb", 0)
    out = storage_svc.usage()
    assert out["over"] is False and out["threshold_bytes"] == 0
    # 阈值以字节计（GB 粒度）：1GB 阈值对小数据不触发、即时生效
    settings().set("disk_usage_warn_gb", 1)
    out = storage_svc.usage()
    assert out["threshold_bytes"] == 1024 ** 3
    assert out["over"] is False
    # 判定式单点：total ≥ threshold_bytes 且阈值非零 ⇒ true
    assert storage_svc.over_state(1024 ** 3, 1) is True
    assert storage_svc.over_state(1024 ** 3 - 1, 1) is False
    assert storage_svc.over_state(10 ** 12, 0) is False


def test_cleanup_reflects_immediately(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    eid = seed_exec("succeeded", OLD)
    touch(tmp_path / "run", eid, "input.chk", 2000)
    touch(tmp_path / "run", eid, "input.rwf", 1000)
    out = storage_svc.usage()
    assert out["entries"][0]["reclaimable_bytes"] == 3000
    stats = finalize.cleanup_expired(
        executions().list_by_state("succeeded"), tmp_path / "run", 7,
        datetime.now().astimezone())
    assert stats == {"checked": 1, "removed_chk": 1, "removed_rwf": 1}
    out = storage_svc.usage()
    assert out["entries"][0]["reclaimable_bytes"] == 0  # 清理后即时反映
    assert out["entries"][0]["total_bytes"] > 0         # 其余文件不动


def test_reclaimable_fresh_succeeded_is_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    eid = seed_exec("succeeded", FRESH)
    touch(tmp_path / "run", eid, "input.chk", 2000)
    assert storage_svc.usage()["entries"][0]["reclaimable_bytes"] == 0


def test_skipped_without_run_dir_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    seed_exec("skipped", FRESH)
    out = storage_svc.usage()
    assert out["entries"] == [] and out["total_entries"] == 0
    assert out["total_bytes"] == 0


def test_storage_usage_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    eid = seed_exec("succeeded", FRESH)
    touch(tmp_path / "run", eid, "input.log", 100)
    r = client.get("/api/v1/storage/usage")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"total_bytes", "threshold_bytes", "over", "entries",
                         "total_entries", "truncated"}
    assert_contract_schema(spec, "GET", "/storage/usage", 200, body)


def test_setting_registered_and_validated(tmp_path, monkeypatch):
    """disk_usage_warn_gb 登记运行级目录：默认 50、0 合法、负值 422。"""
    r = client.get("/api/v1/settings")
    items = {i["key"]: i for i in r.json()["runtime"]}
    assert items["disk_usage_warn_gb"]["effect"] == "immediate"
    r = client.put("/api/v1/settings", json={"values": {"disk_usage_warn_gb": 0}})
    assert r.status_code == 200
    r = client.put("/api/v1/settings", json={"values": {"disk_usage_warn_gb": -1}})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SETTING_VALUE_INVALID"


def test_thousand_dirs_p95_under_2s(tmp_path, monkeypatch):
    """千级执行目录构造基准：P95 < 2s（修订说明二）。"""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    run_root = tmp_path / "run"
    for i in range(1100):
        tid = tasks().create_candidate(f"w{i}.gjf", "imported")
        eid = executions().create(
            task_id=tid, filename=f"w{i}.gjf",
            resources={"nproc": {"value": 1, "defaulted": True},
                       "mem_gb": {"value": 1.0, "defaulted": True}})
        executions().finalize(execution_id=eid, state="succeeded",
                              finished_at=FRESH)
        (run_root / str(eid)).mkdir(parents=True)
        (run_root / str(eid) / "input.log").write_bytes(b"x" * 100)
        (run_root / str(eid) / "input.gjf").write_bytes(b"y" * 50)
    durations = []
    for _ in range(10):
        t0 = time.perf_counter()
        out = storage_svc.usage()
        durations.append(time.perf_counter() - t0)
    durations.sort()
    p95 = durations[int(0.95 * (len(durations) - 1))]
    assert p95 < 2.0, f"P95={p95:.3f}s"
    assert out["total_entries"] == 1100 and out["truncated"] is True
