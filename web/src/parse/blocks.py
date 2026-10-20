"""Gaussian 输入分块解析（roadmap §2.7 节结构与空行规则）。

产出与契约 InputPreview.blocks 逐字段一致的分块结构 + parse_errors（逐节容错）
+ warnings（非阻断，输入勘误计划 G0）+ multistep 标记；预览（尽力而为）
与导入校验（严格，B3）共用。解析器自身绝不抛异常：坏文件回落默认分块并以
parse_errors 标注。

B2（输入勘误计划 G4/G9）：附加节触发识别改由官方 Section Ordering 表驱动
（section_ordering.any_trigger；prop=wrf 兼容触发项经 B6 G16 实测拒绝
已删除，决策点 9）；核心节必需空行
缺失显式检测（route/title EOF 阻断、空分子说明缺节阻断、分子说明与
变量/常数区 EOF 非阻断警告、--Link1-- 前空行附注）。scan_spans/split_lines
为公共 API（服务层节起始行取数，B1 审查 R5 整改——不再以下划线私有名
跨模块导入）。
"""
from __future__ import annotations

import logging
import re

from . import section_ordering
from .keywords import tokenize_route
from .link0_rules import check_link0_lines

log = logging.getLogger(__name__)

# 可编辑节名（契约 PUT blocks/{section}；molecule 与未知节名不可编辑）
_FIXED_SECTIONS = ("link0", "route", "title", "charge_mult")
_ADDITIONAL_RE = re.compile(r"additional-\d+$")

_REQUIRED_BLOCKS = {"link0", "route", "title", "charge_mult", "molecule",
                    "additional_sections"}


def _tokenize_atom_line(line: str) -> list[str]:
    """原子行 → token 序列（G6 首字段取词基座）。

    自由格式分隔符（空白/逗号/斜杠）任意组合，括号/引号感知——保住
    C(Iso=13,Fragment=2) 参数表整词；行内引号外 ! 起截断（注释任意处）。"""
    from .keywords import _tokenize_line
    return _tokenize_line(line)


def _hill_formula(counts: dict[str, int]) -> str:
    """Hill 记法：有碳 C、H 优先其余字母序；无碳全字母序；计数 1 显式。"""
    if not counts:
        return ""
    order = sorted(counts, key=lambda e: (0, "") if e == "C"
                   else (1, "") if e == "H" else (2, e))
    return "".join(f"{e}{counts[e]}" for e in order)


# 元素符号表（按原子序数排列；Gaussian 分子说明允许以序数指定元素，
# 如 melamine 类生成文件全用序数书写坐标）
_ELEMENTS = (
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm",
    "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds",
    "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
)

_ELEMENTS_LOWER = frozenset(e.lower() for e in _ELEMENTS)


def _atom_symbol(tok: str) -> str | None:
    """原子行首 token → 规范元素符号；无法识别返回 None（G5 前旧口径，
    保留供兼容调用；parse_input 现走 _classify_atom 文法）。"""
    sym, _kind = _classify_atom(tok)
    return sym


def _classify_atom(tok: str) -> tuple[str | None, str]:
    """原子行首字段 → (规范元素符号 | None, 类别)（G6 文法，B4）。

    类别：element（计入分子式）/ ghost（鬼原子 -Bq：占一行不计式）/
    dummy（哑原子 X：占一行不计式）/ unknown（无元素前缀：不计式）。
    官方 zmat/oniom 页文法：Element-label（元素符号或原子序数，可后接
    字母数字标签，总长 ≤4）[–Atom-type–Charge][(param=value,…)]。
    - 先剥尾部 (…) 参数表（括号平衡）；
    - 鬼原子判定先于元素识别（分段含 Bq 原子类型，如 O-Bq）；
    - Element-label 取首个 –/- 之前片段（覆盖 C-CT--0.06 类 MM 行）；
    - 元素识别用最长符号前缀（不区分大小写：Cl1→Cl、C1→C、Foo→F+标签
      oo 不告警）；剩余部分须字母数字；找不到任何前缀（Zz）→ unknown；
    - 原子序数形态维持界内映射（1..118）；
    - X / X<数字> 识别为哑原子（Z-matrix 中心，无元素无核电荷）。
    """
    t = tok.strip()
    # 剥尾部 (…) 参数表（如 C(Iso=13,Fragment=2)）
    if t.endswith(")"):
        depth = 0
        for k in range(len(t) - 1, -1, -1):
            if t[k] == ")":
                depth += 1
            elif t[k] == "(":
                depth -= 1
                if depth == 0:
                    t = t[:k]
                    break
    # 鬼原子：按 –/- 分段后含 Bq 原子类型（计入行数、不计分子式）
    segs = [s for s in t.replace("–", "-").split("-") if s]
    if any(s.casefold() == "bq" for s in segs):
        return None, "ghost"
    label = segs[0] if segs else t
    # 哑原子：X 及重复 X 标签（XX——官方测试语料形态）、`-`（同前一原子
    # 位置的哑原子标记），可带尾部数字；无元素、不计分子式
    core = label.rstrip("0123456789")
    if t == "-" or (set(core.casefold()) == {"x"} and core
                    and (label == core or label[len(core):].isdigit())):
        return None, "dummy"
    if label.isdigit():
        if 1 <= int(label) <= len(_ELEMENTS):
            return _ELEMENTS[int(label) - 1], "element"
        return None, "unknown"
    # 最长元素符号前缀（≤2 字符），剩余部分须字母数字或为空（标签总长 ≤4
    # 由官方文法约定，超出不额外拒绝——前缀识别已保证元素归属）
    for n in (2, 1):
        if len(label) >= n and label[:n].casefold() in _ELEMENTS_LOWER:
            rest = label[n:]
            if not rest or rest.isalnum():
                return label[:n].capitalize(), "element"
            return None, "unknown"
    return None, "unknown"


def split_lines(text: str) -> list[str]:
    """全文件逻辑行（换行归一 + 末尾换行切分产物剥离）。

    公共 API（B1 审查 R5 整改）：服务层节起始行取数与解析层共用同一
    行化口径。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":  # 末尾换行符的切分产物不是空行
        lines.pop()
    return lines


def parse_charge_tokens(line: str) -> list[str]:
    """电荷/多重度行 → 整数 token 串（G5 自由格式分隔单点）。

    en-dash 宽容换负号、逗号/斜杠与空白等价——parse_input 与编辑保存
    （services.candidates）共用同一分词口径，各通道「无法解析才阻断」
    （§2.11 矩阵；审查整改 R3：斜杠/en-dash 编辑保存原误拒）。"""
    return line.replace("–", "-").replace(",", " ").replace("/", " ").split()


def _looks_like_variables(region: list[str]) -> bool:
    """无 Variables: 头的隐式变量区：每行「名 数值 [格式]」且名以字母开头。"""
    if not region:
        return False
    for ln in region:
        toks = ln.split()
        if not toks or not toks[0][0].isalpha():
            return False
        try:
            float(toks[1])
        except (IndexError, ValueError):
            return False
        if len(toks) > 3:
            return False
        if len(toks) == 3 and toks[2].casefold() not in ("s", "d", "f"):
            return False
    return True


def _geom_exemption_tier(route_text: str) -> str | None:
    """Geom 检查点豁免档位（C1/C2，B1）：'allcheck' | 'checkpoint' | None。

    官方 geom 页：Geom=AllCheck 时 title/电荷/坐标皆可整体省略；
    Geom=Checkpoint（同义 Check）仅原子坐标取自检查点、title 与电荷/多重度
    行仍必须存在。识别走 tokenize_route 括号/引号感知管道，覆盖裸形、
    括号形（geom=(allcheck,modredundant)）、= 两侧空格（geom = allcheck）、
    键名与括号间空格（geom (allcheck)）及大小写变体；allcheck 与
    checkpoint 并出时 allcheck 优先。本判定仅在 parse_input 消费——
    scan_spans/verify_and_normalize 无 geom 语义，勿在此同步。
    """
    tier: str | None = None
    for _, tok in tokenize_route(route_text):
        t = tok.casefold()
        p = t.find("(")
        if p > 0:
            head = t[:p].rstrip("=")
            opts = [o.strip() for o in t[p:].lstrip("(").rstrip(")").split(",")]
        else:
            head, sep, val = t.partition("=")
            if not sep:
                continue
            opts = [val.strip()]
        if head != "geom":
            continue
        if "allcheck" in opts:
            return "allcheck"
        if "checkpoint" in opts or "check" in opts:
            tier = "checkpoint"
    return tier


def parse_input(text: str) -> dict:
    """解析输入文本 → {"blocks": …, "parse_errors": […], "warnings": […],
    "multistep": bool}；warnings 为非阻断提示通道（G0；B2/B4 检测项扩容）。

    入口防御性剥离 UTF-8 BOM（\\ufeff——导入/提交读取路径 utf-8-sig 之外的
    兜底，B4 G5 项 6）。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = split_lines(text)
    errors: list[dict] = []
    warnings: list[dict] = []

    # 多步任务：解析在首个 --Link1-- 处截断，仅覆盖第一步
    stop = next((k for k, ln in enumerate(lines)
                 if ln.strip().casefold() == "--link1--"), None)
    multistep = stop is not None
    if multistep:
        msg = "多步任务（--Link1--）不支持"
        if stop > 0 and lines[stop - 1].strip():  # G9 项 7：官方前导空行要求
            msg += "（--Link1-- 前缺少空行，官方要求）"
        errors.append({"section": "link1", "line": stop + 1,
                       "message": msg})
        lines = lines[:stop]
    n = len(lines)

    blocks = {
        "link0": {"lines": [], "missing": []},
        "route": "",
        "title": None,
        "charge_mult": "",
        "molecule": {"atom_count": 0, "formula": "",
                     "variables_present": False, "constants_present": False},
        "additional_sections": [],
    }

    def blank(k: int) -> bool:
        return not lines[k].strip()

    def comment(k: int) -> bool:
        return lines[k].lstrip().startswith("!")

    i = 0
    # Link 0：前导空行/注释后连续 % 行，其后不要求终止空行
    while i < n and (blank(i) or comment(i)):
        i += 1
    link0_start = i  # 块首 % 行的全文件 1 起行号 = link0_start + 1（R1）
    while i < n and lines[i].lstrip().startswith("%"):
        blocks["link0"]["lines"].append(lines[i].strip())
        i += 1
    low = [ln.casefold() for ln in blocks["link0"]["lines"]]
    # 核资源已声明的判定：%nproc 前缀超集覆盖 %nprocshared 与早期同义 %nproc、
    # 实测可用的 %nprocshare 截断形式（%nproc 同义性见手册 %cpu 条目 replaces
    # the earlier %nprocshared and %nproc）；%cpu=proc-list 为现行推荐，语义是
    # 绑定具体逻辑处理器（0,1,2 / 0-5 / 混合，gaussian.com/run），与 %nproc
    # 的分配核数语义并行不混同，任一存在即不告警。%mem 带 % 前缀防 chk 行误判。
    blocks["link0"]["missing"] = [
        nm for nm, pats in (("NProcShared", ("%nproc", "%cpu")),
                            ("Mem", ("%mem",)))
        if not any(p in ln for ln in low for p in pats)]
    # G5 项 2/3/4：Link 0 值域（%mem 值域与 >0、%nproc 正整数、%cpu proc-list
    # 含 /n）、单行 ≤500、指令文法与重复——非阻断警告（link0_rules 单点；
    # line_offset 传块首 0 起行号，警告行号 G0 全文件绝对口径）
    for w in check_link0_lines(blocks["link0"]["lines"],
                               line_offset=link0_start):
        warnings.append(w)

    # Route：# 行起连续非空行，终止空行必需
    while i < n and (blank(i) or comment(i)):
        i += 1
    route_lines: list[str] = []
    route_start = i
    route_unterminated = False
    if i < n and lines[i].lstrip().startswith("#"):
        while i < n and not blank(i):
            ln = lines[i].rstrip()
            if i > route_start and ln.lstrip().startswith("%"):
                # G3 情形 1：Link 0 命令错置 route 之后（无空行分隔被吞入，
                # G16 必然误读——阻断）
                errors.append({"section": "route", "line": i + 1,
                               "message": "Link 0 命令必须位于 route 节之前"
                                          "（该 % 行会被并入 route 误读）"})
            route_lines.append(ln)
            i += 1
        if i >= n:  # G9 项 1：route 延展至 EOF（其后内容已被吞并）
            route_unterminated = True
            errors.append({"section": "route", "line": route_start + 1,
                           "message": "route 节未以空行终止"})
    else:
        errors.append({"section": "route", "line": min(i + 1, n),
                       "message": "缺少 route 节（# 开头）"})
    blocks["route"] = "\n".join(route_lines)
    route_cf = blocks["route"].casefold()
    # Geom 豁免档位（C1/C2）：allcheck=仅该档豁免 title/电荷；checkpoint
    # 仅坐标可省——title 与电荷/多重度缺失照常记 parse_errors
    geom_tier = _geom_exemption_tier(blocks["route"])

    # Title：终止空行后连续非空行，至多 5 行（§2.7）
    while i < n and (blank(i) or comment(i)):
        i += 1
    title_lines: list[str] = []
    title_start = i
    while i < n and not blank(i):
        title_lines.append(lines[i].strip())
        i += 1
    if title_lines:
        for k, tl in enumerate(title_lines):
            if tl.lstrip().startswith("%"):
                # G3 情形 2：% 行落入 title 节（route 后有空行分隔时 % 成为
                # title 首行；route 缺失时同样落 title——形态合法但几乎必为
                # 用户错误）；Link0 收集规则只认前导 % 行，此处覆盖其后错置
                errors.append({"section": "title", "line": title_start + k + 1,
                               "message": "疑似 Link 0 命令错置于 title 节"
                                          "（% 命令必须位于 route 节之前）"})
            # G5 项 5：title 禁用字符（@ # ! – _ \ 与控制字符）——编辑保存
            # 保持阻断，导入/提交通道记非阻断警告
            if any(c in tl for c in "@#!–_\\") or any(ord(c) < 32 for c in tl):
                bad = next(c for c in tl
                           if c in "@#!–_\\" or ord(c) < 32)
                warnings.append({"line": title_start + k + 1, "keyword": bad,
                                 "kind": "title_forbidden_char",
                                 "message": "title 含官方建议避免的字符"
                                            f"「{bad!r}」（控制字符不可见时"
                                            "以转义显示）"})
        if len(title_lines) > 5:
            errors.append({"section": "title", "line": i - len(title_lines) + 1,
                           "message": "title 节超过 5 行"})
        blocks["title"] = "\n".join(title_lines)
        if i >= n and geom_tier != "allcheck":  # G9 项 2（AllCheck 豁免集不报）
            errors.append({"section": "title", "line": title_start + 1,
                           "message": "title 节未以空行终止"})
    elif geom_tier != "allcheck":
        msg = "缺少 title 节（仅 Geom=AllCheck 可省略）"
        if route_unterminated:  # G9 项 1：归因提示，不再误导为单纯缺节
            msg += "（route 未以空行终止时其后内容会并入 route）"
        errors.append({"section": "title", "line": min(i + 1, n),
                       "message": msg})

    # 电荷/多重度：title 终止空行后首个内容行
    while i < n and (blank(i) or comment(i)):
        i += 1
    if i < n:
        cm = lines[i].strip()
        i += 1
        # G5 项 1：自由格式分词（空白/逗号/斜杠任意组合）得偶数个整数——
        # 首组 charge 有符号整数、mult ≥1；后续组为 fragment 层（mult≠0，
        # 负值官方仅 Guess=Fragment 合法，宽容放行 + 佐证警告）
        toks = parse_charge_tokens(cm)
        nums: list[int] = []
        parse_ok = bool(toks) and len(toks) % 2 == 0
        if parse_ok:
            for t in toks:
                try:
                    nums.append(int(t))
                except ValueError:
                    parse_ok = False
                    break
        if parse_ok:
            blocks["charge_mult"] = " ".join(str(v) for v in nums)
            charge_line_no = i  # 1 起行号（i 已自增到下一行）
            for g in range(0, len(nums), 2):
                mult = nums[g + 1]
                if (g == 0 and mult < 1) or (g > 0 and mult == 0):
                    parse_ok = False
                    break
            if parse_ok and len(nums) > 2:
                # G6 多组电荷对佐证判定：route 含 Counterpoise/ONIOM 或分子
                # 说明含 Fragment 参数则视为有意为之，否则信息级警告。
                # 佐证按裸子串判（注释行也计入——宽松方向、无阻断风险；属
                # 佐证判定而非 route 触发词识别，不受 §7 裸子串禁令约束）。
                # len(nums) > 2 即「存在后续组」：parse_ok=True 时首组负
                # 多重度已被拒，负号佐证不再单独判定（审查整改 R11）。
                route_l = blocks["route"].casefold()
                has_evidence = ("counterpoise" in route_l
                                or "oniom" in route_l
                                or "guess=fragment" in route_l)
                mol_text = "\n".join(lines[i:n])
                if not has_evidence and "(fragment=" not in mol_text.casefold():
                    pairs = " ".join(toks)
                    warnings.append({
                        "line": charge_line_no, "keyword": pairs,
                        "kind": "molecule_multiple_charge_pairs",
                        "message": "多组电荷-多重度对通常仅用于 "
                                   "Counterpoise/ONIOM/Guess=Fragment 计算"
                                   "（route 未含相应关键字且分子说明无 "
                                   "Fragment 参数），请确认" +
                                   ("；负多重度组官方仅 Guess=Fragment 有"
                                    "语义" if any(v < 0 for v in nums[1::2])
                                    else "")})
        if not parse_ok:
            blocks["charge_mult"] = cm
            errors.append({"section": "charge_mult", "line": i,
                           "message": "电荷/多重度行无法解析（应为整数对："
                                      "首组多重度须为正整数，后续组多重度"
                                      "不得为 0；若上一节未以空行收尾，"
                                      "本行可能是误并内容）"})
    elif geom_tier != "allcheck":
        errors.append({"section": "charge_mult", "line": n,
                       "message": "缺少电荷/多重度行"})

    # 分子说明：原子定义行连续排列至终止空行（Variables:/Constants: 头即使
    # 无空行分隔也构成边界——官方测试语料常见无空行直接跟变量区的形态；
    # pbc 的 Tv 平移向量行与哑原子/鬼原子一样占行不计分子式）
    atoms: list[str] = []
    mol_start = i
    while i < n and not blank(i):
        ln = lines[i].strip()
        if ln.startswith("!"):
            i += 1
            continue
        first_tok = _tokenize_atom_line(ln)
        first = first_tok[0] if first_tok else ""
        if first.rstrip(":").casefold() in ("variables", "variable",
                                            "constants", "constant"):
            break  # 变量/常数区头（含单数形态）即原子块边界
        if first.casefold() == "tv":
            i += 1
            continue  # pbc 平移向量：非原子行，不计原子数
        atoms.append(ln)
        i += 1
    counts: dict[str, int] = {}
    for k, ln in enumerate(atoms):
        # G6：首字段按自由格式分隔取词（括号/引号感知，复用 route token
        # 管道的单行切分——保住 C(Iso=13,Fragment=2) 整词），再按官方文法
        # 分类（鬼/哑原子占一行不计分子式；无元素前缀记警告不计式）
        toks = _tokenize_atom_line(ln)
        sym, kind = _classify_atom(toks[0]) if toks else (None, "unknown")
        if kind == "element" and sym:
            counts[sym] = counts.get(sym, 0) + 1
        elif kind == "unknown":
            warnings.append({"line": mol_start + k + 1,
                             "keyword": toks[0] if toks else ln,
                             "kind": "atom_label_unknown",
                             "message": f"原子标签「{toks[0] if toks else ln}」"
                                        "找不到元素符号前缀（官方文法：元素"
                                        "符号或原子序数 + 可选标签），请确认"
                                        "拼写或元素归属"})
    blocks["molecule"]["atom_count"] = len(atoms)
    blocks["molecule"]["formula"] = _hill_formula(counts)
    if not atoms and geom_tier is None:
        # G9 项 4：电荷行后分子说明整体缺失（Geom 检查点豁免档坐标可省不报）
        errors.append({"section": "molecule", "line": min(i + 1, n),
                       "message": "缺少分子说明节（原子定义行）"})
    elif atoms and i >= n and geom_tier is None:
        # G9 项 5：原子行非空且 EOF 告终（非阻断，避免历史文件误拒）
        warnings.append({"line": mol_start + 1, "keyword": "",
                         "kind": "molecule_unterminated",
                         "message": "分子说明节未以空行终止（建议补终止空行）"})

    # 变量/常数区与附加节：其后以空行分隔的各区域
    # G4：附加节识别改由官方 Section Ordering 表驱动（prop=wrf 兼容项
    # B6 G16 实测拒绝后删除，决策点 9）
    wants_extra = section_ordering.any_trigger(blocks["route"])
    last_addl_start: int | None = None
    while i < n:
        while i < n and (blank(i) or comment(i)):
            i += 1
        if i >= n:
            break
        region_start = i
        region: list[str] = []
        while i < n and not blank(i):
            ln = lines[i].strip()
            if ln and not ln.startswith("!"):
                region.append(ln)
            i += 1
        ran_to_eof = i >= n
        head = region[0].rstrip(":").casefold() if region else ""
        var_like = False
        if head == "variables":
            blocks["molecule"]["variables_present"] = True
            var_like = True
        elif head == "constants":
            blocks["molecule"]["constants_present"] = True
            var_like = True
        elif not wants_extra and _looks_like_variables(region):
            blocks["molecule"]["variables_present"] = True
            var_like = True
        else:
            blocks["additional_sections"].append(
                {"lines": region, "terminator_blank": not ran_to_eof})
            last_addl_start = region_start
        if var_like and ran_to_eof:
            # G9 项 6：变量/常数/隐式变量区 EOF 告终（非阻断）
            warnings.append({"line": region_start + 1, "keyword": "",
                             "kind": "variables_unterminated",
                             "message": "变量/常数区未以空行终止"
                                        "（建议补终止空行）"})

    # G4 项 3：最后一个附加节以 EOF 收尾 → 官方表终止空行判定
    # （非 EOF 位置缺空行在结构上不可观测——会与下一节合并为同一 region）
    if blocks["additional_sections"] and \
            not blocks["additional_sections"][-1]["terminator_blank"]:
        if section_ordering.terminator_missing(blocks["route"]):
            errors.append({"section": "additional",
                           "line": (last_addl_start or 0) + 1,
                           "message": "附加输入节未以空行终止"})
        else:
            log.debug("附加节终止空行按官方表保守不报（混合/例外/无命中）："
                      "route=%r", route_cf)

    return {"blocks": blocks, "parse_errors": errors, "warnings": warnings,
            "multistep": multistep}


# ---------------- 节定位与重组（M2 B2/B6 共用） ----------------

def is_editable_section(name: str) -> bool:
    """节名合法性（不含 molecule——坐标不可编辑）。"""
    return name in _FIXED_SECTIONS or bool(_ADDITIONAL_RE.match(name))


def scan_spans(logical: list[str]) -> dict[str, tuple[int, int]]:
    """节内容行区间（[start, end)，不含节间空行）——公共 API（B1 审查 R5）。

    与 parse_input 同一套扫描规则（同一 blank/comment 判定与节识别顺序），
    供区间替换重组与提交前空行规约共用；molecule 相关区间
    （molecule_atoms/variables/constants/implicit_variables）仅作边界参照。
    """
    n = len(logical)

    def blank(k: int) -> bool:
        return not logical[k].strip()

    def comment(k: int) -> bool:
        return logical[k].lstrip().startswith("!")

    spans: dict[str, tuple[int, int]] = {}
    i = 0
    while i < n and (blank(i) or comment(i)):
        i += 1
    start = i
    while i < n and logical[i].lstrip().startswith("%"):
        i += 1
    if i > start:
        spans["link0"] = (start, i)
    while i < n and (blank(i) or comment(i)):
        i += 1
    if i < n and logical[i].lstrip().startswith("#"):
        start = i
        while i < n and not blank(i):
            i += 1
        spans["route"] = (start, i)
    while i < n and (blank(i) or comment(i)):
        i += 1
    start = i
    while i < n and not blank(i):
        i += 1
    if i > start:
        spans["title"] = (start, i)
    while i < n and (blank(i) or comment(i)):
        i += 1
    if i < n:
        spans["charge_mult"] = (i, i + 1)
        i += 1
    mol_start = i
    while i < n and not blank(i):
        i += 1
    spans["molecule_atoms"] = (mol_start, i)

    route = spans.get("route")
    wants_extra = (section_ordering.any_trigger(
        "\n".join(logical[route[0]:route[1]])) if route else False)
    idx = 0
    while i < n:
        while i < n and (blank(i) or comment(i)):
            i += 1
        if i >= n:
            break
        start = i
        while i < n and not blank(i):
            i += 1
        region = [logical[k].strip() for k in range(start, i)
                  if logical[k].strip() and not logical[k].strip().startswith("!")]
        head = region[0].rstrip(":").casefold() if region else ""
        if head == "variables":
            spans["variables"] = (start, i)
        elif head == "constants":
            spans["constants"] = (start, i)
        elif not wants_extra and _looks_like_variables(region):
            spans["implicit_variables"] = (start, i)
        else:
            spans[f"additional-{idx}"] = (start, i)
            idx += 1
    return spans


def reassemble(text: str, section: str, lines: list[str]) -> str:
    """区间替换重组（m2-plan §2.1 ②）：只替换目标节内容行，其余字节原样
    保留（含行尾风格——不做换行转换）；目标节末尾按不变式规约恰好一个
    空行（link0 除外：其后字节不动、不加空行）。

    目标节在文中不存在（含 additional-<n> 越界）抛 KeyError。
    """
    eol = "\r\n" if "\r\n" in text else "\n"
    logical = text.split(eol)
    if logical and logical[-1] == "":  # 结尾换行符的切分产物不是内容行
        logical.pop()
    spans = scan_spans(logical)
    if section not in spans:
        raise KeyError(section)
    content = list(lines)
    while content and not content[0].strip():  # 节内容不含边界空行
        content.pop(0)
    while content and not content[-1].strip():
        content.pop()
    start, end = spans[section]
    if section in ("link0", "charge_mult"):
        # link0 其后不加空行；charge_mult 是分子说明节首行（其后直接跟原子
        # 定义行，节终止空行在原子块之后）——两者替换后其后字节原样保留
        rebuilt = logical[:start] + content + logical[end:]
    else:
        j = end
        while j < len(logical) and not logical[j].strip():
            j += 1  # 原空行带规约为恰好一个空行
        rebuilt = logical[:start] + content + [""] + logical[j:]
    out = eol.join(rebuilt)
    if text.endswith(eol):
        out += eol
    return out


_CHARGE_MULT_LINE_RE = re.compile(r"^-?\d+[ ,]+\d+$")
_MULTI_STRUCTURE_RE = re.compile(r"qst[23]\b")


def verify_and_normalize(text: str) -> dict:
    """提交前输入核验的规范化（m2-plan §2.5 ①②）。

    ① 全文件换行规范化（\\r\\n、孤立 \\r → \\n）；
    ② 空行规约：除 link0 外每节末尾恰好一个空行（含文件末节与文件末尾），
       link0 之后不加空行；只动节边界空行带（注释行原位保留），节内容与
       分子节内部不动；charge_mult 与原子定义行之间不插空行（分子说明节
       连续，终止空行在原子块之后）。
       多结构例外（§2.7，2026-09-29 本机 G16 实测）：route 含 QST2/QST3 时，
       分子说明节与「首行为电荷/多重度整数对」的附加节（即下一套结构）之间
       规约为恰好两个空行——部分发行版 G16 对单空行紧邻的后续结构会误并单行
       读取报 End of file in ZSymb。

    返回 {"text", "changed"}；解析校验（③④）由调用方执行。
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    logical = split_lines(normalized)
    spans = scan_spans(logical)
    keys = list(spans)
    if not keys:
        return {"text": normalized, "changed": normalized != text}
    route_span = spans.get("route")
    route_cf = "\n".join(logical[route_span[0]:route_span[1]]).casefold() \
        if route_span else ""
    multi_structure = _MULTI_STRUCTURE_RE.search(route_cf) is not None
    out = list(logical[:spans[keys[0]][0]])  # 前导空行/注释原样
    for idx, key in enumerate(keys):
        start, end = spans[key]
        out.extend(logical[start:end])
        last = idx + 1 == len(keys)
        gap_end = spans[keys[idx + 1]][0] if not last else len(logical)
        gap = logical[end:gap_end]
        out.extend(ln for ln in gap
                   if ln.strip() and ln.lstrip().startswith("!"))
        # link0 之后不加空行；charge_mult 直连原子定义行（分子说明节内部）
        if key in ("link0", "charge_mult") or last:
            continue
        sep = 1
        if multi_structure and keys[idx + 1].startswith("additional-"):
            n_start, n_end = spans[keys[idx + 1]]
            first = next((ln for ln in logical[n_start:n_end] if ln.strip()
                          and not ln.lstrip().startswith("!")), "")
            if _CHARGE_MULT_LINE_RE.match(first.strip()):
                sep = 2  # §2.7 多结构例外：下一套结构的电荷行前须双空行
        out.extend([""] * sep)
    body = "\n".join(out)
    if keys[-1] == "link0":  # 末节为 link0：其后不加空行，仅保留原结尾换行
        new_text = body + ("\n" if normalized.endswith("\n") else "")
    else:
        new_text = body + "\n\n" if body else body  # 文件末尾恰一空行
    return {"text": new_text, "changed": new_text != text}
