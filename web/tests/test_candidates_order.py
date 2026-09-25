"""候选列表排序分页测试（m1-acceptance §1.3：跨页全局有序 + 默认序）。

默认序：导入时间倒序（新批在上），同一秒导入的同批文件批内按文件名
自然序——排序唯一实现在取数端（list_candidates 切片前两趟稳定排序：
先 natural_key、再 created_at 倒序），前端按响应序渲染。
原缺口（自然序仅前端页内、跨页无序）由「切片前排序」机制消除。

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


def test_newest_batch_first_natural_within_batch(home, monkeypatch):
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-01-01T00:00:00+00:00")
    _import("h10.gjf", "h2.gjf", "B.gjf", "a3.gjf", "9x.gjf")
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-06-01T00:00:00+00:00")
    _import("m2.gjf", "m10.gjf")
    # 新批（6月）整体在上且批内自然序 m2 < m10；早批（1月）批内自然序
    # a3 < B < h2 < h10 < 9x（字母块先于数字块、h2 先于 h10）
    expected = ["m2.gjf", "m10.gjf", "a3.gjf", "B.gjf", "h2.gjf", "h10.gjf",
                "9x.gjf"]
    assert _page(page_size=3) == (expected[:3], 7)
    merged = sum((_page(page=i, page_size=3)[0] for i in (1, 2, 3)), [])
    assert merged == expected


def test_natural_ties_within_batch_keep_id_desc(home, monkeypatch):
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-01-01T00:00:00+00:00")
    _import("a1-b2.gjf", "a1b2.gjf")  # 「-」仅作分隔，两文件自然键相同
    # 同批同秒且自然键并列：稳定排序保持 id 逆序（新者在前）
    assert _page()[0] == ["a1b2.gjf", "a1-b2.gjf"]


def test_origin_filter_preserves_order(home, monkeypatch):
    from web.src.store import tasks
    monkeypatch.setattr(tasks_repo, "now_iso", lambda: "2026-01-01T00:00:00+00:00")
    _import("h10.gjf", "h2.gjf")
    tid = tasks().create_candidate("a.gjf", "returned_failed")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(INPUT_TEXT,
                                                       encoding="utf-8")
    assert _page(origin="returned_failed") == (["a.gjf"], 1)
    assert _page(origin="imported") == (["h2.gjf", "h10.gjf"], 2)
