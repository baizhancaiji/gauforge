"""更新检查通道单测（D1）。

覆盖：版本比较边界（含源码形态 git describe 后缀）、探测四分支逐字文案
（httpx.MockTransport 注入）、.update-proxy 读写（无尾换行、与 update.sh
printf '%s' 互认）、.update-check 落盘/恢复（失败保留上一份成功值）、
run_check 状态机三分支与流程中不回翻、形态判定边界。

文案断言逐字引用 services/update.py 模块常量（单一来源防漂移，全角标点）。
"""
from __future__ import annotations

import json

import httpx
import pytest

from web.src import config
from web.src.errors import ApiError
from web.src.mock import get_state
from web.src.services import update as upd


@pytest.fixture(autouse=True)
def deploy_root(tmp_path, monkeypatch):
    """伴生文件（.update-proxy/.update-check）与形态判定指向临时部署目录。"""
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    yield tmp_path


@pytest.fixture(autouse=True)
def fresh_service():
    upd.reset_service()
    get_state().event_history.clear()
    yield
    get_state().event_history.clear()
    upd.reset_service()


def _client_with(content: bytes = b"", status: int = 200,
                 exc: Exception | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if exc is not None:
            raise exc
        return httpx.Response(status, content=content)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _phases() -> list[dict]:
    out = []
    for e in get_state().event_history:
        if e["event"] == "update.phase":
            out.append(json.loads(e["data"]) if isinstance(e["data"], str)
                       else e["data"])
    return out


# ---------------- 版本比较（仅严格更大；剥 v 单点） ----------------

@pytest.mark.parametrize("current,latest,expected", [
    ("v2.0.0", "v2.0.1", True),
    ("v2.0.0", "v2.1.0", True),
    ("v2.0.0", "v3.0.0", True),
    ("v2.0.0", "v2.0.0", False),      # 相等不算有更新
    ("v2.0.1", "v2.0.0", False),      # 更小不算
    ("2.0.0", "v2.1.0", True),        # v 前缀混形态
    ("v2.0.0", "not-a-version", False),  # 不可解析视为无更新
    ("v2.0.0-14-gabcdef0", "v2.1.1", True),  # 源码形态 git describe 后缀按基线 tag 比较
])
def test_has_update_boundaries(current, latest, expected):
    assert upd.has_update(current, latest) is expected


# ---------------- release 直链拼接（代理规则与 update.sh 一致） ----------------

_BASE = "https://github.com/baizhancaiji/gauforge"


def test_release_url_direct_and_proxy():
    assert upd.release_url(None, "VERSION") == \
        f"{_BASE}/releases/latest/download/VERSION"
    assert upd.release_url("https://v4.gh-proxy.org", "VERSION") == \
        f"https://v4.gh-proxy.org/{_BASE}/releases/latest/download/VERSION"


def test_release_url_strips_proxy_trailing_slash():
    # update.sh 拼接口径 {proxy%/}/：尾斜杠剥离后拼接，不产生双斜杠。
    assert upd.release_url("https://x.example/", "VERSION") == \
        f"https://x.example/{_BASE}/releases/latest/download/VERSION"


# ---------------- 探测四分支（§3.5 文案逐字） ----------------

def test_fetch_remote_version_ok():
    client = _client_with(content=b"v2.1.1\n")
    assert upd.fetch_remote_version(None, client) == "v2.1.1"


def test_fetch_remote_version_timeout():
    client = _client_with(exc=httpx.ConnectTimeout("boom"))
    with pytest.raises(upd.CheckFailed) as ei:
        upd.fetch_remote_version(None, client)
    assert ei.value.message == "连接超时，请检查网络"


def test_fetch_remote_version_connect_error():
    client = _client_with(exc=httpx.ConnectError("dns failure"))
    with pytest.raises(upd.CheckFailed) as ei:
        upd.fetch_remote_version(None, client)
    assert ei.value.message == "无法连接更新服务器，请检查网络"


def test_fetch_remote_version_non_200():
    client = _client_with(content=b"nope", status=404)
    with pytest.raises(upd.CheckFailed) as ei:
        upd.fetch_remote_version(None, client)
    assert ei.value.message == "更新服务器返回异常（HTTP 404）"


def test_fetch_remote_version_unparsable_body():
    client = _client_with(content=b"  \n", status=200)
    with pytest.raises(upd.CheckFailed) as ei:
        upd.fetch_remote_version(None, client)
    assert ei.value.message == "更新服务器返回异常（HTTP 200）"


# ---------------- .update-proxy（与 update.sh 互认） ----------------

def test_proxy_write_no_trailing_newline():
    upd.write_proxy("https://v4.gh-proxy.org")
    raw = (config.PROJECT_ROOT / ".update-proxy").read_bytes()
    assert raw == b"https://v4.gh-proxy.org"  # URL 原文、无尾换行
    assert upd.read_proxy() == "https://v4.gh-proxy.org"


def test_proxy_null_writes_empty_file_direct():
    upd.write_proxy(None)
    assert (config.PROJECT_ROOT / ".update-proxy").read_bytes() == b""
    assert upd.read_proxy() is None  # 空内容文件 ↔ 直连


def test_proxy_reads_update_sh_format():
    """update.sh 侧写入（printf '%s'）后本侧读取互认。"""
    (config.PROJECT_ROOT / ".update-proxy").write_bytes(b"")
    assert upd.read_proxy() is None
    (config.PROJECT_ROOT / ".update-proxy").write_bytes(
        b"https://v4.gh-proxy.org")
    assert upd.read_proxy() == "https://v4.gh-proxy.org"


def test_proxy_missing_file_is_direct():
    assert upd.read_proxy() is None


# ---------------- .update-check（最近检查结果） ----------------

def test_check_state_missing_falls_back_to_nulls():
    assert upd.load_check_state() == {
        "latest_version": None, "checked_at": None, "had_update": None}


def test_check_state_corrupt_file_falls_back_to_nulls():
    (config.PROJECT_ROOT / ".update-check").write_text("not json",
                                                       encoding="utf-8")
    assert upd.load_check_state() == {
        "latest_version": None, "checked_at": None, "had_update": None}


def test_record_check_success_writes_all():
    upd.record_check(success=True, latest_version="v2.1.1", had_update=True)
    st = upd.load_check_state()
    assert st["latest_version"] == "v2.1.1"
    assert st["had_update"] is True
    assert st["checked_at"] is not None


def test_record_check_failure_keeps_previous_success():
    upd.record_check(success=True, latest_version="v2.1.1", had_update=True)
    before = upd.load_check_state()
    upd.record_check(success=False)
    after = upd.load_check_state()
    assert after["latest_version"] == "v2.1.1"  # 失败保留上一份成功值
    assert after["had_update"] is True
    assert after["checked_at"] >= before["checked_at"]  # checked_at 每次覆盖写


def test_record_check_failure_from_scratch_keeps_nulls():
    upd.record_check(success=False)
    st = upd.load_check_state()
    assert st["latest_version"] is None
    assert st["had_update"] is None
    assert st["checked_at"] is not None


# ---------------- run_check（手动/自动共用入口） ----------------

def test_run_check_available():
    client = _client_with(content=b"v2.1.1\n")
    st = upd.get_service().run_check(client)
    assert st["phase"] == "available"
    assert st["message"] == "发现新版本 v2.1.1！查看更新说明"
    assert st["latest_version"] == "v2.1.1"
    assert st["last_checked_at"] is not None
    phases = _phases()
    assert [p["phase"] for p in phases] == ["checking", "available"]
    assert phases[1]["version"] == "v2.1.1"
    assert all("ts" in p for p in phases)


def test_run_check_up_to_date():
    client = _client_with(content=b"v2.0.0\n")
    st = upd.get_service().run_check(client)
    assert st["phase"] == "up_to_date"
    assert st["message"] == "当前版本已最新！"
    assert [p["phase"] for p in _phases()] == ["checking", "up_to_date"]


def test_run_check_failure_502_and_failed_phase():
    client = _client_with(exc=httpx.ConnectTimeout("boom"))
    svc = upd.get_service()
    with pytest.raises(ApiError) as ei:
        svc.run_check(client)
    assert ei.value.code == "UPDATE_CHECK_FAILED"
    assert ei.value.http == 502
    assert ei.value.message == "连接超时，请检查网络"
    assert svc.phase == "failed"
    # 失败也写 .update-check（checked_at 刷新），latest_version 保留 null。
    st = upd.load_check_state()
    assert st["checked_at"] is not None
    assert st["latest_version"] is None
    assert [p["phase"] for p in _phases()] == ["checking", "failed"]


def test_run_check_failure_keeps_previous_latest():
    upd.record_check(success=True, latest_version="v2.1.1", had_update=True)
    client = _client_with(exc=httpx.ConnectError("down"))
    with pytest.raises(ApiError):
        upd.get_service().run_check(client)
    st = upd.load_check_state()
    assert st["latest_version"] == "v2.1.1"  # 失败保留上一份成功值
    assert st["had_update"] is True


def test_run_check_in_flight_no_rewind():
    """流程执行中检查不回翻状态机（downloading 相保持、零事件）。"""
    svc = upd.get_service()
    svc.transition("downloading", version="v2.1.1")
    n_events = len(get_state().event_history)
    st = svc.run_check(_client_with(content=b"v2.1.1\n"))
    assert st["phase"] == "downloading"
    assert len(get_state().event_history) == n_events


# ---------------- 形态判定（守卫三边界，R11） ----------------

def test_supported_source_form_false():
    assert upd.deployment_supported() is False


def test_supported_deploy_form_true(tmp_path):
    (tmp_path / "VERSION").write_text("v2.1.0", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "hq").write_bytes(b"\x7fELF")
    assert upd.deployment_supported() is True


def test_supported_version_without_bin_hq_false(tmp_path):
    (tmp_path / "VERSION").write_text("v2.1.0", encoding="utf-8")
    assert upd.deployment_supported() is False


def test_supported_bin_hq_without_version_false(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "hq").write_bytes(b"\x7fELF")
    assert upd.deployment_supported() is False


# ---------------- status 初始态 ----------------

def test_status_initial_idle():
    st = upd.get_service().status()
    assert st["current_version"] == config.APP_VERSION
    assert st["phase"] == "idle"
    assert st["message"] == upd.msg_current(config.APP_VERSION)
    assert st["latest_version"] is None
    assert st["last_checked_at"] is None
    assert st["proxy"] is None
    assert st["supported"] is False


def test_transition_emits_version_and_message():
    upd.get_service().transition("available",
                                 message=upd.msg_available("v2.1.1"),
                                 version="v2.1.1")
    (payload,) = _phases()
    assert payload == {"phase": "available", "version": "v2.1.1",
                       "message": "发现新版本 v2.1.1！查看更新说明",
                       "ts": payload["ts"]}
