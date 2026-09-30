"""结果解析单测（M3 B1，m3-plan §4.4/§5 test_analysis_parse）。

金标准 = 新集 6 份（m3-plan §2.2 样本更换记录 2026-10-01，G16WEB_G16_SAMPLES
可覆盖，默认 ~/g16/tests）：
- 正常态 4 份逐属性断言：CVL_open（opt+freq 全属性旗舰）、anion_BC1_393
  （最小 freq；内含已完成 Berny 优化段，optdone=True 属实）、
  CVLH_open_opt_svp_hd（纯 opt，无频率/热化学块）、c9c1_sp_smd_hd（纯 sp，
  optdone=None → opt_converged=null）；
- 异常态 2 份降级分支断言：c8b_ts（Error termination，success=false）、
  crest9_BC1c_c4_res6（强停/截断，无 Normal termination）——均 degraded 且
  已得块保留；
真机依赖缺失时整组显式 skip（-rs 可见 reason，不得静默）。
构造异常输入（空文件/垃圾字节/纯文本）与解析超时无需真机，断言降级不抛出。
"""
from __future__ import annotations

import json

import pytest

from web.src import config
from web.src.parse import results as results_mod

GOLD_OK = ("CVL_open.out", "anion_BC1_393.out",
           "CVLH_open_opt_svp_hd.out", "c9c1_sp_smd_hd.out")
GOLD_BAD = ("c8b_ts.out", "crest9_BC1c_c4_res6.out")
_ALL_GOLD = GOLD_OK + GOLD_BAD


def _sample(name: str):
    return config.G16_SAMPLES_DIR / name


def _gold_available() -> bool:
    return all(_sample(n).is_file() for n in _ALL_GOLD)


requires_gold = pytest.mark.skipif(
    not _gold_available(),
    reason="真机金标准缺失：G16WEB_G16_SAMPLES（默认 ~/g16/tests）下无新集 6 份"
           "（CVL_open/anion_BC1_393/CVLH_open_opt_svp_hd/c9c1_sp_smd_hd/"
           "c8b_ts/crest9_BC1c_c4_res6）")


# ---------------- 金标准 · 正常态逐属性 ----------------

@pytest.fixture(scope="module")
def flagship():
    if not _gold_available():
        pytest.skip("真机金标准缺失（见模块 docstring）")
    return results_mod.parse_output(_sample("CVL_open.out"))


@requires_gold
def test_flagship_state_and_provenance(flagship):
    """CVL_open：parsed、解析器/来源/方法摘要口径。"""
    r = flagship["result"]
    assert r["state"] == "parsed" and r["parse_error"] is None
    assert r["parser"]["name"] == "cclib"
    assert r["parser"]["version"] == pytest.approx(
        _cclib_version(), abs=0) or r["parser"]["version"] == _cclib_version()
    assert r["package"] == {"name": "Gaussian", "version": "2016+A.03"}
    assert r["method"] == "B3LYP/def2SVP"
    assert r["missing"] == []  # parsed 恒空（预期缺失由 blocks 承载）


def _cclib_version() -> str:
    import cclib
    return str(cclib.__version__)


@requires_gold
def test_flagship_summary(flagship):
    """CVL_open 概览数值（2026-10-01 探针实证）。"""
    s = flagship["result"]["summary"]
    assert s["natom"] == 60 and s["nbasis"] == 579 and s["nmo"] == 579
    assert s["homos"] == [110.0]
    assert s["opt_converged"] is True
    assert s["freq_count"] == 174 and s["imaginary_freq_count"] == 0
    assert s["scf_energy_eV"] == pytest.approx(-35976.551926354434, rel=1e-9)
    # eV→hartree 换算单点（cclib convertor 口径）
    assert s["scf_energy_hartree"] == pytest.approx(
        s["scf_energy_eV"] / 27.211386245988, rel=1e-6)


@requires_gold
def test_flagship_blocks_all_available(flagship):
    assert flagship["result"]["blocks"] == {
        "convergence": True, "frequencies": True, "orbitals": True,
        "thermochemistry": True}


@requires_gold
def test_flagship_convergence(flagship):
    c = flagship["convergence"]
    assert c["downsampled"] is False
    assert len(c["scf_trace"]) == 28          # 逐几何步 SCF 迹线
    assert len(c["scf_trace"][0]["cycles"][0]) == 3   # 3 列判据
    assert c["scf_targets"] == pytest.approx([1e-08, 1e-06, 1e-06])
    assert len(c["geo_trace"]) == 28 and len(c["geo_targets"]) == 4
    assert len(c["energy_series"]) == 28
    assert c["energy_series"][-1]["energy_eV"] == pytest.approx(
        flagship["result"]["summary"]["scf_energy_eV"], rel=1e-12)
    assert {p["geometry_step"] for p in c["scf_trace"]} == set(range(1, 29))


@requires_gold
def test_flagship_frequencies(flagship):
    freqs = flagship["frequencies"]["frequencies"]
    assert len(freqs) == 174
    first = freqs[0]
    assert first["index"] == 1
    assert first["frequency_cm"] == pytest.approx(16.48, abs=0.01)
    assert first["ir_intensity"] == pytest.approx(0.1584, abs=1e-3)
    assert first["reduced_mass"] == pytest.approx(3.2263, abs=1e-3)
    assert first["symmetry"] == "A"
    assert first["imaginary"] is False
    assert [f["index"] for f in freqs] == list(range(1, 175))


@requires_gold
def test_flagship_orbitals(flagship):
    o = flagship["orbitals"]
    assert o["nmo"] == 579 and o["nbasis"] == 579 and o["homos"] == [110.0]
    assert len(o["orbitals"]) == 579
    # cclib homos 为 0 基：HOMO = moenergies[110] = 清单 1 基第 111 项
    # （与 cubegen MO=<n> 同基，C4 预置 HOMO=111）
    homo = o["orbitals"][110]
    assert homo["index"] == 111
    assert homo["energy_eV"] == pytest.approx(-5.024310135632, rel=1e-9)
    # 新集实证：mosyms 全缺 → symmetry null；闭壳层单组 → spin null
    assert homo["symmetry"] is None and homo["spin"] is None


@requires_gold
def test_flagship_thermochemistry(flagship):
    t = flagship["thermochemistry"]
    assert t is not None and set(t) == {"enthalpy", "entropy", "freeenergy",
                                        "zpve"}
    assert t["enthalpy"] == pytest.approx(-1321.561739, rel=1e-9)


@requires_gold
def test_anion_freq_with_real_optdone():
    """anion_BC1_393：内含已完成 Berny 优化段，optdone=True 属实（非误报，
    勿按「纯 freq 必 null」断言——样本更换记录口径）。"""
    out = results_mod.parse_output(_sample("anion_BC1_393.out"))
    s = out["result"]["summary"]
    assert out["result"]["state"] == "parsed"
    assert s["natom"] == 15 and s["freq_count"] == 39
    assert s["opt_converged"] is True
    assert out["result"]["blocks"] == {
        "convergence": True, "frequencies": True, "orbitals": True,
        "thermochemistry": True}
    assert len(out["frequencies"]["frequencies"]) == 39


@requires_gold
def test_pure_opt_missing_blocks_stay_parsed():
    """CVLH_open_opt_svp_hd：纯 opt 无频率/热化学 → 块置 false、state 仍
    parsed、missing 恒空（预期缺失不是缺失事故）。"""
    out = results_mod.parse_output(_sample("CVLH_open_opt_svp_hd.out"))
    r = out["result"]
    assert r["state"] == "parsed" and r["missing"] == []
    assert r["summary"]["freq_count"] is None
    assert r["blocks"]["frequencies"] is False
    assert r["blocks"]["thermochemistry"] is False
    assert out["frequencies"]["frequencies"] == []
    assert out["thermochemistry"] is None
    assert r["blocks"]["convergence"] is True          # 21 步优化迹线
    assert len(out["convergence"]["geo_trace"]) == 21
    assert out["convergence"]["scf_targets"] == pytest.approx(
        [1e-08, 1e-06, 1e-06])


@requires_gold
def test_pure_sp_opt_converged_null():
    """c9c1_sp_smd_hd：optdone/optstatus 皆无 → opt_converged=null（非优化
    任务）；收敛块仅 SCF 迹线（geo 空）。"""
    out = results_mod.parse_output(_sample("c9c1_sp_smd_hd.out"))
    r = out["result"]
    assert r["state"] == "parsed"
    assert r["summary"]["opt_converged"] is None
    assert r["summary"]["freq_count"] is None
    assert r["blocks"] == {"convergence": True, "frequencies": False,
                           "orbitals": True, "thermochemistry": False}
    c = out["convergence"]
    assert len(c["scf_trace"]) == 1 and c["geo_trace"] == []
    assert len(c["energy_series"]) == 1


# ---------------- 金标准 · 异常态降级分支（真机） ----------------

@requires_gold
def test_error_termination_degrades_with_partial_blocks():
    """c8b_ts：Error termination → success=false → degraded，已得块保留
    （SCF 迹线/轨道仍在），missing 登记缺失属性。"""
    out = results_mod.parse_output(_sample("c8b_ts.out"))
    r = out["result"]
    assert r["state"] == "degraded"
    assert r["parse_error"] is not None and "success" in r["parse_error"]
    assert r["blocks"]["convergence"] is True     # 3 步迹线已得
    assert len(out["convergence"]["scf_trace"]) == 3
    assert r["blocks"]["orbitals"] is True        # MO 表已得
    assert r["blocks"]["frequencies"] is False
    assert "vibfreqs" in r["missing"]


@requires_gold
def test_stalled_truncation_degrades_with_partial_blocks():
    """crest9_BC1c_c4_res6：强停/截断（无 Normal termination）→ degraded，
    已得 SCF 迹线保留。"""
    out = results_mod.parse_output(_sample("crest9_BC1c_c4_res6.out"))
    r = out["result"]
    assert r["state"] == "degraded"
    assert r["parse_error"] is not None
    assert r["blocks"]["convergence"] is True
    assert len(out["convergence"]["scf_trace"]) >= 1


# ---------------- 构造异常输入（无需真机）：降级不抛出 ----------------

@pytest.mark.parametrize("content,label", [
    (b"", "空文件"),
    (bytes(range(256)) * 8, "垃圾字节"),
    (b"hello world\nnot a gaussian output\n", "纯文本"),
])
def test_degraded_inputs_never_raise(tmp_path, content, label):
    path = tmp_path / "bad.out"
    path.write_bytes(content)
    out = results_mod.parse_output(path)
    r = out["result"]
    assert r["state"] == "degraded" and r["parse_error"], label
    assert r["blocks"] == {"convergence": False, "frequencies": False,
                           "orbitals": False, "thermochemistry": False}
    assert out["frequencies"]["frequencies"] == []
    assert out["orbitals"]["orbitals"] == []
    assert out["thermochemistry"] is None
    # 全形状 JSON 可序列化（numpy 原生化与 NaN 守卫的最终检验）
    assert json.loads(json.dumps(out, ensure_ascii=False)) == json.loads(
        json.dumps(out, ensure_ascii=False))


def test_parse_timeout_degrades(tmp_path, monkeypatch):
    """超时按 degraded 落地（60s 上限的注入化验证，不真等 60s）。"""
    import time

    path = tmp_path / "slow.out"
    path.write_bytes(b"stub")

    def _slow(_path):
        time.sleep(1.0)
        raise AssertionError("超时后不应再消费结果")

    monkeypatch.setattr(results_mod, "_parse_sync", _slow)
    out = results_mod.parse_output(path, timeout_s=0.2)
    assert out["result"]["state"] == "degraded"
    assert "解析超时" in out["result"]["parse_error"]


def test_missing_file_degrades(tmp_path):
    out = results_mod.parse_output(tmp_path / "nope.out")
    assert out["result"]["state"] == "degraded"
