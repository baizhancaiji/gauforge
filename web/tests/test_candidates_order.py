"""候选列表排序分页测试（m1-acceptance §1.3：跨页全局有序 + 默认序）。

默认序（2026-09-27 验收修正）：回退候选（origin=returned_*）置顶、导入候选
在后，两组内均按 created_at 倒序（最新在上，让出错条目一眼可见）；同秒导入
的批内按 id 逆序（后导入在前）——排序唯一实现在取数端（list_candidates
切片前两趟稳定排序：先 id 逆序、再 (是否回退, created_at) 倒序），前端按
响应序渲染。原「批内文件名自然序」退役（文件名自然序仅历史 filename_* 排序保留）。

测试构造为反例：先导入时间晚的批、后导入时间早的批（id 序与 created_at 序
相反）——若实现误用纯 id 序或自然序，断言即失败（区别于巧合通过）。

隔离：conftest autouse 隔离 SQLite；home fixture 重定向 config.HOME_DIR；
now_iso 打点控制批次时间（created_at 为秒精度，同批返回同一时刻）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.main import app
from web.src.services.candidates import import_files
from web.src.store import tasks_repo

client = TestClient(app)

INPUT_TEXT = "%chk=w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """inputs/（导入副本落盘）重定向到 tmp_path。"""
    (tmp_path / "inputs").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


def _import(*names: str) -> None:
    """按传入序整批导入（id 递增 = 传入序）。"""
    import_files([(n, INPUT_TEXT.encode("utf-8")) for n in names])


def _seed(name: str, origin: str = "returned_failed") -> None:
    """直接播种一条回退候选（回退产生不经导入，见 roadmap §2.1 退回路径）。"""
    from web.src.store import tasks
    tid = tasks().create_candidate(name, origin)
    (config.HOME_DIR / "inputs" / str(tid)).write_text(INPUT_TEXT,
                                                       encoding="utf-8")


def _page(page: int = 1, page_size: int | None = None,
          origin: str | None = None) -> tuple[list[str], int]:
    params: dict = {"page": page}
    if page_size is not None:
        params["page_size"] = page_size
    if origin is not None:
        params["origin"] = origin
    r = client.get("/api/v1/candidates", params=params)
    assert r.status_code == 200
    body = r.json()
    return [c["filename"] for c in body["items"]], body["total"]


def test_created_desc_batches_and_id_desc_within_batch(home, monkeypatch):
    # 先导入 6月批（id 小），后导入 1月批（id 大）——created_at 倒序下 6月批
    # 整体在前，与 id 序相反；同秒批内 id 逆序（后导入在前）
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-06-01T00:00:00+00:00")
    _import("m2.gjf", "m10.gjf")
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-01-01T00:00:00+00:00")
    _import("h10.gjf", "h2.gjf", "B.gjf", "a3.gjf", "9x.gjf")
    expected = ["m10.gjf", "m2.gjf", "9x.gjf", "a3.gjf", "B.gjf",
                "h2.gjf", "h10.gjf"]
    assert _page(page_size=3) == (expected[:3], 7)
    merged = sum((_page(page=i, page_size=3)[0] for i in (1, 2, 3)), [])
    assert merged == expected


def test_returned_first_then_created_desc(home, monkeypatch):
    """回退候选置顶（组内创建时间倒序），导入候选其后——出错条目一眼可见。

    回退组先播种（id 小、时间早），导入组后播种（id 大、时间晚）——id 序
    与预期相反，可区分「回退置顶 + 时间倒序」与「纯 id 逆序」。"""
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-04-01T00:00:00+00:00")
    _seed("ret_old.gjf")
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-05-01T00:00:00+00:00")
    _seed("ret_a.gjf")
    _seed("ret_b.gjf", origin="returned_unrun")
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-02-01T00:00:00+00:00")
    _import("old.gjf")
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-01-01T00:00:00+00:00")
    _import("older.gjf")
    # 回退组整体置顶：组内创建时间倒序（ret_b/ret_a 同秒 id 逆序 → ret_b 前）；
    # 导入组其后：old（2月）在 older（1月）之前，与 id 序相反
    expected = ["ret_b.gjf", "ret_a.gjf", "ret_old.gjf", "old.gjf", "older.gjf"]
    assert _page() == (expected, 5)
    # 回退组与导入组跨页同样不交错（切片前全量排序）
    merged = sum((_page(page=i, page_size=2)[0] for i in (1, 2, 3)), [])
    assert merged == expected


def test_origin_filter_preserves_order(home, monkeypatch):
    from web.src.store import tasks
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-01-01T00:00:00+00:00")
    _import("h10.gjf", "h2.gjf")
    tid = tasks().create_candidate("a.gjf", "returned_failed")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(INPUT_TEXT,
                                                       encoding="utf-8")
    assert _page(origin="returned_failed") == (["a.gjf"], 1)
    # 导入组同秒批内 id 逆序（h2 后导入在前）
    assert _page(origin="imported") == (["h2.gjf", "h10.gjf"], 2)
