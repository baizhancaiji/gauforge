"""提交前输入核验测试（B6，m2-plan §5 test_submit_verify）。

覆盖：换行规范化（CRLF/孤立 \\r）、空行规约正反例（Link0 后不加/多余空行
去/末节与文件末尾补、Variables-Constants 分隔保真）、多结构任务（QST2/QST3）
结构交界双空行规约（§2.7 例外：正反例、幂等、非多结构回归、Variables 共存、
三条提交路径）、解析失败与多步拒绝（不落盘）、三条提交路径统一（行内/队列/
重新排队）、无变化零操作、有变化原子写回且重解析结构不变、normalized 标记
一致、金标准样本不损坏。
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from web.src.errors import ApiError
from web.src.parse.blocks import parse_input, verify_and_normalize
from web.src.services import history as history_svc
from web.src.services.candidates import import_files
from web.src.services.verify import verify_and_store
from web.src.store import executions, queues, seats, tasks
from web.src.routers.candidates import submit_candidate
from web.src.routers.queues import submit_queue

CLEAN = (  # 规范形态：link0 后无空行、节末恰一空行、文件末尾恰一空行
    "%mem=1GB\n"
    "%nprocshared=4\n"
    "#p opt freq b3lyp/6-31g(d)\n"
    "\n"
    "水分子示例\n"
    "\n"
    "0 1\n"
    "O 0.0 0.0 0.0\n"
    "H 1 R1\n"
    "\n"
    "Variables:\n"
    "R1 0.96\n"
    "\n"
)


def _mask(blocks: dict) -> dict:
    """结构不变断言的掩码：附加节 terminator_blank 由规约统一置 True。"""
    b = copy.deepcopy(blocks)
    for s in b["additional_sections"]:
        s["terminator_blank"] = True
    return b


@pytest.fixture()
def ind(tmp_path, monkeypatch) -> Path:
    """工作区隔离（沿 test_e2e 先例）：HOME_DIR 指向 tmp，默认 inputs 目录
    即本夹具目录——路由层提交路径与服务的输入副本读写全部落在隔离区。"""
    from web.src import config
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    d = tmp_path / "inputs"
    d.mkdir()
    return d


def _mk(ind: Path, text: str, name: str = "a.gjf") -> int:
    (out,) = import_files([(name, text.encode("utf-8"))], inputs_dir=ind)
    return out["id"]


def _file(ind: Path, tid: int) -> bytes:
    return (ind / str(tid)).read_bytes()


# ---------------- 换行规范化 ----------------

def test_crlf_normalized_on_inline_submit(ind):
    tid = _mk(ind, CLEAN.replace("\n", "\r\n"))
    out = submit_candidate(tid, None)
    assert out["normalized"] is True
    data = _file(ind, tid)
    assert b"\r" not in data  # CRLF→LF
    assert parse_input(data.decode("utf-8"))["blocks"] == parse_input(CLEAN)["blocks"]


def test_lone_cr_normalized(ind):
    tid = _mk(ind, CLEAN.replace("\n", "\r"))
    assert verify_and_store(tid) is True
    assert b"\r" not in _file(ind, tid)


# ---------------- 空行规约 ----------------

def test_blank_after_link0_removed():
    r = verify_and_normalize("%mem=1GB\n\n\n#p opt\n\nt\n\n0 1\nO\n\n")
    assert r["changed"] is True
    assert r["text"].startswith("%mem=1GB\n#p opt\n")  # Link0 之后不加空行


def test_extra_blank_runs_collapsed():
    r = verify_and_normalize(
        "%mem=1GB\n#p opt\n\n\n\nt\n\n\n\n0 1\nO\n\n\n\nVariables:\nR1 1.0\n\n\n\n")
    assert r["text"] == "%mem=1GB\n#p opt\n\nt\n\n0 1\nO\n\nVariables:\nR1 1.0\n\n"


def test_missing_final_blank_added():
    r = verify_and_normalize("%mem=1GB\n#p opt\n\nt\n\n0 1\nO\n")
    assert r["text"].endswith("O\n\n")  # 文件末节 + 文件末尾恰一空行
    assert r["changed"] is True


def test_variables_constants_separation_kept():
    text = ("%mem=1GB\n#p opt\n\nt\n\n0 1\nO\nH 1 R1\n\n\nVariables:\n"
            "R1 0.96\n\n\n\nConstants:\nR1 0.95\n\n")
    r = verify_and_normalize(text)
    assert "Variables:\nR1 0.96\n\nConstants:\nR1 0.95\n\n" in r["text"]
    # 规约只动节边界空行带，节内容不动
    assert parse_input(r["text"])["blocks"]["molecule"] == \
        parse_input(text)["blocks"]["molecule"]


def test_clean_sample_zero_change(ind):
    """无变化零操作：副本字节不变、normalized=False。"""
    tid = _mk(ind, CLEAN)
    before = _file(ind, tid)
    out = submit_candidate(tid, None)
    assert out["normalized"] is False
    assert _file(ind, tid) == before
    assert not list(ind.glob("*.tmp"))


# ---------------- 多结构任务结构交界双空行（§2.7 例外） ----------------
# 本机 G16 实测：部分发行版输入读取层把「单空行紧邻」的后续结构误并为单行
# （约 800 字符行缓冲截断），报 End of file in ZSymb；结构交界须恰双空行。

QST2_DOUBLE = (  # 多结构规范形态：结构交界恰双空行，其余节末恰一空行
    "%mem=1GB\n"
    "#p opt=(qst2,calcfc) freq b3lyp/6-31g(d)\n"
    "\n"
    "qst2 示例\n"
    "\n"
    "0 1\n"
    "O 0.0 0.0 0.0\n"
    "H 0.96 0.0 0.0\n"
    "H 0.0 0.96 0.0\n"
    "\n"
    "\n"
    "0 1\n"
    "O 0.0 0.0 0.0\n"
    "H -0.96 0.0 0.0\n"
    "H 0.0 0.96 0.0\n"
    "\n"
)
# 同一文件的「单空行交界」形态（导入常见形态，规范化应补为双空行）
QST2_SINGLE = QST2_DOUBLE.replace(
    "H 0.0 0.96 0.0\n\n\n0 1", "H 0.0 0.96 0.0\n\n0 1")


def test_qst2_structure_gap_normalized_to_double():
    r = verify_and_normalize(QST2_SINGLE)
    assert r["changed"] is True
    # 结构交界恰双空行
    assert "H 0.0 0.96 0.0\n\n\n0 1" in r["text"]
    # 其余交界仍恰一空行（route→title、title→电荷行；双空行会令 title 读空、
    # 电荷行误读 title 文本，见 §2.7 例外条款）
    assert "#p opt=(qst2,calcfc) freq b3lyp/6-31g(d)\n\nqst2 示例\n" in r["text"]
    assert "qst2 示例\n\n0 1\n" in r["text"]
    # 结构不变
    assert _mask(parse_input(r["text"])["blocks"]) == \
        _mask(parse_input(QST2_SINGLE)["blocks"])


def test_qst2_double_blank_idempotent():
    r = verify_and_normalize(QST2_DOUBLE)
    assert r["changed"] is False
    assert r["text"] == QST2_DOUBLE


def test_qst3_all_structure_gaps_double():
    text = ("%mem=1GB\n#p opt=(qst3) b3lyp/6-31g(d)\n\nt\n\n"
            "0 1\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\nH 0.0 0.96 0.0\n\n"
            "0 1\nO 0.0 0.0 0.0\nH -0.96 0.0 0.0\nH 0.0 0.96 0.0\n\n"
            "0 1\nO 0.0 0.0 0.0\nH 0.0 0.0 0.96\nH 0.96 0.0 0.0\n\n")
    r = verify_and_normalize(text)
    assert r["text"].count("\n\n\n0 1") == 2  # 两处结构交界均双空行


def test_non_qst_gap_stays_single():
    """非多结构任务维持既有规约（恰好一空行），行为不回退：单空行形态本身
    即规范形态（零操作），结构交界不会被误补双空行。"""
    src = QST2_SINGLE.replace("opt=(qst2,calcfc) freq", "opt freq")
    r = verify_and_normalize(src)
    assert r["changed"] is False
    assert r["text"] == src


def test_qst2_with_variables_sections():
    """结构交界双空行不波及 Variables 区：变量区分隔保持单空行。"""
    text = ("%mem=1GB\n#p opt=qst2\n\nt\n\n"
            "0 1\nO\nH 1 R1\n\n\n"
            "0 1\nO\nH -1 R1\n\n\n"
            "Variables:\nR1 0.96\n\n")
    r = verify_and_normalize(text)
    assert "H 1 R1\n\n\n0 1\n" in r["text"]        # 结构交界双空行
    assert "H -1 R1\n\nVariables:\n" in r["text"]  # 结构 2 → 变量区 单空行


def test_qst2_submit_keeps_double_blank(ind):
    """三条提交路径统一回归（行内提交为代表）：导入→提交后副本仍保双空行
    （用户实测回归：规范化曾把双空行压回单空行致派发副本再次踩雷）。"""
    tid = _mk(ind, QST2_DOUBLE)
    out = submit_candidate(tid, None)
    assert out["normalized"] is False  # 规范形态零操作
    assert _file(ind, tid) == QST2_DOUBLE.encode()
    tid2 = _mk(ind, QST2_SINGLE, name="b.gjf")
    out2 = submit_candidate(tid2, None)
    assert out2["normalized"] is True
    assert "H 0.0 0.96 0.0\n\n\n0 1" in _file(ind, tid2).decode("utf-8")


# ---------------- 解析失败与多步拒绝（不落盘） ----------------

def test_parse_failed_rejected_without_write(ind):
    """导入后副本被改坏（历史遗留场景）：提交核验拒绝且不落盘。"""
    tid = _mk(ind, CLEAN)
    bad = CLEAN.replace("0 1", "zero one")
    (ind / str(tid)).write_text(bad, encoding="utf-8")
    before = _file(ind, tid)
    with pytest.raises(ApiError) as ei:
        submit_candidate(tid, None)
    body = ei.value.body()["error"]
    assert body["code"] == "INPUT_PARSE_FAILED"
    assert body["details"]["section"] == "charge_mult"
    assert body["details"]["line"] >= 1
    assert _file(ind, tid) == before  # 核验失败不写盘


def test_multistep_rejected(ind):
    tid = _mk(ind, CLEAN)
    messy = CLEAN + "--Link1--\n%mem=2GB\n\n#p hf\n\nt\n\n0 1\nO\n\n"
    (ind / str(tid)).write_text(messy, encoding="utf-8")
    before = _file(ind, tid)
    with pytest.raises(ApiError) as ei:
        submit_candidate(tid, None)
    assert ei.value.body()["error"]["code"] == "INPUT_MULTISTEP_UNSUPPORTED"
    assert _file(ind, tid) == before


# ---------------- 三条提交路径统一 ----------------

def test_queue_submit_verifies_each_member(ind):
    t1 = _mk(ind, CLEAN.replace("\n", "\r\n"), name="a.gjf")  # 需规范化
    t2 = _mk(ind, CLEAN, name="b.gjf")  # 已规范
    qid = "QQ0001"
    queues().create(qid, name="队列", skip_failed=False)
    tasks().enqueue(t1, qid, 0)
    tasks().enqueue(t2, qid, 1)
    out = submit_queue(qid)
    assert out["normalized"] is True  # 任一成员规范化即 true
    assert b"\r" not in _file(ind, t1)
    assert _file(ind, t2) == CLEAN.encode()
    assert queues().get(qid)["state"] == "submitted"


def test_queue_submit_rejects_whole_queue_on_bad_member(ind):
    good = _mk(ind, CLEAN, name="a.gjf")
    bad = _mk(ind, CLEAN, name="b.gjf")
    (ind / str(bad)).write_text(CLEAN.replace("0 1", "x y"), encoding="utf-8")
    qid = "QQ0002"
    queues().create(qid, name="队列", skip_failed=False)
    tasks().enqueue(good, qid, 0)
    tasks().enqueue(bad, qid, 1)
    before_good = _file(ind, good)
    n_seats = seats().count()
    with pytest.raises(ApiError) as ei:
        submit_queue(qid)
    body = ei.value.body()["error"]
    assert body["code"] == "INPUT_PARSE_FAILED"
    assert body["details"]["task_id"] == bad  # 指明成员
    assert seats().count() == n_seats  # 未建席位（整队拒绝）
    assert queues().get(qid)["state"] == "unsubmitted"
    assert _file(ind, good) == before_good


def test_requeue_verifies_and_flags(ind):
    tid = _mk(ind, CLEAN.replace("\n", "\r\n"))
    eid = executions().create(task_id=tid, filename="a.gjf",
                              resources={"nproc": {"value": 4, "defaulted": False},
                                         "mem_gb": {"value": 8.0, "defaulted": False}},
                              state="running")
    executions().finalize(execution_id=eid, state="failed",
                          finished_at="2026-09-26T00:00:00+00:00",
                          cause="program_error")
    out = history_svc.requeue(eid)
    assert out["normalized"] is True
    assert b"\r" not in _file(ind, tid)
    assert tasks().get(tid)["form"] == "seat_task"


# ---------------- 写回后重解析结构不变 ----------------

def test_normalized_write_keeps_structure(ind):
    messy = ("%mem=1GB\r\n\r\n\r\n#p opt\r\n\r\nt\r\n\r\n0 1\r\nO\r\nH 1 R1\r\n"
             "\r\nVariables:\r\nR1 0.96\r\n")
    tid = _mk(ind, messy)
    before = _mask(parse_input(messy)["blocks"])
    assert verify_and_store(tid) is True
    after = parse_input(_file(ind, tid).decode("utf-8"))["blocks"]
    assert _mask(after) == before


# ---------------- 金标准样本不损坏 ----------------

GOLDEN_DIR = Path.home() / "g16" / "tests" / "com"


@pytest.mark.skipif(not GOLDEN_DIR.is_dir(), reason="金标准目录不存在")
def test_golden_samples_normalize_without_damage():
    """金标准输入核验：规范化不改变分块结构、不新增解析错误。"""
    checked = 0
    for f in sorted(GOLDEN_DIR.glob("*.com"))[:10]:
        text = f.read_text(encoding="utf-8", errors="replace")
        r = verify_and_normalize(text)
        b0 = parse_input(text)
        b1 = parse_input(r["text"])
        assert _mask(b0["blocks"]) == _mask(b1["blocks"])
        assert len(b1["parse_errors"]) <= len(b0["parse_errors"])
        checked += 1
    assert checked == 10
