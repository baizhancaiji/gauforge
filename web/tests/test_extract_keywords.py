"""关键词字典生成脚本与加载器测试（B1，m2-plan §2.1 + 插波 3.2.0 批次 B 扩面）。

脚本以子进程运行（sys.executable，AGENTS §十）；mini 知识库 fixtures
为 gaussian-kb 数据目录同构样本（page_manifest.json + markdown/ 正文，
正文缺失时仅出面①基座——扩面提取对缺失文件静默跳过）。

插波 3.2.0 批次 B 增补断言（m4-combo-template-deploy-plan §4/§8.1）：
词典全小写、无重复词、排序稳定；enforce 达标判据 ①②③ 的逐条精确匹配。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from web.src.parse import keywords as kw_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "extract_keywords.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "keywords_page_manifest.json"
FIX_MD = Path(__file__).resolve().parent / "fixtures"

# mini 清单预期词条：keyword 分类 6 页，剔除文章页 thermo/oniom_technote；
# slug 全集（opt/densityfit/cas/extrabasis/cbs）+ 标题等价变体
# （nodensityfit/casscf/extradensitybasis；「CBS Methods」含空格不收）。
EXPECTED = ["cas", "casscf", "cbs", "densityfit", "extrabasis",
            "extradensitybasis", "nodensityfit", "opt"]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          cwd=REPO_ROOT, capture_output=True, text=True)


def _run_to(tmp_path: Path, name: str) -> Path:
    out = tmp_path / name
    proc = _run("--kb-dir", str(tmp_path), "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    return out


def _make_kb_dir(tmp_path: Path, *, with_markdown: bool = False) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "page_manifest.json").write_bytes(FIXTURE.read_bytes())
    if with_markdown:
        md = tmp_path / "markdown"
        (md / "gv6").mkdir(parents=True)
        (md / "keyword").mkdir(parents=True)
        (md / "structure").mkdir(parents=True)
        shutil.copy(FIX_MD / "kb_gv6_table.md",
                    md / "gv6" / "gv6-gaussian-calculation-setup-keywords-and-options.md")
        shutil.copy(FIX_MD / "kb_dft.md", md / "keyword" / "dft.md")
        shutil.copy(FIX_MD / "kb_basissets.md", md / "structure" / "basissets.md")
    return tmp_path


def test_mini_kb_extraction_deterministic(tmp_path):
    """mini 清单抽取结果确定：slug 全集 + 标题变体、文章页与他分类剔除。"""
    kb = _make_kb_dir(tmp_path)
    out1 = _run_to(kb, "a.txt")
    out2 = _run_to(kb, "b.txt")
    assert out1.read_text(encoding="utf-8").splitlines() == EXPECTED
    assert out1.read_bytes() == out2.read_bytes()  # 两次运行逐字节一致（幂等）


def test_mini_kb_markdown_faces(tmp_path):
    """扩面提取：gv6 对照表/dft 锚点/basissets 族与形态规则，噪声词剔除。"""
    kb = _make_kb_dir(tmp_path, with_markdown=True)
    out = _run_to(kb, "md.txt")
    words = set(out.read_text(encoding="utf-8").splitlines())
    # 面②gv6 对照表末列（route 切分、= 全形、单字母白名单）
    assert {"freq=roa", "opt=rfo", "opt", "freq", "p", "b3lyp"} <= words
    # 面②dft 短语锚点（正/反序）与族正则
    assert {"pbe1pbe", "b1b95", "m06", "m062x", "wb97xd"} <= words
    # 面③basissets 族 + 极化/弥散形态生成（+ 插于数字与 g 之间）
    assert {"sto-3g", "cc-pvtz", "aug-cc-pvtz", "def2svp", "lanl2dz",
            "6-31g(d)", "6-31+g(d,p)", "6-311++g(2d,2p)", "6-31g**"} <= words
    # 噪声剔除：gv6 散文单元、句首英文词、Link0 行
    prose = {"prefix", "fragment", "molecule", "specification", "included",
             "the", "functionals", "related", "specified", "r", "u",
             "%mem", "%nprocshared"}
    assert not (words & prose)


def test_kb_dir_and_out_parameters_effective(tmp_path):
    """--kb-dir 指向他目录时只读该目录清单；--out 落点参数化。"""
    kb = _make_kb_dir(tmp_path / "kb")
    out = tmp_path / "custom" / "kw.txt"
    proc = _run("--kb-dir", str(kb), "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    assert out.read_text(encoding="utf-8").splitlines() == EXPECTED


def test_output_format_sorted_lowercase_lf(tmp_path):
    """每行一词、小写、按码点排序、LF 行尾且文件以换行收尾。"""
    kb = _make_kb_dir(tmp_path)
    data = _run_to(kb, "f.txt").read_bytes()
    assert b"\r" not in data
    assert data.endswith(b"\n")
    lines = data.decode("utf-8").splitlines()
    assert lines == sorted(lines)
    assert all(w == w.casefold() and w for w in lines)


def test_real_kb_inrepo_dictionary_matches_regeneration(tmp_path):
    """入库字典与对真实知识库（gaussian-kb 结构化数据目录）重生成一致。"""
    real_kb = Path("~/gaussian-kb/data").expanduser()
    if not (real_kb / "page_manifest.json").is_file():
        import pytest
        pytest.skip("gaussian-kb 结构化数据目录不存在")
    out = _run_to(real_kb, "regen.txt")
    inrepo = kw_mod.DICT_PATH.read_bytes()
    assert out.read_bytes() == inrepo, \
        "入库字典与重生成不一致：请重跑 scripts/extract_keywords.py"
    # 规模登记：97 词条（m2-plan 基座）→ 387（插波 3.2.0 批次 B 扩面，
    # 面①97 + 面②gv6 对照表与 dft 锚点 + 面③basissets 族与形态生成）
    assert len(inrepo.decode("utf-8").splitlines()) == 387


def test_inrepo_dictionary_lowercase_unique_sorted():
    """入库词典全小写、无重复词、排序稳定（需求三，§4 新断言）。"""
    lines = kw_mod.DICT_PATH.read_text(encoding="utf-8").splitlines()
    assert lines == sorted(lines)
    assert len(lines) == len(set(lines))
    assert all(w == w.casefold() and w for w in lines)


# ---------------- enforce 达标判据（§8.1，逐条精确匹配） ----------------

def test_gate_default_route_tokens_in_dictionary():
    """判据①：初始 route 全 token（p/b3lyp/6-31g(d)/opt/freq）精确匹配。"""
    words = kw_mod.load_keywords(refresh=True)
    for tok in ("p", "b3lyp", "6-31g(d)", "opt", "freq"):
        assert tok in words, tok


def test_gate_temp_freq_variants_in_dictionary():
    """判据②：temp/temperature 与 freq 变体集在词典内。"""
    words = kw_mod.load_keywords(refresh=True)
    for tok in ("temp", "temperature", "freq", "freq=vcd", "freq=anharmonic",
                "freq=noraman", "freq=roa", "freq=projected"):
        assert tok in words, tok


def test_gate_named_methods_and_bases_in_dictionary():
    """判据③：具名方法面与具名基组面（§8.1 定案清单）逐条精确匹配，
    数量下界各 ≥10（enforce 切换闸门底线，非提取目标）。"""
    words = kw_mod.load_keywords(refresh=True)
    # 方法面（§8.1 素材源②定案：gv6 对照表 + dft 页章节）
    methods = ["hf", "mp2", "b3lyp", "wb97xd", "cam-b3lyp", "m06", "m062x",
               "m11", "mn15", "ccsd", "casscf", "am1", "pm6", "pbepbe",
               "hseh1pbe", "wb97x", "lc-wpbe", "b97d", "b2plypd3",
               "bhandhlyp", "pw6b95d3", "tpsstpss", "mp4(sdtq)", "cbs-qb3",
               "w1bd", "uff", "amber"]
    # 基组面（§8.1 素材源③定案：basissets 页族与形态生成；def2-svp 文献
    # 连字符形按 KB/G16 关键词形 def2svp 收录）
    bases = ["6-31g(d)", "6-31g(d,p)", "6-31+g(d,p)", "6-311+g(d,p)",
             "6-311++g(2d,2p)", "6-31g(3df,3pd)", "sto-3g", "3-21g(d)",
             "cc-pvtz", "aug-cc-pvtz", "def2svp", "def2tzvp", "lanl2dz",
             "cep-121g", "svpfit", "dgdzvp", "qzvp",
             "epr-iii", "midix", "cbsb7"]
    missing_m = [w for w in methods if w not in words]
    missing_b = [w for w in bases if w not in words]
    assert not missing_m, f"方法面缺失：{missing_m}"
    assert not missing_b, f"基组面缺失：{missing_b}"
    assert len(methods) >= 10 and len(bases) >= 10


# ---------------- parse.keywords 加载器 ----------------

def test_loader_reads_inrepo_dictionary():
    words = kw_mod.load_keywords(refresh=True)
    assert len(words) == 387
    assert "opt" in words and "casscf" in words and "scrf" in words
    assert all(w == w.casefold() for w in words)


def test_loader_missing_file_degrades_to_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(kw_mod, "DICT_PATH", tmp_path / "absent.txt")
    words = kw_mod.load_keywords(refresh=True)
    assert words == frozenset()  # 缺失降级零警告，不抛异常
