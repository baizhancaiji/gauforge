"""G16 官方 Section Ordering 表固化（输入勘误计划 G4，B2 数据 SSOT）。

官方 input 页 Section Ordering 全表 59 行（G16 Rev. C.01，2018-02-19 快照，
与计划 §1.2 逐行一致）落码：4 core + 54 additional + 1 automatic。消费方：
- any_trigger：parse_input / scan_spans 的 wants_extra 判定（附加节识别与
  隐式变量区抑制）的官方口径（§2.12 的 prop=wrf 兼容触发项经 B6 G16
  Rev. C.01 实测拒绝（QPErr syntax error）已删除，决策点 9 裁决）；
- additional_hits / terminator_missing：最后一个附加节以 EOF 收尾时，
  route 命中的 additional 行全为 terminator=yes 才记 parse_errors，
  混合 yes/no 保守不报（§7 风险缓解）。

谓词只做「头部精确等值 / 选项集精确包含」判定，禁裸子串（§7 风险）；
散文行（MM 参数、半经验参数、BOMD/ADMP、PCM、IRC、IOp 组合、ReadWindow）
由人工转换为具名谓词（pred_*）。禁止把 core 行的 Route Section | all 导入
any_trigger（否则恒真）。附加节出现顺序与 PDB 自动触发不校验（解析器无
节名、不解析残基，§2.12 已登记为已知限制）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from .keywords import token_head, token_options, tokenize_route

log = logging.getLogger(__name__)


class RouteFacts:
    """route 文本 → 谓词可判定的事实视图。

    _heads：全部 token 的关键字头部集合（token_head，casefold）；
    _opts：头部 → 该头部所有出现处选项的并集（token_options，casefold）。
    @file token 豁免（整文件包含，非关键字）。"""

    __slots__ = ("_heads", "_opts")

    def __init__(self, route_text: str):
        heads: set[str] = set()
        opts: dict[str, set[str]] = {}
        for _, tok in tokenize_route(route_text):
            head = token_head(tok)
            if not head or head.startswith("@"):
                continue
            heads.add(head)
            opts.setdefault(head, set()).update(token_options(tok))
        self._heads = frozenset(heads)
        self._opts = {k: frozenset(v) for k, v in opts.items()}

    def has(self, head: str) -> bool:
        """关键字头部精确等值（裸形或任意取值形态均计入头部）。"""
        return head in self._heads

    def opts_of(self, head: str) -> frozenset[str]:
        """该头部全部出现的选项并集（裸形头部为空集）。"""
        return self._opts.get(head, frozenset())

    def all_option_values(self) -> frozenset[str]:
        """跨头部选项全集（read_window 等「任意关键字的选项」谓词用）。"""
        out: set[str] = set()
        for v in self._opts.values():
            out |= v
        return frozenset(out)


# ---------------- 谓词原语（精确等值/包含，禁裸子串） ----------------

Pred = Callable[[RouteFacts], bool]


def _key(*names: str) -> Pred:
    return lambda f: any(f.has(n) for n in names)


def _opt_any(head: str, opts: tuple[str, ...]) -> Pred:
    s = frozenset(opts)
    return lambda f: bool(f.opts_of(head) & s)


def _opt_all(head: str, opts: tuple[str, ...]) -> Pred:
    s = frozenset(opts)
    return lambda f: s <= f.opts_of(head)


def _and(*ps: Pred) -> Pred:
    return lambda f: all(p(f) for p in ps)


def _or(*ps: Pred) -> Pred:
    return lambda f: any(p(f) for p in ps)


# ---------------- 散文行人工转换的具名谓词（§2.4 单列） ----------------

# 半经验方法关键字集（semiempirical 页方法清单；Input/Both/MOPACExternal
# 是其选项——两行半经验参数节官方原文均含 Both options）
_SEMI_METHODS = ("am1", "pm3", "pm6", "pm7", "pm3mm", "pddg", "indo", "cndo",
                 "mindo", "mindo3", "mndo", "rm1")

# MM 方法关键字集（mm 页 Parameter Precedence Options 的宿主方法）
_MM_METHODS = ("amber", "dreiding", "uff")

_MODREDUN = ("modredun", "modredundant")


def _semi_with(f: RouteFacts, *opt_names: str) -> bool:
    want = frozenset(opt_names)
    return any(f.opts_of(m) & want for m in _SEMI_METHODS)


def pred_semi_empirical_input(f: RouteFacts) -> bool:
    """Gaussian 格式半经验参数：半经验方法关键字的 Input 选项。"""
    return _semi_with(f, "input")


def pred_semi_empirical_both(f: RouteFacts) -> bool:
    """Both 选项（官方两行半经验参数节均由其触发）。"""
    return _semi_with(f, "both")


def pred_mopac_external(f: RouteFacts) -> bool:
    """MOPAC 格式半经验参数：半经验方法关键字的 MOPACExternal 选项。"""
    return _semi_with(f, "mopacexternal")


def pred_mm_parameters(f: RouteFacts) -> bool:
    """MM 参数节：MM 方法关键字（Amber/Dreiding/UFF）的参数优先级选项。"""
    want = frozenset(("hardfirst", "softfirst", "softonly", "modify"))
    return any(f.opts_of(m) & want for m in _MM_METHODS)


def pred_admp_bomd(f: RouteFacts) -> bool:
    """BOMD/ADMP 必读输入及其 ReadVelocity/ReadMWVelocity 选项。"""
    if f.has("admp") or f.has("bomd"):
        return True
    want = frozenset(("readvelocity", "readmwvelocity"))
    return any(f.opts_of(k) & want for k in ("admp", "bomd"))


def pred_pcm_input(f: RouteFacts) -> bool:
    """PCM 输入节：SCRF=(ExternalIteration,Read) 或 (SCRF=ONIOMPCM=A,Read)。"""
    opts = f.opts_of("scrf")
    if {"externaliteration", "read"} <= opts:
        return True
    return "read" in opts and any(
        o.partition("=")[0] == "oniompcm" for o in opts)


def pred_irc_report_read(f: RouteFacts) -> bool:
    """IRC 表坐标：IRC(Report=Read)。"""
    return "report=read" in f.opts_of("irc")


def pred_read_window(f: RouteFacts) -> bool:
    """轨道冻结信息：post-SCF 方法关键字的 ReadWindow 选项（frozencore
    页，RW 同义词）；缩写 RW 词面过短不纳入（§2.12 已知限制）。"""
    return "readwindow" in f.all_option_values()


def pred_pop_mk_iop(f: RouteFacts) -> bool:
    """Antechamber 输出文件：Pop=MK 与 IOp(6/50=1) 组合并出。"""
    return "mk" in f.opts_of("pop") and f.has("iop")


def pred_nmr_cgst_iop(f: RouteFacts) -> bool:
    """ACID 输出文件名：NMR=CGST 与 IOp(10/93=1) 组合并出。"""
    return "cgst" in f.opts_of("nmr") and f.has("iop")


# ---------------- 官方表（59 行，与 input 页 Section Ordering 逐行对应） ----------------


@dataclass(frozen=True)
class SectionRule:
    section_id: str
    kind: str        # core | additional | automatic
    terminator: str  # yes | no（官方 Final blank line? 列）
    predicate: Pred  # 仅 additional 行被 any_trigger/additional_hits 消费
    official: str    # 官方触发表原文（节名 | 关键字，审计对照）


def _r(section_id: str, kind: str, terminator: str, predicate: Pred,
       official: str) -> SectionRule:
    return SectionRule(section_id, kind, terminator, predicate, official)


TABLE: tuple[SectionRule, ...] = (
    _r("link0", "core", "no", lambda f: True,
       "Link 0 commands | % commands"),
    _r("route", "core", "yes", lambda f: True, "Route Section | all"),
    _r("extra_overlays", "additional", "yes", _key("extraoverlays"),
       "Extra Overlays | ExtraOverlays"),
    _r("title", "core", "yes", lambda f: True,
       "Title section | all except Geom=AllCheck"),
    _r("molecule", "core", "yes", lambda f: True,
       "Molecule specification | all except Geom=AllCheck"),
    _r("geom_connectivity", "additional", "yes",
       _opt_any("geom", ("connect", "modconnect")),
       "Connectivity specifications | Geom=Connect or ModConnect"),
    _r("geom_readopt", "additional", "yes", _opt_any("geom", ("readopt",)),
       "Alterations to frozen atoms | Geom=ReadOpt"),
    _r("opt_modredundant", "additional", "yes", _opt_any("opt", _MODREDUN),
       "Modifications to coordinates | Opt=ModRedundant"),
    _r("qst2_qst3_second_structure", "additional", "yes",
       _opt_any("opt", ("qst2", "qst3")),
       "2nd title and molecule specification | Opt=QST2 or QST3"),
    _r("qst2_qst3_second_connectivity", "additional", "yes",
       _and(_opt_any("geom", ("connect", "modconnect")),
            _opt_any("opt", ("qst2", "qst3"))),
       "Connectivity specs for 2nd set | Geom=Connect/ModConnect and "
       "Opt=QST2/QST3"),
    _r("qst2_qst3_second_readopt", "additional", "yes",
       _opt_any("geom", ("readopt",)),
       "2nd Alterations to frozen atoms | Geom=ReadOpt"),
    _r("qst2_qst3_second_modifications", "additional", "yes",
       _opt_any("opt", ("qst2", "qst3")),
       "Modifications to 2nd set of coordinates | Opt=QST2 or QST3"),
    _r("qst3_third_structure", "additional", "yes",
       _opt_any("opt", ("qst3",)),
       "3rd title and initial TS structure | Opt=QST3"),
    _r("qst3_third_connectivity", "additional", "yes",
       _and(_opt_any("geom", ("connect", "modconnect")),
            _opt_any("opt", ("qst3",)), _opt_any("opt", _MODREDUN)),
       "Connectivity specs for 3rd set | Geom=Connect or ModConnect "
       "Opt=(ModRedun, QST3)"),
    _r("qst3_third_readopt", "additional", "yes",
       _opt_any("geom", ("readopt",)),
       "3rd Alterations to frozen atoms | Geom=ReadOpt"),
    _r("qst3_third_modifications", "additional", "yes",
       _and(_opt_any("opt", ("qst3",)), _opt_any("opt", _MODREDUN)),
       "Modifications to 3rd set | Opt=(ModRedun, QST3)"),
    _r("pdb_secondary_structure", "automatic", "yes", lambda f: False,
       "PDB secondary structure | automatic if residue info"),
    _r("readisotopes", "additional", "yes", _key("readisotopes"),
       "Atomic masses | ReadIsotopes option"),
    _r("external_readinput", "additional", "yes",
       _and(_key("external"), _opt_any("external", ("readinput",))),
       "External | External=(…,ReadInput)"),
    _r("mm_parameters", "additional", "yes", pred_mm_parameters,
       "Molecular Mechanics parameters | HardFirst, SoftFirst, SoftOnly, "
       "Modify options"),
    _r("frequency_of_interest", "additional", "yes",
       _or(_opt_any("cphf", ("rdfreq",)), _opt_any("freq", ("roa",))),
       "Frequency of interest | CPHF=RdFreq or Freq=ROA"),
    _r("background_charge", "additional", "yes", _key("charge"),
       "Background charge distribution | Charge"),
    _r("admp_bomd", "additional", "yes", pred_admp_bomd,
       "BOMD/ADMP input | ADMP and BOMD required input and ReadVelocity, "
       "ReadMWVelocity options"),
    _r("pcm_input", "additional", "yes", pred_pcm_input,
       "PCM input | SCRF=(ExternalIteration,Read) and "
       "(SCRF=ONIOMPCM=A,Read)"),
    _r("irc_report_read", "additional", "yes", pred_irc_report_read,
       "Coordinates for IRC table | IRC(Report=Read)"),
    _r("geom_readharmonic", "additional", "yes",
       _opt_any("geom", ("readharmonic",)),
       "Harmonic constraints | Geom=ReadHarmonic"),
    _r("semi_empirical_gaussian", "additional", "yes",
       _or(pred_semi_empirical_input, pred_semi_empirical_both),
       "Semi-empirical parameters (Gaussian) | Input option and Both options"),
    _r("semi_empirical_mopac", "additional", "yes",
       _or(pred_mopac_external, pred_semi_empirical_both),
       "Semi-empirical parameters (MOPAC) | MOPACExternal and Both options"),
    _r("basis_set_specification", "additional", "yes",
       _key("gen", "genecp", "extrabasis"),
       "Basis set specification | Gen, GenECP, ExtraBasis"),
    _r("basis_alterations", "additional", "yes", _key("massage"),
       "Basis set alterations | Massage"),
    _r("field_read", "additional", "yes",
       _and(_key("field"), _opt_any("field", ("read",))),
       "Finite field coefficients | Field=Read"),
    _r("ecp_specification", "additional", "yes",
       _or(_opt_any("pseudo", ("cards",)), _key("genecp")),
       "ECP specification | Pseudo=Cards, GenECP"),
    _r("density_fitting_basis", "additional", "yes",
       _key("extradensitybasis"),
       "Density fitting basis set | ExtraDensityBasis"),
    _r("pcm_solvation_input", "additional", "yes",
       _opt_any("scrf", ("read",)), "PCM solvation model input | SCRF=Read"),
    _r("dftb_parameters", "additional", "yes", _key("dftb"),
       "DFTB parameters | DFTB"),
    _r("guess_input", "additional", "yes", _opt_any("guess", ("input",)),
       "Source for initial guess | Guess=Input"),
    _r("guess_lowsymm", "additional", "no", _opt_any("guess", ("lowsymm",)),
       "Symmetry types to combine | Guess=LowSymm"),
    _r("guess_cards", "additional", "yes", _opt_any("guess", ("cards",)),
       "Orbital specifications | Guess=Cards"),
    _r("guess_alter", "additional", "yes", _opt_any("guess", ("alter",)),
       "Orbital alterations | Guess=Alter"),
    _r("guess_permute", "additional", "yes", _opt_any("guess", ("permute",)),
       "Orbital reordering | Guess=Permute"),
    _r("gvb_pairs", "additional", "no", _key("gvb"),
       "# Orbitals/GVB pair | GVB"),
    _r("cas_stateaverage", "additional", "yes",
       _opt_any("cas", ("stateaverage",)),
       "Weights for CAS state averaging | CAS=StateAverage"),
    _r("casscf_spinorbit", "additional", "no",
       _opt_any("casscf", ("spinorbit",)),
       "States of interest for spin orbit coupling | CASSCF=SpinOrbit"),
    _r("read_window", "additional", "yes", pred_read_window,
       "Orbital freezing information | ReadWindow options"),
    _r("ept_readorbitals", "additional", "yes",
       _opt_any("ept", ("readorbitals",)),
       "EPT orbitals to refine | EPT=ReadOrbitals"),
    _r("nmr_readatoms", "additional", "yes",
       _opt_any("nmr", ("readatoms",)),
       "Atoms list for spin-spin coupling constants | NMR=ReadAtoms"),
    _r("pop_readradii", "additional", "yes",
       _opt_any("pop", ("readradii", "readatradii")),
       "Alternate atomic radii | Pop=ReadRadii or ReadAtRadii"),
    _r("antechamber_output", "additional", "yes", pred_pop_mk_iop,
       "Antechamber output file | Pop=MK IOp(6/50=1)"),
    _r("electrostatic_properties", "additional", "yes",
       _opt_any("prop", ("read", "opt")),
       "Data for electrostatic properties | Prop=Read or Opt"),
    _r("nbo_input", "additional", "no",
       _opt_any("pop", ("nboread", "nbo6read")),
       "NBO input | Pop=NBORead or Pop=NBO6Read"),
    _r("freq_selectnormalmodes", "additional", "yes",
       _opt_any("freq", ("selectnormalmodes",)),
       "Harmonic Normal Mode selection | Freq=SelectNormalModes"),
    _r("freq_readhindered", "additional", "yes",
       _opt_any("freq", ("readhindered",)),
       "Hindered Rotor input | Freq=ReadHindered"),
    _r("freq_selectanharmonicmodes", "additional", "yes",
       _opt_any("freq", ("selectanharmonicmodes",)),
       "Anharmonic Normal Mode selection | Freq=SelectAnharmonicModes"),
    _r("freq_readanharmonic", "additional", "yes",
       _opt_any("freq", ("readanharmonic",)),
       "Input for Anharmonic | Freq=ReadAnharmonic"),
    _r("freq_readfcht", "additional", "yes",
       _opt_any("freq", ("readfcht",)), "Input for FCHT | Freq=ReadFCHT"),
    _r("pickett_atom_list", "additional", "no",
       _opt_any("output", ("pickett",)),
       "Atom list for Pickett file generation | Output=Pickett"),
    _r("acid_output", "additional", "yes", pred_nmr_cgst_iop,
       "ACID output filename | NMR=CGST IOp(10/93=1)"),
    _r("proaims_output", "additional", "no", _opt_any("output", ("wfn",)),
       "PROAIMS output filename | Output=WFN"),
    _r("matrix_element_output", "additional", "yes",
       _opt_any("output", ("matrixelement", "raw")),
       "Matrix element filename | Output=MatrixElement or Output=Raw"),
)


# ---------------- 公共判定（parse_input / scan_spans 消费） ----------------

def additional_hits(route_text: str) -> tuple[SectionRule, ...]:
    """route 文本 → 命中的官方 additional 行（不含兼容项，官方表口径）。"""
    f = RouteFacts(route_text)
    return tuple(r for r in TABLE
                 if r.kind == "additional" and r.predicate(f))


def any_trigger(route_text: str) -> bool:
    """附加节口径触发判定：官方 additional 行命中即触发。

    只消费 additional 行——core 行的 Route Section | all 恒真禁止导入；
    automatic 行（PDB）无 route 谓词不参与（§2.12）。prop=wrf 兼容项经
    B6 G16 实测拒绝已删除（决策点 9）：该形态 G16 自身报 QPErr，
    无附加节识别价值，route_option_unknown 警告照发（A 类口径）。"""
    f = RouteFacts(route_text)
    return any(r.kind == "additional" and r.predicate(f) for r in TABLE)


def terminator_missing(route_text: str) -> bool:
    """末附加节以 EOF 收尾时是否记 parse_errors：命中的 additional 行
    全为 terminator=yes 才 True；命中为空或含 no（混合保守）为 False。"""
    hits = additional_hits(route_text)
    return bool(hits) and all(r.terminator == "yes" for r in hits)
