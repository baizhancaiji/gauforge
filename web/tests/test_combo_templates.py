"""组合流精修模板测试（插波 3.2.0 批次 B，m4-combo-template-deploy-plan §4）。

提交 #3（迁移+repo+config 常量）落本文件种子/重启 roundtrip/is_default
事务性断言；#5（校验服务+端点）补 §3.2 校验矩阵逐 reason（11 项）与
端点 200/404/422 契约、序列化往返断言。
"""
from __future__ import annotations

import pytest

from web.src import config
from web.src.store import Database, run_migrations
from web.src.store.combo_templates_repo import ComboTemplatesRepo


def _fields(**over):
    """合法全量字段（对齐 repo.update 形参；存储层 int/float/str|None）。"""
    base = {"name": "配置1", "route": config.COMBO_TEMPLATE_INITIAL_ROUTE,
            "nproc": None, "mem_gb": None, "cpu": None, "is_default": False}
    base.update(over)
    return base


@pytest.fixture()
def repo(tmp_path):
    d = Database(tmp_path / "ct.db")
    run_migrations(d)
    yield ComboTemplatesRepo(d)
    d.close()


def test_seed_idempotent_rerun(tmp_path):
    """迁移重复执行不重复播种（INSERT OR IGNORE），恒 5 行。"""
    d = Database(tmp_path / "ct.db")
    run_migrations(d)
    run_migrations(d)  # 幂等重跑
    rows = ComboTemplatesRepo(d).get_all()
    assert [r["template_id"] for r in rows] == [1, 2, 3, 4, 5]
    d.close()


def test_seed_content(repo):
    """5 套方案初始全存在：name=配置n、route=初始值、link0 三字段空、
    is_default 仅 id=1。"""
    rows = repo.get_all()
    assert [r["name"] for r in rows] == [f"配置{i}" for i in range(1, 6)]
    assert all(r["route"] == config.COMBO_TEMPLATE_INITIAL_ROUTE
               for r in rows)
    assert all(r["nproc"] is None and r["mem_gb"] is None and r["cpu"] is None
               for r in rows)
    assert [r["template_id"] for r in rows if r["is_default"]] == [1]


def test_restart_roundtrip(tmp_path):
    """保存后重开连接（模拟重启）读值一致。"""
    d1 = Database(tmp_path / "ct.db")
    run_migrations(d1)
    ComboTemplatesRepo(d1).update(
        2, _fields(name="自定义", route="#p hf opt", nproc=4, mem_gb=8.0))
    d1.close()

    d2 = Database(tmp_path / "ct.db")
    run_migrations(d2)
    row = ComboTemplatesRepo(d2).get(2)
    assert row["name"] == "自定义" and row["route"] == "#p hf opt"
    assert row["nproc"] == 4 and row["mem_gb"] == 8.0
    assert row["cpu"] is None and row["is_default"] == 0
    d2.close()


def test_is_default_exclusive_migration(repo):
    """is_default 迁移事务性：置 1 同事务清其余，恒有且仅有一个默认。"""
    repo.update(3, _fields(is_default=True))
    assert [r["template_id"] for r in repo.get_all() if r["is_default"]] == [3]
    repo.update(5, _fields(is_default=True))
    rows = repo.get_all()
    assert [r["template_id"] for r in rows if r["is_default"]] == [5]
    assert sum(r["is_default"] for r in rows) == 1


def test_update_refreshes_updated_at(repo):
    before = repo.get(1)["updated_at"]
    row = repo.update(1, _fields(name="改名"))
    assert row["name"] == "改名"
    assert row["updated_at"] >= before  # 审计时间戳不早于更新前


def test_get_unknown_returns_none(repo):
    assert repo.get(9) is None
