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

import json
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


def test_non_succeeded_gates(home):
    """B13 门槛分列迁移（原 test_non_succeeded_409）：failed 缺 fchk
    POST 502（details 引导先转换）、skipped POST/GET 409（details.state）、
    failed 已有 cube GET 200（不要求 fchk）、cube 缺失 GET 404。"""
    tid = tasks().create_candidate("x.gjf", "imported")
    failed = executions().create(task_id=tid, filename="x.gjf",
                                 resources={"nproc": {"value": 1, "defaulted": True},
                                            "mem_gb": {"value": 1.0, "defaulted": True}})
    executions().finalize(execution_id=failed, state="failed",
                          finished_at="2026-01-01T00:00:00+08:00")
    r = post_cube(failed, kind="Potential")
    assert r.status_code == 502
    assert r.json()["error"]["details"]["reason"] == "fchk_missing"

    tid2 = tasks().create_candidate("y.gjf", "imported")
    skipped = executions().create(task_id=tid2, filename="y.gjf",
                                  resources={"nproc": {"value": 1, "defaulted": True},
                                             "mem_gb": {"value": 1.0, "defaulted": True}})
    executions().finalize(execution_id=skipped, state="skipped",
                          finished_at="2026-01-01T00:00:00+08:00")
    r = post_cube(skipped, kind="Potential")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["state"] == "skipped"
    assert client.get(
        f"/api/v1/history/{skipped}/analysis/cube/{'0' * 64}").status_code == 409

    cid = "1" * 64  # failed 已有 cube：GET 200（不要求 fchk 在场）
    cubes = config.HOME_DIR / "run" / str(failed) / "cubes"
    cubes.mkdir(parents=True)
    (cubes / f"{cid}.cube").write_bytes(b"cube-data")
    ok = client.get(f"/api/v1/history/{failed}/analysis/cube/{cid}")
    assert ok.status_code == 200 and ok.content == b"cube-data"
    assert client.get(
        f"/api/v1/history/{failed}/analysis/cube/{'0' * 64}").status_code == 404


def test_kinds_match_contract_enum():
    """KINDS 与契约 CubeRequest.kind 枚举同源（漂移守卫；B13 追平
    Alpha/Beta 六种，与 A6 契约相等）。"""
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


# ---------------- B13：α/β 预校验三级源 / 档位 / 门槛分列 ----------------

# fchk 头锚点最小文本（锚点名与 ~/g16/doc/formchk.txt 权威格式一致，
# 核验项 6 留痕；hermetic 源②用例不依赖真机 fchk）
FCHK_CLOSED_ANCHORS = (
    "Gaussian, Inc.\n"
    " Number of atoms                            I                3\n"
    " Multiplicity                               I                1\n"
    " Number of alpha electrons                  I                5\n"
    " Number of beta electrons                   I                5\n"
    " Number of basis functions                  I               19\n"
    " Alpha Orbital Energies                     R   N=          19\n"
    "  -0.5 0.1 0.2\n")
FCHK_OPEN_ANCHORS = (
    "Gaussian, Inc.\n"
    " Number of atoms                            I                2\n"
    " Multiplicity                               I                2\n"
    " Number of alpha electrons                  I                5\n"
    " Number of beta electrons                   I                4\n"
    " Number of basis functions                  I               17\n"
    " Alpha Orbital Energies                     R   N=          17\n"
    "  -0.5 0.1\n"
    " Beta Orbital Energies                      R   N=          17\n"
    "  -0.4 0.1\n")
# 矛盾形态：Mult=1 与 Beta 段并存（闭壳判据含「无 Beta 段」被破坏）
FCHK_CONTRADICTORY = (
    " Multiplicity                               I                1\n"
    " Number of alpha electrons                  I                5\n"
    " Number of beta electrons                   I                5\n"
    " Alpha Orbital Energies                     R   N=          19\n"
    " Beta Orbital Energies                      R   N=          19\n")
# 无 Alpha 段（源②不可得前提——不得反推闭壳层）
FCHK_NO_ALPHA_SECTION = (
    " Multiplicity                               I                1\n"
    " Number of alpha electrons                  I                5\n")


def degraded_payload() -> dict:
    """degraded analysis.json 形态（§2.2：nmo=0/nbasis=0/homos=[]/
    blocks.orbitals=false 一律判源①不可得）。"""
    payload = _payload()
    payload["result"]["summary"]["nmo"] = 0
    payload["result"]["summary"]["nbasis"] = 0
    payload["result"]["summary"]["homos"] = []
    payload["result"]["blocks"]["orbitals"] = False
    return payload


def seed_failed(*, with_fchk: bytes | None = None,
                analysis: dict | None = None,
                state: str = "failed") -> int:
    tid = tasks().create_candidate("oh.gjf", "imported")
    eid = executions().create(task_id=tid, filename="oh.gjf",
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1.0, "defaulted": True}})
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True, exist_ok=True)
    executions().finalize(execution_id=eid, state=state,
                          finished_at="2026-01-01T00:00:00+08:00")
    if with_fchk is not None:
        (run_d / "input.fchk").write_bytes(with_fchk)
    if analysis is not None:
        (run_d / "analysis.json").write_text(
            results_parse.dumps_compact(analysis), encoding="utf-8")
    return eid


def make_cubegen_sentinel(home, sentinel: Path) -> None:
    make_cubegen(home / "g16",
                 f'echo run > "{sentinel}"\nprintf "cube\\n" > "$4"\n')


def test_alpha_beta_closed_shell_422(home):
    """闭壳层条目 α/β 422 closed_shell（源① homos 单元素）——cubegen
    不被调用（闭壳层 α/β 会静默产出半密度 cube，必须 fail-closed）。"""
    eid = seed_succeeded(with_fchk=FCHK_CLOSED_ANCHORS.encode())
    sentinel = home / "g16" / "cubegen-ran"
    make_cubegen_sentinel(home, sentinel)
    for kind in ("Alpha", "Beta"):
        r = post_cube(eid, kind=kind)
        assert r.status_code == 422, kind
        body = r.json()["error"]
        assert body["code"] == "VALIDATION_FAILED"
        assert body["details"]["reason"] == "closed_shell"
    assert not sentinel.exists()


def test_alpha_beta_shell_unknown_422(home):
    """failed 条目 degraded analysis.json 在场判源①不可得 + fchk 无
    Alpha 段源②不可得 → 422 shell_unknown；零补写断言（degraded 文件
    原样、缺失文件不重建）。"""
    analysis = degraded_payload()
    eid = seed_failed(with_fchk=FCHK_NO_ALPHA_SECTION.encode(),
                      analysis=analysis)
    sentinel = home / "g16" / "cubegen-ran"
    make_cubegen_sentinel(home, sentinel)
    r = post_cube(eid, kind="Alpha")
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["details"]["reason"] == "shell_unknown"
    assert not sentinel.exists()
    after = json.loads((config.HOME_DIR / "run" / str(eid)
                        / "analysis.json").read_text(encoding="utf-8"))
    assert after == analysis  # 零补写（degraded 原样）

    eid2 = seed_failed(with_fchk=FCHK_NO_ALPHA_SECTION.encode())
    r = post_cube(eid2, kind="Beta")
    assert r.status_code == 422
    assert r.json()["error"]["details"]["reason"] == "shell_unknown"
    assert not (config.HOME_DIR / "run" / str(eid2) / "analysis.json").exists()


def test_alpha_beta_shell_unknown_contradictory(home):
    """矛盾形态（Mult=1 与 Beta 段并存）→ 两判据不成立 → shell_unknown。"""
    eid = seed_failed(with_fchk=FCHK_CONTRADICTORY.encode())
    r = post_cube(eid, kind="Alpha")
    assert r.status_code == 422
    assert r.json()["error"]["details"]["reason"] == "shell_unknown"


def test_alpha_beta_open_shell_pass_failed(home):
    """failed + 开壳锚点 fchk（源②：Mult=2、α≠β）→ α/β 出 cube。"""
    eid = seed_failed(with_fchk=FCHK_OPEN_ANCHORS.encode())
    make_cubegen(home / "g16", 'printf "cube\\n" > "$4"\n')
    for kind in ("Alpha", "Beta"):
        r = post_cube(eid, kind=kind)
        assert r.status_code == 200, kind


def test_mo_upper_open_total_span_failed(home):
    """failed 开壳 MO 上界 = Alpha N + Beta N（17+17=34，自旋块总口径）：
    MO=34 通过、MO=35 422 details.max=34（§0.5 OH 实测口径 hermetic 版）。"""
    eid = seed_failed(with_fchk=FCHK_OPEN_ANCHORS.encode())
    make_cubegen(home / "g16", 'printf "cube\\n" > "$4"\n')
    assert post_cube(eid, kind="MO", orbital=34).status_code == 200
    r = post_cube(eid, kind="MO", orbital=35)
    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"][0]["max"] == 34


def test_mo_upper_source1_failed_direct(home):
    """failed 直读在场有效 analysis.json（homos 两元素、nbasis=17）→
    上界 2×17=34 源①直读（无补写、无重建）。"""
    payload = _payload()
    payload["result"]["summary"]["nmo"] = 17
    payload["result"]["summary"]["nbasis"] = 17
    payload["result"]["summary"]["homos"] = [4.0, 3.0]
    eid = seed_failed(with_fchk=b"FCHK", analysis=payload)
    make_cubegen(home / "g16", 'printf "cube\\n" > "$4"\n')
    assert post_cube(eid, kind="MO", orbital=34).status_code == 200
    r = post_cube(eid, kind="MO", orbital=35)
    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"][0]["max"] == 34


def test_mo_upper_unknown_422(home):
    """failed 两源皆不可得（无 analysis.json + fchk 无 Alpha 段）→
    422 mo_upper_unknown——不再降级为仅正整数校验。"""
    eid = seed_failed(with_fchk=b"junk-no-anchors")
    r = post_cube(eid, kind="MO", orbital=1)
    assert r.status_code == 422
    assert r.json()["error"]["details"]["reason"] == "mo_upper_unknown"


def test_npts_presets_and_idempotent_distinct(home):
    """npts -2/-3/-4 档位直透 cubegen 位置参数；-3 与 80 幂等区分
    （不同 cube_id）；越界值 422。"""
    eid = seed_succeeded(with_fchk=b"FCHK")
    args_log = home / "g16" / "args.txt"
    make_cubegen(home / "g16",
                 f'echo "$@" >> "{args_log}"\nprintf "c\\n" > "$4"\n')
    ids = set()
    for n in (-2, -3, -4):
        r = post_cube(eid, kind="Potential", npts=n)
        assert r.status_code == 200, n
        ids.add(r.json()["cube_id"])
    assert len(ids) == 3  # 三档幂等互异
    r80 = post_cube(eid, kind="Potential", npts=80)
    assert r80.json()["cube_id"] not in ids  # -3 与 80 天然不同 id
    args = [ln.split() for ln in
            args_log.read_text().strip().splitlines()]
    assert [a[4] for a in args[:3]] == ["-2", "-3", "-4"]  # 直透位置参数
    for bad in (-1, 0, 39, 121, "80"):
        r = post_cube(eid, kind="Potential", npts=bad)
        assert r.status_code == 422, bad


def test_get_cube_after_fchk_cleaned(home):
    """GET 门槛不要求 fchk（B13 分列语义）：cube 已生成后 fchk 清理 →
    GET 仍 200。"""
    eid = seed_failed(with_fchk=b"FCHK")
    make_cubegen(home / "g16", 'printf "cube\\n" > "$4"\n')
    cid = post_cube(eid, kind="Potential").json()["cube_id"]
    (config.HOME_DIR / "run" / str(eid) / "input.fchk").unlink()
    r = client.get(f"/api/v1/history/{eid}/analysis/cube/{cid}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("chemical/x-cube")


def test_succeeded_orbitals_false_keeps_422(home):
    """succeeded blocks.orbitals=false 既有 422 ANALYSIS_PARSE_FAILED
    「无 MO 表」语义零变更（M3 口径）。"""
    eid = seed_succeeded(with_fchk=b"FCHK")
    payload = _payload()
    payload["result"]["blocks"]["orbitals"] = False
    (config.HOME_DIR / "run" / str(eid) / "analysis.json").write_text(
        results_parse.dumps_compact(payload), encoding="utf-8")
    r = post_cube(eid, kind="MO", orbital=1)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ANALYSIS_PARSE_FAILED"


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


@pytest.mark.skipif(not (_real_available() and FCHK_OPEN.is_file()),
                    reason="真机依赖缺失：~/g16/cubegen 或 "
                           "oh_doublet_popreg.fchk 不在位")
def test_real_machine_alpha_beta_oh(home):
    """B13 真机核验（§0.5 实测口径）：开壳层 OH α/β 正常出 cube；
    MO=34（2×nbasis 总口径）通过、MO=35 422 details.max=34；
    closed-shell 水 α/β 422 closed_shell。"""
    settings().set("g16_root", str(G16_ROOT))
    # 源①链：analysis.json homos 两元素 + 真机 cubegen
    payload = _payload()
    payload["result"]["summary"]["nmo"] = 17
    payload["result"]["summary"]["nbasis"] = 17
    payload["result"]["summary"]["homos"] = [4.0, 3.0]
    eid = seed_succeeded(with_fchk=FCHK_OPEN.read_bytes())
    (config.HOME_DIR / "run" / str(eid) / "analysis.json").write_text(
        results_parse.dumps_compact(payload), encoding="utf-8")
    for kind in ("Alpha", "Beta"):
        r = post_cube(eid, kind=kind)
        assert r.status_code == 200, kind
        stream = client.get(
            f"/api/v1/history/{eid}/analysis/cube/{r.json()['cube_id']}")
        assert stream.status_code == 200 and len(stream.content) > 1000
    assert post_cube(eid, kind="MO", orbital=34).status_code == 200
    r = post_cube(eid, kind="MO", orbital=35)
    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"][0]["max"] == 34

    # 源②链：failed 条目无 analysis.json，真机 fchk 头锚点判定开壳
    eid2 = seed_failed(with_fchk=FCHK_OPEN.read_bytes())
    r = post_cube(eid2, kind="Alpha")
    assert r.status_code == 200
    assert not (config.HOME_DIR / "run" / str(eid2)
                / "analysis.json").exists()  # 零补写

    # 闭壳层水 α/β 422（源① homos 单元素；真机半密度形态不放行）
    eid3 = seed_succeeded(with_fchk=FCHK_CLOSED.read_bytes())
    r = post_cube(eid3, kind="Alpha")
    assert r.status_code == 422
    assert r.json()["error"]["details"]["reason"] == "closed_shell"
