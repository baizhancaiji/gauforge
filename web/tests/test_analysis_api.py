"""分析端点契约与边界测试（M3 B3，m3-plan §4.6/§5 test_analysis_api）。

- 四端点契约形状（openapi-core 逐端点校验）与 workspace-out 四块合一形状；
- 非 succeeded 409 ANALYSIS_UNAVAILABLE；running/未知 id 404；
- analysis.json 缺失/损坏 → 惰性重建一次（重建成功 200 / 无执行目录 409）；
- 块缺失 422 ANALYSIS_PARSE_FAILED（blocks 标志驱动）；
- workspace-out 路径守卫：越界（../、绝对路径、symlink 逃逸）、非法后缀
  400 WORKSPACE_PATH_OUTSIDE，缺失 404，垃圾输入 422、解析超时 422（桩注入）；
- 收敛响应 >2MB 预算按步均匀抽稀（downsampled=true，§2.3）。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.engine import finalize
from web.src.parse import results as results_parse
from web.src.store import executions, settings, tasks
from .conftest import assert_contract_schema, load_spec

spec = load_spec()
client = TestClient(__import__("web.src.main", fromlist=["app"]).app)

SIMPLE = "#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "run").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


def _payload(*, state="parsed", blocks=None, missing=None) -> dict:
    """契约合规的最小 analysis 负载（合成构造，不依赖真机）。"""
    blocks = blocks or {"convergence": True, "frequencies": True,
                        "orbitals": True, "thermochemistry": True}
    return {
        "result": {
            "state": state, "parse_error": None if state == "parsed" else "x",
            "parser": {"name": "cclib", "version": "1.8.1"},
            "package": {"name": "Gaussian", "version": "2016+A.03"},
            "method": "B3LYP/def2SVP",
            "summary": {"natom": 3, "nmo": 19, "nbasis": 19,
                        "scf_energy_eV": -2000.0,
                        "scf_energy_hartree": -73.5,
                        "opt_converged": True, "freq_count": 3,
                        "imaginary_freq_count": 0, "homos": [4.0]},
            "blocks": blocks, "missing": missing or [],
        },
        "convergence": {
            "downsampled": False,
            "scf_trace": [{"geometry_step": 1, "cycles": [[1e-5, 1e-4, 1e-4]]}],
            "scf_targets": [1e-8, 1e-6, 1e-6],
            "geo_trace": [{"geometry_step": 1, "values": [1e-5, 1e-6, 1e-4,
                                                          1e-5]}],
            "geo_targets": [4.5e-4, 3e-4, 1.8e-3, 1.2e-3],
            "energy_series": [{"geometry_step": 1, "energy_eV": -2000.0,
                               "energy_hartree": -73.5}],
        },
        "frequencies": {"frequencies": [
            {"index": 1, "frequency_cm": 1600.0, "ir_intensity": 10.0,
             "symmetry": "A", "reduced_mass": 1.0, "imaginary": False}]},
        "orbitals": {"nmo": 19, "nbasis": 19, "homos": [4.0],
                     "orbitals": [{"index": 1, "energy_eV": -500.0,
                                   "symmetry": None, "spin": None}]},
        "thermochemistry": {"enthalpy": -73.5, "entropy": 1e-4,
                            "freeenergy": -73.6, "zpve": 0.02},
    }


def seed_succeeded(payload: dict | None = None, *,
                   state: str = "succeeded") -> int:
    """落库终态执行行 + run 目录（payload 给定时写 analysis.json）。"""
    tid = tasks().create_candidate("h2o.gjf", "imported")
    eid = executions().create(task_id=tid, filename="h2o.gjf",
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1.0, "defaulted": True}})
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True, exist_ok=True)
    (run_d / "input.log").write_text(SIMPLE, encoding="utf-8")
    executions().finalize(execution_id=eid, state=state,
                          finished_at="2026-01-01T00:00:00+08:00",
                          result_ref="analysis.json" if payload else None)
    if payload is not None:
        (run_d / "analysis.json").write_text(
            results_parse.dumps_compact(payload), encoding="utf-8")
    return eid


# ---------------- 契约形状（合成负载） ----------------

def test_overview_contract(home):
    eid = seed_succeeded(_payload())
    r = client.get(f"/api/v1/history/{eid}/analysis")
    assert r.status_code == 200
    assert r.json()["state"] == "parsed"
    assert_contract_schema(spec, "GET", "/history/{id}/analysis", 200, r.json())


def test_convergence_contract(home):
    eid = seed_succeeded(_payload())
    r = client.get(f"/api/v1/history/{eid}/analysis/convergence")
    assert r.status_code == 200
    assert r.json()["downsampled"] is False
    assert_contract_schema(spec, "GET", "/history/{id}/analysis/convergence",
                           200, r.json())


def test_frequencies_contract(home):
    eid = seed_succeeded(_payload())
    r = client.get(f"/api/v1/history/{eid}/analysis/frequencies")
    assert r.status_code == 200
    assert len(r.json()["frequencies"]) == 1
    assert_contract_schema(spec, "GET", "/history/{id}/analysis/frequencies",
                           200, r.json())


def test_orbitals_contract(home):
    eid = seed_succeeded(_payload())
    r = client.get(f"/api/v1/history/{eid}/analysis/orbitals")
    assert r.status_code == 200
    assert r.json()["orbitals"][0]["spin"] is None
    assert_contract_schema(spec, "GET", "/history/{id}/analysis/orbitals",
                           200, r.json())


# ---------------- 可见性边界：404 / 409 / 422 ----------------

def test_non_succeeded_conflicts_409(home):
    for state in ("failed", "skipped"):
        eid = seed_succeeded(_payload(), state=state)
        r = client.get(f"/api/v1/history/{eid}/analysis")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "ANALYSIS_UNAVAILABLE"
    eid = seed_succeeded(_payload(), state="failed")
    for ep in ("convergence", "frequencies", "orbitals"):
        r = client.get(f"/api/v1/history/{eid}/analysis/{ep}")
        assert r.status_code == 409


def test_running_and_unknown_404(home):
    tid = tasks().create_candidate("x.gjf", "imported")
    eid = executions().create(task_id=tid, filename="x.gjf",
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1.0, "defaulted": True}})
    assert client.get(f"/api/v1/history/{eid}/analysis").status_code == 404
    assert client.get("/api/v1/history/99999/analysis").status_code == 404


def test_block_missing_422(home):
    payload = _payload(blocks={"convergence": True, "frequencies": False,
                               "orbitals": True, "thermochemistry": False})
    eid = seed_succeeded(payload)
    r = client.get(f"/api/v1/history/{eid}/analysis/frequencies")
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "ANALYSIS_PARSE_FAILED"
    assert body["details"]["block"] == "frequencies"


# ---------------- 惰性重建（决策点 2） ----------------

def test_lazy_rebuild_success(home, monkeypatch):
    """缺失 → 补跑一次写入合成负载 → 200。"""
    eid = seed_succeeded(None)

    def _rebuild(run_dir, **k):
        (run_dir / "analysis.json").write_text(
            results_parse.dumps_compact(_payload()), encoding="utf-8")
        return finalize.ANALYSIS_NAME

    monkeypatch.setattr(finalize, "write_analysis", _rebuild)
    r = client.get(f"/api/v1/history/{eid}/analysis")
    assert r.status_code == 200 and r.json()["state"] == "parsed"


def test_lazy_rebuild_degraded_lands_200(home):
    """缺失 + 真重建链路：垃圾 input.log → degraded 产物落盘 → 200 degraded
    （degraded 可查口径 §7.1-5）。"""
    eid = seed_succeeded(None)
    (config.HOME_DIR / "run" / str(eid) / "input.log").write_bytes(b"garbage")
    r = client.get(f"/api/v1/history/{eid}/analysis")
    assert r.status_code == 200
    assert r.json()["state"] == "degraded"
    assert_contract_schema(spec, "GET", "/history/{id}/analysis", 200, r.json())


def test_lazy_rebuild_failure_409(home):
    """run 目录整体缺失 → 重建失败 → 409 ANALYSIS_UNAVAILABLE。"""
    tid = tasks().create_candidate("x.gjf", "imported")
    eid = executions().create(task_id=tid, filename="x.gjf",
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1.0, "defaulted": True}})
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at="2026-01-01T00:00:00+08:00")
    r = client.get(f"/api/v1/history/{eid}/analysis")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ANALYSIS_UNAVAILABLE"


def test_corrupted_analysis_triggers_rebuild(home, monkeypatch):
    eid = seed_succeeded(None)
    (config.HOME_DIR / "run" / str(eid) / "analysis.json").write_text(
        "{broken", encoding="utf-8")

    def _rebuild(run_dir, **k):
        (run_dir / "analysis.json").write_text(
            results_parse.dumps_compact(_payload()), encoding="utf-8")
        return finalize.ANALYSIS_NAME

    monkeypatch.setattr(finalize, "write_analysis", _rebuild)
    r = client.get(f"/api/v1/history/{eid}/analysis")
    assert r.status_code == 200 and r.json()["state"] == "parsed"


# ---------------- workspace-out ----------------

def _gold_copy(tmp_out: Path) -> bool:
    src = config.G16_SAMPLES_DIR / "anion_BC1_393.out"
    if not src.is_file():
        return False
    tmp_out.write_bytes(src.read_bytes())
    return True


def test_workspace_out_contract_with_gold(home):
    target = home / "samples" / "anion.out"
    target.parent.mkdir()
    if not _gold_copy(target):
        pytest.skip("真机金标准缺失（G16WEB_G16_SAMPLES 无 anion_BC1_393.out）")
    r = client.post("/api/v1/analysis/workspace-out", json={"path": "samples/anion.out"})
    assert r.status_code == 200
    body = r.json()
    assert body["overview"]["state"] == "parsed"
    assert body["overview"]["summary"]["freq_count"] == 39
    assert set(body) == {"overview", "convergence", "frequencies", "orbitals"}
    assert_contract_schema(spec, "POST", "/analysis/workspace-out", 200, body)


def test_workspace_out_unparseable_422(home):
    target = home / "bad.out"
    target.write_bytes(b"not a gaussian output at all")
    r = client.post("/api/v1/analysis/workspace-out", json={"path": "bad.out"})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "ANALYSIS_PARSE_FAILED"
    assert body["details"]["reason"] == "unparseable"


def test_workspace_out_timeout_422(home, monkeypatch):
    target = home / "slow.out"
    target.write_bytes(b"stub")

    def _slow(_path):
        time.sleep(1.0)

    monkeypatch.setattr(results_parse, "PARSE_TIMEOUT_S", 0.2)
    monkeypatch.setattr(results_parse, "_parse_sync", _slow)
    r = client.post("/api/v1/analysis/workspace-out", json={"path": "slow.out"})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "ANALYSIS_PARSE_FAILED"
    assert body["details"]["reason"] == "timeout"


@pytest.mark.parametrize("bad", [
    "../outside.out",                      # 相对越界
    "/etc/passwd",                          # 绝对路径
    "sub/../../escape.out",                 # 中段回溯
    "notes.txt",                            # 非法后缀
    "no/such/file.out",                     # 工作区内缺失
])
def test_workspace_out_path_guards(home, bad):
    (home / "sub").mkdir(exist_ok=True)
    r = client.post("/api/v1/analysis/workspace-out", json={"path": bad})
    assert r.status_code in (400, 404)
    if r.status_code == 400:
        assert r.json()["error"]["code"] == "WORKSPACE_PATH_OUTSIDE"
    else:
        assert r.json()["error"]["code"] == "NOT_FOUND"


def test_workspace_out_symlink_escape_rejected(home):
    outside = home.parent / "outside_secret.out"
    outside.write_text("secret", encoding="utf-8")
    link = home / "leak.out"
    os.symlink(outside, link)
    try:
        r = client.post("/api/v1/analysis/workspace-out",
                        json={"path": "leak.out"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "WORKSPACE_PATH_OUTSIDE"
    finally:
        link.unlink(missing_ok=True)
        outside.unlink(missing_ok=True)


def test_workspace_out_requires_string_path(home):
    r = client.post("/api/v1/analysis/workspace-out", json={"path": 1})
    assert r.status_code == 400


# ---------------- 收敛响应预算抽稀（§2.3） ----------------

def test_convergence_downsampled_over_budget(home):
    big = _payload()
    n = 60000
    big["convergence"]["energy_series"] = [
        {"geometry_step": i + 1, "energy_eV": -2000.0 - i * 1e-6,
         "energy_hartree": -73.5 - i * 1e-8} for i in range(n)]
    big["convergence"]["scf_trace"] = [
        {"geometry_step": i + 1, "cycles": [[1e-5, 1e-4, 1e-4]]}
        for i in range(n)]
    eid = seed_succeeded(big)
    r = client.get(f"/api/v1/history/{eid}/analysis/convergence")
    assert r.status_code == 200
    body = r.json()
    assert body["downsampled"] is True
    assert len(body["energy_series"]) < n
    assert len(body["scf_trace"]) < n
    assert body["energy_series"][-1]["geometry_step"] == n  # 末点恒保留
    assert len(json.dumps(body, ensure_ascii=False)) <= 2 * 1024 * 1024
    assert_contract_schema(spec, "GET", "/history/{id}/analysis/convergence",
                           200, body)


# ---------------- 金标准端到端（真机依赖，缺失显式 skip） ----------------

def test_gold_full_chain_via_api(home):
    """真机链路：金标准 .out → finalize 落盘 → 四端点契约形状+数值。"""
    src = config.G16_SAMPLES_DIR / "CVL_open.out"
    if not src.is_file():
        pytest.skip("真机金标准缺失（G16WEB_G16_SAMPLES 无 CVL_open.out）")
    eid = seed_succeeded(None)
    run_d = config.HOME_DIR / "run" / str(eid)
    (run_d / "input.log").write_bytes(src.read_bytes())
    assert finalize.write_analysis(run_d) == "analysis.json"
    r = client.get(f"/api/v1/history/{eid}/analysis")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["natom"] == 60
    assert body["blocks"] == {"convergence": True, "frequencies": True,
                              "orbitals": True, "thermochemistry": True}
    assert_contract_schema(spec, "GET", "/history/{id}/analysis", 200, body)
    for ep in ("convergence", "frequencies", "orbitals"):
        rr = client.get(f"/api/v1/history/{eid}/analysis/{ep}")
        assert rr.status_code == 200
        assert_contract_schema(spec, "GET",
                               f"/history/{{id}}/analysis/{ep}", 200, rr.json())
    freqs = client.get(f"/api/v1/history/{eid}/analysis/frequencies").json()
    assert len(freqs["frequencies"]) == 174
