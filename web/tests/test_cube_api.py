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

import io
import json
import os
import stat
import time
import zipfile
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


def seed_succeeded(*, with_fchk: bytes | None = None,
                   filename: str = "h2o.gjf") -> int:
    tid = tasks().create_candidate(filename, "imported")
    eid = executions().create(task_id=tid, filename=filename,
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


# fixture 集（修订批 B18 §5）：038 形态反例 / 闭壳·开壳全段 fchk /
# shell 不可判定样例 / 假 cubegen 三形态
FIXTURES = Path(__file__).parent / "fixtures" / "g16tools"


def fchk_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


FCHK_FULL_CLOSED = fchk_fixture("fchk_full_closed.txt")
FCHK_FULL_OPEN = fchk_fixture("fchk_full_open.txt")
FCHK_038_SHAPE = fchk_fixture("fchk_038_shape.txt")


def install_fake_cubegen(root: Path, name: str) -> None:
    dst = root / "cubegen"
    dst.write_bytes((FIXTURES / name).read_bytes())
    dst.chmod(0o755)


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
    """g16_root 无 cubegen（摘除场景）→ 503 显式（fixture 带全段——
    段预校验先于探测通过，不误改本用例语义）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
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
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    make_cubegen(home / "g16", 'echo "boom bad fchk" >&2\nexit 3\n')
    r = post_cube(eid, kind="MO", orbital=1)
    assert r.status_code == 502
    body = r.json()["error"]
    assert body["code"] == "CUBE_GENERATION_FAILED"
    assert "boom bad fchk" in body["details"]["stderr_tail"]


def test_timeout_502(home, monkeypatch):
    from web.src.services import cube as cube_svc
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    install_fake_cubegen(home / "g16", "cubegen_slow.sh")
    monkeypatch.setattr(cube_svc, "CUBEGEN_TIMEOUT_S", 0.2)
    r = post_cube(eid, kind="Potential")
    assert r.status_code == 502
    assert r.json()["error"]["details"]["reason"] == "timeout"


# ---------------- 幂等与文件流 ----------------

def test_idempotent_hit_single_invocation(home):
    """同参数重复 POST 同 cube_id；fake cubegen 以哨兵计数仅执行一次。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
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
    """服务端合成 cubegen 实参：MO=<n> 与 <kind>=SCF（§2.4 请求文法；
    fixture 取开壳全段——Spin 段在场的合成 fchk，段预校验不误拦）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_OPEN)
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
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
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
    "  -0.4 0.1\n"
    " Alpha MO coefficients                      R   N=          17\n"
    "  1.0 0.1\n"
    " Beta MO coefficients                       R   N=          17\n"
    "  1.0 0.1\n"
    " Total SCF Density                          R   N=          17\n"
    "  1.0 0.1\n"
    " Spin SCF Density                           R   N=          17\n"
    "  0.1 0.1\n")
# 开壳层缺自旋密度段形态（修订批 §5 缺漏 2：α/β 应 422 data_missing——
# shell 判据锚点在场判开壳、段校验拦缺 Spin）
FCHK_OPEN_NO_SPIN = (
    "Gaussian, Inc.\n"
    " Multiplicity                               I                2\n"
    " Number of alpha electrons                  I                5\n"
    " Number of beta electrons                   I                4\n"
    " Alpha Orbital Energies                     R   N=          17\n"
    " Beta Orbital Energies                      R   N=          17\n"
    " Alpha MO coefficients                      R   N=          17\n"
    " Beta MO coefficients                       R   N=          17\n"
    " Total SCF Density                          R   N=          17\n")
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
    eid = seed_failed(with_fchk=FCHK_FULL_OPEN, analysis=payload)
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
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
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
    eid = seed_failed(with_fchk=FCHK_FULL_CLOSED)
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


# ---------------- 修订批 B18：数据段预校验与批量端点 ----------------

def post_batch(eid: int, **body):
    return client.post(f"/api/v1/history/{eid}/analysis/cube/batch",
                       json=body)


def seed_analysis_openshell(eid: int, *, nbasis: int = 17) -> None:
    """覆盖 analysis.json 为开壳层形态（homos 两元素；MO 上界 2×nbasis）。"""
    payload = _payload()
    payload["result"]["summary"]["nmo"] = nbasis
    payload["result"]["summary"]["nbasis"] = nbasis
    payload["result"]["summary"]["homos"] = [4.0, 3.0]
    (config.HOME_DIR / "run" / str(eid) / "analysis.json").write_text(
        results_parse.dumps_compact(payload), encoding="utf-8")


# ---------------- 单端点段预校验（R4 同步插入） ----------------

def test_single_data_missing_422_038_matrix(home):
    """038 形态反例逐 kind 矩阵（§5 缺漏 1）：Density/Potential/Spin 422
    data_missing（details.section 缺失段名 + details.kind 归属）、α/β 422
    closed_shell（先经既有 shell 判定）、MO 生成成功。"""
    eid = seed_succeeded(with_fchk=FCHK_038_SHAPE)
    sentinel = home / "g16" / "cubegen-ran"
    make_cubegen_sentinel(home, sentinel)
    for kind, section in (("Density", "Total SCF Density"),
                          ("Potential", "Total SCF Density"),
                          ("Spin", "Spin SCF Density")):
        r = post_cube(eid, kind=kind)
        assert r.status_code == 422, kind
        body = r.json()["error"]
        assert body["code"] == "VALIDATION_FAILED"
        assert body["details"]["reason"] == "data_missing", kind
        assert body["details"]["section"] == section, kind
        assert body["details"]["kind"] == kind, kind
    for kind in ("Alpha", "Beta"):  # 闭壳层形态被既有闸拦截、不进段校验
        r = post_cube(eid, kind=kind)
        assert r.status_code == 422, kind
        assert r.json()["error"]["details"]["reason"] == "closed_shell", kind
    assert not sentinel.exists()  # 422 全支路零子进程
    r = post_cube(eid, kind="MO", orbital=3)  # MO 系数在场 → 可生成
    assert r.status_code == 200
    assert sentinel.exists()


def test_single_closed_shell_spin_data_missing_422(home):
    """闭壳层健全条目 Spin → 422 data_missing（缺 Spin SCF Density 段；
    §5 单端点段校验——闭壳 Spin 422）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    r = post_cube(eid, kind="Spin")
    assert r.status_code == 422
    body = r.json()["error"]["details"]
    assert body["reason"] == "data_missing"
    assert body["section"] == "Spin SCF Density"


def test_single_open_shell_alpha_beta_missing_spin_422(home):
    """开壳层缺 Spin 段（异常终止形态）：α/β 过 shell 判定后 422
    data_missing section=Spin SCF Density（§5 缺漏 2，fail-closed 不产出
    半密度 cube）。"""
    eid = seed_failed(with_fchk=FCHK_OPEN_NO_SPIN.encode())
    make_cubegen_sentinel(home, home / "g16" / "cubegen-ran")
    for kind in ("Alpha", "Beta"):
        r = post_cube(eid, kind=kind)
        assert r.status_code == 422, kind
        body = r.json()["error"]["details"]
        assert body["reason"] == "data_missing", kind
        assert body["section"] == "Spin SCF Density", kind


def test_single_idempotent_hit_skips_section_recheck(home):
    """幂等命中先于段校验（§5 缺漏 6）：已生成 cube 后 fchk 被替换为
    缺段形态，重复 POST 幂等命中 200、不重查不 422。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    make_cubegen(home / "g16", 'printf "cube\\n" > "$4"\n')
    cid = post_cube(eid, kind="Potential").json()["cube_id"]
    (config.HOME_DIR / "run" / str(eid) / "input.fchk").write_bytes(
        FCHK_038_SHAPE)  # 缺密度段形态
    r = post_cube(eid, kind="Potential")
    assert r.status_code == 200 and r.json()["cube_id"] == cid


def test_single_shell_undetectable_mo_passes(home):
    """shell 不可判定条目 MO 放行（§5 缺漏 12，§2.4 MO 支路定稿）：
    无三级源样例（无 analysis、fchk 无 Alpha Orbital Energies 锚点）+
    Alpha MO coefficients 在场 → 单端点与批量 ["MO"] 均 200，
    不因 shell 不可判定 422 shell_unknown。"""
    eid = seed_failed(with_fchk=fchk_fixture("fchk_noshell_alpha_mo.txt"))
    install_fake_cubegen(home / "g16", "cubegen_ok.sh")
    assert post_cube(eid, kind="MO", orbital=1).status_code == 200
    r = post_batch(eid, kinds=["MO"], orbital=1, npts=-3)
    assert r.status_code == 200


# ---------------- 批量端点：文法 422（errors[] 词形） ----------------

@pytest.mark.parametrize("body", [
    {"kinds": []},                                   # 空
    {"kinds": ["MO"] * 7},                           # 超 6
    {"kinds": "MO"},                                 # 非数组
    {"kinds": ["MO", "MO"]},                         # 重复
    {"kinds": ["MO", "Junk"]},                       # 未知 kind
    {"kinds": ["MO", 1]},                            # 元素类型错
    {"kinds": ["MO"]},                               # MO 缺 orbital
    {"kinds": ["MO"], "orbital": 0},                 # orbital 下界
    {"kinds": ["MO"], "orbital": 20},                # 越上界（nmo=19）
    {"kinds": ["Potential"], "orbital": 1},          # 非 MO 带 orbital
    {"kinds": ["Potential"], "npts": 39},            # npts 越界
    {"kinds": ["Potential", "Potential"]},           # 重复（多元素）
])
def test_batch_grammar_422(home, body):
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    r = post_batch(eid, **body)
    assert r.status_code == 422, body
    payload = r.json()["error"]
    assert payload["code"] == "VALIDATION_FAILED", body
    assert "errors" in payload["details"], body     # 文法 422 errors[] 词形
    assert "kind_errors" not in payload["details"], body  # 两键互斥


def test_batch_len1_legal_200(home):
    """批量端点 kinds 长度 1 合法（§5 缺漏 9）——恰选 1 类前端路由单
    端点，批量自身受理性由契约测试钉死。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    install_fake_cubegen(home / "g16", "cubegen_ok.sh")
    r = post_batch(eid, kinds=["Potential"], npts=-2)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"


def test_batch_parse_failed_passthrough(home):
    """succeeded 无 MO 表（blocks.orbitals=false）批量含 MO → 422
    ANALYSIS_PARSE_FAILED 文法步透传（details {"block": "orbitals"}，
    两键皆无——前端 message 兜底形态钉死，§5 缺漏 15）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    payload = _payload()
    payload["result"]["blocks"]["orbitals"] = False
    (config.HOME_DIR / "run" / str(eid) / "analysis.json").write_text(
        results_parse.dumps_compact(payload), encoding="utf-8")
    r = post_batch(eid, kinds=["MO"], orbital=1)
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "ANALYSIS_PARSE_FAILED"
    assert body["details"] == {"block": "orbitals"}


# ---------------- 批量端点：fchk 闸先于段校验（码型分歧钉死） ----------------

def test_batch_fchk_gate_precedes_section(home):
    """闭壳层 + fchk 缺失同组合（§5 缺漏 8）：批量 502 fchk_missing
    （fchk 闸步骤③先于 shell/段校验步骤④）、单端点 422 closed_shell
    （shell 判定先行的既有码型，分歧按契约声明钉死）。"""
    tid = tasks().create_candidate("oh.gjf", "imported")
    eid = executions().create(task_id=tid, filename="oh.gjf",
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1.0, "defaulted": True}})
    executions().finalize(execution_id=eid, state="failed",
                          finished_at="2026-01-01T00:00:00+08:00")
    # analysis.json homos 单元素（闭壳层）：shell 判定可判定——单端点
    # shell 先行出 closed_shell；批量 fchk 闸先行出 502（fchk 不在场）
    config.HOME_DIR.joinpath("run", str(eid)).mkdir(parents=True,
                                                    exist_ok=True)
    payload = _payload()
    (config.HOME_DIR / "run" / str(eid) / "analysis.json").write_text(
        results_parse.dumps_compact(payload), encoding="utf-8")
    r = post_batch(eid, kinds=["Alpha", "Potential"])
    assert r.status_code == 502
    body = r.json()["error"]
    assert body["code"] == "CUBE_GENERATION_FAILED"
    assert body["details"]["reason"] == "fchk_missing"
    r = post_cube(eid, kind="Alpha")  # 单端点：shell 判定先行 422
    assert r.status_code == 422
    assert r.json()["error"]["details"]["reason"] == "closed_shell"


# ---------------- 批量端点：前置全量校验（kind_errors[]） ----------------

def test_batch_closed_healthy_all_six_kind_errors(home):
    """闭壳层健全条目全选六类 → 422 kind_errors[] 逐 kind 罗列（Spin
    data_missing、α/β closed_shell，§2.8 核验项 3 后半），其余三类无错
    不罗列；零生成零子进程。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    sentinel = home / "g16" / "cubegen-ran"
    make_cubegen_sentinel(home, sentinel)
    r = post_batch(eid, kinds=list(cube_svc.KINDS), orbital=1)
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "VALIDATION_FAILED"
    assert "errors" not in body["details"]          # 前置校验 kind_errors[] 词形
    ke = body["details"]["kind_errors"]
    assert ke == [
        {"kind": "Spin", "reason": "data_missing",
         "section": "Spin SCF Density"},
        {"kind": "Alpha", "reason": "closed_shell"},
        {"kind": "Beta", "reason": "closed_shell"},
    ]  # 规范序罗列；MO/Potential/Density 段齐备不罗列
    assert not sentinel.exists()  # 零生成零子进程


def test_batch_038_shape_matrix(home):
    """038 形态反例批量多选（§5 缺漏 1 批量侧，D7 走查路径 3 同形）：
    五类（不含 MO）→ 422 逐 kind 罗列零生成；仅勾选 MO → ZIP 200。"""
    eid = seed_succeeded(with_fchk=FCHK_038_SHAPE)
    install_fake_cubegen(home / "g16", "cubegen_ok.sh")
    r = post_batch(eid, kinds=["Density", "Potential", "Spin",
                               "Alpha", "Beta"])
    assert r.status_code == 422
    ke = r.json()["error"]["details"]["kind_errors"]
    assert ke == [  # 规范序（KINDS 序）罗列：Potential 先于 Density
        {"kind": "Potential", "reason": "data_missing",
         "section": "Total SCF Density"},
        {"kind": "Density", "reason": "data_missing",
         "section": "Total SCF Density"},
        {"kind": "Spin", "reason": "data_missing",
         "section": "Spin SCF Density"},
        {"kind": "Alpha", "reason": "closed_shell"},
        {"kind": "Beta", "reason": "closed_shell"},
    ]
    r = post_batch(eid, kinds=["MO"], orbital=3, npts=-3)  # 仅 MO 可生成
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o-MO-3-medium.cube"]


def test_batch_idempotent_reverse_form_422(home):
    """批量幂等序相反形态（§5 缺漏 10）：曾成功生成后 fchk 被替换为
    缺段形态，批量请求在前置全量校验即 422（先全量后生成的有意设计，
    与单端点幂等命中不重查相反）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    install_fake_cubegen(home / "g16", "cubegen_ok.sh")
    assert post_cube(eid, kind="Potential").status_code == 200
    (config.HOME_DIR / "run" / str(eid) / "input.fchk").write_bytes(
        FCHK_038_SHAPE)
    r = post_batch(eid, kinds=["Potential"])
    assert r.status_code == 422
    ke = r.json()["error"]["details"]["kind_errors"]
    assert ke == [{"kind": "Potential", "reason": "data_missing",
                   "section": "Total SCF Density"}]


# ---------------- 批量端点：生成与打包 ----------------

def test_batch_zip_all_six_all_segment(home):
    """开壳层健全条目全选六类（§2.8 核验项 3 基线 hermetic 版）：ZIP
    条目命名逐 kind（规范序、MO 含轨道号段）、包名类型段 all、
    testzip 完整性、临时包发送后删除、幂等命中零子进程复核。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_OPEN)
    seed_analysis_openshell(eid)
    sentinel = home / "g16" / "invocations"
    make_cubegen(home / "g16",
                 f'echo run >> "{sentinel}"\nprintf "cube\\n" > "$4"\n')
    r = post_batch(eid, kinds=list(cube_svc.KINDS), orbital=5, npts=-3)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    disp = r.headers["content-disposition"]
    assert "filename*=UTF-8''h2o-all-medium.zip" in disp
    assert "filename=h2o-all-medium.zip" in disp
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.testzip() is None
    assert zf.namelist() == [
        "h2o-MO-5-medium.cube", "h2o-Potential-medium.cube",
        "h2o-Density-medium.cube", "h2o-Spin-medium.cube",
        "h2o-Alpha-medium.cube", "h2o-Beta-medium.cube"]  # 规范序平铺
    assert_contract_schema(spec, "POST",
                           "/history/{id}/analysis/cube/batch", 200,
                           r.content, content_type="application/zip")
    tmp_zips = list((config.HOME_DIR / "tmp").glob("export-cube-*.zip"))
    assert tmp_zips == []  # BackgroundTask 删包（残留由启动清扫兜底）
    # 幂等复核：同参数重复批量请求零子进程（ZIP 直复用已生成 cube）
    before = sentinel.read_text().strip().splitlines()
    r2 = post_batch(eid, kinds=list(cube_svc.KINDS), orbital=5, npts=-3)
    assert r2.status_code == 200
    after = sentinel.read_text().strip().splitlines()
    assert len(after) == len(before) == 6  # 六类各一次、重试零新增


def test_batch_zip_subset_canonical_order_and_free_integer(home):
    """子集包名类型段规范序（Density+MO → MO-Density）、40–120 自由
    整数档命名段无符号数值原样入名（§5 缺漏 11、§2.5）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    install_fake_cubegen(home / "g16", "cubegen_ok.sh")
    r = post_batch(eid, kinds=["Density", "MO"], orbital=2, npts=80)
    assert r.status_code == 200
    disp = r.headers["content-disposition"]
    assert "filename*=UTF-8''h2o-MO-Density-80.zip" in disp
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o-MO-2-80.cube", "h2o-Density-80.cube"]


def test_batch_rfc5987_chinese_stem(home):
    """中文 stem 包名 RFC 5987 + ASCII fallback（§5 缺漏 4，沿 fchk
    下载先例）：包名公式类型段/档位段恒为 ASCII——全中文 stem 时清洗
    残段为 ASCII 后缀（类型段-档位段），execution-<id> 回落仅清洗为空
    时可达（本公式下理论兜底）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED, filename="水No1.gjf")
    install_fake_cubegen(home / "g16", "cubegen_ok.sh")
    r = post_batch(eid, kinds=["Density"])
    assert r.status_code == 200
    disp = r.headers["content-disposition"]
    assert "filename*=UTF-8''%E6%B0%B4No1-Density-80.zip" in disp
    assert "filename=No1-Density-80.zip" in disp
    eid2 = seed_succeeded(with_fchk=FCHK_FULL_CLOSED, filename="水.gjf")
    r2 = post_batch(eid2, kinds=["Density"])
    assert r2.status_code == 200
    disp2 = r2.headers["content-disposition"]
    assert "filename*=UTF-8''%E6%B0%B4-Density-80.zip" in disp2
    assert "filename=Density-80.zip" in disp2  # 中文段清洗、ASCII 后缀保留


def test_batch_idempotent_reuse_zero_subprocess(home):
    """批量幂等命中逐 kind 复用（§2.3 执行模型）：单端点已生成 Potential
    后批量 [Potential, Density] → 仅 Density 新执行一次（哨兵计数 2）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    sentinel = home / "g16" / "invocations"
    make_cubegen(home / "g16",
                 f'echo run >> "{sentinel}"\nprintf "cube\\n" > "$4"\n')
    assert post_cube(eid, kind="Potential").status_code == 200
    assert len(sentinel.read_text().strip().splitlines()) == 1
    r = post_batch(eid, kinds=["Potential", "Density"])
    assert r.status_code == 200
    lines = sentinel.read_text().strip().splitlines()
    assert len(lines) == 2  # Potential 幂等命中零子进程、Density 新执行
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["h2o-Potential-80.cube", "h2o-Density-80.cube"]


def test_batch_fail_fast_502_with_cache(home):
    """批量中途 cubegen 失败 fail-fast（§5 缺漏 5）：502 携带 failing
    kind、kind_arg、npts、stderr_tail；已生成类留存幂等缓存——修复后
    重试只补缺失类（哨兵计数续接，不重算已生成类）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_OPEN)  # Density/Spin 段齐备
    install_fake_cubegen(home / "g16", "cubegen_fail_on_n.sh")
    run_d = config.HOME_DIR / "run" / str(eid)
    monkeyfail = pytest.MonkeyPatch()
    try:
        monkeyfail.setenv("CUBEGEN_FAIL_ON", "2")
        r = post_batch(eid, kinds=["Density", "Spin"])
        assert r.status_code == 502
        body = r.json()["error"]
        assert body["code"] == "CUBE_GENERATION_FAILED"
        assert body["details"]["kind"] == "Spin"      # failing kind 归属
        assert body["details"]["kind_arg"] == "Spin=SCF"
        assert body["details"]["npts"] == 80
        assert "boom on call 2" in body["details"]["stderr_tail"]
        cubes = sorted(p.name for p in (run_d / "cubes").glob("*.cube"))
        assert len(cubes) == 1  # 已生成 Density 留存（幂等缓存）
        # 「修复」= 抬高失败阈值（第 3 次调用起不再触发）——重试只补
        # 缺失的 Spin，计数续接证明 Density 未重算
        monkeyfail.setenv("CUBEGEN_FAIL_ON", "99")
        r2 = post_batch(eid, kinds=["Density", "Spin"])
        assert r2.status_code == 200
    finally:
        monkeyfail.undo()
    state = (run_d / "cubegen-invocations.state").read_text().strip()
    assert state == "3"  # 重试仅补 Spin（第 3 次调用），Density 幂等复用
    zf = zipfile.ZipFile(io.BytesIO(r2.content))
    assert zf.namelist() == ["h2o-Density-80.cube", "h2o-Spin-80.cube"]


def test_batch_executable_missing_503(home):
    """批量 + g16_root 无 cubegen（§5 缺漏 13）：生成阶段首类子进程
    调用即失败 503、零产物（前置校验已通过——探测属生成阶段）。"""
    eid = seed_succeeded(with_fchk=FCHK_FULL_CLOSED)
    r = post_batch(eid, kinds=["Potential", "Density"])
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "CUBE_EXECUTABLE_MISSING"
    cubes = config.HOME_DIR / "run" / str(eid) / "cubes"
    assert not cubes.exists() or not any(cubes.iterdir())  # 零产物


def test_batch_skipped_409_and_nonterminal_404(home):
    """批量终态门槛与单端点同口径：skipped 409（details.state）、非终态
    running 404。"""
    tid = tasks().create_candidate("y.gjf", "imported")
    skipped = executions().create(task_id=tid, filename="y.gjf",
                                  resources={"nproc": {"value": 1, "defaulted": True},
                                             "mem_gb": {"value": 1.0, "defaulted": True}})
    executions().finalize(execution_id=skipped, state="skipped",
                          finished_at="2026-01-01T00:00:00+08:00")
    r = post_batch(skipped, kinds=["Potential"])
    assert r.status_code == 409
    assert r.json()["error"]["details"]["state"] == "skipped"
    tid2 = tasks().create_candidate("z.gjf", "imported")
    running = executions().create(task_id=tid2, filename="z.gjf",
                                  resources={"nproc": {"value": 1, "defaulted": True},
                                             "mem_gb": {"value": 1.0, "defaulted": True}})
    r = post_batch(running, kinds=["Potential"])
    assert r.status_code == 404


@pytest.mark.skipif(not (_real_available() and FCHK_OPEN.is_file()),
                    reason="真机依赖缺失：~/g16/cubegen 或 "
                           "oh_doublet_popreg.fchk 不在位")
def test_real_machine_batch_all_six_oh(home):
    """§2.8 核验项 3（真机基线）：开壳层 OH 全选六类 × medium 真机
    端到端——ZIP 完整性、条目命名逐 kind、体积量级留痕（供细档叠加
    提示的量级表述校准；耗时粗记）。"""
    settings().set("g16_root", str(G16_ROOT))
    eid = seed_succeeded(with_fchk=FCHK_OPEN.read_bytes())
    seed_analysis_openshell(eid)  # homos 两元素：α/β 过闸、MO 上界 34
    t0 = time.monotonic()
    r = post_batch(eid, kinds=list(cube_svc.KINDS), orbital=5, npts=-3)
    elapsed = time.monotonic() - t0
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.testzip() is None
    assert zf.namelist() == [
        "h2o-MO-5-medium.cube", "h2o-Potential-medium.cube",
        "h2o-Density-medium.cube", "h2o-Spin-medium.cube",
        "h2o-Alpha-medium.cube", "h2o-Beta-medium.cube"]
    entries_mb = sum(i.file_size for i in zf.infolist()) / 1e6
    print(f"\n[真机基线留痕] 全选六类 × medium：耗时 {elapsed:.1f}s、"
          f"ZIP {len(r.content) / 1e6:.1f}MB、条目合计 {entries_mb:.1f}MB")
