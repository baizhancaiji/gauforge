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


def test_link0_nproc_synonyms_not_missing():
    """%nproc 系变体与 %CPU proc-list 均视为核资源已声明，不再误报缺失。

    %NProc 为 G16 早期同义形式（手册 %CPU 条目 replaces the earlier
    %NProcShared and %NProc）；%nprocshare 截断形式无文档背书但实测可用，
    检测取 %nproc 前缀超集；%CPU=proc-list 为现行推荐（列表/区间/混合，
    gaussian.com/run），语义是绑定具体逻辑处理器，同样算已声明。"""
    for line in ("%NProcShared=4", "%nprocshared=4", "%nproc=4", "%NProc=4",
                 "%nprocshare=4", "%CPU=0-3", "%cpu=0,1,2,3", "%CPU=0-2,5"):
        r = parse_input(f"{line}\n%mem=2GB\n\n#p hf/sto-3g\n\nt\n\n0 1\nO\n"
                        "H 1 0.96\nH 1 0.96 2 1.0\n")
        assert r["blocks"]["link0"]["missing"] == [], line


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


def test_atomic_number_atom_specs():
    """分子说明以原子序数书写（Gaussian 允许）：计入化学式，不空缺。

    回归：cat_BC1_amino_TZVP.gjf 全序数坐标（7=N/6=C/1=H）解析后
    atom_count 正常而 formula 空串，预览卡 FORMULA 列错位。"""
    text = "%chk=/tmp/x.chk\n\n#p opt freq\n\nt\n\n1 1\n" \
        "7 0 0 0\n6 1.4 0 0\n1 2.0 1.0 0\n"
    m = parse_input(text)["blocks"]["molecule"]
    assert m["atom_count"] == 3
    assert m["formula"] == "C1H1N1"
    # Z-matrix 序数形式同样计入
    zm = "#p hf/sto-3g\n\nt\n\n0 1\n8\n1 1 0.96\n1 1 0.96 2 104.5\n"
    assert parse_input(zm)["blocks"]["molecule"]["formula"] == "H2O1"
    # 超界序数容错：不识别不抛异常，原子行数照常统计
    bad = parse_input("#p hf/sto-3g\n\nt\n\n0 1\n999 0 0 0\n")
    assert bad["blocks"]["molecule"]["atom_count"] == 1
    assert bad["blocks"]["molecule"]["formula"] == ""


def test_parse_input_warnings_channel_default_empty():
    """G0：parse_input 返回值含 warnings 通道；规范输入（各节空行终止）
    默认空列表（非阻断）。WATER 样例 Variables/Constants 区以终止空行收尾。"""
    assert parse_input(WATER + "\n")["warnings"] == []
    r = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nO\nH 1 0.96\n"
                    "H 1 0.96 2 1.0\n\n")
    assert r["warnings"] == []
    assert set(r) == {"blocks", "parse_errors", "multistep", "warnings"}


def test_geometric_allcheck_missing_sections_allowed():
    r = parse_input("#p hf/sto-3g geom=allcheck\n\n")
    assert r["blocks"]["title"] is None
    assert r["parse_errors"] == []


def test_geometric_checkpoint_requires_title_and_charge():
    """C1：Geom=Checkpoint 仅豁免原子坐标，title 与电荷/多重度行仍必须存在
    （官方 geom 页：Only the charge and multiplicity are read from the input
    stream；title 按 Section Ordering 表除 AllCheck 外全部要求）。"""
    base = "#p b3lyp/6-31g(d) geom=checkpoint\n\n"
    r = parse_input(base)  # 缺 title、缺电荷/多重度 → 双报
    sections = {e["section"] for e in r["parse_errors"]}
    assert {"title", "charge_mult"} <= sections
    # title 与电荷行齐备、仅省原子坐标 → 合法
    r2 = parse_input(base + "水分子\n\n0 1\n")
    assert r2["parse_errors"] == []
    assert r2["blocks"]["title"] == "水分子"
    assert r2["blocks"]["charge_mult"] == "0 1"


def test_geometric_check_synonym_same_tier():
    """C1：Geom=Check 为 Checkpoint 同义词，豁免档位一致。"""
    r = parse_input("#p hf/sto-3g geom=check\n\n")
    sections = {e["section"] for e in r["parse_errors"]}
    assert {"title", "charge_mult"} <= sections


def test_geometric_bracket_and_space_forms_match_bare():
    """C2：括号/空格形态与裸形态判定一致（官方选项四种合法形态与
    「= 两侧允许任意空格」规则）。"""
    # AllCheck 括号形：title/电荷整体省略，不报错
    r = parse_input("#p b3lyp/6-31g(d) geom=(allcheck,modredundant)\n\n")
    assert r["parse_errors"] == []
    # 逗号后空格
    r2 = parse_input("#p hf/sto-3g geom=(allcheck, modredundant)\n\n")
    assert r2["parse_errors"] == []
    # 等号两侧空格
    r3 = parse_input("#p hf/sto-3g geom = allcheck\n\n")
    assert r3["parse_errors"] == []
    # 无等号括号形
    r4 = parse_input("#p hf/sto-3g geom (allcheck)\n\n")
    assert r4["parse_errors"] == []
    # checkpoint 括号形：仅坐标可省，title/电荷必须存在
    r5 = parse_input("#p hf/sto-3g geom=(checkpoint, modredundant)\n\n")
    sections = {e["section"] for e in r5["parse_errors"]}
    assert {"title", "charge_mult"} <= sections


def test_title_missing_message_names_allcheck_only():
    """C1 文案精确化：title 缺失提示仅 AllCheck 豁免（Checkpoint 不再列）。"""
    r = parse_input("#p hf/sto-3g\n\n")
    msg = next(e["message"] for e in r["parse_errors"]
               if e["section"] == "title")
    assert "AllCheck" in msg
    assert "Checkpoint" not in msg


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
    # 末节直达 EOF，无终止空行；Gen 命中的官方行全为 terminator=yes
    # → G4 记 parse_errors（附加输入节未以空行终止）
    assert secs[1]["lines"] == ["eps=4.0"]
    assert secs[1]["terminator_blank"] is False
    assert any(e["section"] == "additional" and "未以空行终止" in e["message"]
               for e in r["parse_errors"])
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


# ---------------- G4：Section Ordering 官方口径（B2） ----------------

def test_g4_official_table_drives_extra_section_detection():
    """Pseudo=Cards 等此前未收录的触发词改由官方表驱动识别（官方口径，
    不再依赖隐式变量区启发式的兜底路径）。"""
    text = ("#p hf/sto-3g pseudo=cards\n\nt\n\n0 1\nO 0 0 0\nH 0 0 0.96\n"
            "H 0 0.96 -0.24\n\n****\nO 0\nS 6 1.0\n1.0 0.0 0.0\n\n")
    r = parse_input(text)
    secs = r["blocks"]["additional_sections"]
    assert len(secs) == 1
    assert secs[0]["lines"][0] == "****"
    assert r["parse_errors"] == []


def test_g4_terminator_no_exception_not_reported():
    """Pop=NBORead 官方例外（terminator=no）：末节 EOF 收尾不报阻断。"""
    text = ("#p b3lyp/6-31g(d) pop=nboread\n\nt\n\n0 1\nO 0 0 0\n"
            "H 0 0 0.96\n\n$NBO NRTKEYWORD=nrtstep end\n")
    r = parse_input(text)
    assert r["blocks"]["additional_sections"][-1]["terminator_blank"] is False
    assert r["parse_errors"] == []


def test_g4_mixed_yes_no_conservative_not_reported():
    """Gen + Pop=NBORead 混合命中（yes + no）→ 保守不报（§7 风险缓解）。"""
    text = ("#p b3lyp/6-31g(d) gen pop=nboread\n\nt\n\n0 1\nO 0 0 0\n"
            "H 0 0 0.96\n\nH 0\nS 3 1.0\n****\n\neps=4.0\n")
    r = parse_input(text)
    assert not any(e["section"] == "additional" for e in r["parse_errors"])


def test_g4_compat_prop_wrf_still_triggers_wants_extra():
    """兼容触发词 prop=wrf（官方表未列）保留一版：附加节识别不回退；
    兼容项不参与官方表 terminator 判定（命中集合为空 → 不报）。"""
    text = ("#p b3lyp/6-31g(d) prop=wrf\n\nt\n\n0 1\nO 0 0 0\n"
            "H 0 0 0.96\n\nsome data line\n")
    r = parse_input(text)
    assert len(r["blocks"]["additional_sections"]) == 1
    assert r["parse_errors"] == []


def test_g4_implicit_variables_suppressed_by_trigger():
    """触发词在场时「名 数值」形态 region 归附加节（官方口径），不再
    走隐式变量区启发式。"""
    with_gen = ("#p hf/sto-3g gen\n\nt\n\n0 1\nO 0 0 0\nH 0 0 0.96\n"
                "\nH 0\nS 3 1.0\n\nR1 0.96\n\n")
    r = parse_input(with_gen)
    assert r["blocks"]["molecule"]["variables_present"] is False
    assert len(r["blocks"]["additional_sections"]) == 2
    # 无触发词时同形态 region 仍按启发式识别为隐式变量区（既有行为）
    plain = ("#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\nH 0 0 0.96\n\nR1 0.96\n\n")
    r2 = parse_input(plain)
    assert r2["blocks"]["molecule"]["variables_present"] is True
    assert r2["blocks"]["additional_sections"] == []


# ---------------- G9：核心节必需空行缺失检测（B2） ----------------

def test_g9_route_eof_unterminated_with_title_hint():
    """route 未以空行终止（吞并到 EOF）：报 route 未终止，title 落空的
    报错附根因提示（归因不再误导）。"""
    r = parse_input("#p hf/sto-3g\n未命名\n")
    assert any(e["section"] == "route" and "未以空行终止" in e["message"]
               for e in r["parse_errors"])
    t = next(e for e in r["parse_errors"] if e["section"] == "title")
    assert "route" in t["message"]  # 根因：未终止时内容并入 route


def test_g9_title_eof_unterminated():
    """title 吞并电荷行至 EOF：报 title 未以空行终止。"""
    r = parse_input("#p hf/sto-3g\n\ntitle\n0 1\nO 0 0 0\n")
    assert any(e["section"] == "title" and "未以空行终止" in e["message"]
               for e in r["parse_errors"])
    assert r["blocks"]["title"] == "title\n0 1\nO 0 0 0"


def test_g9_title_eof_allcheck_exempt_route_still_required():
    """Geom=AllCheck 豁免集内 title 未终止不报；但 route 终止空行不豁免。"""
    r = parse_input("#p hf/sto-3g geom=allcheck\n\ntitle\n0 1\nO 0 0 0\n")
    assert not any("未以空行终止" in e["message"] for e in r["parse_errors"])
    r2 = parse_input("#p hf/sto-3g geom=allcheck\n")
    assert any(e["section"] == "route" and "未以空行终止" in e["message"]
               for e in r2["parse_errors"])


def test_g9_charge_mult_parse_failure_hint():
    """电荷行解析失败文案附根因（上一节未以空行收尾时本行可能是误并内容）。"""
    r = parse_input("#p hf/sto-3g\n\nt\n\nzero one\nO\n")
    e = next(e for e in r["parse_errors"] if e["section"] == "charge_mult")
    assert "空行" in e["message"]


def test_g9_empty_molecule_rejected_geom_tiers_exempt():
    """电荷行后无原子行 → 缺分子说明节；Geom 检查点豁免档（坐标可省）
    不报。"""
    r = parse_input("#p hf/sto-3g\n\nt\n\n0 1\n")
    assert any(e["section"] == "molecule" and "分子说明" in e["message"]
               for e in r["parse_errors"])
    assert parse_input("#p hf/sto-3g geom=allcheck\n\n")["parse_errors"] == []
    assert parse_input("#p hf/sto-3g geom=checkpoint\n\nt\n\n0 1\n")[
        "parse_errors"] == []


def test_g9_molecule_eof_warning_and_geom_exemption():
    """分子说明 EOF 未终止 → 非阻断 warning；有终止空行或 Geom 坐标豁免
    档不产生。"""
    r = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\nH 0 0 0.96\n")
    assert [w["kind"] for w in r["warnings"]] == ["molecule_unterminated"]
    assert r["parse_errors"] == []
    fine = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\nH 0 0 0.96\n\n")
    assert fine["warnings"] == []
    exempt = parse_input("#p hf/sto-3g geom=checkpoint\n\nt\n\n0 1\nO 0 0 0\n")
    assert exempt["warnings"] == []


def test_g9_variables_eof_warning():
    """Variables/Constants/隐式变量区以 EOF 告终 → 非阻断 warning。"""
    vs = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nO\nH 1 0.96\n"
                     "H 1 0.96 2 1.0\n\nVariables:\nR1 0.96\n")
    assert [w["kind"] for w in vs["warnings"]] == ["variables_unterminated"]
    cs = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nO\nH 1 0.96\n\nConstants:\n"
                     "R1 0.96\n")
    assert [w["kind"] for w in cs["warnings"]] == ["variables_unterminated"]
    impl = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nO\nH 1 0.96\n\nR1 0.96\n")
    assert [w["kind"] for w in impl["warnings"]] == ["variables_unterminated"]


def test_g9_link1_without_preceding_blank_annotated():
    """--Link1-- 前缺空行：既有 link1 错误附注官方要求（预览可见的提示性
    补强）。"""
    text = "#p hf/sto-3g\n--Link1--\n\n#p hf/sto-3g\n\nt\n\n0 1\nO\n"
    r = parse_input(text)
    e = r["parse_errors"][0]
    assert e["section"] == "link1"
    assert "缺少空行" in e["message"]
