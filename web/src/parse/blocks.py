"""Gaussian 输入分块解析（roadmap §2.7 节结构与空行规则）。

产出与契约 InputPreview.blocks 逐字段一致的分块结构 + parse_errors（逐节容错）
+ multistep 标记；预览（尽力而为）与导入校验（严格，B3）共用。
解析器自身绝不抛异常：坏文件回落默认分块并以 parse_errors 标注。
"""
from __future__ import annotations

import re

# 附加输入节触发的 route 关键词（小写子串匹配，覆盖常见读取类节）
_EXTRA_KEYWORDS = ("gen", "modredundant", "guess=alter", "scrf=read",
                   "pop=nbo", "prop=wrf")

# 可编辑节名（契约 PUT blocks/{section}；molecule 与未知节名不可编辑）
_FIXED_SECTIONS = ("link0", "route", "title", "charge_mult")
_ADDITIONAL_RE = re.compile(r"additional-\d+$")

_REQUIRED_BLOCKS = {"link0", "route", "title", "charge_mult", "molecule",
                    "additional_sections"}


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


def _atom_symbol(tok: str) -> str | None:
    """原子行首 token → 规范元素符号；无法识别返回 None。

    元素符号（可带尾部数字标签，如 C1）归一为首字母大写；纯数字按
    原子序数映射，超界序数不识别（容错不抛异常）。"""
    name = tok.rstrip("0123456789")
    if name.isalpha():
        return name.capitalize()
    if tok.isdigit() and 1 <= int(tok) <= len(_ELEMENTS):
        return _ELEMENTS[int(tok) - 1]
    return None


def _split_lines(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":  # 末尾换行符的切分产物不是空行
        lines.pop()
    return lines


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


def parse_input(text: str) -> dict:
    """解析输入文本 → {"blocks": …, "parse_errors": […], "multistep": bool}。"""
    lines = _split_lines(text)
    errors: list[dict] = []

    # 多步任务：解析在首个 --Link1-- 处截断，仅覆盖第一步
    stop = next((k for k, ln in enumerate(lines)
                 if ln.strip().casefold() == "--link1--"), None)
    multistep = stop is not None
    if multistep:
        errors.append({"section": "link1", "line": stop + 1,
                       "message": "多步任务（--Link1--）不支持"})
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
    while i < n and lines[i].lstrip().startswith("%"):
        blocks["link0"]["lines"].append(lines[i].strip())
        i += 1
    low = [ln.casefold() for ln in blocks["link0"]["lines"]]
    # 核资源已声明的判定：%nproc 前缀超集覆盖 %NProcShared 与早期同义 %NProc、
    # 实测可用的 %nprocshare 截断形式（%NProc 同义性见手册 %CPU 条目 replaces
    # the earlier %NProcShared and %NProc）；%CPU=proc-list 为现行推荐，语义是
    # 绑定具体逻辑处理器（0,1,2 / 0-5 / 混合，gaussian.com/run），与 %nproc
    # 的分配核数语义并行不混同，任一存在即不告警。%Mem 带 % 前缀防 chk 行误判。
    blocks["link0"]["missing"] = [
        nm for nm, pats in (("NProcShared", ("%nproc", "%cpu")),
                            ("Mem", ("%mem",)))
        if not any(p in ln for ln in low for p in pats)]

    # Route：# 行起连续非空行，终止空行必需
    while i < n and (blank(i) or comment(i)):
        i += 1
    route_lines: list[str] = []
    if i < n and lines[i].lstrip().startswith("#"):
        while i < n and not blank(i):
            route_lines.append(lines[i].rstrip())
            i += 1
    else:
        errors.append({"section": "route", "line": min(i + 1, n),
                       "message": "缺少 route 节（# 开头）"})
    blocks["route"] = "\n".join(route_lines)
    route_cf = blocks["route"].casefold()
    geom_checkpoint = ("geom=allcheck" in route_cf
                       or "geom=checkpoint" in route_cf)

    # Title：终止空行后连续非空行，至多 5 行（§2.7）
    while i < n and (blank(i) or comment(i)):
        i += 1
    title_lines: list[str] = []
    while i < n and not blank(i):
        title_lines.append(lines[i].strip())
        i += 1
    if title_lines:
        if len(title_lines) > 5:
            errors.append({"section": "title", "line": i - len(title_lines) + 1,
                           "message": "title 节超过 5 行"})
        blocks["title"] = "\n".join(title_lines)
    elif not geom_checkpoint:
        errors.append({"section": "title", "line": min(i + 1, n),
                       "message": "缺少 title 节（仅 Geom=AllCheck/Checkpoint 合法）"})

    # 电荷/多重度：title 终止空行后首个内容行
    while i < n and (blank(i) or comment(i)):
        i += 1
    if i < n:
        cm = lines[i].strip()
        i += 1
        parts = cm.replace(",", " ").split()
        try:
            blocks["charge_mult"] = f"{int(parts[0])} {int(parts[1])}"
        except (IndexError, ValueError):
            blocks["charge_mult"] = cm
            errors.append({"section": "charge_mult", "line": i,
                           "message": "电荷/多重度行无法解析（应为两个整数）"})
    elif not geom_checkpoint:
        errors.append({"section": "charge_mult", "line": n,
                       "message": "缺少电荷/多重度行"})

    # 分子说明：原子定义行连续排列至终止空行
    atoms: list[str] = []
    while i < n and not blank(i):
        ln = lines[i].strip()
        if ln and not ln.startswith("!"):
            atoms.append(ln)
        i += 1
    counts: dict[str, int] = {}
    for ln in atoms:
        sym = _atom_symbol(ln.split()[0])
        if sym:
            counts[sym] = counts.get(sym, 0) + 1
    blocks["molecule"]["atom_count"] = len(atoms)
    blocks["molecule"]["formula"] = _hill_formula(counts)

    # 变量/常数区与附加节：其后以空行分隔的各区域
    wants_extra = any(kw in route_cf for kw in _EXTRA_KEYWORDS)
    while i < n:
        while i < n and (blank(i) or comment(i)):
            i += 1
        if i >= n:
            break
        region: list[str] = []
        while i < n and not blank(i):
            ln = lines[i].strip()
            if ln and not ln.startswith("!"):
                region.append(ln)
            i += 1
        ran_to_eof = i >= n
        head = region[0].rstrip(":").casefold() if region else ""
        if head == "variables":
            blocks["molecule"]["variables_present"] = True
        elif head == "constants":
            blocks["molecule"]["constants_present"] = True
        elif not wants_extra and _looks_like_variables(region):
            blocks["molecule"]["variables_present"] = True
        else:
            blocks["additional_sections"].append(
                {"lines": region, "terminator_blank": not ran_to_eof})

    return {"blocks": blocks, "parse_errors": errors, "multistep": multistep}


# ---------------- 节定位与重组（M2 B2/B6 共用） ----------------

def is_editable_section(name: str) -> bool:
    """节名合法性（不含 molecule——坐标不可编辑）。"""
    return name in _FIXED_SECTIONS or bool(_ADDITIONAL_RE.match(name))


def _scan_spans(logical: list[str]) -> dict[str, tuple[int, int]]:
    """节内容行区间（[start, end)，不含节间空行）。

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
    route_cf = "\n".join(logical[route[0]:route[1]]).casefold() if route else ""
    wants_extra = any(kw in route_cf for kw in _EXTRA_KEYWORDS)
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
    spans = _scan_spans(logical)
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
    logical = _split_lines(normalized)
    spans = _scan_spans(logical)
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
