"""工具箱域端点测试（3.8.0 工具箱 B15，toolbox-plan §5 test_toolbox）。

- freqmem 锚点解析 fixtures（r/p/d/f/g/h/i 合法样例 + Unrecognized/SCF
  两种错误形态——真机 2026-11-17 采集，假 freqmem 按 $4 角动量回放）；
- 载荷值域（num_atoms/num_basis/nproc 非正整数/超上限、shell 白名单外）；
- 白名单外（含 s）422 自有中文提示（不调 freqmem——哨兵断言），freqmem
  Unrecognized 防御 422 携带原文（两支分列）；
- 对照 verdict 算术（充足/不足/相等/delta 符号；nproc>1 总量口径与缺省
  1 等价）；
- prefill 取执行记录 resources（无声明 → default、声明可解析 → declared、
  不可解析回落 defaulted=true → default、不回读 run/<id>/input.gjf）+
  零值守卫 409（details.missing 维度）+ 非终态 404 + 终态非 succeeded 409；
- solvents 解析 184 条（JN=1 行数=NSolv + 每 id 恰一条 JN=1、多别名收
  全、DiethylEther 三别名）+ 交叉核对反例 502 ×2（NSolv 篡改/重复 JN=1）
  + 缓存命中（二次请求零子进程）+ g16_root symlink 换目标失效重取 + 503；
- 真机段（~/g16 在位：freqmem/solname 实调，缺失显式 skip 带 reason）。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.services import toolbox as toolbox_svc
from web.src.store import executions, settings, tasks

client = TestClient(__import__("web.src.main", fromlist=["app"]).app)

FIXTURES = Path(__file__).parent / "fixtures" / "g16tools"
F_SOLNAME = FIXTURES / "solname_output.txt"
F_BAD_NSOLV = FIXTURES / "solname_bad_nsolv.txt"
F_DUP_JN1 = FIXTURES / "solname_dup_jn1.txt"

G16_ROOT = Path("~/g16").expanduser()

ANALYSIS_OK = {"result": {"summary": {"natom": 3, "nbasis": 25,
                                      "homos": [12.0], "nmo": 25},
                          "blocks": {}}}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()  # 无工具：默认即摘除场景
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    toolbox_svc._solvents_cache = None  # 进程内缓存逐用例复位
    return tmp_path


def make_tool(root: Path, name: str, script: str) -> Path:
    f = root / name
    f.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    f.chmod(0o755)
    return f


def install_freqmem_by_basis(root: Path, mapping: dict[str, Path],
                             sentinel: Path | None = None) -> None:
    """假 freqmem：按第 4 参（角动量字母）回放对应 fixture；可选哨兵。"""
    cases: list[str] = []
    for basis, fixture in mapping.items():
        body = fixture.read_text(encoding="utf-8")
        quoted = body.replace("'", "'\\''")
        cases.append(f"  '{basis}') printf '%s\\n' '{quoted}';;\n")
    script = "case \"$4\" in\n" + "".join(cases) + "  *) exit 9;;\nesac\n"
    if sentinel is not None:
        script = f'echo run >> "{sentinel}"\n' + script
    make_tool(root, "freqmem", script)


# ---------------- freqmem：载荷值域与白名单 ----------------

def test_payload_value_governance_422(home):
    eid_cases = [
        {"num_atoms": 0, "num_basis": 25, "shell": "r", "basis_type": "p"},
        {"num_atoms": 3, "num_basis": -1, "shell": "r", "basis_type": "p"},
        {"num_atoms": 100001, "num_basis": 25, "shell": "r",
         "basis_type": "p"},  # 防御上限
        {"num_atoms": 3, "num_basis": 25, "shell": "x", "basis_type": "p"},
        {"num_atoms": 3.5, "num_basis": 25, "shell": "r", "basis_type": "p"},
        {"num_atoms": True, "num_basis": 25, "shell": "r", "basis_type": "p"},
        {"num_atoms": 3, "num_basis": 25, "shell": "r", "basis_type": "p",
         "nproc": 257},  # 与 link0_default_nproc 值域同口径上限
        {"num_atoms": 3, "num_basis": 25, "shell": "r", "basis_type": "p",
         "nproc": 0},
        {"num_atoms": 3, "num_basis": 25, "shell": "r", "basis_type": "p",
         "compare_mem_gb": -1},
        {"num_atoms": 3, "num_basis": 25, "shell": "r", "basis_type": "p",
         "compare_mem_gb": "8"},
    ]
    for body in eid_cases:
        r = client.post("/api/v1/toolbox/freqmem", json=body)
        assert r.status_code == 422, body
        assert r.json()["error"]["code"] == "VALIDATION_FAILED", body


def test_basis_whitelist_s_rejected_before_tool(home):
    """白名单外（含 s）→ 422 自有中文提示「角动量字母仅支持 p/d/f/g/h/i」，
    不调 freqmem（哨兵断言）——与防御路径分列。"""
    sentinel = home / "freqmem-ran"
    make_tool(home / "g16", "freqmem", f'echo run > "{sentinel}"\n')
    r = client.post("/api/v1/toolbox/freqmem",
                    json={"num_atoms": 3, "num_basis": 25, "shell": "r",
                          "basis_type": "s"})
    assert r.status_code == 422
    body = r.json()["error"]
    assert "角动量字母仅支持 p/d/f/g/h/i" in body["message"]
    assert body["details"]["errors"][0]["reason"] == "whitelist"
    assert not sentinel.exists()  # 白名单先拦，不调 freqmem


# ---------------- freqmem：锚点判定与对照算术 ----------------

def _basis_fixture(name: str) -> Path:
    return FIXTURES / name


def test_freqmem_anchor_all_basis_letters(home):
    """锚点判定：p/d/f/g/h/i 合法样例（r/u 壳层）均 200，minimum 按锚点
    数值、basis_type_echo 回显；退出码恒 0 不作判据（fixture 无退出码
    依赖）。"""
    mapping = {b: _basis_fixture(f"freqmem_r_{b}.txt")
               for b in ("p", "f", "g", "h", "i")}
    mapping["d"] = _basis_fixture("freqmem_r_p.txt")  # d 与 p 同形样例复用
    install_freqmem_by_basis(home / "g16", mapping)
    for basis in ("p", "d", "f", "g", "h", "i"):
        r = client.post("/api/v1/toolbox/freqmem",
                        json={"num_atoms": 3, "num_basis": 25,
                              "shell": "r", "basis_type": basis})
        assert r.status_code == 200, basis
        body = r.json()
        assert body["basis_type_echo"] == basis
        assert body["per_thread"] is True
        assert body["minimum_mw"] > 0
        assert abs(body["minimum_gb"]
                   - body["minimum_mw"] * 8 / 1024) < 1e-9
        assert body["verdict"] is None  # 未携带对照不返回 verdict
    # u 壳层样例
    install_freqmem_by_basis(home / "g16",
                             {"f": _basis_fixture("freqmem_u_f.txt")})
    r = client.post("/api/v1/toolbox/freqmem",
                    json={"num_atoms": 3, "num_basis": 25, "shell": "u",
                          "basis_type": "f"})
    assert r.status_code == 200


def test_freqmem_defensive_unrecognized_422_with_raw(home):
    """白名单内但 freqmem 输出 Unrecognized → 422 防御路径携带原文错误行
    （与白名单拦截分列——此时哨兵证明确实调用了工具）。"""
    sentinel = home / "freqmem-ran"
    install_freqmem_by_basis(
        home / "g16", {"p": _basis_fixture("freqmem_err_unrecognized.txt")},
        sentinel=sentinel)
    r = client.post("/api/v1/toolbox/freqmem",
                    json={"num_atoms": 3, "num_basis": 25, "shell": "r",
                          "basis_type": "p"})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["details"]["reason"] == "freqmem_unrecognized"
    assert any('Unrecognized basis type "S"' in ln
               for ln in body["details"]["error_lines"])
    assert sentinel.exists()

    install_freqmem_by_basis(
        home / "g16", {"p": _basis_fixture("freqmem_err_scf.txt")})
    r = client.post("/api/v1/toolbox/freqmem",
                    json={"num_atoms": 3, "num_basis": 25, "shell": "r",
                          "basis_type": "p"})
    assert r.status_code == 422
    assert any('Unrecognized SCF type "X"' in ln for ln in
               r.json()["error"]["details"]["error_lines"])


def test_freqmem_verdict_arithmetic(home):
    """对照 verdict 算术：总量口径 sufficient/delta_gb 符号与相等边界；
    nproc 缺省 1 与显式 1 等价。"""
    install_freqmem_by_basis(home / "g16",
                             {"p": _basis_fixture("freqmem_r_p.txt")})
    body = {"num_atoms": 3, "num_basis": 25, "shell": "r",
            "basis_type": "p", "compare_mem_gb": 8.0, "nproc": 4}
    r = client.post("/api/v1/toolbox/freqmem", json=body)
    v = r.json()["verdict"]
    need = 3.30 * 8 / 1024  # fixture 锚点 3.30 MW
    assert v["nproc"] == 4
    assert v["sufficient"] is True            # 8GB ≥ 3.30MW×8 核换算
    assert abs(v["delta_gb"] - (8.0 - need * 4)) < 1e-9

    r = client.post("/api/v1/toolbox/freqmem",
                    json={**body, "compare_mem_gb": 0.01})
    v = r.json()["verdict"]
    assert v["sufficient"] is False and v["delta_gb"] < 0  # 不足：缺口负值

    r = client.post("/api/v1/toolbox/freqmem",
                    json={**body, "nproc": 1, "compare_mem_gb": need})
    v = r.json()["verdict"]
    assert v["nproc"] == 1
    assert v["sufficient"] is True and abs(v["delta_gb"]) < 1e-9  # 相等

    # 缺省 nproc=1 等价于显式 1（载荷不带 nproc）
    r2 = client.post("/api/v1/toolbox/freqmem",
                     json={**{k: v for k, v in body.items() if k != "nproc"},
                           "compare_mem_gb": need})
    assert r2.json()["verdict"] == v


def test_freqmem_tool_missing_503_and_timeout_502(home, monkeypatch):
    """freqmem 可执行缺失 503（details.tool）；超时 502（reason=timeout）。"""
    r = client.post("/api/v1/toolbox/freqmem",
                    json={"num_atoms": 3, "num_basis": 25, "shell": "r",
                          "basis_type": "p"})
    assert r.status_code == 503
    assert r.json()["error"]["details"]["tool"] == "freqmem"

    make_tool(home / "g16", "freqmem", "sleep 5\n")
    monkeypatch.setattr(toolbox_svc, "FREQMEM_TIMEOUT_S", 0.2)
    r = client.post("/api/v1/toolbox/freqmem",
                    json={"num_atoms": 3, "num_basis": 25, "shell": "r",
                          "basis_type": "p"})
    assert r.status_code == 502
    assert r.json()["error"]["details"]["reason"] == "timeout"


# ---------------- prefill：执行记录 resources 三态 ----------------

def _seed_exec(state: str = "succeeded", resources: dict | None = None,
               analysis: dict | None = ANALYSIS_OK,
               gjf_text: str | None = None) -> int:
    tid = tasks().create_candidate("h2o.gjf", "imported")
    eid = executions().create(
        task_id=tid, filename="h2o.gjf",
        resources=resources if resources is not None else
        {"nproc": {"value": 1, "defaulted": True},
         "mem_gb": {"value": 1.0, "defaulted": True}})
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True, exist_ok=True)
    if gjf_text is not None:  # 执行副本在场——断言 prefill 不回读它
        (run_d / "input.gjf").write_text(gjf_text, encoding="utf-8")
    if analysis is not None:
        import json
        (run_d / "analysis.json").write_text(
            json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    executions().finalize(execution_id=eid, state=state,
                          finished_at="2026-01-01T00:00:00+08:00")
    return eid


def test_prefill_declared_vs_default(home):
    """prefill 取执行记录 resources：无声明 → default（设置缺省值）、
    声明可解析 → declared、不可解析回落（defaulted=true）→ default。"""
    eid = _seed_exec(resources={
        "nproc": {"value": 4, "defaulted": False},
        "mem_gb": {"value": 8.0, "defaulted": False}})
    r = client.get(f"/api/v1/toolbox/freqmem-prefill?execution_id={eid}")
    assert r.status_code == 200
    body = r.json()
    assert body["num_atoms"] == 3 and body["num_basis"] == 25
    assert body["shell"] == "r"  # homos 单元素闭壳层
    assert body["suggested_compare_mem_gb"] == 8.0
    assert body["suggested_mem_source"] == "declared"
    assert body["suggested_nproc"] == 4
    assert body["suggested_nproc_source"] == "declared"

    eid2 = _seed_exec(resources={
        "nproc": {"value": 4, "defaulted": True},
        "mem_gb": {"value": 8.0, "defaulted": True}})
    body2 = client.get(
        f"/api/v1/toolbox/freqmem-prefill?execution_id={eid2}").json()
    assert body2["suggested_mem_source"] == "default"
    assert body2["suggested_nproc_source"] == "default"

    # 不可解析声明回落：dispatcher 记账 defaulted=true → 按 default 标注
    eid3 = _seed_exec(resources={
        "nproc": {"value": 4, "defaulted": True},
        "mem_gb": {"value": 8.0, "defaulted": True}})
    body3 = client.get(
        f"/api/v1/toolbox/freqmem-prefill?execution_id={eid3}").json()
    assert body3["suggested_mem_source"] == "default"

    # 存量条目缺 resources：按设置缺省值预填并标 default
    eid4 = _seed_exec(resources={})
    body4 = client.get(
        f"/api/v1/toolbox/freqmem-prefill?execution_id={eid4}").json()
    assert body4["suggested_mem_source"] == "default"
    assert body4["suggested_nproc_source"] == "default"
    assert body4["suggested_nproc"] == int(
        settings().get("link0_default_nproc"))


def test_prefill_does_not_read_execution_copy(home):
    """prefill 不回读 run/<id>/input.gjf：副本声明 2GB/8 核（若回读会恒
    判 declared 且值错误），预填仍按执行记录缺省口径。"""
    eid = _seed_exec(
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}},
        gjf_text="%mem=2GB\n%nprocshared=8\n#p freq\n\n水\n\n0 1\nO\n")
    body = client.get(
        f"/api/v1/toolbox/freqmem-prefill?execution_id={eid}").json()
    assert body["suggested_mem_source"] == "default"
    assert body["suggested_nproc_source"] == "default"
    assert body["suggested_compare_mem_gb"] != 2.0
    assert body["suggested_nproc"] != 8


def test_prefill_zero_guards_409(home):
    """零值/缺失守卫：natom/nbasis/homos 零或缺失 409（details.missing
    维度）——不猜数。"""
    for mutate in (
        lambda s: s.update({"natom": 0}),
        lambda s: s.update({"nbasis": 0}),
        lambda s: s.update({"homos": []}),
        lambda s: s.pop("natom"),
    ):
        analysis = {"result": {"summary": {"natom": 3, "nbasis": 25,
                                           "homos": [12.0], "nmo": 25},
                               "blocks": {}}}
        mutate(analysis["result"]["summary"])
        eid = _seed_exec(analysis=analysis)
        r = client.get(f"/api/v1/toolbox/freqmem-prefill?execution_id={eid}")
        assert r.status_code == 409, mutate
        assert r.json()["error"]["code"] == "ANALYSIS_UNAVAILABLE"
        assert r.json()["error"]["details"]["missing"]


def test_prefill_state_gates(home):
    """非终态（running）404、终态非 succeeded（failed/skipped）409、
    analysis.json 缺失且重建失败 409（load_analysis 既有语义）。"""
    tid = tasks().create_candidate("x.gjf", "imported")
    running = executions().create(
        task_id=tid, filename="x.gjf",
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})
    assert client.get(
        f"/api/v1/toolbox/freqmem-prefill?execution_id={running}"
    ).status_code == 404

    failed = _seed_exec(state="failed")
    assert client.get(
        f"/api/v1/toolbox/freqmem-prefill?execution_id={failed}"
    ).status_code == 409

    skipped = _seed_exec(state="skipped", analysis=None)
    assert client.get(
        f"/api/v1/toolbox/freqmem-prefill?execution_id={skipped}"
    ).status_code == 409

    no_analysis = _seed_exec(analysis=None)
    assert client.get(
        f"/api/v1/toolbox/freqmem-prefill?execution_id={no_analysis}"
    ).status_code == 409


def test_prefill_open_shell_u(home):
    """homos 两元素开壳层 → shell=u。"""
    analysis = {"result": {"summary": {"natom": 2, "nbasis": 17,
                                       "homos": [4.0, 3.0], "nmo": 17},
                           "blocks": {}}}
    eid = _seed_exec(analysis=analysis)
    body = client.get(
        f"/api/v1/toolbox/freqmem-prefill?execution_id={eid}").json()
    assert body["shell"] == "u"


# ---------------- solvents：解析 / 交叉核对 / 缓存 ----------------

def _install_solname(root: Path, fixture: Path,
                     sentinel: Path | None = None) -> None:
    body = fixture.read_text(encoding="utf-8").replace("'", "'\\''")
    script = f"printf '%s\\n' '{body}'\n"
    if sentinel is not None:
        script = f'echo run >> "{sentinel}"\n' + script
    make_tool(root, "solname", script)


def test_solvents_parse_184_entries(home):
    """真机原样 215 行解析：184 条（JN=1 行数=NSolv、每 id 恰一条
    JN=1）、多别名收全、DiethylEther 三别名、无别名呈现空数组。"""
    _install_solname(home / "g16", F_SOLNAME)
    r = client.get("/api/v1/toolbox/solvents")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 184
    assert len(body["solvents"]) == 184
    by_id = {s["id"]: s for s in body["solvents"]}
    assert by_id[1] == {"id": 1, "name": "Water", "aliases": ["H2O"]}
    ether = by_id[8]
    assert ether["name"] == "DiethylEther"
    assert ether["aliases"] == ["Ethylether", "Ether", "CH3CH2OCH2CH3"]
    no_alias = [s for s in body["solvents"] if not s["aliases"]]
    assert len(no_alias) == 161  # 161 无别名 + 17×1 + 5×2 + 1×3 = 30 条


def test_solvents_cross_check_failures_502(home):
    """交叉核对反例 502（防御解析缺陷）：头行计数篡改版 / 重复 JN=1 版。"""
    _install_solname(home / "g16", F_BAD_NSOLV)
    r = client.get("/api/v1/toolbox/solvents")
    assert r.status_code == 502
    assert r.json()["error"]["details"]["reason"] == "cross_check_failed"

    toolbox_svc._solvents_cache = None
    _install_solname(home / "g16", F_DUP_JN1)
    r = client.get("/api/v1/toolbox/solvents")
    assert r.status_code == 502
    assert r.json()["error"]["details"]["reason"] == "dup_jn1"


def test_solvents_cache_hit_zero_subprocess(home):
    """缓存命中：二次请求零子进程（哨兵单行）；调用失败不缓存（下次
    请求重试）。"""
    sentinel = home / "solname-ran"
    _install_solname(home / "g16", F_SOLNAME, sentinel=sentinel)
    assert client.get("/api/v1/toolbox/solvents").status_code == 200
    assert client.get("/api/v1/toolbox/solvents").status_code == 200
    assert len(sentinel.read_text().strip().splitlines()) == 1

    # 失败不缓存：换 502 形态后再查仍触发子进程
    toolbox_svc._solvents_cache = None
    sentinel2 = home / "solname-ran2"
    _install_solname(home / "g16", F_BAD_NSOLV, sentinel=sentinel2)
    assert client.get("/api/v1/toolbox/solvents").status_code == 502
    assert client.get("/api/v1/toolbox/solvents").status_code == 502
    assert len(sentinel2.read_text().strip().splitlines()) == 2


def test_solvents_symlink_target_change_invalidates(home):
    """缓存键 = g16_root realpath：符号链接换目标（路径字符串不变）同样
    失效重取。"""
    real1 = home / "g16real1"
    real1.mkdir()
    _install_solname(real1, F_SOLNAME)
    link = home / "g16"
    link.rmdir()
    link.symlink_to(real1)
    assert client.get("/api/v1/toolbox/solvents").json()["count"] == 184

    real2 = home / "g16real2"
    real2.mkdir()
    tiny = home / "tiny.txt"
    tiny.write_text(" NSolv= 1\n I=   1 JN= 1 Name=OnlyOne\n",
                    encoding="utf-8")
    _install_solname(real2, tiny)
    link.unlink()
    link.symlink_to(real2)  # 路径字符串不变、realpath 已换
    body = client.get("/api/v1/toolbox/solvents").json()
    assert body["count"] == 1  # 失效重取（非旧缓存）


def test_solvents_tool_missing_503(home):
    """solname 可执行缺失 503（details.tool=solname；空目录摘除场景）。"""
    r = client.get("/api/v1/toolbox/solvents")
    assert r.status_code == 503
    assert r.json()["error"]["details"]["tool"] == "solname"


# ---------------- 真机段（缺失显式 skip 带 reason） ----------------

@pytest.mark.skipif(not (G16_ROOT / "freqmem").is_file()
                    or not os.access(G16_ROOT / "freqmem", os.X_OK),
                    reason="真机依赖缺失：~/g16/freqmem 不在位")
def test_real_freqmem(home):
    """真机实调：3/25/r/p 锚点输出与 fixture 逐位一致（核验项 5 复测）。"""
    settings().set("g16_root", str(G16_ROOT))
    r = client.post("/api/v1/toolbox/freqmem",
                    json={"num_atoms": 3, "num_basis": 25, "shell": "r",
                          "basis_type": "p", "compare_mem_gb": 8.0,
                          "nproc": 4})
    assert r.status_code == 200
    body = r.json()
    fixture = FIXTURES.joinpath("freqmem_r_p.txt").read_text("utf-8")
    assert "3.30" in fixture  # fixture 基线
    assert abs(body["minimum_mw"] - 3.30) < 1e-9
    assert body["verdict"]["sufficient"] is True

    r = client.post("/api/v1/toolbox/freqmem",
                    json={"num_atoms": 3, "num_basis": 25, "shell": "r",
                          "basis_type": "i"})
    assert r.status_code == 200
    assert abs(r.json()["minimum_mw"] - 158.80) < 1e-9  # 核验项 5 留痕值


@pytest.mark.skipif(not (G16_ROOT / "solname").is_file()
                    or not os.access(G16_ROOT / "solname", os.X_OK),
                    reason="真机依赖缺失：~/g16/solname 不在位")
def test_real_solname(home):
    """真机实调：184 条与 fixture 解析一致（Water/H2O 在案）。"""
    settings().set("g16_root", str(G16_ROOT))
    body = client.get("/api/v1/toolbox/solvents").json()
    assert body["count"] == 184
    assert body["solvents"][0]["name"] == "Water"
