"""关键词字典生成脚本与加载器测试（B1，m2-plan §5 测试表）。

脚本以子进程运行（sys.executable，AGENTS §十）；mini 知识库 fixtures
为 gaussian-kb page_manifest.json 同构样本（keyword/structure 分类、
文章页、标题等价变体各形态齐备）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from web.src.parse import keywords as kw_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "extract_keywords.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "keywords_page_manifest.json"

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


def _make_kb_dir(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "page_manifest.json").write_bytes(FIXTURE.read_bytes())
    return tmp_path


def test_mini_kb_extraction_deterministic(tmp_path):
    """mini 清单抽取结果确定：slug 全集 + 标题变体、文章页与他分类剔除。"""
    kb = _make_kb_dir(tmp_path)
    out1 = _run_to(kb, "a.txt")
    out2 = _run_to(kb, "b.txt")
    assert out1.read_text(encoding="utf-8").splitlines() == EXPECTED
    assert out1.read_bytes() == out2.read_bytes()  # 两次运行逐字节一致（幂等）


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
    # 规模登记（m2-plan §2.1）：86 真关键词页 → 97 词条（86 slug + 11 变体）
    assert len(inrepo.decode("utf-8").splitlines()) == 97


# ---------------- parse.keywords 加载器 ----------------

def test_loader_reads_inrepo_dictionary():
    words = kw_mod.load_keywords(refresh=True)
    assert len(words) == 97
    assert "opt" in words and "casscf" in words and "scrf" in words
    assert all(w == w.casefold() for w in words)


def test_loader_missing_file_degrades_to_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(kw_mod, "DICT_PATH", tmp_path / "absent.txt")
    words = kw_mod.load_keywords(refresh=True)
    assert words == frozenset()  # 缺失降级零警告，不抛异常
