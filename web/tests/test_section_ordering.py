"""Section Ordering 官方表固化测试（输入勘误计划 G4，B2 表驱动）。

期望清单以计划 §1.2 全表（= 官方 input 页 Section Ordering，G16 Rev. C.01
2018-02-19 快照，59 行）为 fixture 逐行断言 kind/terminator；any_trigger
只消费 additional 行、普通 route 恒 False、多触发词混合 yes/no 保守不报。
"""
from __future__ import annotations

from web.src.parse import section_ordering as so

# (section_id, kind, terminator) × 59 —— 与官方表逐行对应
EXPECTED = (
    ("link0", "core", "no"),
    ("route", "core", "yes"),
    ("extra_overlays", "additional", "yes"),
    ("title", "core", "yes"),
    ("molecule", "core", "yes"),
    ("geom_connectivity", "additional", "yes"),
    ("geom_readopt", "additional", "yes"),
    ("opt_modredundant", "additional", "yes"),
    ("qst2_qst3_second_structure", "additional", "yes"),
    ("qst2_qst3_second_connectivity", "additional", "yes"),
    ("qst2_qst3_second_readopt", "additional", "yes"),
    ("qst2_qst3_second_modifications", "additional", "yes"),
    ("qst3_third_structure", "additional", "yes"),
    ("qst3_third_connectivity", "additional", "yes"),
    ("qst3_third_readopt", "additional", "yes"),
    ("qst3_third_modifications", "additional", "yes"),
    ("pdb_secondary_structure", "automatic", "yes"),
    ("readisotopes", "additional", "yes"),
    ("external_readinput", "additional", "yes"),
    ("mm_parameters", "additional", "yes"),
    ("frequency_of_interest", "additional", "yes"),
    ("background_charge", "additional", "yes"),
    ("admp_bomd", "additional", "yes"),
    ("pcm_input", "additional", "yes"),
    ("irc_report_read", "additional", "yes"),
    ("geom_readharmonic", "additional", "yes"),
    ("semi_empirical_gaussian", "additional", "yes"),
    ("semi_empirical_mopac", "additional", "yes"),
    ("basis_set_specification", "additional", "yes"),
    ("basis_alterations", "additional", "yes"),
    ("field_read", "additional", "yes"),
    ("ecp_specification", "additional", "yes"),
    ("density_fitting_basis", "additional", "yes"),
    ("pcm_solvation_input", "additional", "yes"),
    ("dftb_parameters", "additional", "yes"),
    ("guess_input", "additional", "yes"),
    ("guess_lowsymm", "additional", "no"),
    ("guess_cards", "additional", "yes"),
    ("guess_alter", "additional", "yes"),
    ("guess_permute", "additional", "yes"),
    ("gvb_pairs", "additional", "no"),
    ("cas_stateaverage", "additional", "yes"),
    ("casscf_spinorbit", "additional", "no"),
    ("read_window", "additional", "yes"),
    ("ept_readorbitals", "additional", "yes"),
    ("nmr_readatoms", "additional", "yes"),
    ("pop_readradii", "additional", "yes"),
    ("antechamber_output", "additional", "yes"),
    ("electrostatic_properties", "additional", "yes"),
    ("nbo_input", "additional", "no"),
    ("freq_selectnormalmodes", "additional", "yes"),
    ("freq_readhindered", "additional", "yes"),
    ("freq_selectanharmonicmodes", "additional", "yes"),
    ("freq_readanharmonic", "additional", "yes"),
    ("freq_readfcht", "additional", "yes"),
    ("pickett_atom_list", "additional", "no"),
    ("acid_output", "additional", "yes"),
    ("proaims_output", "additional", "no"),
    ("matrix_element_output", "additional", "yes"),
)


def test_table_shape_matches_official_59_rows():
    """59 行 = 4 core + 54 additional + 1 automatic；逐行对照官方表。"""
    got = tuple((r.section_id, r.kind, r.terminator) for r in so.TABLE)
    assert got == EXPECTED
    assert sum(r.kind == "core" for r in so.TABLE) == 4
    assert sum(r.kind == "additional" for r in so.TABLE) == 54
    assert sum(r.kind == "automatic" for r in so.TABLE) == 1
    # no 例外全集 7 行：core 的 Link 0 + additional 6 行
    assert sum(r.terminator == "no" for r in so.TABLE) == 7


def test_any_trigger_false_for_ordinary_route():
    """负向：普通 route（无读取类关键字）不触发附加节口径。"""
    for route in ("#p b3lyp/6-31g(d) opt freq",
                  "#p hf/sto-3g scf=tight",
                  "#T b3lyp/6-31g(d,p) pop=reg",
                  "#p mp2/6-31g(d) iop(6/50=1)"):
        assert so.any_trigger(route) is False, route


def test_any_trigger_true_for_representative_rows():
    """代表性触发行逐条命中（裸形/选项形/组合谓词/散文行人工转换）。"""
    cases = {
        "#p extraoverlays": "extra_overlays",
        "#p geom=connect": "geom_connectivity",
        "#p geom=(modconnect)": "geom_connectivity",
        "#p geom=readopt": "geom_readopt",
        "#p opt=modredundant": "opt_modredundant",
        "#p opt=(modredun,calcfc)": "opt_modredundant",
        "#p opt=qst2": "qst2_qst3_second_structure",
        "#p opt=qst3": "qst3_third_structure",
        "#p readisotopes": "readisotopes",
        "#p external=(runtink,readinput)": "external_readinput",
        "#p amber=hardfirst": "mm_parameters",
        "#p amber=softonly": "mm_parameters",
        "#p cphf=rdfreq": "frequency_of_interest",
        "#p freq=roa": "frequency_of_interest",
        "#p charge": "background_charge",
        "#p bomd": "admp_bomd",
        "#p bomd=readvelocity": "admp_bomd",
        "#p scrf=(externaliteration,read)": "pcm_input",
        "#p scrf=(oniompcm=a,read)": "pcm_input",
        "#p irc(report=read)": "irc_report_read",
        "#p geom=readharmonic": "geom_readharmonic",
        "#p am1=input": "semi_empirical_gaussian",
        "#p pm3=mopacexternal": "semi_empirical_mopac",
        "#p gen": "basis_set_specification",
        "#p genecp": "basis_set_specification",
        "#p extrabasis": "basis_set_specification",
        "#p massage": "basis_alterations",
        "#p field=read": "field_read",
        "#p pseudo=cards": "ecp_specification",
        "#p extradensitybasis": "density_fitting_basis",
        "#p scrf=read": "pcm_solvation_input",
        "#p dftb": "dftb_parameters",
        "#p guess=input": "guess_input",
        "#p guess=lowsymm": "guess_lowsymm",
        "#p guess=cards": "guess_cards",
        "#p guess=alter": "guess_alter",
        "#p guess=permute": "guess_permute",
        "#p gvb": "gvb_pairs",
        "#p cas=stateaverage": "cas_stateaverage",
        "#p casscf=spinorbit": "casscf_spinorbit",
        "#p mp2=readwindow": "read_window",
        "#p ept=readorbitals": "ept_readorbitals",
        "#p nmr=readatoms": "nmr_readatoms",
        "#p pop=readradii": "pop_readradii",
        "#p pop=readatradii": "pop_readradii",
        "#p prop=read": "electrostatic_properties",
        "#p prop=opt": "electrostatic_properties",
        "#p pop=nboread": "nbo_input",
        "#p pop=nbo6read": "nbo_input",
        "#p freq=selectnormalmodes": "freq_selectnormalmodes",
        "#p freq=readhindered": "freq_readhindered",
        "#p freq=selectanharmonicmodes": "freq_selectanharmonicmodes",
        "#p freq=readanharmonic": "freq_readanharmonic",
        "#p freq=readfcht": "freq_readfcht",
        "#p output=pickett": "pickett_atom_list",
        "#p output=wfn": "proaims_output",
        "#p output=matrixelement": "matrix_element_output",
        "#p output=raw": "matrix_element_output",
    }
    for route, section_id in cases.items():
        hits = {r.section_id for r in so.additional_hits(route)}
        assert section_id in hits, route
    # Both 选项按官方两行原文同时命中 Gaussian 与 MOPAC 格式行
    both_hits = {r.section_id for r in so.additional_hits("#p pm6=both")}
    assert {"semi_empirical_gaussian", "semi_empirical_mopac"} <= both_hits


def test_combined_predicates_need_both_keywords():
    """组合谓词行（AND 跨关键字）单边不命中。"""
    for route in ("#p geom=connect opt=ts", "#p opt=(modredun,calcfc)"):
        hits = {r.section_id for r in so.additional_hits(route)}
        assert "qst3_third_connectivity" not in hits, route
        assert "qst2_qst3_second_connectivity" not in hits, route
    both = {r.section_id for r in
            so.additional_hits("#p geom=connect opt=qst2")}
    assert "qst2_qst3_second_connectivity" in both
    third = {r.section_id for r in
             so.additional_hits("#p geom=(connect) opt=(modredun,qst3)")}
    assert "qst3_third_connectivity" in third
    # Antechamber/ACID 行要求 Pop/NMR 选项与 IOp 关键字并出
    assert "antechamber_output" not in {
        r.section_id for r in so.additional_hits("#p pop=mk")}
    assert "antechamber_output" in {
        r.section_id for r in so.additional_hits("#p pop=mk iop(6/50=1)")}
    assert "acid_output" in {
        r.section_id for r in so.additional_hits("#p nmr=cgst iop(10/93=1)")}


def test_terminator_verdict_matrix():
    """末节 EOF 终止空行判定：全 yes 报 / 全 no 不报 / 混合保守不报 / 空不报。"""
    assert so.terminator_missing("#p hf/sto-3g gen") is True
    assert so.terminator_missing("#p b3lyp/6-31g(d) pop=nboread") is False
    assert so.terminator_missing("#p gen pop=nboread") is False  # 混合保守
    assert so.terminator_missing("#p b3lyp/6-31g(d) opt freq") is False
    assert so.terminator_missing("#p b3lyp/6-31g(d) prop=wrf") is False


def test_compat_extra_keywords_removed_after_g16_smoke():
    """prop=wrf 兼容触发项经 B6 G16 Rev. C.01 实测拒绝（QPErr syntax
    error，A 类 G03 旧形态）后删除（决策点 9 裁决）：any_trigger 不再
    因该形态触发，COMPAT_EXTRA_KEYWORDS 常量随之移除。"""
    assert so.any_trigger("#p b3lyp/6-31g(d) prop=wrf") is False
    assert not hasattr(so, "COMPAT_EXTRA_KEYWORDS")
