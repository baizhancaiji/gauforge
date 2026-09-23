"""自然序排序测试（m1-plan §5：字母块 casefold 字典序、数字块数值序、字母 < 数字）。"""
from web.src.parse.naturalsort import natural_key


def test_letters_casefold_dictionary_order():
    names = ["banana", "Apple", "cherry", "apple2"]
    assert sorted(names, key=natural_key) == ["Apple", "apple2", "banana", "cherry"]


def test_digit_runs_numeric_order():
    names = ["a10", "a2", "a1"]
    assert sorted(names, key=natural_key) == ["a1", "a2", "a10"]


def test_letters_before_digits():
    # 字母块 < 数字块（A–Z 先于 0–9）：a2 < a10 < b1 < 10x
    names = ["10x", "b1", "a10", "a2"]
    assert sorted(names, key=natural_key) == ["a2", "a10", "b1", "10x"]
    assert natural_key("b1") < natural_key("10x")


def test_mixed_boundaries():
    assert natural_key("a2") < natural_key("a10")
    assert natural_key("x1y2") < natural_key("x1y10")
    assert natural_key("a2") < natural_key("b1")


def test_case_insensitive_tie_is_stable():
    # 不区分大小写：B2 排在 b10 前；等值键保持输入稳定序
    names = ["b10", "B2", "a5"]
    assert sorted(names, key=natural_key) == ["a5", "B2", "b10"]
    assert sorted(["b1", "B1"], key=natural_key) == ["b1", "B1"]


def test_separators_are_ignored():
    # 非字母数字字符仅作分隔，不参与键
    assert natural_key("a1-b2") == natural_key("a1b2")
    assert natural_key("test_0002.com") == natural_key("test0002com")


def test_degenerate_inputs():
    assert natural_key("") == ()
    assert natural_key("...") == ()
    assert (natural_key("9x") < natural_key("az")) is False  # 数字块 > 字母块
    assert natural_key("az") < natural_key("9x")
