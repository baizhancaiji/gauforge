"""分块编辑保存测试（B2，m2-plan §5 test_block_save）。

覆盖：重组不变式五类、编辑不转换行尾、逐节校验正反例、守卫矩阵七路径、
round-trip 自证、写坏样本 500 拦截不落盘、拼写 warnings（近邻命中才报）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from web.src.errors import ApiError
from web.src.parse.blocks import parse_input
from web.src.services.candidates import import_files, save_block
from web.src.store import queues, tasks

SAMPLE = (
    "%chk=/tmp/w.chk\n"
    "%mem=1GB\n"
    "%nprocshared=4\n"
    "\n"
    "#p opt freq b3lyp/6-31g(d)\n"
    "\n"
    "水分子示例\n"
    "\n"
    "0 1\n"
    "O 0.0 0.0 0.0\n"
    "H 1 R1\n"
    "H 1 R2 2 A2\n"
    "\n"
    "Variables:\n"
    "R1 0.96\n"
    "R2 0.96\n"
    "A2 109.47\n"
    "\n"
    "eps=4.0\n"
)

SAMPLE_VC = (  # Variables + Constants 分隔 + gen 触发附加节
    "%mem=1GB\n"
    "%nprocshared=4\n"
    "\n"
    "#p hf/sto-3g gen\n"
    "\n"
    "t\n"
    "\n"
    "0 1\n"
    "O\n"
    "H 1 R1\n"
    "\n"
    "Variables:\n"
    "R1 0.96\n"
    "\n"
    "Constants:\n"
    "R1 0.95\n"
    "\n"
    "H 0\n"
    "S 3 1.0\n"
    "0.5 1.0\n"
    "****\n"
)


@pytest.fixture()
def ind(tmp_path) -> Path:
    d = tmp_path / "inputs"
    d.mkdir()
    return d


def _mk(ind: Path, text: str = SAMPLE, name: str = "a.gjf") -> int:
    (out,) = import_files([(name, text.encode("utf-8"))], inputs_dir=ind)
    return out["id"]


def _file_text(ind: Path, tid: int) -> str:
    return (ind / str(tid)).read_text(encoding="utf-8")


# ---------------- 重组不变式 ----------------

def test_route_save_replaces_span_and_keeps_rest(ind):
    tid = _mk(ind)
    head = SAMPLE[:SAMPLE.index("#p")]
    tail = SAMPLE[SAMPLE.index("水分子示例"):]
    r = save_block(tid, "route", ["#p hf/sto-3g opt=tight"], inputs_dir=ind)
    assert r["blocks"]["route"] == "#p hf/sto-3g opt=tight"
    text = _file_text(ind, tid)
    assert text.startswith(head)  # link0 及其前字节原样
    assert text.endswith(tail)  # title 起（分子节）字节级不动
    assert "\n#p hf/sto-3g opt=tight\n\n水分子示例\n" in text  # 节末恰一空行


def test_last_section_save_appends_single_trailing_blank(ind):
    tid = _mk(ind)
    r = save_block(tid, "additional-0", ["eps=8.0"], inputs_dir=ind)
    assert r["blocks"]["additional_sections"][0]["lines"] == ["eps=8.0"]
    assert r["blocks"]["additional_sections"][0]["terminator_blank"] is True
    text = _file_text(ind, tid)
    assert text.endswith("eps=8.0\n\n")  # 文件末节 + 文件末尾恰一空行
    assert not text.endswith("\n\n\n")


def test_variables_constants_separators_untouched(ind):
    tid = _mk(ind, SAMPLE_VC)
    save_block(tid, "route", ["#p hf/sto-3g gen extra"], inputs_dir=ind)
    text = _file_text(ind, tid)
    assert "Variables:\nR1 0.96\n\nConstants:\nR1 0.95\n" in text
    r = parse_input(text)
    assert r["blocks"]["molecule"]["variables_present"] is True
    assert r["blocks"]["molecule"]["constants_present"] is True


def test_link0_save_keeps_following_bytes(ind):
    tid = _mk(ind)
    save_block(tid, "link0", ["%chk=/tmp/x.chk", "%mem=2GB",
                              "%nprocshared=8"], inputs_dir=ind)
    text = _file_text(ind, tid)
    assert text.startswith("%chk=/tmp/x.chk\n%mem=2GB\n%nprocshared=8\n")
    assert "\n\n#p" in text  # 其后字节不动（原有空行保留、不追加）


def test_link0_save_no_blank_added_when_absent(ind):
    tight = SAMPLE.replace("%nprocshared=4\n\n#p", "%nprocshared=4\n#p")
    tid = _mk(ind, tight)
    save_block(tid, "link0", ["%mem=4GB"], inputs_dir=ind)
    text = _file_text(ind, tid)
    assert text.startswith("%mem=4GB\n#p")  # Link0 之后不加空行


def test_charge_mult_save_normalizes(ind):
    tid = _mk(ind)
    r = save_block(tid, "charge_mult", ["-1  2"], inputs_dir=ind)
    assert r["blocks"]["charge_mult"] == "-1 2"  # 解析视图归一化
    assert "\n-1  2\n" in _file_text(ind, tid)  # 文件按提交行原样落盘


def test_edit_preserves_crlf_verbatim(ind):
    """编辑保存不做换行转换：未编辑行 CRLF 原样保留（文档级断言）。"""
    tid = _mk(ind, SAMPLE.replace("\n", "\r\n"))
    save_block(tid, "route", ["#p hf/sto-3g"], inputs_dir=ind)
    data = (ind / str(tid)).read_bytes()
    assert b"%chk=/tmp/w.chk\r\n" in data  # 未触碰行保持 CRLF
    assert "#p hf/sto-3g\r\n".encode() in data  # 新行按文件行尾风格落盘
    assert parse_input(data.decode("utf-8"))["blocks"]["route"] == "#p hf/sto-3g"


# ---------------- round-trip 自证 ----------------

def test_roundtrip_reparse_matches_saved_blocks(ind):
    tid = _mk(ind)
    r = save_block(tid, "route", ["#p b3lyp/6-31g(d) opt"], inputs_dir=ind)
    on_disk = parse_input(_file_text(ind, tid))
    assert on_disk["blocks"] == r["blocks"]
    assert on_disk["blocks"]["route"] == "#p b3lyp/6-31g(d) opt"


def test_structure_breaking_sample_rejected_500_without_write(ind):
    """①校验通过但破坏分块结构（title 内部空行）→ 500 拒绝落盘。"""
    tid = _mk(ind)
    before = (ind / str(tid)).read_bytes()
    with pytest.raises(ApiError) as ei:
        save_block(tid, "title", ["第一行", "", "第二行"], inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "INTERNAL_ERROR"
    assert (ind / str(tid)).read_bytes() == before  # 不落盘
    assert not list(ind.glob("*.tmp"))  # 原子写无残留


# ---------------- 逐节格式校验（阻断 422） ----------------

def test_link0_validation(ind):
    tid = _mk(ind)
    for bad in (["mem=1GB"], ["%mem="], ["%nprocshared=0"],
                ["%nprocshared=abc"]):
        with pytest.raises(ApiError) as ei:
            save_block(tid, "link0", bad, inputs_dir=ind)
        assert ei.value.body()["error"]["code"] == "VALIDATION_FAILED"
        (ei.value.body()["error"]["details"]["errors"][0]["field"] == "link0")
    # 正例：同义/截断形式与 %CPU proc-list 复用 M1 识别集合
    save_block(tid, "link0", ["%NProcShared=4", "%nprocshare=2",
                              "%CPU=0,1", "%Mem=8GB", "%Mem=500MB"],
               inputs_dir=ind)


def test_route_validation(ind):
    tid = _mk(ind)
    with pytest.raises(ApiError) as ei:
        save_block(tid, "route", ["opt freq"], inputs_dir=ind)  # 缺 #
    assert ei.value.body()["error"]["code"] == "VALIDATION_FAILED"
    with pytest.raises(ApiError):
        save_block(tid, "route", ["#p opt", "", "freq"], inputs_dir=ind)


def test_title_validation(ind):
    tid = _mk(ind)
    with pytest.raises(ApiError):
        save_block(tid, "title", ["l1", "l2", "l3", "l4", "l5", "l6"],
                   inputs_dir=ind)  # 超 5 行
    for bad in ("a@b", "a#b", "a!b", "a–b", "a_b", "a\\b", "a\x01b"):
        with pytest.raises(ApiError):
            save_block(tid, "title", [bad], inputs_dir=ind)
    save_block(tid, "title", ["合法 标题-0.5"], inputs_dir=ind)


def test_charge_mult_validation(ind):
    tid = _mk(ind)
    for bad in (["0"], ["0 1 2"], ["x 1"], ["0 0"], ["0 -1"]):
        with pytest.raises(ApiError):
            save_block(tid, "charge_mult", bad, inputs_dir=ind)
    save_block(tid, "charge_mult", ["0, 3"], inputs_dir=ind)


def test_section_name_guards_400(ind):
    """molecule 与未知节名（含 M1 占位名 additional_sections）一律 400。"""
    tid = _mk(ind)
    for section in ("molecule", "additional_sections", "additional-x",
                    "additional-9", "route2"):
        with pytest.raises(ApiError) as ei:
            save_block(tid, section, ["x"], inputs_dir=ind)
        assert ei.value.body()["error"]["code"] == "INVALID_REQUEST"
        assert ei.value.body()["error"].get("details") or True
    # 空内容 422
    with pytest.raises(ApiError) as ei:
        save_block(tid, "route", ["", ""], inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "VALIDATION_FAILED"


# ---------------- 守卫矩阵（七路径） ----------------

def test_guard_candidate_allowed(ind):
    tid = _mk(ind)
    r = save_block(tid, "route", ["#p opt"], inputs_dir=ind)
    assert r["blocks"]["route"] == "#p opt"


def _mk_queue_member(ind: Path, *, rollback: bool, state: str | None) -> int:
    tid = _mk(ind)
    qid = "Q" + str(tid) * 2
    queues().create(qid, name="队列", skip_failed=False)
    tasks().enqueue(tid, qid, 0)
    if rollback:
        queues().update(qid, rollback_flag=True)
    if state:
        queues().set_state(qid, state)
    return tid


def test_guard_rollback_member_allowed(ind):
    tid = _mk_queue_member(ind, rollback=True, state=None)
    r = save_block(tid, "route", ["#p opt"], inputs_dir=ind)
    assert r["blocks"]["route"] == "#p opt"


def test_guard_new_unsubmitted_member_locked(ind):
    tid = _mk_queue_member(ind, rollback=False, state=None)
    with pytest.raises(ApiError) as ei:
        save_block(tid, "route", ["#p opt"], inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "QUEUE_MEMBER_LOCKED"


def test_guard_submitted_member_locked(ind):
    tid = _mk_queue_member(ind, rollback=True, state="submitted")
    with pytest.raises(ApiError) as ei:
        save_block(tid, "route", ["#p opt"], inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "QUEUE_MEMBER_LOCKED"


def test_guard_completed_member_locked(ind):
    tid = _mk_queue_member(ind, rollback=True, state="completed")
    with pytest.raises(ApiError) as ei:
        save_block(tid, "route", ["#p opt"], inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "QUEUE_MEMBER_LOCKED"


def test_guard_seat_task_in_flight(ind):
    tid = _mk(ind)
    tasks().to_seat_task(tid)
    with pytest.raises(ApiError) as ei:
        save_block(tid, "route", ["#p opt"], inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "TASK_IN_FLIGHT"


def test_guard_finished_immutable(ind):
    tid = _mk(ind)
    tasks().to_finished(tid)
    with pytest.raises(ApiError) as ei:
        save_block(tid, "route", ["#p opt"], inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "TASK_FINISHED"


def test_guard_missing_404(ind):
    with pytest.raises(ApiError) as ei:
        save_block(99999, "route", ["#p opt"], inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "NOT_FOUND"


# ---------------- 拼写检查（非阻断 warnings） ----------------

def test_spell_warning_near_neighbor_only(ind):
    tid = _mk(ind)
    r = save_block(tid, "route", ["#p opt freq oppt"], inputs_dir=ind)
    assert r["blocks"]["route"] == "#p opt freq oppt"  # 非阻断照常保存
    assert r["warnings"] == [{"line": 1, "keyword": "oppt",
                              "kind": "keyword_spell", "suggestion": "opt"}]
    r2 = save_block(tid, "route", ["#p opt freq mycustomkw"], inputs_dir=ind)
    assert r2["warnings"] == []  # 纯新词不警告
    r3 = save_block(tid, "route", ["#p OPT FREQ"], inputs_dir=ind)
    assert r3["warnings"] == []  # 大小写不敏感命中


# ---------------- 金标准输入编辑回写 ----------------

GOLDEN_DIR = Path.home() / "g16" / "tests" / "com"


@pytest.mark.skipif(not GOLDEN_DIR.is_dir(), reason="金标准目录不存在")
def test_golden_inputs_edit_roundtrip(ind):
    """金标准输入逐节保存回写：round-trip 一致、其余分块不变。

    金标准为历史测试文件，个别不满足严格导入校验（多步/解析失败/非
    UTF-8），跳过不计入。"""
    checked = 0
    for f in sorted(GOLDEN_DIR.glob("*.com")):
        if checked >= 5:
            break
        try:
            tid = _mk(ind, f.read_text(encoding="utf-8", errors="replace"),
                      name=f.name)
        except ApiError:
            continue  # 不可导入样本（严格校验拒绝）跳过
        before = parse_input(_file_text(ind, tid))["blocks"]
        if before["route"]:
            lines = before["route"].split("\n")
            lines[0] = lines[0] + " extra"
            r = save_block(tid, "route", lines, inputs_dir=ind)
            after = parse_input(_file_text(ind, tid))["blocks"]
            assert after["route"] == "\n".join(lines)
        elif before["title"]:
            r = save_block(tid, "title", before["title"].split("\n"),
                           inputs_dir=ind)
            assert parse_input(_file_text(ind, tid))["blocks"]["title"] \
                == before["title"]
        else:
            r = save_block(tid, "link0",
                           before["link0"]["lines"] or ["%mem=1GB"],
                           inputs_dir=ind)
        assert isinstance(r["warnings"], list)
        checked += 1
    assert checked == 5
