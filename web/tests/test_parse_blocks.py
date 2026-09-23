"""输入分块解析测试（m1-plan §5：五段切块/Link0/缺失识别/多步/CRLF/Variables/金标准）。"""
from pathlib import Path

import pytest

from web.src.parse.blocks import parse_input

GOLDEN_DIR = Path.home() / "g16" / "tests" / "com"

WATER = """%chk=/tmp/water.chk
%mem=1GB
%nprocshared=4

#p B3LYP/6-31G(d) opt freq

水分子优化
两行标题

0 1
O
H 1 R1
H 1 R2 2 A2

Variables:
R1 0.96
R2 0.96
A2 109.47

Constants:
RC 1.0
"""


def test_five_section_split_with_variables_constants():
    r = parse_input(WATER)
    b = r["blocks"]
    assert b["link0"] == {"lines": ["%chk=/tmp/water.chk", "%mem=1GB",
                                    "%nprocshared=4"], "missing": []}
    assert b["route"] == "#p B3LYP/6-31G(d) opt freq"
    assert b["title"] == "水分子优化\n两行标题"
    assert b["charge_mult"] == "0 1"
    assert b["molecule"] == {"atom_count": 3, "formula": "H2O1",
                             "variables_present": True, "constants_present": True}
    assert b["additional_sections"] == []
    assert r["parse_errors"] == []
    assert r["multistep"] is False


def test_link0_missing_detection():
    r = parse_input("%mem=2GB\n\n#p hf/sto-3g\n\nt\n\n0 1\nO\nH 1 0.96\n"
                    "H 1 0.96 2 1.0\n")
    assert r["blocks"]["link0"]["missing"] == ["NProcShared"]
    r2 = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nO\nH 1 0.96\nH 1 0.96 2 1.0\n")
    assert r2["blocks"]["link0"]["missing"] == ["NProcShared", "Mem"]
    assert r2["blocks"]["link0"]["lines"] == []


def test_title_over_five_lines_rejected():
    body = "#p hf/sto-3g\n\n" + "\n".join(f"line{i}" for i in range(1, 7)) \
        + "\n\n0 1\nO\n"
    r = parse_input(body)
    assert any(e["section"] == "title" for e in r["parse_errors"])
    assert r["blocks"]["title"] is not None


def test_multistep_link1_rejected():
    text = ("#p hf/sto-3g\n\nstep one\n\n0 1\nO\nH 1 0.96\nH 1 0.96 2 1.0\n\n"
            "--Link1--\n\n#p hf/sto-3g\n\nstep two\n\n0 1\nO\n")
    r = parse_input(text)
    assert r["multistep"] is True
    assert r["parse_errors"][0]["section"] == "link1"
    assert r["parse_errors"][0]["line"] == 10
    # 仅解析第一步，第二步内容不混入
    assert r["blocks"]["route"] == "#p hf/sto-3g"
    assert r["blocks"]["molecule"]["atom_count"] == 3


def test_crlf_normalization():
    r = parse_input("%mem=1GB\r\n\r\n#p hf/sto-3g\r\n\r\nt\r\n\r\n0 1\r\n"
                    "O\r\nH 1 0.96\r\nH 1 0.96 2 1.0\r\n")
    assert r["parse_errors"] == []
    assert r["blocks"]["charge_mult"] == "0 1"
    assert r["blocks"]["molecule"]["formula"] == "H2O1"


def test_hill_formula_rules():
    # 计数 1 显式；无碳按字母序；有碳 C、H 优先
    r = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nO\nH 1 0.96\nH 1 0.96 2 1.0\n")
    assert r["blocks"]["molecule"]["formula"] == "H2O1"
    benzene = ("#p hf/sto-3g\n\nt\n\n0 1\nC 0 0 0\nC 1.39 0 0\n"
               "H 2 1.09 1 120\nH 1 1.09 1 120\n")
    assert parse_input(benzene)["blocks"]["molecule"]["formula"] == "C2H2"
    # 元素大小写归一（cl → Cl）
    cl2 = "#p hf/sto-3g\n\nt\n\n0 1\ncl\nCL 1 2.0\n"
    assert parse_input(cl2)["blocks"]["molecule"]["formula"] == "Cl2"


def test_geometric_allcheck_missing_sections_allowed():
    r = parse_input("#p hf/sto-3g geom=allcheck\n\n")
    assert r["blocks"]["title"] is None
    assert r["parse_errors"] == []


def test_bad_files_tolerated_no_exception():
    # 空文件 / 乱文本：不抛异常，route/title 容错 + parse_errors 标注
    for text in ("", "just one line\n", "%mem=1GB\n", "! 只有一句注释\n"):
        r = parse_input(text)
        assert set(r["blocks"]) == {"link0", "route", "title", "charge_mult",
                                    "molecule", "additional_sections"}
        assert r["blocks"]["title"] is None or isinstance(r["blocks"]["title"], str)
    r = parse_input("")
    sections = {e["section"] for e in r["parse_errors"]}
    assert {"route", "title", "charge_mult"} <= sections


def test_bad_charge_mult_recorded():
    r = parse_input("#p hf/sto-3g\n\nt\n\nzero one\nO\n")
    assert r["blocks"]["charge_mult"] == "zero one"
    assert any(e["section"] == "charge_mult" for e in r["parse_errors"])


def test_additional_section_with_gen_and_terminator():
    text = ("%mem=512MB\n\n#p hf/sto-3g gen\n\ntest\n\n0 1\nO 0 0 0\n"
            "H 0 0 0.96\nH 0 0.96 -0.24\n\nH 0\nS 3 1.0\n0.5 1.0\n****\n\n"
            "eps=4.0\n")
    r = parse_input(text)
    secs = r["blocks"]["additional_sections"]
    assert len(secs) == 2
    assert secs[0]["lines"][0] == "H 0"
    assert secs[0]["terminator_blank"] is True
    # 末节直达 EOF，无终止空行
    assert secs[1]["lines"] == ["eps=4.0"]
    assert secs[1]["terminator_blank"] is False
    assert r["blocks"]["molecule"]["variables_present"] is False


@pytest.mark.skipif(not GOLDEN_DIR.is_dir(), reason="金标准目录不存在")
def test_golden_suite_no_crash_and_contract_shape():
    files = sorted(GOLDEN_DIR.glob("*.com"))
    assert len(files) > 1000
    for f in files:
        r = parse_input(f.read_text(encoding="utf-8", errors="replace"))
        assert set(r["blocks"]) == {"link0", "route", "title", "charge_mult",
                                    "molecule", "additional_sections"}
        for e in r["parse_errors"]:
            assert set(e) == {"section", "line", "message"}


@pytest.mark.skipif(not GOLDEN_DIR.is_dir(), reason="金标准目录不存在")
def test_golden_curated_samples():
    r0 = parse_input((GOLDEN_DIR / "test0000.com").read_text(encoding="utf-8"))
    b0 = r0["blocks"]
    assert b0["charge_mult"] == "0 1"
    assert b0["title"] == "Gaussian Test Job 00\nWater with archiving"
    assert b0["molecule"] == {"atom_count": 3, "formula": "H2O1",
                              "variables_present": False, "constants_present": False}
    assert b0["link0"]["missing"] == ["NProcShared", "Mem"]
    assert b0["route"].startswith("#")

    r1 = parse_input((GOLDEN_DIR / "test0001.com").read_text(encoding="utf-8"))
    b1 = r1["blocks"]
    assert b1["molecule"]["formula"] == "O2"
    assert b1["molecule"]["variables_present"] is True
    assert b1["charge_mult"] == "0 1"
