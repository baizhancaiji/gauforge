"""设置持久化测试（m1-plan §5 test_settings_persist.py，B1）。

覆盖：运行级参数 SQLite 读写与重启一致；启动级环境变量优先且不入库；
越界/未知/只读 key 校验失败列表。
"""
from __future__ import annotations

import pytest

from web.src import config
from web.src.store import Database, run_migrations
from web.src.store.settings_repo import SettingsRepo


@pytest.fixture()
def repo(tmp_path):
    d = Database(tmp_path / "s.db")
    run_migrations(d)
    yield SettingsRepo(d)
    d.close()


def test_runtime_value_roundtrip_persists(tmp_path):
    """写库后重开新连接（模拟重启）读值一致。"""
    d1 = Database(tmp_path / "p.db")
    run_migrations(d1)
    s1 = SettingsRepo(d1)
    s1.set("listen_port", 8400)
    s1.set("g16_root", "~/g16-custom")
    d1.close()

    d2 = Database(tmp_path / "p.db")
    run_migrations(d2)
    s2 = SettingsRepo(d2)
    assert s2.get("listen_port") == 8400
    assert s2.get("g16_root") == "~/g16-custom"
    d2.close()


def test_missing_key_falls_back_to_default(repo):
    """无记录回落代码默认值（config.RUNTIME_DEFAULTS）。"""
    assert repo.get("page_size") == config.RUNTIME_DEFAULTS["page_size"]
    assert repo.all()["parallel_window"] == config.RUNTIME_DEFAULTS["parallel_window"]


def test_startup_keys_not_persistable(repo):
    """启动级参数不入库：设置表写不进，读仍走环境变量。"""
    failures = repo.apply_update({"workspace_root": "/tmp/x"})
    assert failures and failures[0]["reason"] == "readonly"
    failures = repo.apply_update({"bind_address": "0.0.0.0"})
    assert failures and failures[0]["reason"] == "readonly"
    assert repo.get("workspace_root") is None  # 从未入库
    # 启动级读值仍由环境变量决定（config.setting_value）。
    assert config.setting_value("bind_address") == config.BIND_ADDR


def test_validation_unknown_and_readonly(repo):
    assert repo.apply_update({"nope": 1})[0]["reason"] == "unknown_setting"
    failures = repo.apply_update({"workspace_root": "x", "bind_address": "x"})
    assert all(f["reason"] == "readonly" for f in failures)


def test_validation_out_of_range(repo):
    failures = repo.apply_update({"page_size": 99999, "parallel_window": 0})
    reasons = {f["key"]: f["reason"] for f in failures}
    assert reasons == {"page_size": "out_of_range", "parallel_window": "out_of_range"}


def test_apply_update_all_or_nothing(repo):
    """整批校验先于应用：任一失败则全批不写入。"""
    failures = repo.apply_update({"page_size": 100, "parallel_window": 999})
    assert failures  # parallel_window 越界
    assert repo.get("page_size") == config.RUNTIME_DEFAULTS["page_size"]  # 未写入


def test_apply_update_valid_batch(repo):
    assert repo.apply_update({"page_size": 120, "sse_heartbeat_seconds": 20}) == []
    assert repo.get("page_size") == 120
    assert repo.get("sse_heartbeat_seconds") == 20


def test_type_coercion_int_and_number(repo):
    """契约 value_type：integer 项收整数、number 项收数值（bool 拒绝）。"""
    assert repo.apply_update({"page_size": "abc"})[0]["reason"] == "out_of_range"
    assert repo.apply_update({"page_size": True})[0]["reason"] == "out_of_range"
    assert repo.apply_update({"link0_default_mem_gb": 12}) == []
    assert repo.get("link0_default_mem_gb") == 12
