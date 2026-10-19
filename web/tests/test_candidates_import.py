"""候选导入/剔除/title 实时解析测试（B3，m1-plan §5 测试表）。

隔离：SQLite 走 conftest autouse（tmp_path 文件库）；inputs/ 用例级
tmp_path，不触真实工作区（G16WEB_HOME）。
"""
from pathlib import Path

import pytest

from web.src.errors import ApiError
from web.src.services.candidates import (
    delete_candidate,
    import_files,
    resolve_title,
)
from web.src.store import tasks

VALID_TEXT = (
    "%chk=/tmp/water.chk\n"
    "%mem=1GB\n%nprocshared=4\n"
    "\n#p B3LYP/6-31G(d) opt freq\n\n"
    "水分子优化\n\n0 1\nO\nH 1 R1\nH 1 R2 2 A2\n\n"
    "Variables:\nR1 0.96\nR2 0.96\nA2 109.47\n")
VALID = VALID_TEXT.encode("utf-8")


@pytest.fixture()
def ind(tmp_path) -> Path:
    d = tmp_path / "inputs"
    d.mkdir()
    return d


def _rows():
    return tasks().list_by_form("candidate")


# ---------------- 导入：单/批量/重复 ----------------

def test_import_single_creates_row_and_copy(ind):
    (out,) = import_files([("h2o.gjf", VALID)], inputs_dir=ind)
    assert out["filename"] == "h2o.gjf"
    assert out["duplicate"] is False
    row = tasks().get(out["id"])
    assert row["form"] == "candidate"
    assert row["origin"] == "imported"
    assert (ind / str(out["id"])).read_bytes() == VALID


def test_import_batch_distinct_ids(ind):
    out = import_files([("a.gjf", VALID), ("b.com", VALID)], inputs_dir=ind)
    assert len({o["id"] for o in out}) == 2
    assert len(_rows()) == 2
    assert [(ind / str(o["id"])).exists() for o in out] == [True, True]


def test_reimport_same_file_new_id_with_duplicate_hint(ind):
    first = import_files([("h2o.gjf", VALID)], inputs_dir=ind)
    second = import_files([("h2o.gjf", VALID)], inputs_dir=ind)
    assert first[0]["id"] != second[0]["id"]
    assert [o["duplicate"] for o in (first + second)] == [False, True]
    assert len(_rows()) == 2


def test_duplicate_within_batch_flagged(ind):
    out = import_files([("h2o.gjf", VALID), ("h2o.gjf", VALID)],
                       inputs_dir=ind)
    assert [o["duplicate"] for o in out] == [False, True]


def test_same_content_different_name_not_duplicate(ind):
    out = import_files([("a.gjf", VALID), ("b.gjf", VALID)], inputs_dir=ind)
    assert [o["duplicate"] for o in out] == [False, False]


def test_extension_case_insensitive(ind):
    out = import_files([("H2O.GJF", VALID), ("x.CoM", VALID)], inputs_dir=ind)
    assert len(out) == 2


# ---------------- 校验失败：整批原子 + details 逐文件 ----------------

def test_unsupported_extension_rejected_atomically(ind):
    with pytest.raises(ApiError) as ei:
        import_files([("ok.gjf", VALID), ("bad.txt", VALID)], inputs_dir=ind)
    err = ei.value.body()["error"]
    assert err["code"] == "VALIDATION_FAILED"
    entries = err["details"]["errors"]
    assert [e["filename"] for e in entries] == ["bad.txt"]
    assert entries[0]["reason"] == "UNSUPPORTED_EXTENSION"
    assert _rows() == []
    assert list(ind.iterdir()) == []


def test_multistep_rejected_atomically(ind):
    ms = (VALID_TEXT + "--Link1--\n%mem=2GB\n\n#p hf/sto-3g\n\nt\n\n0 1\nO\n")
    with pytest.raises(ApiError) as ei:
        import_files([("two.gjf", ms.encode("utf-8")), ("ok.gjf", VALID)],
                     inputs_dir=ind)
    entries = ei.value.body()["error"]["details"]["errors"]
    assert [e["reason"] for e in entries] == ["INPUT_MULTISTEP_UNSUPPORTED"]
    assert _rows() == []
    assert list(ind.iterdir()) == []


def test_parse_failed_rejected_atomically(ind):
    bad = b"no route marker\n\n0 1\nO\nH\n"  # 缺 # 路由节
    with pytest.raises(ApiError) as ei:
        import_files([("bad.gjf", bad), ("ok.gjf", VALID)], inputs_dir=ind)
    entries = ei.value.body()["error"]["details"]["errors"]
    assert [e["filename"] for e in entries] == ["bad.gjf"]
    assert entries[0]["reason"] == "INPUT_PARSE_FAILED"
    assert "parse_errors" in entries[0]
    assert _rows() == []
    assert list(ind.iterdir()) == []


def test_invalid_filename_rejected(ind):
    with pytest.raises(ApiError) as ei:
        import_files([("", VALID)], inputs_dir=ind)
    entries = ei.value.body()["error"]["details"]["errors"]
    assert entries[0]["reason"] == "INVALID_FILENAME"


def test_mode_and_empty_files_validation(ind):
    with pytest.raises(ApiError) as ei:
        import_files([("h2o.gjf", VALID)], mode="dir", inputs_dir=ind)
    err = ei.value.body()["error"]
    assert err["details"]["errors"][0]["field"] == "mode"
    with pytest.raises(ApiError):
        import_files([], inputs_dir=ind)
    assert _rows() == []


# ---------------- 副本独立性 / CRLF ----------------

def test_crlf_preserved_verbatim(ind):
    crlf = VALID_TEXT.replace("\n", "\r\n").encode("utf-8")
    (out,) = import_files([("w.gjf", crlf)], inputs_dir=ind)
    assert (ind / str(out["id"])).read_bytes() == crlf


def test_import_copy_independent_of_source(tmp_path, ind):
    src = tmp_path / "src.gjf"
    src.write_bytes(VALID)
    (out,) = import_files([(src.name, src.read_bytes())], inputs_dir=ind)
    src.unlink()  # 导入后删源文件：预览/提交不受影响
    assert (ind / str(out["id"])).read_bytes() == VALID
    assert resolve_title(out["id"], inputs_dir=ind) == "水分子优化"


# ---------------- title 实时解析（不落库） ----------------

def test_title_resolved_realtime(ind):
    (out,) = import_files([("h2o.gjf", VALID)], inputs_dir=ind)
    assert resolve_title(out["id"], inputs_dir=ind) == "水分子优化"
    edited = VALID_TEXT.replace("水分子优化", "新标题").encode("utf-8")
    (ind / str(out["id"])).write_bytes(edited)
    assert resolve_title(out["id"], inputs_dir=ind) == "新标题"


def test_title_none_when_missing_or_undecodable(ind):
    assert resolve_title(12345, inputs_dir=ind) is None
    (out,) = import_files([("h2o.gjf", VALID)], inputs_dir=ind)
    (ind / str(out["id"])).write_bytes(b"\xff\xfe\x00bad")
    assert resolve_title(out["id"], inputs_dir=ind) is None


# ---------------- 剔除：删副本与记录 ----------------

def test_delete_removes_row_and_copy(ind):
    (out,) = import_files([("h2o.gjf", VALID)], inputs_dir=ind)
    tid = out["id"]
    delete_candidate(tid, inputs_dir=ind)
    assert _rows() == []
    assert not (ind / str(tid)).exists()
    with pytest.raises(ApiError) as ei:
        delete_candidate(tid, inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "NOT_FOUND"


def test_delete_only_candidate_form(ind):
    """删除任务实体的唯一入口在候选列表：其余形态按不存在处理。"""
    (out,) = import_files([("h2o.gjf", VALID)], inputs_dir=ind)
    tid = out["id"]
    tasks().to_seat_task(tid)
    with pytest.raises(ApiError):
        delete_candidate(tid, inputs_dir=ind)
    assert (ind / str(tid)).exists()


def test_delete_candidate_with_history_detaches_not_deletes(ind):
    """携带执行记录的候选删除：转 finished 离开候选列表，行与文件保留
    （executions.task_id 外键下删行必失败，先删文件会留幽灵候选——
    2026-10-04 客户端 3.0.0 实测）；再次删除按非候选形态 404。"""
    from web.src.store import executions

    (out,) = import_files([("h2o.gjf", VALID)], inputs_dir=ind)
    tid = out["id"]
    eid = executions().create(
        task_id=tid, filename="h2o.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1.0, "defaulted": False}},
        state="skipped")
    executions().finalize(execution_id=eid, state="skipped",
                          finished_at="2026-10-04T12:00:00+00:00",
                          cause="queue_manually_stopped")

    delete_candidate(tid, inputs_dir=ind)
    row = tasks().get(tid)
    assert row is not None and row["form"] == "finished"  # 归历史所有
    assert (ind / str(tid)).exists()  # 输入副本保留
    assert executions().list_by_task(tid)  # 历史保留
    with pytest.raises(ApiError) as ei:
        delete_candidate(tid, inputs_dir=ind)
    assert ei.value.body()["error"]["code"] == "NOT_FOUND"


# ---------------- G1：导入通道拼写/重复 warnings（B3） ----------------

SPELL_NOTE = """#p opf freq b3lyp/6-31g(d)

拼错关键字导入

0 1
O 0.0 0.0 0.0
H 0.0 0.0 0.96
"""


def test_import_carries_spell_warnings(ind):
    """有近邻的拼错关键字导入不阻断，files[] 条目携带 warnings（行号全文件
    1 起）。"""
    out = import_files([("spell.gjf", SPELL_NOTE.encode())], inputs_dir=ind)
    assert out[0]["warnings"], "导入成功条目应携带非阻断警告"
    w = out[0]["warnings"][0]
    assert w["kind"] == "keyword_spell"
    assert w["line"] == 1 and w["suggestion"] == "opt"
    assert w["message"]


def test_import_rejected_batch_has_no_warnings_field(ind):
    """整批 422 的 details.errors[] 保持既有逐文件错误形态，不新增 warnings。"""
    from web.src.errors import ApiError
    with pytest.raises(ApiError) as ei:
        import_files([("bad.gjf", b"#p hf/sto-3g\n\nno title\n\nzero one\n")],
                     inputs_dir=ind)
    detail = ei.value.body()["error"]["details"]["errors"][0]
    assert "warnings" not in detail


def test_import_duplicate_keyword_warning(ind):
    """route 重复关键字（mp2 mp2）在导入通道出 route_duplicate 警告。"""
    text = "#p mp2 mp2/6-31g(d)\n\nt\n\n0 1\nO 0 0 0\n"
    out = import_files([("dup.gjf", text.encode())], inputs_dir=ind)
    kinds = {w["kind"] for w in out[0]["warnings"]}
    assert "route_duplicate" in kinds
