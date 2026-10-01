"""cube 端点测试（M3 B4，m3-plan §4.7/§5 test_cube_api）。

- 参数治理：kind 白名单外 422、MO orbital 必填且 1≤n≤nmo（上界取
  analysis.json）、npts 40–120 越界/类型 422 VALIDATION_FAILED；
- 非 succeeded 409；fchk 缺失 502（details 注明 formchk 产物缺失）；
- cubegen 缺失 503 CUBE_EXECUTABLE_MISSING（测试环境 g16_root 为空目录
  即天然摘除场景，显式不静默）；非零退出 502 携带 stderr 尾部；超时 502；
- 幂等：同参数重复 POST 返回同 cube_id，fake cubegen 仅执行一次；
- 真机集成（~/g16/cubegen + 新集小 fchk，缺失显式 skip）：MO=1 与
  Potential=SCF 生成成功、GET 文件流 chemical/x-cube；开壳层 fchk 演练。
"""
from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.parse import results as results_parse
from web.src.services import cube as cube_svc
from web.src.store import executions, settings, tasks
from .conftest import assert_contract_schema, load_spec
from .test_analysis_api import _payload

spec = load_spec()
client = TestClient(__import__("web.src.main", fromlist=["app"]).app)

G16_ROOT = Path("~/g16").expanduser()  # cubegen 二进制定位（g16_root 语义）
# 样本引用走集中配置（config.G16_SAMPLES_DIR，风险 7 预案），不硬编码真机路径
FCHK_CLOSED = config.G16_SAMPLES_DIR / "h2o_optfreq_popreg.fchk"
FCHK_OPEN = config.G16_SAMPLES_DIR / "oh_doublet_popreg.fchk"

SIMPLE = "#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()  # 无 cubegen：默认即摘除场景
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


def seed_succeeded(*, with_fchk: bytes | None = None) -> int:
    tid = tasks().create_candidate("h2o.gjf", "imported")
    eid = executions().create(task_id=tid, filename="h2o.gjf",
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1.0, "defaulted": True}})
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True, exist_ok=True)
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at="2026-01-01T00:00:00+08:00")
    # analysis.json（MO 上界 nmo=19）
    payload = _payload()
    payload["result"]["summary"]["nmo"] = 19
    (run_d / "analysis.json").write_text(
        results_parse.dumps_compact(payload), encoding="utf-8")
    if with_fchk is not None:
        (run_d / "input.fchk").write_bytes(with_fchk)
    return eid


def make_cubegen(root: Path, script: str) -> None:
    f = root / "cubegen"
    f.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    f.chmod(0o755)


def post_cube(eid: int, **body):
    return client.post(f"/api/v1/history/{eid}/analysis/cube", json=body)


# ---------------- 参数治理（422） ----------------

@pytest.mark.parametrize("body", [
    {"kind": "Chelpg"},                       # 白名单外
    {"kind": "MO"},                           # MO 缺 orbital
    {"kind": "MO", "orbital": 0},             # 下界
    {"kind": "MO", "orbital": 20},            # 越上界（nmo=19）
    {"kind": "MO", "orbital": True},          # bool 拒绝
    {"kind": "MO", "orbital": 1, "npts": 39},   # npts 下界
    {"kind": "MO", "orbital": 1, "npts": 121},  # npts 上界
    {"kind": "MO", "orbital": 1, "npts": "80"},  # 类型
    {"kind": "Potential", "orbital": 1},      # 非 MO 不收 orbital
])
def test_parameter_governance_422(home, body):
    eid = seed_succeeded()
    r = post_cube(eid, **body)
    assert r.status_code == 422, body
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_mo_orbital_bound_from_analysis(home):
    """orbital=nmo（19）通过、nmo+1 拒绝——上界取自 analysis.json。"""
    eid = seed_succeeded()
    ok = post_cube(eid, kind="MO", orbital=19)
    # fixture 无 fchk：校验通过后确定走 502（fchk 缺失先于 cubegen 探测）
    assert ok.status_code == 502
    bad = post_cube(eid, kind="MO", orbital=20)
    assert bad.status_code == 422


def test_non_succeeded_409(home):
    tid = tasks().create_candidate("x.gjf", "imported")
    eid = executions().create(task_id=tid, filename="x.gjf",
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1.0, "defaulted": True}})
    executions().finalize(execution_id=eid, state="failed",
                          finished_at="2026-01-01T00:00:00+08:00")
    assert post_cube(eid, kind="Potential").status_code == 409
    # GET 文件流同语义（契约 409 已登记）
    assert client.get(
        f"/api/v1/history/{eid}/analysis/cube/{'0' * 64}").status_code == 409


def test_kinds_match_contract_enum():
    """KINDS 与契约 CubeRequest.kind 枚举同源（漂移守卫）。"""
    import yaml
    raw = yaml.safe_load(config.CONTRACT_PATH.read_text(encoding="utf-8"))
    kind = raw["components"]["schemas"]["CubeRequest"]["properties"]["kind"]
    assert kind["enum"] == list(cube_svc.KINDS)


# ---------------- 执行面（502/503） ----------------

def test_cubegen_missing_503(home):
    """g16_root 无 cubegen（摘除场景）→ 503 显式。"""
    eid = seed_succeeded(with_fchk=b"FCHK")
    r = post_cube(eid, kind="Potential")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "CUBE_EXECUTABLE_MISSING"


def test_fchk_missing_502(home):
    """fchk 缺失 → 502 details 注明 formchk 产物缺失（不触 cubegen）。"""
    eid = seed_succeeded()
    make_cubegen(home / "g16", 'cp "$1" "$2"\n')
    r = post_cube(eid, kind="Potential")
    assert r.status_code == 502
    body = r.json()["error"]
    assert body["code"] == "CUBE_GENERATION_FAILED"
    assert body["details"]["reason"] == "fchk_missing"


def test_nonzero_exit_502_with_stderr_tail(home):
    eid = seed_succeeded(with_fchk=b"FCHK")
    make_cubegen(home / "g16", 'echo "boom bad fchk" >&2\nexit 3\n')
    r = post_cube(eid, kind="MO", orbital=1)
    assert r.status_code == 502
    body = r.json()["error"]
    assert body["code"] == "CUBE_GENERATION_FAILED"
    assert "boom bad fchk" in body["details"]["stderr_tail"]


def test_timeout_502(home, monkeypatch):
    from web.src.services import cube as cube_svc
    eid = seed_succeeded(with_fchk=b"FCHK")
    make_cubegen(home / "g16", 'sleep 2\n')
    monkeypatch.setattr(cube_svc, "CUBEGEN_TIMEOUT_S", 0.2)
    r = post_cube(eid, kind="Potential")
    assert r.status_code == 502
    assert r.json()["error"]["details"]["reason"] == "timeout"


# ---------------- 幂等与文件流 ----------------

def test_idempotent_hit_single_invocation(home):
    """同参数重复 POST 同 cube_id；fake cubegen 以哨兵计数仅执行一次。"""
    eid = seed_succeeded(with_fchk=b"FCHK")
    sentinel = home / "g16" / "invocations"
    make_cubegen(home / "g16",
                 f'echo run >> "{sentinel}"\n'
                 'printf "cube from cubegen\\n" > "$4"\n')
    r1 = post_cube(eid, kind="MO", orbital=5, npts=40)
    assert r1.status_code == 200
    cid = r1.json()["cube_id"]
    assert_contract_schema(spec, "POST", "/history/{id}/analysis/cube",
                           200, r1.json())
    r2 = post_cube(eid, kind="MO", orbital=5, npts=40)
    assert r2.status_code == 200 and r2.json()["cube_id"] == cid
    assert len(sentinel.read_text().strip().splitlines()) == 1  # 幂等只跑一次
    # 产物落 run/<id>/cubes/<cube_id>.cube
    cube_file = config.HOME_DIR / "run" / str(eid) / "cubes" / f"{cid}.cube"
    assert cube_file.is_file()


def test_kind_args_synthesized(home):
    """服务端合成 cubegen 实参：MO=<n> 与 <kind>=SCF（§2.4 请求文法）。"""
    eid = seed_succeeded(with_fchk=b"FCHK")
    args_log = home / "g16" / "args.txt"
    make_cubegen(home / "g16", 'echo "$@" >> "%s"\nprintf "c\\n" > "$4"\n'
                 % args_log)
    post_cube(eid, kind="MO", orbital=7)
    post_cube(eid, kind="Spin")
    lines = args_log.read_text().strip().splitlines()
    assert lines[0].split()[1] == "MO=7"
    assert lines[1].split()[1] == "Spin=SCF"
    assert lines[0].split()[-2:] == ["80", "h"]  # npts 默认 80、格式 h


def test_get_cube_stream_and_404(home):
    eid = seed_succeeded(with_fchk=b"FCHK")
    make_cubegen(home / "g16", 'printf "header line\\n" > "$4"\n')
    cid = post_cube(eid, kind="MO", orbital=1).json()["cube_id"]
    r = client.get(f"/api/v1/history/{eid}/analysis/cube/{cid}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("chemical/x-cube")
    assert r.content.startswith(b"header line")
    assert_contract_schema(spec, "GET",
                           "/history/{id}/analysis/cube/{cube_id}", 200,
                           r.content,
                           content_type="chemical/x-cube")
    # 未知/形态非法（含路径穿越形态）一律 404
    assert client.get(
        f"/api/v1/history/{eid}/analysis/cube/{'0'*64}").status_code == 404
    assert client.get(
        f"/api/v1/history/{eid}/analysis/cube/..%2Fevil").status_code == 404


# ---------------- 真机集成（缺失显式 skip） ----------------

def _real_available() -> bool:
    exe = G16_ROOT / "cubegen"
    return (exe.is_file() and os.access(exe, os.X_OK)
            and FCHK_CLOSED.is_file())


@pytest.mark.skipif(not _real_available(),
                    reason="真机依赖缺失：~/g16/cubegen 或 "
                           "h2o_optfreq_popreg.fchk 不在位")
def test_real_machine_mo_and_potential(home):
    """真机小 fchk：MO=1 与 Potential=SCF 各生成成功（B4 质量标准）。"""
    settings().set("g16_root", str(G16_ROOT))
    eid = seed_succeeded(with_fchk=FCHK_CLOSED.read_bytes())
    for body in ({"kind": "MO", "orbital": 1},
                 {"kind": "Potential"}):
        r = post_cube(eid, **body)
        assert r.status_code == 200, body
        cid = r.json()["cube_id"]
        stream = client.get(f"/api/v1/history/{eid}/analysis/cube/{cid}")
        assert stream.status_code == 200
        assert len(stream.content) > 1000  # cube 头两行为注释行（非 Gaus）


@pytest.mark.skipif(not (_real_available() and FCHK_OPEN.is_file()),
                    reason="真机依赖缺失：~/g16/cubegen 或 "
                           "oh_doublet_popreg.fchk 不在位")
def test_real_machine_open_shell(home):
    """开壳层 fchk 风险 4 演练：MO=1 生成成功。"""
    settings().set("g16_root", str(G16_ROOT))
    eid = seed_succeeded(with_fchk=FCHK_OPEN.read_bytes())
    r = post_cube(eid, kind="MO", orbital=1)
    assert r.status_code == 200
