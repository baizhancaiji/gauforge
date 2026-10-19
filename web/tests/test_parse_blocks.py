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


# ---------------- G2：route 重复关键字判定表（B3） ----------------

def test_g2_route_duplicate_matrix():
    """§2.6 判定表逐行：容器头白名单、裸形+选项形豁免、IOp 并写豁免。"""
    from web.src.parse.keywords import check_route_duplicates

    def kinds(route):
        return [w["keyword"] for w in check_route_duplicates(route)]

    # 同头部均裸 → 警告
    assert kinds("#p mp2 mp2/6-31g(d)") == ["mp2"]
    # 容器头裸形 + 选项形 → 豁免（官方追加取值）
    assert kinds("#p freq freq=readfcht") == []
    assert kinds("#p opt opt=(calcfc,ts)") == []
    # 两个非空选项集 → 警告
    assert kinds("#p freq=readfc freq=readfcht") == ["freq"]
    assert kinds("#p opt=(calcfc,ts) opt=(qst3)") == ["opt"]
    assert kinds("#p scf=tight scf=xqc") == ["scf"]
    # IOp 多条目取值并列 → 豁免
    assert kinds("#p b3lyp/6-31g(d) iop(5/17=1) iop(6/50=1)") == []
    # 正常 route → 无
    assert kinds("#p opt freq") == []
    # 白名单外头部重复 → 警告（mark 等）
    assert kinds("#p mark mark b3lyp/6-31g(d)") == ["mark"]
    # 跨行 route 同样检测（token 管道跨行）
    assert kinds("#p mp2\nmp2") == ["mp2"]


def test_g2_route_duplicate_warning_shape():
    from web.src.parse.keywords import check_route_duplicates
    ws = check_route_duplicates("#p scf=tight scf=xqc", line_offset=3)
    assert len(ws) == 1
    w = ws[0]
    assert w["kind"] == "route_duplicate"
    assert w["line"] == 3 + 1
    assert "scf" in w["message"] and w["keyword"] == "scf"
    assert set(w) >= {"line", "keyword", "kind", "message"}


def test_g2_container_bare_plus_multiple_valued_forms_exempt():
    """审查整改 R7 登记口径：容器头「1 裸形 + 多个选项形」并出整体豁免
    （官方追加取值语义的推广；0 裸形 + 2 选项形仍警告——判定表原行）。"""
    from web.src.parse.keywords import check_route_duplicates
    assert check_route_duplicates(
        "#p freq freq=readfcht freq=readanharmonic") == []
    assert check_route_duplicates("#p opt opt=maxcycle=50 opt=restart") == []
    ws = check_route_duplicates("#p freq=readfcht freq=readanharmonic")
    assert [w["kind"] for w in ws] == ["route_duplicate"]


# ---------------- G8：route 子选项归属判定（B5） ----------------

def test_g8_option_unknown_matrix():
    """§2.9 用例清单：在典零警告/嵌套取值/带值选项/未知选项/跨关键字误置/
    部分命中仅报未命中/近邻建议/值形白名单零警告。"""
    from web.src.parse.keywords import check_route_options

    # 在典零警告（opt=calcfc/opt=ts 均在典；B5 前整词近邻会误报
    # keyword_spell suggestion=opt=calcfc——选项化后消除）
    assert check_route_options("#p opt=(calcfc,ts)") == []
    # 嵌套一层取值：solvent=water 剥值查 scrf=solvent（在典）、read 查 scrf=read
    assert check_route_options("#p scrf=(solvent=water,read)") == []
    # 带值选项剥值查典：td=nstates/td=root 在典
    assert check_route_options("#p td=(nstates=6,root=2)") == []
    # 未知选项 → route_option_unknown（keyword=出错选项原文）
    ws = check_route_options("#p geom=(allcheck,xyzzy)")
    assert [(w["kind"], w["keyword"]) for w in ws] \
        == [("route_option_unknown", "xyzzy")]
    # 跨关键字误置：readfcht 是 Freq 选项（freq=readfcht 在典、opt=readfcht 不在）
    ws = check_route_options("#p opt=(readfcht)")
    assert [(w["kind"], w["keyword"]) for w in ws] \
        == [("route_option_unknown", "readfcht")]
    # 同族合法值零警告（opt=readfc 在典）
    assert check_route_options("#p opt=(readfc)") == []
    # 部分命中只报未命中选项（不因 calcfc 命中整体放行）
    ws = check_route_options("#p opt=(calcfc,xyzzy)")
    assert [w["keyword"] for w in ws] == ["xyzzy"]
    # 选项级拼写建议：近邻于该键选项集（cutoff 同 keyword_spell）
    ws = check_route_options("#p opt=(calfcf)")
    assert len(ws) == 1 and ws[0].get("suggestion") == "calcfc"
    # 值形白名单：括号内容为取值/模型化学/命令串，不做选项查典
    assert check_route_options("#p IOp(6/50=1)") == []
    assert check_route_options("#p ONIOM(B3LYP/6-31G(d):AM1:UFF)") == []
    assert check_route_options('#p External="RunTink Amber"') == []
    # message 同时给出选项与左侧关键字（大写键名，官方书写惯例）
    msg = check_route_options("#p geom=(allcheck,xyzzy)")[0]["message"]
    assert "GEOM" in msg and "xyzzy" in msg
    assert set(check_route_options("#p opt=(xyzzy)")[0]) \
        >= {"line", "keyword", "kind", "message"}


def test_g8_unique_prefix_and_non_option_heads():
    """官方最短唯一缩写判活与豁免面（B5 口径修正：input 页 Syntax Rules
    明文「All keywords and options may be shortened to their shortest unique
    abbreviation」——计划 §1.1 摘录漏 "and options"，原「缩写选项按未命中」
    口径在官方语料实测 45.7% 文件误报，按官方原文修正）。"""
    from web.src.parse.keywords import check_route_options

    # 唯一前缀判活：curr→current（density）、numer→numerical（freq）、
    # lowsym→lowsymm（guess）
    assert check_route_options("#p density=curr") == []
    assert check_route_options("#p freq=numer") == []
    assert check_route_options("#p guess=(cards,lowsym)") == []
    # 歧义前缀：conv 同前缀于 conver/conventional——官方明文非法
    # （「may be abbreviated to Conven, but not to Conv」），报未知
    ws = check_route_options("#p scf=conv")
    assert [(w["kind"], w["keyword"]) for w in ws] \
        == [("route_option_unknown", "conv")]
    # 非选项型键（典无 键=* 组合词条目）：基组/方法括号形不做选项查典
    assert check_route_options("#p b3lyp/6-31g(d,p) mp4(sdtq) sto-3g(*)") == []
    # ccsd 有组合词条目（readamplitudes 等）但 (t) 是方法微扰阶标记：
    # 单字母非官方选项名形态（面⑤提取规则选项基名 ≥2 字符）
    assert check_route_options("#p ccsd(t) ccsd(t,q)") == []
    # 整词在典的基组括号形整 token 豁免
    assert check_route_options("#p 6-31g(3df,3pd)") == []


def test_g8_line_offset_absolute():
    from web.src.parse.keywords import check_route_options
    ws = check_route_options("#p opt freq\ngeom=(allcheck,xyzzy)",
                             line_offset=4)
    assert ws[0]["line"] == 6  # geom= 位于 route 第 2 行(1 起)+ 偏移 4


def test_spell_option_tokens_no_spurious_neighbor():
    """B5 拼写选项化：含选项 token 不再做整词近邻（键名命中即交选项判定）。"""
    from web.src.parse import keywords as kw
    assert kw.check_route_spelling("#p opt=(calcfc,ts)") == []
    assert kw.check_route_spelling("#p freq=readfcht") == []


# ---------------- G7：字典扩面与缩写精确匹配口径（B5） ----------------

def test_g7_route_alt_forms_in_dictionary():
    """面⑥：route 页 Alternate Forms（#N/#P/#T）替代表单 n/t 入典
    （p 已由面②单字母白名单覆盖）。"""
    from web.src.parse import keywords as kw
    assert {"n", "p", "t"} <= kw.load_keywords(refresh=True)


def test_g7_abbreviation_exact_match_scope():
    """决策点 5：词典精确匹配——组合词 scf=conven/scf=conv 与裸词 fre/geo
    均不在典（面⑤只收 scf=conver/conventional）；= 形 token 按 C3 键名
    精确命中放行（决策点 5 原文「保持整词与键名精确命中」，scf 键在典，
    enforce 不拒——§2.8「scf=conven enforce 拒绝」与 §2.3 键名命中规则
    冲突，以决策点 5 原文为准，实现口径随批登记），裸词缩写查典失败。"""
    from web.src.parse import keywords as kw
    words = kw.load_keywords(refresh=True)
    for tok in ("scf=conven", "scf=conv", "fre", "geo"):
        assert tok not in words, tok
    assert kw.token_in_dict("scf=conven", words)
    assert not kw.token_in_dict("fre", words)
    assert not kw.token_in_dict("geo", words)


def test_g7_bare_abbreviations_spell_near_neighbor():
    """warn 通道：裸词缩写按拼写近邻提示（fre→freq、geo→geom），
    不做前缀近似放行（决策点 5）。"""
    from web.src.parse import keywords as kw
    sug = {w["keyword"]: w.get("suggestion")
           for w in kw.check_route_spelling("#p fre geo")}
    assert sug == {"fre": "freq", "geo": "geom"}


# ---------------- G3：Link 0 错位检测（B3） ----------------

def test_g3_link0_into_route_text_blocked():
    """情形 1：route 后无空行直接跟 % 行 → 被吞入 route 文本，记
    parse_errors（G16 必然误读）。"""
    r = parse_input("%mem=1GB\n\n#p hf/sto-3g\n%chk=/tmp/x.chk\n\nt\n\n"
                    "0 1\nO 0 0 0\n\n")
    e = next(e for e in r["parse_errors"] if e["section"] == "route"
             and "Link 0" in e["message"])
    assert "route 节之前" in e["message"]
    assert "%chk=/tmp/x.chk" in r["blocks"]["route"]  # 吞并事实不变


def test_g3_link0_as_title_first_line_blocked():
    """情形 2：route 后有空行再跟 % 行 → 成 title 首行，记 parse_errors
    （title 形态合法但几乎必为用户错误）。"""
    r = parse_input("%mem=1GB\n\n#p hf/sto-3g\n\n%chk=/tmp/x.chk\n\n"
                    "0 1\nO 0 0 0\n\n")
    e = next(e for e in r["parse_errors"] if e["section"] == "title")
    assert "Link 0" in e["message"]
    assert r["blocks"]["title"] == "%chk=/tmp/x.chk"


def test_g3_link0_at_title_position_without_route():
    """route 缺失时 % 行落在 title 节（标题行之后）同样按情形 2 记
    parse_errors（文件开头的 % 行归 Link0 收集，不在本检测面）。"""
    r = parse_input("水分子标题\n%chk=/tmp/x.chk\n\n0 1\nO 0 0 0\n\n")
    assert any(e["section"] == "title" and "Link 0" in e["message"]
               for e in r["parse_errors"])


def test_g3_link0_in_molecule_spec_not_scanned():
    """检测范围限定 route 起点至 title 结束：分子说明后附加节中以 % 开头
    的行不误报。"""
    text = ("#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\n\n%foo=bar data\n\n")
    r = parse_input(text)
    assert not any("Link 0" in e["message"] for e in r["parse_errors"])


# ---------------- G5：值域拉齐与多组电荷对（B4） ----------------

def test_g5_negative_charge_and_zero_mult():
    """负电荷合法（有符号整数）；首组多重度须 ≥1（0 拒）。"""
    ok = parse_input("#p hf/sto-3g\n\nt\n\n-1 2\nO 0 0 0\nH 0 0 0.96\n\n")
    assert ok["blocks"]["charge_mult"] == "-1 2"
    assert ok["parse_errors"] == []
    bad = parse_input("#p hf/sto-3g\n\nt\n\n0 0\nO 0 0 0\n\n")
    assert any(e["section"] == "charge_mult" for e in bad["parse_errors"])


def test_g5_multiple_charge_pairs_kept_and_warned_without_evidence():
    """多组电荷-多重度对同解析：charge_mult 保留全部组；无 Counterpoise/
    ONIOM/Fragment 佐证 → molecule_multiple_charge_pairs 信息警告。"""
    r = parse_input("#p hf/sto-3g\n\nt\n\n1 2 1 2 0 1\nO 0 0 0\n\n")
    assert r["blocks"]["charge_mult"] == "1 2 1 2 0 1"
    kinds = [w["kind"] for w in r["warnings"]]
    assert "molecule_multiple_charge_pairs" in kinds
    # 有佐证（Counterpoise）零警告
    cp = parse_input("#p hf/sto-3g counterpoise=2\n\nt\n\n1 2 1 2 0 1\n"
                     "O(Fragment=1) 0 0 0\nO(Fragment=2) 0 0 1.1\n\n")
    assert cp["blocks"]["charge_mult"] == "1 2 1 2 0 1"
    assert not any(w["kind"] == "molecule_multiple_charge_pairs"
                   for w in cp["warnings"])


def test_g5_negative_mult_fragment_gate():
    """负多重度组仅 Guess=Fragment 有官方语义：无则警告、有则零警告。"""
    no_gate = parse_input("#p hf/sto-3g\n\nt\n\n0 1 0 -2\nO 0 0 0\n\n")
    assert any(w["kind"] == "molecule_multiple_charge_pairs"
               and "Guess=Fragment" in w["message"] for w in no_gate["warnings"])
    gated = parse_input("#p hf/sto-3g guess=fragment\n\nt\n\n0 1 0 -2\n"
                        "O 0 0 0\n\n")
    assert not any(w["kind"] == "molecule_multiple_charge_pairs"
                   for w in gated["warnings"])


def test_g5_charge_mult_free_format_separators():
    """电荷行自由格式分隔（逗号/斜杠任意组合，官方 Counterpoise 示例）。"""
    r = parse_input("#p hf/sto-3g counterpoise=2\n\nt\n\n1,2 1,2 0,1\n"
                    "O 0 0 0\n\n")
    assert r["blocks"]["charge_mult"] == "1 2 1 2 0 1"
    r2 = parse_input("#p hf/sto-3g\n\nt\n\n0/1\nO 0 0 0\n\n")
    assert r2["blocks"]["charge_mult"] == "0 1"


def test_g5_link0_value_domain_and_positive_mem():
    """%mem 值域收紧（W|B 删除）且须 >0：%mem=2W / %mem=0 → 警告
    （kind=link0_value_invalid），KB..TW 与无单位合法。"""
    for line in ("%mem=2W", "%mem=0", "%mem=2B", "%mem=-1GB"):
        r = parse_input(f"{line}\n\n#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\n\n")
        assert any(w["kind"] == "link0_value_invalid" for w in r["warnings"]), line
    for line in ("%mem=2GB", "%mem=800MB", "%mem=500KB", "%mem=1TW",
                 "%mem=100", "%mem=2.5GW"):
        r = parse_input(f"{line}\n\n#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\n\n")
        assert not any(w["kind"] == "link0_value_invalid"
                       for w in r["warnings"]), line


def test_g5_link0_line_length_cap():
    """Link 0 单行 ≤500 字符：超限记 link0_line_too_long 警告（导入/提交
    通道），不阻断。"""
    long_line = "%mem=" + "1" * 500 + "GB"
    r = parse_input(f"{long_line}\n\n#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\n\n")
    kinds = [w["kind"] for w in r["warnings"]]
    assert "link0_line_too_long" in kinds


def test_g5_link0_directive_grammar_and_duplicates():
    """官方无等号指令合法零警告；未知指令/同名重复记警告（不阻断）。"""
    good = parse_input("%save\n%kjob l502 2\n%subst l913 /tmp\n\n"
                       "#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\n\n")
    assert not any(w["kind"].startswith("link0_directive")
                   for w in good["warnings"])
    unknown = parse_input("%foobar=1\n\n#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\n\n")
    kinds = [w["kind"] for w in unknown["warnings"]]
    assert "link0_directive_unknown" in kinds
    dup = parse_input("%mem=1GB\n%mem=2GB\n\n#p hf/sto-3g\n\nt\n\n0 1\n"
                      "O 0 0 0\n\n")
    kinds2 = [w["kind"] for w in dup["warnings"]]
    assert "link0_directive_duplicate" in kinds2
    # 含多个 = 的取值形不按普通 key=value 二次切分
    multi = parse_input("%gpucpu=0-3=0-1,16-17\n\n#p hf/sto-3g\n\nt\n\n"
                        "0 1\nO 0 0 0\n\n")
    assert not any(w["kind"] == "link0_directive_unknown"
                   for w in multi["warnings"])


def test_g5_link0_warning_lines_are_file_absolute():
    """审查整改 R1：Link0 警告 line 为全文件绝对行号（G0 口径）——前导
    空行场景不回落块内序号，重复指令取首次出现行。"""
    r = parse_input("\n\n%mem=2W\n\n#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\n\n")
    w = next(w for w in r["warnings"] if w["kind"] == "link0_value_invalid")
    assert w["line"] == 3  # %mem=2W 在全文件第 3 行（块内序号应为 1）
    dup = parse_input("\n%mem=2GB\n%mem=4GB\n\n#p hf/sto-3g\n\nt\n\n"
                      "0 1\nO 0 0 0\n\n")
    d = next(w for w in dup["warnings"]
             if w["kind"] == "link0_directive_duplicate")
    assert d["line"] == 2  # 首个 %mem 的全文件行号（原恒为 1）


def test_g5_cpu_slash_n_suffix():
    """%cpu 区间 /n 步长后缀（官方 0-5/2 形）全通道放行。"""
    r = parse_input("%cpu=0-5/2\n\n#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\n\n")
    assert not any(w["kind"] == "link0_value_invalid" for w in r["warnings"])
    from web.src.parse.link0_rules import cpu_list_count
    assert cpu_list_count("0-5/2") == 3
    assert cpu_list_count("0-5") == 6
    assert cpu_list_count("0,2,4") == 3


def test_g5_title_forbidden_char_warning():
    """title 禁用字符：parse_input 记警告（编辑保存保持阻断）。"""
    r = parse_input("#p hf/sto-3g\n\nt@itle\n\n0 1\nO 0 0 0\n\n")
    assert any(w["kind"] == "title_forbidden_char" for w in r["warnings"])


# ---------------- G6：原子行文法（B4） ----------------

def test_g6_ghost_atom_excluded_from_formula():
    """鬼原子 O-Bq：计入 atom_count（占一行）、不计入分子式。"""
    r = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nO 0 0 0\nO-Bq 0 0 3.0\n\n")
    m = r["blocks"]["molecule"]
    assert m["atom_count"] == 2
    assert m["formula"] == "O1"
    assert not any(w["kind"] == "atom_label_unknown" for w in r["warnings"])


def test_g6_dummy_atom_x():
    """哑原子 X / X<数字>：计数入原子行数、不计入分子式、不告警。"""
    r = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nX 0 0 0\nO 1 1.0\n"
                    "X3 1 1.2 2 90.0\n\n")
    m = r["blocks"]["molecule"]
    assert m["atom_count"] == 3
    assert m["formula"] == "O1"
    assert not any(w["kind"] == "atom_label_unknown" for w in r["warnings"])


def test_g6_unknown_label_warned_known_prefix_not():
    """找不到元素符号前缀（Zz）→ atom_label_unknown 警告；字母标签
    Foo（F+oo）不告警。"""
    bad = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nZz 0 0 0\nO 0 0 1.0\n\n")
    assert any(w["kind"] == "atom_label_unknown" and w["keyword"] == "Zz"
               for w in bad["warnings"])
    assert bad["blocks"]["molecule"]["formula"] == "O1"  # Zz 不入式
    good = parse_input("#p hf/sto-3g\n\nt\n\n0 1\nFoo 0 0 0\nO 0 0 1.0\n\n")
    assert good["blocks"]["molecule"]["formula"] == "F1O1"
    assert not any(w["kind"] == "atom_label_unknown" for w in good["warnings"])


def test_g6_mm_and_free_format_atom_lines():
    """MM/ONIOM 形（C-CT--0.06）、参数表（C(Iso=13,Fragment=2)）与自由
    格式分隔（C,0,0,0 / C/0/0/0）均解析为首元素。"""
    for line in ("C-CT--0.06    0.0 0.0 0.0", "C(Iso=13,Fragment=2) 0 0 0",
                 "C,0,0,0", "C/0/0/0", "Cl1 0 0 0"):
        r = parse_input(f"#p hf/sto-3g\n\nt\n\n0 1\n{line}\n\n")
        f = r["blocks"]["molecule"]["formula"]
        assert f.startswith("C") or f.startswith("Cl"), (line, f)
        assert not any(w["kind"] == "atom_label_unknown"
                       for w in r["warnings"]), line
