"""route 关键词字典加载、token 化与拼写检查（m2-plan B1/B2；B1 C3 换管道）。

字典文件 web/src/parse/keywords.txt 由 scripts/extract_keywords.py 从
gaussian-kb 结构化知识库生成（纳入版本管理、可重生成）；进程内缓存一次，
缺失时降级为空集（拼写检查零警告）并记日志，不阻断保存。

token 化管道（输入勘误计划 §2.3 C3，官方 input 页 Syntax Rules）：
括号/引号感知切分——括号深度为 0 处空白/逗号/斜杠/# 为分隔符，深度 >0
保留（6-31g(d,p)、IOp(6/50=1) 整词）；双引号内不切分
（External="RunTink Amber"）；行内首个引号外且括号外的 ! 起截断注释
（括号/引号内的 ! 属值的一部分，与官方「注释任意处」的取舍登记于
input-verify-gap-b1-review R3）；@ 开头 token 豁免（@file 整文件包含，
含 /N 抑制回显后缀）；裸 = 与相邻 token 粘合（= 两侧允许任意空格），
键名与 ( 之间有空格的 key (…) 形同样合并。该管道是 C3/G4/G8 共用基座。
"""
from __future__ import annotations

import difflib
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

DICT_PATH = Path(__file__).resolve().parent / "keywords.txt"

_cache: frozenset[str] | None = None


def load_keywords(path: Path | None = None, *,
                  refresh: bool = False) -> frozenset[str]:
    """读入关键词全集（小写）；缺失降级为空集。"""
    global _cache
    if _cache is not None and not refresh and path is None:
        return _cache
    target = path if path is not None else DICT_PATH
    try:
        words = frozenset(
            w for w in target.read_text(encoding="utf-8").splitlines() if w)
    except OSError:
        log.warning("关键词字典缺失（%s）：拼写检查降级为零警告", target)
        words = frozenset()
    if path is None:
        _cache = words
    return words


# ---------------- token 化管道（C3 公共基座） ----------------

# 深度为 0 时的行内分隔符：空白、逗号、斜杠、#（官方任意组合）
_SEP_CHARS = ",/#"

# @file 的 /N 抑制回显后缀：/ 后紧跟数字、数字后为行尾或分隔符
_AT_SUFFIX_N = re.compile(r"\d+(?=$|[\s,/#])")


def _tokenize_line(line: str) -> list[str]:
    """单物理行 → token 序列（括号/引号感知；首个引号外 ! 起截断）。

    引号内与括号深度 >0 处的空白/逗号/斜杠/#/! 均不切分（值为整体，
    如 External="RunTink Amber"、6-31g(d,p)、IOp(6/50=1)、opt(ca!lcfc)）。"""
    depth = 0
    in_quote = False
    cut = len(line)
    for idx, ch in enumerate(line):
        if in_quote:
            if ch == '"':
                in_quote = False
            continue
        if ch == '"':
            in_quote = True
        elif depth == 0 and ch == "!":
            cut = idx
            break
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
    head = line[:cut]
    toks: list[str] = []
    cur: list[str] = []
    depth = 0
    in_quote = False
    for j, ch in enumerate(head):
        if in_quote:
            cur.append(ch)
            if ch == '"':
                in_quote = False
            continue
        if ch == '"':
            cur.append(ch)
            in_quote = True
            continue
        if depth == 0 and (ch.isspace() or ch in _SEP_CHARS):
            if (ch == "/" and cur and cur[0] == "@"
                    and _AT_SUFFIX_N.match(head, j + 1)):
                cur.append(ch)  # @file/N 抑制回显后缀并入 @ token
                continue
            if cur:
                toks.append("".join(cur))
                cur = []
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        cur.append(ch)
    if cur:
        toks.append("".join(cur))
    return toks


def _is_bare_word(tok: str) -> bool:
    """纯词 token（无括号/等号/斜杠）：可与其后 (…) 括号 token 合并。"""
    return bool(tok) and all(c.isalnum() for c in tok)


def _merge_pairs(pairs: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """裸 = 粘合与 key (…) 合并：opt = (calcfc, ts) → opt=(calcfc, ts)，
    opt (calcfc, ts) → opt(calcfc, ts)；行号取关键字所在物理行。"""
    out: list[tuple[int, str]] = []
    pending_eq = False
    for ln, tok in pairs:
        if tok == "=":
            if out:
                pl, pt = out.pop()
                out.append((pl, pt + "="))
                pending_eq = True
            else:
                out.append((ln, tok))
            continue
        if pending_eq and out:
            pl, pt = out.pop()
            out.append((pl, pt + tok))
            pending_eq = False
            continue
        if (tok.startswith("(") and out and not pending_eq
                and _is_bare_word(out[-1][1])):
            pl, pt = out.pop()
            out.append((pl, pt + tok))
            continue
        out.append((ln, tok))
        pending_eq = False
    return out


def tokenize_route(route_text: str) -> list[tuple[int, str]]:
    """route 节文本 → [(物理行号 1 起, token), …]。

    括号/引号感知切分 + 裸 = 粘合 + key (…) 合并（见模块 docstring）；
    同一物理行的 token 携带该行行号（跨行粘合取关键字所在行）。
    """
    pairs: list[tuple[int, str]] = []
    for ln, line in enumerate(route_text.split("\n"), start=1):
        pairs.extend((ln, t) for t in _tokenize_line(line))
    return _merge_pairs(pairs)


def token_head(tok: str) -> str:
    """token → 关键字头部（首个 ( 或 = 前，去尾 =、casefold）。

    opt=(calcfc,ts) → opt；geom=allcheck → geom；gen → gen；
    iop(6/50=1) → iop（B2 G4 触发词判定与 G2 重复检测共用的头部口径）。"""
    t = tok.strip()
    p = t.find("(")
    head = t[:p] if p > 0 else t.partition("=")[0]
    return head.rstrip("=").strip().casefold()


def token_options(tok: str) -> frozenset[str]:
    """token → 选项集（casefold、strip；裸 token 为空集）。

    括号形按逗号切分（iop(6/50=1) 括号内无逗号整体保留为 {'6/50=1'}）；
    = 取值形取值为单项；scrf=(solvent=water,read) → {'solvent=water','read'}。"""
    t = tok.strip()
    p = t.find("(")
    if p > 0:
        inner = t[p:].lstrip("(").rstrip(")")
        items = inner.split(",")
    else:
        _, sep, val = t.partition("=")
        items = [val] if sep else []
    return frozenset(s.strip().casefold() for s in items if s.strip())


# 容器头白名单（G2，官方允许追加取值的关键字——裸形与选项形并出不告警；
# IOp 文法为多条目取值列表并列取值语义，同豁免；白名单外头部重复即警告）
_CONTAINER_HEADS = frozenset((
    "opt", "freq", "scrf", "geom", "guess", "pop", "irc", "td", "nmr",
    "prop", "cas", "cphf", "ept", "output", "charge", "iop"))


def check_route_duplicates(route_text: str, *,
                           line_offset: int = 0) -> list[dict]:
    """route 重复关键字检测（G2，非阻断 warnings）。

    token 头部聚合后按 §2.6 判定表：同头部 ≥2 次时——
    - 均裸形 → 警告 route_duplicate（官方 testrt 自认盲区：重复 MP2 跑成 MP4）；
    - 容器头白名单内（opt/freq/scrf/geom/guess/pop/irc/td/nmr/prop/cas/
      cphf/ept/output/charge/iop）裸形 + 选项形并出 → 豁免（官方允许的
      追加取值；B3 G16 冒烟待确认，证实裸形被拒则回退为警告）；
    - 同头部两个非空选项集 → 警告；
    - iop 两个取值 token 并写 → 豁免（多条目取值列表）。
    白名单外头部只要重复即警告。line 为 route 节内行号 + line_offset。

    组合场景口径（审查整改 R7 登记）：判定表只定义「全裸 / 裸+选项混合 /
    全选项」三态，「1 裸形 + 多个选项形」（freq freq=readfcht
    freq=readanharmonic）按混合公式整体豁免（bare≥1 ∧ valued≥1）——追加
    取值语义对选项形个数不设限；仅「0 裸形 + ≥2 选项形」仍按判定表警告。
    """
    if not route_text.strip():
        return []
    groups: dict[str, list[tuple[int, str, frozenset[str]]]] = {}
    for line_no, tok in tokenize_route(route_text):
        head = token_head(tok)
        if not head or head.startswith("@"):
            continue
        groups.setdefault(head, []).append(
            (line_no, tok, token_options(tok)))
    out: list[dict] = []
    for head, hits in groups.items():
        if len(hits) < 2:
            continue
        bare = sum(1 for _, _, opts in hits if not opts)
        valued = len(hits) - bare
        # 白名单容器头「裸形 + 选项形」混合 = 官方允许的追加取值；同头部
        # 两个裸形或两个非空选项集仍警告；iop 多条目取值并列恒豁免
        exempt = (head == "iop"
                  or (head in _CONTAINER_HEADS and bare >= 1 and valued >= 1))
        if exempt:
            continue
        first_line = hits[0][0]
        names = "、".join(t for _, t, _ in hits[:3])
        out.append({
            "line": first_line + line_offset, "keyword": head,
            "kind": "route_duplicate",
            "message": f"route 中关键字「{head}」出现 {len(hits)} 次"
                       f"（{names}），官方 testrt 不检测重复（重复 MP2 会跑成"
                       "MP4 类意外结果），请确认是否有意为之"})
    return out


def token_in_dict(tok: str, words: frozenset[str]) -> bool:
    """token 词典命中判定（精确匹配，不近似；缩写不识别——输入勘误计划
    决策点 5）：整词命中 ∨ key=value 键名命中且值非空 ∨ kw(opt)/kw=(opt)
    括号形键名命中且括号内容非空（iop(6/50=1) 含 = 的括号值按 ( 前头部
    取键）；@ 开头 token 豁免（@file 整文件包含）。
    """
    t = tok.strip()
    if not t or t.startswith("@"):
        return True
    cf = t.casefold()
    if cf in words:
        return True
    p = t.find("(")
    if p > 0:
        head = t[:p].strip()
        if head.endswith("="):
            head = head[:-1]
        return head.casefold() in words and t[p:].strip() != "()"
    key, sep, val = t.partition("=")
    return bool(sep) and bool(val.strip()) and key.strip().casefold() in words


# ---------------- G8 子选项归属判定（B5） ----------------

# 值形关键字白名单：括号内容为数值/模型化学组合/命令串，不做选项查典
# （IOp(6/50=1) 取值列表、ONIOM(B3LYP/6-31G(d):AM1:UFF) 模型化学、
# External="RunTink Amber" 命令名、Field=Z-100/XXYZ-20 场向量取值——
# field.md「Field=XXYZ-20 applies the indicated hexadecapole field」，
# B6 三路差集审计新发现，warn 级宁漏勿误，§2.9）。
# iop 成员实际不判活：IOp(6/50=1) 按 = 拆键得 iop(6/50（含括号），键名
# 不在典即零警告；成员保留为键名恰为裸 iop 时的防御。
_VALUE_FORM_HEADS = frozenset(("iop", "oniom", "external", "field"))

# 选项基名的尾部参数括号剥离（如 window(13,-12) → window）；仅剥参数，
# 不回查括号内。td=window(…) 系 G03 时代 TD/CIS 选项，G16 手册 TD/CIS 页
# 均无 Window——A 类旧形态（决策点 11：预期警告，语料 7 条），不入典
# （B6 G10-b 词典扩面口径：A 类判归形态不因扩面消除）。
_PAREN_TAIL = re.compile(r"\([^)]*\)")


def _split_key_options(tok: str) -> tuple[str | None, str]:
    """含选项 token → (键名 casefold, 选项区文本)；裸 token → (None, "")。

    括号选项形 kw(...) / kw=(...)（= 缺省或紧邻 ( 之前）取最外层括号内
    文本；= 取值形取值段（= 与 ( 之间有键外字符或无括号，值可再含括号，
    如 td=window(13,-12)）。"""
    t = tok.strip()
    if not t:
        return None, ""
    p = t.find("(")
    eq = t.find("=")
    if p > 0 and (eq < 0 or p == eq + 1):
        close = t.rfind(")")
        return (t[:p].rstrip("=").strip().casefold(),
                t[p + 1:close] if close > p else t[p + 1:])
    if eq > 0:
        return t[:eq].strip().casefold(), t[eq + 1:]
    return None, ""


def _key_options(key: str, words: frozenset[str]) -> frozenset[str]:
    """键的官方选项基名集（词典 键=* 组合词条目，带值条目剥值归一）。

    无组合词条目 → 空集：该键非选项型（基组/方法括号形如 6-31g(d,p)、
    mp4(sdtq)、纯值形），不做选项查典。"""
    prefix = key + "="
    return frozenset(
        w[len(prefix):].partition("=")[0]
        for w in words if w.startswith(prefix) and len(w) > len(prefix))


def _split_option_items(inner: str) -> list[str]:
    """选项区文本 → 顶层逗号切分的选项序列（括号深度感知，保留原文）。"""
    out: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in inner:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [s.strip() for s in out if s.strip()]


def _option_unknowns(tok: str, line: int, words: frozenset[str],
                     cutoff: float) -> list[dict]:
    """单 token 逐选项判定：未命中官方选项集的选项记 route_option_unknown。

    判定链（全部通过则零警告）：键在典 → 非值形白名单 → 该键为选项型
    （典有 键=* 组合词）→ 逐选项：键=基名 组合词在典（带值/嵌套一层取值
    剥值归一）∨ 纯数字取值（temp=300 类值形）∨ 单字母基名（官方选项名
    ≥2 字符——面⑤提取同规；ccsd(t) 微扰阶标记）∨ 该键选项集内唯一前缀
    （官方最短唯一缩写，Syntax Rules「All keywords and options may be
    shortened to their shortest unique abbreviation」；键内歧义前缀不判活
    ——B6 G16 冒烟实测：freq=readanh 因 readanharm/readanharmonic 歧义被
    G16 拒绝（警告正确），scf=conv 歧义却被 G16 接受（B5「拒绝」系推断
    错误）——词典口径对后者偏保守，登记 §2.12 已知限制）。
    未命中者近邻于该键选项集附 suggestion。"""
    key, inner = _split_key_options(tok)
    if key is None or not key or key not in words \
            or key in _VALUE_FORM_HEADS:
        return []
    opts = _key_options(key, words)
    if not opts:
        return []
    ordered = sorted(opts)
    out: list[dict] = []
    for item in _split_option_items(inner):
        base = _PAREN_TAIL.sub("", item.partition("=")[0]).strip().casefold()
        if not base or f"{key}={base}" in words or base.isdigit():
            continue
        if len(base) < 2:
            continue
        if sum(1 for o in opts if o.startswith(base)) == 1:
            continue  # 官方最短唯一缩写
        near = difflib.get_close_matches(base, ordered, n=1, cutoff=cutoff)
        w: dict = {
            "line": line, "keyword": item, "kind": "route_option_unknown",
            "message": f"「{item}」疑似非 {key.upper()} 的官方选项"
                       f"（「{key}」的官方选项集中无「{base}」，"
                       "请对照手册确认）"}
        if near:
            w["suggestion"] = near[0]
        out.append(w)
    return out


def check_route_options(route_text: str, *, cutoff: float = 0.8,
                        dictionary: frozenset[str] | None = None,
                        line_offset: int = 0) -> list[dict]:
    """route 子选项归属校验（G8，非阻断 warnings；决策点 6：仅 warn）。

    面⑤组合词覆盖非全量，误报不阻断；enforce 化前置覆盖率评估另批立项。
    line 为 route 节内行号 + line_offset（分块保存传 route 起始行换算的
    全文件偏移）。"""
    words = dictionary if dictionary is not None else load_keywords()
    if not words or not route_text:
        return []
    out: list[dict] = []
    for line_no, tok in tokenize_route(route_text):
        t = tok.strip()
        if not t or t.startswith("@"):
            continue
        out.extend(
            _option_unknowns(tok, line_no + line_offset, words, cutoff))
    return out


def check_route_spelling(route_text: str, *, cutoff: float = 0.8,
                         dictionary: frozenset[str] | None = None,
                         line_offset: int = 0) -> list[dict]:
    """route 节关键词拼写检查（非阻断，m2-plan §2.1 定稿；B1 换 token 管道，
    B5 选项化——含选项 token 交 G8 逐选项判定）。

    含选项 token（键在典、值形白名单外、键为选项型）跳过——其警告职责
    单点归 check_route_options（G8 逐选项判定），本函数不再做整词近邻
    （B1 C3 键名命中消除 opt=(calcfc,ts) 误报的口径延伸）；其余 token 先
    走 token_in_dict 精确
    命中（整词/键名/括号形/@豁免），未命中且与某词典条目接近
    （difflib.get_close_matches cutoff=0.80）→ kind=keyword_spell + 首个
    近邻 suggestion；纯新词（无近邻）不警告——方法学与基组不在字典，
    「未收录即警告」会使检查失效。line 为 route 节内行号（1 起）+
    line_offset（分块保存传 route 起始行号换算的全文件偏移）。
    """
    words = dictionary if dictionary is not None else load_keywords()
    if not words or not route_text:
        return []
    ordered = sorted(words)  # 排序保证近邻并列时结果确定
    out: list[dict] = []
    for line_no, tok in tokenize_route(route_text):
        key, _ = _split_key_options(tok)
        if (key is not None and key in words
                and key not in _VALUE_FORM_HEADS
                and _key_options(key, words)):
            continue
        if token_in_dict(tok, words):
            continue
        near = difflib.get_close_matches(tok.casefold(), ordered, n=1,
                                         cutoff=cutoff)
        if near:
            out.append({
                "line": line_no + line_offset, "keyword": tok,
                "kind": "keyword_spell",
                "message": f"「{tok}」疑似拼写错误，是否意为「{near[0]}」",
                "suggestion": near[0]})
    return out
