"""版本单一事实来源解析链测试（version-update-impl-plan B1，§1.2-1）。

- 三级解析优先级：VERSION 文件 → git describe --tags → CHANGELOG.jsonl
  最新 released 行兜底；全链失败兜底 v0.0.0+unknown 并告警、不炸启动。
- 对外形态口径：APP_VERSION 带 v 前缀；bare_version() 为剥 v 单点。
"""
from __future__ import annotations

import logging

from web.src import config

# ---------------- 三级解析链：优先级 ----------------


def test_version_file_wins_over_git_and_changelog(tmp_path, monkeypatch):
    (tmp_path / "VERSION").write_text("v9.9.9\n", encoding="utf-8")
    monkeypatch.setattr(config, "_version_from_git", lambda root: "v8.8.8")
    monkeypatch.setattr(config, "_version_from_changelog", lambda root: "7.7.7")
    assert config.resolve_version(tmp_path) == "v9.9.9"


def test_git_wins_over_changelog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_version_from_git",
                        lambda root: "v2.0.0-3-gabc0000")
    monkeypatch.setattr(config, "_version_from_changelog", lambda root: "7.7.7")
    assert config.resolve_version(tmp_path) == "v2.0.0-3-gabc0000"


# ---------------- 三级解析链：边界 ----------------


def test_git_failure_falls_back_to_changelog(tmp_path):
    """tmp_path 非 git 仓库（git describe 失败）→ CHANGELOG released 兜底。"""
    (tmp_path / "CHANGELOG.jsonl").write_text(
        '{"version":"1.2.3","status":"released"}\n', encoding="utf-8")
    assert config.resolve_version(tmp_path) == "v1.2.3"


def test_changelog_takes_latest_released_row(tmp_path):
    """append-only 时序（旧→新）：取末个 released，跳过 unreleased 与坏行。"""
    (tmp_path / "CHANGELOG.jsonl").write_text(
        '{"version":"0.9.0","status":"released"}\n'
        "not-json\n"
        '{"version":null,"status":"unreleased","changes":[]}\n'
        '{"version":"1.2.3","status":"released"}\n',
        encoding="utf-8")
    assert config.resolve_version(tmp_path) == "v1.2.3"


def test_all_sources_missing_falls_back_unknown(tmp_path, caplog):
    """全链失败：兜底 v0.0.0+unknown 并 logger.warning，不抛异常。"""
    with caplog.at_level(logging.WARNING, logger="web.src.config"):
        assert config.resolve_version(tmp_path) == "v0.0.0+unknown"
    assert any("版本解析链" in r.message for r in caplog.records)


def test_version_file_normalized_to_v_prefix(tmp_path):
    """VERSION 文件缺 v 前缀/带空白时归一为带 v 形态。"""
    (tmp_path / "VERSION").write_text(" 2.1.0 \n", encoding="utf-8")
    assert config.resolve_version(tmp_path) == "v2.1.0"


def test_source_form_resolves_from_real_repo():
    """真实仓库（源码形态）：解析产物带 v 前缀且非兜底值。"""
    assert config.APP_VERSION.startswith("v")
    assert config.APP_VERSION != "v0.0.0+unknown"


# ---------------- 对外形态口径：v 前缀剥离单点 ----------------


def test_bare_version_strips_v_prefix():
    assert config.bare_version("v2.1.0") == "2.1.0"
    assert config.bare_version("2.0.0") == "2.0.0"  # 无前缀原样返回


def test_bare_version_defaults_to_app_version():
    assert config.bare_version() == config.APP_VERSION[1:]


# ---------------- 更新通道默认值与检查周期参数 ----------------


def test_update_channel_defaults():
    assert config.UPDATE_ASSET == "gauforge-deploy-linux-x64.tar.gz"
    assert config.UPDATE_DEFAULT_PROXY == "https://v4.gh-proxy.org"
    assert config.UPDATE_CONNECT_TIMEOUT_S == 15
    assert config.UPDATE_READ_TIMEOUT_S == 30
    assert config.UPDATE_BASE.startswith("https://github.com/")


def test_update_check_interval_setting_metadata():
    assert config.RUNTIME_DEFAULTS["update_check_interval"] == "weekly"
    meta = next(m for m in config.RUNTIME_SETTINGS
                if m["key"] == "update_check_interval")
    assert meta["value_type"] == "string"
    assert meta["range"] == {"enum": ["daily", "weekly", "monthly", "never"]}
    assert meta["effect"] == "immediate"
    assert meta["editable"] is True
