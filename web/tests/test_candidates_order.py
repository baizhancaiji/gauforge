"""候选列表自然序分页测试（m1-acceptance §1.3 末项：跨页全局有序）。

原缺口：自然序仅在前端页内执行，后端按 id 逆序直接切片——跨页全局
无序，且前后端双实现无对照测试。修复后排序唯一实现在取数端
（list_candidates 切片前按 natural_key 稳定排序），前端废止页内重排
（utils/naturalsort.ts 删除，双实现随之消除）。

隔离：conftest autouse 隔离 SQLite；home fixture 重定向 config.HOME_DIR。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.main import app
from web.src.services.candidates import import_files

client = TestClient(app)

INPUT_TEXT = "%chk=w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """inputs/（导入副本落盘）重定向到 tmp_path。"""
    (tmp_path / "inputs").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


def _import(*names: str) -> None:
    """按传入序整批导入（id 递增 = 传入序），构造 id 序 ≠ 自然序。"""
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


def test_cross_page_global_natural_order(home):
    _import("h10.gjf", "h2.gjf", "B.gjf", "a3.gjf", "9x.gjf")
    # 导入序（= id 逆序取数序）与自然序相反：全局自然序应为
    # a3, B, h2, h10, 9x（字母块先于数字块、h2 先于 h10、大小写不敏感）
    assert _page(page_size=2) == (["a3.gjf", "B.gjf"], 5)
    assert _page(page=2, page_size=2)[0] == ["h2.gjf", "h10.gjf"]
    assert _page(page=3, page_size=2)[0] == ["9x.gjf"]
    merged = sum((_page(page=i, page_size=2)[0] for i in (1, 2, 3)), [])
    assert merged == ["a3.gjf", "B.gjf", "h2.gjf", "h10.gjf", "9x.gjf"]


def test_ties_keep_id_desc_view_order(home):
    _import("a1-b2.gjf", "a1b2.gjf")  # 「-」仅作分隔，两文件自然键相同
    # 稳定排序：并列保持 id 逆序（新者在前），与修复前页内展示序一致
    assert _page()[0] == ["a1b2.gjf", "a1-b2.gjf"]


def test_origin_filter_preserves_global_order(home):
    from web.src.store import tasks
    _import("h10.gjf", "h2.gjf")
    tid = tasks().create_candidate("a.gjf", "returned_failed")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(INPUT_TEXT,
                                                       encoding="utf-8")
    assert _page(origin="returned_failed") == (["a.gjf"], 1)
    assert _page(origin="imported") == (["h2.gjf", "h10.gjf"], 2)
