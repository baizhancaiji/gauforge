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
                       "MP4 类意外结果），请确认是否 intended"})
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


def check_route_spelling(route_text: str, *, cutoff: float = 0.8,
                         dictionary: frozenset[str] | None = None,
                         line_offset: int = 0) -> list[dict]:
    """route 节关键词拼写检查（非阻断，m2-plan §2.1 定稿；B1 换 token 管道）。

    先走 token_in_dict 精确命中（整词/键名/括号形/@豁免），未命中且与某
    词典条目接近（difflib.get_close_matches cutoff=0.80）→ kind=keyword_spell
    + 首个近邻 suggestion；纯新词（无近邻）不警告——方法学与基组不在字典，
    「未收录即警告」会使检查失效。line 为 route 节内行号（1 起）+
    line_offset（分块保存传 route 起始行号换算的全文件偏移）。
    """
    words = dictionary if dictionary is not None else load_keywords()
    if not words or not route_text:
        return []
    ordered = sorted(words)  # 排序保证近邻并列时结果确定
    out: list[dict] = []
    for line_no, tok in tokenize_route(route_text):
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
