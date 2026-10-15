#!/usr/bin/env python3
"""G16 route 关键词字典生成（m2-plan B1 基座 + 插波 3.2.0 批次 B 扩面
+ 3.3 unreleased 面⑤选项面）。

数据源：gaussian-kb 结构化知识库数据目录（官方 HTML 经 gaussian-kb 抽取，
与 MCP list_gaussian_pages/get_gaussian_page 同源同数）：
- page_manifest.json（页面清单）；
- markdown/<category>/<slug>.md（页面正文，缺失时对应面跳过）。

词条面（插波 3.2.0 批次 B 定案，m4-combo-template-deploy-plan §8.1：
尽可能从 gaussian-kb 提取、最大化词典覆盖，同时噪声可控）：
- 面①（基座，m2-plan §2.1 原规则不动摇）：keyword 分类页 slug 全集 +
  标题等价变体，剔除 8 篇文章/版本说明页；
- 面②（方法面，首选源）：gv6 计算设置关键词对照页表格末列（UI→route
  对照，route 切分同 parse.keywords：[/\s#]+）+ dft 页具名泛函族正则
  （Truhlar 组/wB97 族/B97 族/LC- 前缀/BHandH/B2PLYP 族等章节）与
  「Keyword if used alone: X」「the keyword is X」短语锚点；
- 面③（基组面）：basissets 页具名基组族正则（数值 g 系/cc-pV*Z/def2*/
  lanl2*/d95*/cep-*/epr-*/sdd*/dg* 系/svp·tzv·qzvp 系/5D·6D·7F·10F）+
  「Adding Polarization and Diffuse Functions」节明示的极化/弥散形态
  规则生成（(d)/(d,p)/(3df,3pd)/*/\*\*/+/\+\+/aug-/(d') 等完整单 token）；
- 面④（评估结论，不设规则）：gen/pseudo/extrabasis 等页正文为自由格式
  基组/ECP 输入与散文示例，无新增可规则化结构面（其 route 词面已由
  面①②③覆盖），按噪声可控原则不提取。
- 面⑤（选项面，3.3 unreleased 批次：scf=xqc 词典缺失事故）：keyword 页
  Options 章节（##/### 层级、章节名含 option）下的 #### 条目即官方选项名，
  规范化去占位符后以「页 slug=选项」小写组合词入典（route 切分 [/\s#]+
  同规：KW=OPT 为单 token）。章节名不含 option 的核实项走白名单（bd 页
  Related Keywords 节 NewFCBD/OldFCBD、opt 页 Set Opt. Goal 节 QST2/QST3/
  Saddle/Conical、scrf 页 Solvents 节 G03Defaults、dft 页 Empirical
  Dispersion 节 GD2/GD3/GD3BJ/PFD——载体为 EmpiricalDispersion 关键词）。

词条小写化、按码点排序、去重——确定性输出，重跑幂等。

用法：python scripts/extract_keywords.py [--kb-dir DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

# 非关键词页剔除名单（A1 实地核查结论，m2-plan §2.1 留档）：
# 文章/技术札记/版本说明，标题非关键词名。
EXCLUDED_SLUGS = frozenset({
    "afc",             # Modeling Antiferromagnetic Coupling in Gaussian
    "g09_c01",         # Revision C.01（版本说明）
    "nmrcomp",         # Comparing NMR Methods in ChemDraw and Gaussian
    "oniom_technote",  # Investigating the Reactivity ... with ONIOM
    "qst2",            # Transition State Optimizations with Opt=QST2
    "thermo",          # Thermochemistry in Gaussian
    "vcd",             # Studying Chirality with VCD
    "vib",             # Vibrational Analysis in Gaussian
})

# 标题等价变体切分：「X and Y」/「X & Y」（HTML 实体先解码）。
_TITLE_SPLIT = re.compile(r"\s+and\s+|\s*&\s*")
_WORD_KEEP = re.compile(r"[^a-z0-9-]")

# route token 切分（与 parse.keywords._TOKEN_SPLIT 同规）。
_ROUTE_SPLIT = re.compile(r"[/\s#]+")

# 面②gv6 对照表散文单元格残余词停用表（"fragment in molecule
# specification"/"R prefix" 等 UI 说明语切分后的碎片）。
_PROSE_STOP = frozenset({"prefix", "fragment", "molecule", "specification",
                         "included", "in"})
# 面②gv6 对照表允许的单字母词（"#p" → p；其余单字母为表格噪声）。
_SINGLE_OK = frozenset({"p"})
# 词条字符集（含 * 与 ' ：6-31g*、6-31g(d',p') 形态）。
_TOKEN_CHARSET = re.compile(r"^[a-z0-9=+,().*'-]+$")


def _title_variants(title: str) -> list[str]:
    """标题派生变体：切分后各侧均为无空格单词才收（含单词标题自身）。"""
    text = html.unescape(title or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _TITLE_SPLIT.split(text) if p.strip()]
    if not parts or any(" " in p for p in parts):
        return []
    return parts


def extract_manifest(manifest_path: Path) -> set[str]:
    """面①：keyword 分类页 slug 全集 + 标题等价变体。"""
    pages = json.loads(manifest_path.read_text(encoding="utf-8"))
    words: set[str] = set()
    for page in pages:
        if page.get("category") != "keyword":
            continue
        slug = str(page.get("slug") or "")
        if not slug or slug in EXCLUDED_SLUGS:
            continue
        words.add(slug.casefold())
        for variant in _title_variants(str(page.get("title") or "")):
            word = _WORD_KEEP.sub("", variant.casefold())
            if len(word) >= 2:
                words.add(word)
    return words


def _table_words(text: str) -> set[str]:
    """面②gv6 对照页：表格行末列（route 词面列）按 route 切分提取。

    Link0 行（% 前缀）与表头/分隔行剔除；词形过滤：停用表、单字母白名单、
    字符集（尾随 = 剥离——"irc=maxpoints= *n*" 占位写法归一为键面）。
    """
    words: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or set(s) <= {"|", "-", ":", " "}:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        cell = cells[-1]
        if cell.startswith("%"):  # Link0 Tab 行为 Link0 指令面，非 route 词
            continue
        for tok in _ROUTE_SPLIT.split(cell.casefold()):
            tok = tok.rstrip("=")
            if not tok or not tok[0].isalnum():
                continue
            if tok in _PROSE_STOP:
                continue
            if len(tok) == 1 and tok not in _SINGLE_OK:
                continue
            if not _TOKEN_CHARSET.match(tok):
                continue
            words.add(tok)
    return words


# dft 页具名泛函族正则（§8.1 素材源②：按页内章节词形定案——形状独特、
# 与散文词零碰撞；每组注明对应章节）。
_DFT_FAMILIES = tuple(re.compile(p) for p in (
    r"^m0[568][0-9a-z]*$",      # Truhlar 组：M05/M052X/M06/M062X/M06HF/M06L/M08HX
    r"^m11l?$",                 # M11/M11L
    r"^mn1[25](?:sx|l)?$",      # MN12L/MN12SX/MN15/MN15L
    r"^pw6b95d3?$",             # PW6B95/PW6B95D3
    r"^sogga11x?$",             # SOGGA11/SOGGA11X
    r"^n12(?:sx)?$",            # N12/N12SX
    r"^wb97[a-z0-9]*$",         # Long-Range：wB97/wB97X/wB97XD
    r"^lc-[a-z0-9-]+$",         # LC- 前缀族：LC-wPBE/LC-wHPBE/LC-BLYP
    r"^b97[0-9]*[a-z0-9]*$",    # B97 修订族：B97/B971/B972/B97D/B97D3
    r"^bhandh(?:lyp)?$",        # BHandH/BHandHLYP
    r"^(?:b|mpw)2plypd3?$",     # B2PLYPD/B2PLYPD3/mPW2PLYPD（色散表）
    r"^(?:o|x)3lyp$",           # O3LYP/X3LYP
    r"^rev?tpss[a-z]*$",        # TPSS/TPSSh/RevTPSS
    r"^apfd?$",                 # APF/APFD（色散）
))

# 「keyword is X」类短语锚点（dft 页正文的显式关键词指称句式）。
# 捕获词须大写开头——官方文档中关键词恒以大写字母书写，散文指称
# （keyword is specified/keyword with 等）以小写起句，借此零噪声排除。
_KW_PHRASE = re.compile(
    r"(?:[Kk]eyword\s+is|[Kk]eyword\s+if\s+used\s+alone:|[Kk]eyword)\s+"
    r"([A-Z][A-Za-z0-9!,'()+*/.\[\]-]*)")
# 反序指称（"The B1B95 keyword is used…"——名称在 keyword 之前）。
_KW_PHRASE_REV = re.compile(r"([A-Z][A-Za-z0-9!,'()+*/.\[\]-]*)\s+[Kk]eywords?\b")


def _dft_words(text: str) -> set[str]:
    """面②dft 页：族正则全页扫描 + 短语锚点捕获。"""
    folded = text.casefold()
    words: set[str] = set()
    tokens = (t for t in re.split(r"[^a-z0-9+'(),.*'!\]-]+", folded) if t)
    for raw in tokens:
        tok = raw.strip("!'()*.,-")
        if not tok or len(tok) > 30:
            continue
        if any(p.match(tok) for p in _DFT_FAMILIES):
            words.add(tok)
    for pat in (_KW_PHRASE, _KW_PHRASE_REV):
        for m in pat.finditer(text):
            # 反序锚点守卫：捕获词须含数字或非首字母大写（B1B95/
            # EmpiricalDispersion 型技术词恒满足，句首普通英文词
            # The/Functionals/Related 恒不满足）——防 "The keyword" 误捕。
            raw = m.group(1)
            if pat is _KW_PHRASE_REV and len(raw) > 1 \
                    and not (any(c.isdigit() for c in raw)
                             or any(c.isupper() for c in raw[1:])):
                continue
            for tok in re.split(r"[\s,;]+", raw):
                tok = tok.casefold().strip("(),'!*.")
                if 1 < len(tok) <= 30 and _TOKEN_CHARSET.match(tok) \
                        and tok[0].isalnum():
                    words.add(tok)
    return words


# basissets 页具名基组族正则（§8.1 素材源③；词形独特、散文零碰撞）。
_BASIS_FAMILIES = tuple(re.compile(p) for p in (
    r"^sto-\d+g$",
    r"^(?:mc-)?\d+-\d+g$",
    r"^cep-\d+g$",
    r"^d95v?$",
    r"^(?:shc|sec)$",
    r"^lanl2(?:dz|mb)$",
    r"^sdd(?:all)?$",
    r"^(?:aug-)?cc-pv(?:[dtq]|5|6)z$",
    r"^(?:sp|d)?aug-cc-pv[dtqz56]+$",
    r"^def2[a-z]{2,6}(?:pp)?$",  # 页内明示「连字符去除」形：Def2SV…Def2QZVPP
    r"^(?:svp|tzv|tzvp|qzvp)$",
    r"^(?:svpfit|tzvpfit|w06)$",
    r"^dgdzvp2?$",
    r"^dgtzvp$",
    r"^dga[12]$",
    r"^epr-(?:ii|iii)$",
    r"^ugbs\d?[pvo]?$",
    r"^mtsmall$",
    r"^midix$",
    r"^cbsb7$",
    r"^(?:[56]d|10f|7f)$",
))

# 极化/弥散形态规则生成（basissets「Adding Polarization and Diffuse
# Functions」节明示形态；6-31+g(d,p) 系完整单 token；"*"/"**" 与
# (d)/(d,p) 同义并存；6-31g† 系对应 (d')/(d',p')/(+(d'f)) 撇号形；
# 弥散 + / ++ 按页例插于数字与 g 之间——6-31+g、6-311++g）。
_BASIS_VARIANTS: dict[str, tuple[str, ...]] = {
    "sto-3g": ("*",),
    "3-21g": ("", "(d)", "*"),
    "6-21g": ("", "(d)", "(d,p)", "*", "**"),
    "4-31g": ("", "(d)", "(d,p)", "*", "**"),
    "6-31g": ("", "(d)", "(d,p)", "(3df,3pd)", "*", "**", "(d')", "(d',p')"),
    "6-31+g": ("", "(d)", "(d,p)", "(3df,2p)", "(d'f)"),
    "6-31++g": ("", "(d,p)", "(2d,2p)"),
    "6-311g": ("", "(d)", "(d,p)", "(2d,d,p)"),
    "6-311+g": ("", "(d)", "(d,p)"),
    "6-311++g": ("", "(2d,2p)"),
    "mc-311g": ("",),
}


# 面⑤章节外核实项白名单（3.3 选项面全库审计，2026-10-15）：官方文档置于
# 名称不含 option 的章节、但经原文核实确为该载体关键词选项的条目（键为
# 载体关键词，可与页面 slug 不同）：bd 页 Related Keywords 节、opt 页
# Set Opt. Goal 节、scrf 页 Solvents 节、dft 页 Empirical Dispersion 节
# （原文「The EmpiricalDispersion keyword ... takes the following
# options」）、integral 页 Relativistic Calculations 节、sacci 页 Input 节
# （Spin State Options 章的延续）。
_MANUAL_OPTIONS: dict[str, tuple[str, ...]] = {
    "bd": ("NewFCBD", "OldFCBD"),
    "opt": ("QST2", "QST3", "Saddle", "Conical"),
    "scrf": ("G03Defaults",),
    "empiricaldispersion": ("PFD", "GD2", "GD3", "GD3BJ"),
    "integral": ("DKH", "DKH0", "DKHSO", "RESC"),
    "sacci": ("TargetState", "AddElectron", "SubElectron", "TransitionFrom",
              "AllProperties", "NoProperty", "SelectCISOnly", "SACOnly"),
}

# Options 章节：## 与 ### 层级（如 gen 页 ### Option、integral 页
# ### General Basis Set-Related Options 均为三级）。捕获条件为两级
# 章节名任一含 option：仅按最近一级判断会把 ## Options 内 ### 选项
# 分组（组名可不含 option，如 freq 页各模式组）之后的条目整体漏掉。
_CHAPTER_HEADING = re.compile(r"^(##|###)\s+(.+)$")
_OPTION_HEADING = re.compile(r"^####\s+(.+)$")


def _norm_option(heading: str) -> str | None:
    """#### 选项标题 → 选项基名；不可规整为单 token 的返回 None。

    去斜体占位符后剥参数形态：NDamp=*N*→ndamp、VShift[=N]→vshift、
    Saddle=N→saddle、TargetState=(...)→targetstate；散文章节标题
    （含空格）与占位符残留形态剔除。
    """
    text = heading.strip().replace("*", "").replace("_", "")
    text = re.sub(r"\[=.*\]$", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = text.split("=", 1)[0].strip()
    if len(text) < 2 or " " in text \
            or not re.fullmatch(r"[A-Za-z0-9'-]+", text):
        return None
    return text


def _option_words(markdown_dir: Path) -> set[str]:
    """面⑤keyword 页：Options 章节 #### 条目规则提取 + 章节外白名单。"""
    words: set[str] = set()
    kdir = markdown_dir / "keyword"
    if not kdir.is_dir():
        return words
    for page in sorted(kdir.glob("*.md")):
        slug = page.stem
        if slug in EXCLUDED_SLUGS:
            continue
        lv2 = lv3 = None
        for line in page.read_text(encoding="utf-8").splitlines():
            m = _CHAPTER_HEADING.match(line)
            if m:
                if m.group(1) == "##":
                    lv2, lv3 = m.group(2).strip(), None
                else:
                    lv3 = m.group(2).strip()
                continue
            m = _OPTION_HEADING.match(line)
            if m and ((lv2 and "option" in lv2.casefold())
                      or (lv3 and "option" in lv3.casefold())):
                opt = _norm_option(m.group(1))
                if opt:
                    words.add(f"{slug}={opt}".casefold())
    for carrier, opts in _MANUAL_OPTIONS.items():
        for opt in opts:
            words.add(f"{carrier}={opt}".casefold())
    return words


def _basis_words(text: str) -> set[str]:
    """面③basissets 页：族正则全页扫描 + 极化/弥散形态规则生成。"""
    folded = text.casefold()
    words: set[str] = set()
    for raw in re.split(r"[^a-z0-9+'(),.*!-]+", folded):
        tok = raw.strip("!'*.,-")
        if 1 < len(tok) <= 30 and any(p.match(tok) for p in _BASIS_FAMILIES):
            words.add(tok)
    for base, suffixes in _BASIS_VARIANTS.items():
        for suf in suffixes:
            words.add(base + suf)
    for z in ("dz", "tz", "qz", "5z", "6z"):
        words.add(f"aug-cc-pv{z}")
    return words


def extract(manifest_path: Path, markdown_dir: Path | None) -> list[str]:
    """产出排序去重的词条全集（四条提取面并集）。"""
    words = extract_manifest(manifest_path)
    if markdown_dir is not None and markdown_dir.is_dir():
        gv6 = markdown_dir / "gv6" / \
            "gv6-gaussian-calculation-setup-keywords-and-options.md"
        if gv6.is_file():
            words |= _table_words(gv6.read_text(encoding="utf-8"))
        dft = markdown_dir / "keyword" / "dft.md"
        if dft.is_file():
            words |= _dft_words(dft.read_text(encoding="utf-8"))
        basis = markdown_dir / "structure" / "basissets.md"
        if basis.is_file():
            words |= _basis_words(basis.read_text(encoding="utf-8"))
        words |= _option_words(markdown_dir)
    return sorted(words)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G16 route 关键词字典生成")
    parser.add_argument("--kb-dir", type=Path,
                        default=Path("~/gaussian-kb/data").expanduser(),
                        help="gaussian-kb 结构化数据目录（含 page_manifest.json"
                             " 与 markdown/ 正文；正文缺失时仅出面①基座）")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[1]
                        / "web" / "src" / "parse" / "keywords.txt",
                        help="字典输出路径（默认入库位置）")
    args = parser.parse_args(argv)
    manifest = args.kb_dir / "page_manifest.json"
    if not manifest.is_file():
        print(f"页面清单不存在：{manifest}", file=sys.stderr)
        return 1
    words = extract(manifest, args.kb_dir / "markdown")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(w + "\n" for w in words), encoding="utf-8")
    print(f"词条 {len(words)} 个 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
