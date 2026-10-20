"""审计工具 warn/review 过滤层谓词测试（B6 审查整改 R1，先行红）。

R1（input-verify-gap-b6-code-review.md §三）：warn_candidates.json（1262）
→ review_candidates.json（475）过渡层谓词原先未入库，独立复核不可复现。
整改将两层脚本化入 audit_prose_options.py：

- warn 层：G8 判定链（check_route_options）复过滤——保留实际产生
  route_option_unknown 的形态（键不在典/键无选项集/唯一前缀判活/值形
  白名单者零警告，不入复核面）；
- review 层：warn 形态中，非 P2-only（有字面「键=选项」或语料命中证据）
  直接保留；P2-only 形态的宿主条目抓取上下文（snippet 拼接，casefold）
  含选项语义词根 synonym / says to / default / option / keyword 之一者
  保留，其余为纯散文普通词提及归因排除（excluded_candidates.json）。

谓词与 B6 历史产物（B5 时点判定链 + B5 词典）精确分割：401/401 保留、
0/787 误排；复现程序见 docs/plans/input-verify-gap-b6-prose-audit.md §9。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_prose_options.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("audit_prose_options", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------- review 层谓词 ----------------

def test_review_layer_keeps_literal_and_corpus_evidence():
    """非 P2-only 形态（字面/语料证据）无论 snippet 如何一律保留。"""
    mod = _load_mod()
    warn = [
        {"key": "opt", "option": "addredundant", "sources": ["path1_literal"]},
        {"key": "freq", "option": "nnroa", "sources": ["path3_corpus"]},
        {"key": "cphf", "option": "sg1", "sources": ["path2_prose", "path3_corpus"]},
    ]
    p2 = []
    review, excluded = mod.review_layer(warn, p2)
    assert [e["option"] for e in review] == ["addredundant", "nnroa", "sg1"]
    assert excluded == []


def test_review_layer_p2_only_anchor_word_roots():
    """P2-only 形态按 snippet 五词根锚分割：含任一词根保留，全无则排除。"""
    mod = _load_mod()
    anchors = {
        "synonyms": "AddRedundant is synonymous with ModRedundant",
        "says": "NNROA says to use the numerical ROA method",
        "default": "The default is NoBandGap",
        "option": "This option only affects excited states",
        "keyword": "via the keyword may be used",
    }
    warn = [{"key": "k", "option": o, "sources": ["path2_prose"]}
            for o in anchors]
    p2 = [{"key": "k", "option": o, "snippets": {"k#e": text}}
          for o, text in anchors.items()]
    review, excluded = mod.review_layer(warn, p2)
    assert {e["option"] for e in review} == set(anchors)
    assert excluded == []


def test_review_layer_excludes_plain_prose_without_anchor():
    """P2-only 无词根锚（纯散文普通词提及）排除并附机械归因。"""
    mod = _load_mod()
    warn = [{"key": "admp", "option": "cartesian", "sources": ["path2_prose"]}]
    p2 = [{"key": "admp", "option": "cartesian",
           "snippets": {"admp#Read":
                        "Read initial Cartesian velocities from the input stream."}}]
    review, excluded = mod.review_layer(warn, p2)
    assert review == []
    assert len(excluded) == 1
    assert excluded[0]["option"] == "cartesian"
    assert excluded[0]["reason"]  # 机械归因非空


def test_review_layer_anchor_casefold_and_multi_snippet():
    """词根匹配大小写不敏感，多条目 snippet 拼接后命中即保留。"""
    mod = _load_mod()
    warn = [
        {"key": "k", "option": "upper", "sources": ["path2_prose"]},
        {"key": "k", "option": "second", "sources": ["path2_prose"]},
    ]
    p2 = [
        {"key": "k", "option": "upper",
         "snippets": {"k#E": "The Default is Upper"}},
        {"key": "k", "option": "second",
         "snippets": {"k#A": "plain prose only", "k#B": "mentions Keyword"}},
    ]
    review, excluded = mod.review_layer(warn, p2)
    assert {e["option"] for e in review} == {"upper", "second"}
    assert excluded == []


def test_review_layer_funnel_closure():
    """漏斗闭合：review ∪ excluded = warn，且二者不相交。"""
    mod = _load_mod()
    warn = [
        {"key": "a", "option": "keep1", "sources": ["path1_literal"]},
        {"key": "a", "option": "keep2", "sources": ["path2_prose"]},
        {"key": "b", "option": "drop1", "sources": ["path2_prose"]},
        {"key": "b", "option": "drop2", "sources": ["path2_prose"]},
    ]
    p2 = [
        {"key": "a", "option": "keep2", "snippets": {"a#E": "a synonym list"}},
        {"key": "b", "option": "drop1", "snippets": {"b#E": "plain text"}},
        {"key": "b", "option": "drop2", "snippets": {"b#E": "more plain text"}},
    ]
    review, excluded = mod.review_layer(warn, p2)
    rk = {(e["key"], e["option"]) for e in review}
    ek = {(e["key"], e["option"]) for e in excluded}
    wk = {(e["key"], e["option"]) for e in warn}
    assert rk | ek == wk
    assert not rk & ek


# ---------------- warn 层（G8 判定链复过滤） ----------------

def test_warn_layer_keeps_only_chain_warning_forms():
    """warn 层保留实际产生 route_option_unknown 的形态：
    键无选项集/唯一前缀判活/键不在典者零警告排除。"""
    mod = _load_mod()
    words = frozenset({"opt", "opt=calcfc", "opt=ts", "opt=modredundant"})
    merged = [
        {"key": "opt", "option": "xyzzy", "sources": ["path2_prose"]},
        {"key": "opt", "option": "calcfc", "sources": ["path1_literal"]},
        {"key": "opt", "option": "modredun", "sources": ["path3_corpus"]},
        {"key": "nosuchkey", "option": "xyzzy", "sources": ["path2_prose"]},
    ]
    kept = mod.warn_layer(merged, words)
    assert [(e["key"], e["option"]) for e in kept] == [("opt", "xyzzy")]
