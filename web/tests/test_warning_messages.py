"""warnings 逐 kind message 中文警告语模板断言（B9 G13 文案口径）。

§2.16 文案修订②：警告 message 一律为中文警告语（关键字名、选项名、单位
等术语保留原文；kind 字样系机器通道标识，不得进入 message 文案）。本文件
即「逐 kind message 模板清单」：每 kind 至少一个产警告样例，断言 message
含 CJK 且命中模板短语——模板措辞变更须在此同步登记（随批留痕口径）。
"""
from __future__ import annotations

import re

import pytest

from web.src.parse.blocks import parse_input
from web.src.parse.keywords import (
    check_route_duplicates,
    check_route_options,
    check_route_spelling,
)
from web.src.parse.link0_rules import check_link0_lines

_CJK = re.compile(r"[\u4e00-\u9fff]")

# openapi Warning.kind 权威词表（12 kind，扩容须同步本清单）
KIND_VOCABULARY = frozenset((
    "keyword_spell", "route_duplicate", "route_option_unknown",
    "molecule_unterminated", "variables_unterminated",
    "link0_value_invalid", "link0_line_too_long",
    "link0_directive_unknown", "link0_directive_duplicate",
    "title_forbidden_char", "atom_label_unknown",
    "molecule_multiple_charge_pairs",
))


def _parse_warnings(text: str) -> list[dict]:
    return parse_input(text)["warnings"]


def _file(route: str, *, title: str = "t", charge: str = "0 1",
          molecule: str = "O 0 0 0", tail: str = "\n") -> str:
    """最小合法输入样板（Link0 齐全，杜绝无关警告干扰按 kind 过滤）。"""
    return (f"%mem=1GB\n%nprocshared=4\n\n{route}\n\n{title}\n\n"
            f"{charge}\n{molecule}\n{tail}")


# (kind, 产警告调用, message 必含模板短语) —— 模板短语即随批留痕的文案清单
CASES = [
    ("keyword_spell", lambda: check_route_spelling("#p optt"),
     ("疑似拼写错误",)),
    ("route_duplicate", lambda: check_route_duplicates("#p opt opt"),
     ("官方 testrt 不检测重复",)),
    ("route_option_unknown", lambda: check_route_options("#p opt=(calcfc,xyzzy)"),
     ("官方选项集中无",)),
    ("title_forbidden_char", lambda: _parse_warnings(_file("#p opt", title="t_")),
     ("官方建议避免的字符",)),
    ("molecule_multiple_charge_pairs",
     lambda: _parse_warnings(_file("#p opt", charge="0 1 0 1")),
     ("多组电荷-多重度对",)),
    ("atom_label_unknown",
     lambda: _parse_warnings(_file("#p opt", molecule="Zz 0 0 0")),
     ("找不到元素符号前缀",)),
    ("molecule_unterminated", lambda: _parse_warnings(_file("#p opt", tail="")),
     ("未以空行终止",)),
    ("variables_unterminated",
     lambda: _parse_warnings(_file("#p opt", tail="\nVariables:\nR 0.9\n")),
     ("未以空行终止",)),
    # link0_value_invalid 三种值域子模板（%mem 正数 / %nproc 系正整数 / %cpu 列表）
    ("link0_value_invalid", lambda: check_link0_lines(["%mem=2W"]),
     ("须为正数",)),
    ("link0_value_invalid", lambda: check_link0_lines(["%nprocshared=0"]),
     ("须为正整数",)),
    ("link0_value_invalid", lambda: check_link0_lines(["%cpu=x-y"]),
     ("处理器列表",)),
    ("link0_line_too_long", lambda: check_link0_lines(["%" + "a" * 500]),
     ("官方上限",)),
    ("link0_directive_unknown", lambda: check_link0_lines(["%foobar=1"]),
     ("官方指令集外",)),
    ("link0_directive_duplicate",
     lambda: check_link0_lines(["%mem=1GB", "%mem=2GB"]),
     ("重复出现",)),
]


@pytest.mark.parametrize("kind,produce,phrases", CASES,
                         ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_warning_message_is_chinese(kind: str, produce, phrases) -> None:
    ws = [w for w in produce() if w["kind"] == kind]
    assert ws, f"样例未产出 kind={kind} 警告（样例失效须随批修正）"
    for w in ws:
        assert w["message"], f"{kind} message 为空（G0 口径 message 必填）"
        assert _CJK.search(w["message"]), \
            f"{kind} message 非中文警告语：{w['message']!r}"
        assert kind not in w["message"], \
            f"{kind} message 携带机器通道标识 kind 字样：{w['message']!r}"
        for p in phrases:
            assert p in w["message"], \
                f"{kind} message 缺模板短语「{p}」：{w['message']!r}"


def test_template_list_covers_kind_vocabulary() -> None:
    """模板清单覆盖 openapi Warning.kind 词表全集——词表扩容时本断言
    强制同步补样例，杜绝新 kind 无中文文案口径即上线。"""
    covered = {c[0] for c in CASES}
    assert covered == set(KIND_VOCABULARY)
