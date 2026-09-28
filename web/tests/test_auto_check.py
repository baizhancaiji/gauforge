"""自动检查调度单测（D4）。

覆盖：四档窗口起点计算（daily/weekly/monthly/never，本地 01:00 锚定）、
周一/月初跨日边界、补查窗口判定双分支（窗口未查过补查 / 已查过跳过）、
never 不排程不补查、到点只发现不安装（emit available、零 apply 动作）、
自动检查失败不炸循环、设置变更下次轮询生效（30s 口径）、run 循环可停。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from web.src import config
from web.src.mock import get_state
from web.src.services import update as upd

TZ = timezone(timedelta(hours=8))  # 固定时区（aware，窗口判定全程 aware）


def dt(*args) -> datetime:
    return datetime(*args, tzinfo=TZ)


@pytest.fixture(autouse=True)
def deploy_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    yield tmp_path


@pytest.fixture(autouse=True)
def fresh_service():
    upd.reset_service()
    get_state().event_history.clear()
    yield
    upd.reset_service()
    get_state().event_history.clear()


@pytest.fixture(autouse=True)
def clean_settings():
    from web.src import store
    store.get_db().run("DELETE FROM settings")
    yield
    store.get_db().run("DELETE FROM settings")


def _reader(interval: str):
    return lambda: interval


# ---------------- 窗口起点（四档 + 跨日边界） ----------------

def test_window_start_daily():
    assert upd.window_start("daily", dt(2026, 9, 28, 15)) == dt(2026, 9, 28, 1)
    assert upd.window_start("daily", dt(2026, 9, 28, 0, 30)) == \
        dt(2026, 9, 28, 1)


def test_window_start_weekly():
    assert upd.window_start("weekly", dt(2026, 9, 30, 10)) == \
        dt(2026, 9, 28, 1)  # 2026-09-28 为周一
    assert upd.window_start("weekly", dt(2026, 10, 4, 20)) == \
        dt(2026, 9, 28, 1)  # 周日仍属本周窗口


def test_window_start_weekly_monday_early_morning():
    """周一 00:30：窗口起点=当日 01:00（未来）→ 尚未进入本周窗口。"""
    assert upd.window_start("weekly", dt(2026, 9, 28, 0, 30)) == \
        dt(2026, 9, 28, 1)
    assert dt(2026, 9, 28, 0, 30) < upd.window_start(
        "weekly", dt(2026, 9, 28, 0, 30))


def test_window_start_monthly():
    assert upd.window_start("monthly", dt(2026, 9, 28, 15)) == \
        dt(2026, 9, 1, 1)
    # 月初跨日：1 日 00:30 起点为当日 01:00（未来）；02:00 已在窗口内。
    assert upd.window_start("monthly", dt(2026, 10, 1, 0, 30)) == \
        dt(2026, 10, 1, 1)
    assert upd.window_start("monthly", dt(2026, 10, 1, 2)) == \
        dt(2026, 10, 1, 1)


def test_window_start_never_is_none():
    assert upd.window_start("never", dt(2026, 9, 28, 15)) is None


# ---------------- 补查窗口判定 ----------------

def test_checked_within_window():
    assert upd.checked_within_window("2026-09-28T01:30:00+08:00",
                                     dt(2026, 9, 28, 1)) is True
    assert upd.checked_within_window("2026-09-27T23:00:00+08:00",
                                     dt(2026, 9, 28, 1)) is False
    assert upd.checked_within_window(None, dt(2026, 9, 28, 1)) is False
    assert upd.checked_within_window("not-a-date", dt(2026, 9, 28, 1)) is False


def test_should_run_never_checked_daily():
    """窗口已开始且从未查过 → 补查（服务启动 ≤5min 补查由首轮醒来满足）。"""
    sched = upd.AutoCheckScheduler(settings_reader=_reader("daily"),
                                   clock=lambda: dt(2026, 9, 28, 8))
    assert sched.should_run_now() is True


def test_should_run_window_not_started():
    sched = upd.AutoCheckScheduler(settings_reader=_reader("daily"),
                                   clock=lambda: dt(2026, 9, 28, 0, 30))
    assert sched.should_run_now() is False


def test_should_run_checked_this_window_skips():
    """本窗口已查过（checked_at 落在窗口起点之后）→ 不重复请求远端。"""
    (config.PROJECT_ROOT / ".update-check").write_text(
        '{"latest_version": "v2.0.0", "checked_at": '
        '"2026-09-28T01:30:00+08:00", "had_update": false}',
        encoding="utf-8")
    sched = upd.AutoCheckScheduler(settings_reader=_reader("daily"),
                                   clock=lambda: dt(2026, 9, 28, 8))
    assert sched.should_run_now() is False


def test_should_run_checked_previous_window():
    """上次检查在上一窗口（昨天 23:00）→ 本窗口未查 → 补查。"""
    (config.PROJECT_ROOT / ".update-check").write_text(
        '{"latest_version": "v2.0.0", "checked_at": '
        '"2026-09-27T23:00:00+08:00", "had_update": false}',
        encoding="utf-8")
    sched = upd.AutoCheckScheduler(settings_reader=_reader("daily"),
                                   clock=lambda: dt(2026, 9, 28, 8))
    assert sched.should_run_now() is True


def test_should_run_weekly_checked_last_week():
    (config.PROJECT_ROOT / ".update-check").write_text(
        '{"latest_version": "v2.0.0", "checked_at": '
        '"2026-09-21T01:30:00+08:00", "had_update": false}',
        encoding="utf-8")
    sched = upd.AutoCheckScheduler(settings_reader=_reader("weekly"),
                                   clock=lambda: dt(2026, 9, 30, 8))
    assert sched.should_run_now() is True  # 上周一的检查不算本窗口


def test_should_run_never_neither_schedule_nor_backfill():
    sched = upd.AutoCheckScheduler(settings_reader=_reader("never"),
                                   clock=lambda: dt(2026, 9, 28, 8))
    assert sched.should_run_now() is False


def test_should_run_corrupt_checked_at_treated_unchecked():
    (config.PROJECT_ROOT / ".update-check").write_text("garbage",
                                                       encoding="utf-8")
    sched = upd.AutoCheckScheduler(settings_reader=_reader("daily"),
                                   clock=lambda: dt(2026, 9, 28, 8))
    assert sched.should_run_now() is True  # 解析失败按未查过 → 补查


# ---------------- 到点只发现不安装 ----------------

def _mock_release(monkeypatch, version=b"v2.1.1", exc=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if exc is not None:
            raise exc
        url = str(request.url)
        if url.endswith("/VERSION"):
            return httpx.Response(200, content=version)
        return httpx.Response(200, content=b"x")
    monkeypatch.setattr(upd, "_client",
                        lambda: httpx.Client(
                            transport=httpx.MockTransport(handler)))


def test_step_discovers_without_applying(monkeypatch, deploy_root):
    """到点触发：emit update.phase(available)；无 downloading/apply 动作。"""
    monkeypatch.setattr(upd.UpdateService, "_popen",
                        staticmethod(lambda args, **kw: pytest.fail(
                            "自动检查不得触发 apply")))
    _mock_release(monkeypatch)
    sched = upd.AutoCheckScheduler(settings_reader=_reader("daily"),
                                   clock=lambda: dt(2026, 9, 28, 8))
    asyncio.run(sched.step())
    svc = upd.get_service()
    assert svc.phase == "available"
    events = [e["event"] for e in get_state().event_history]
    assert events.count("update.phase") == 2  # checking → available
    assert "downloading" not in [p["phase"] for p in
                                 [__import__("json").loads(e["data"])
                                  for e in get_state().event_history
                                  if e["event"] == "update.phase"]]


def test_step_check_failure_does_not_raise(monkeypatch):
    _mock_release(monkeypatch, exc=httpx.ConnectTimeout("boom"))
    sched = upd.AutoCheckScheduler(settings_reader=_reader("daily"),
                                   clock=lambda: dt(2026, 9, 28, 8))
    asyncio.run(sched.step())  # ApiError 被吞（文案已入 failed 相）
    assert upd.get_service().phase == "failed"


def test_step_not_due_noop(monkeypatch):
    _mock_release(monkeypatch)
    sched = upd.AutoCheckScheduler(settings_reader=_reader("daily"),
                                   clock=lambda: dt(2026, 9, 28, 0, 30))
    asyncio.run(sched.step())
    assert upd.get_service().phase == "idle"
    assert get_state().event_history == []


# ---------------- 设置变更即时生效（30s 口径） ----------------

def test_settings_change_takes_effect_next_poll():
    """运行级参数保存后，调度器下一轮醒来即读到新值（never → 不再触发）。"""
    from web.src.store import settings as settings_store
    settings_store().set("update_check_interval", "daily")
    sched = upd.AutoCheckScheduler(clock=lambda: dt(2026, 9, 28, 8))
    assert sched.should_run_now() is True
    settings_store().set("update_check_interval", "never")
    assert sched.should_run_now() is False  # 下次轮询生效
    settings_store().set("update_check_interval", "monthly")
    assert sched.should_run_now() is True  # 月内窗口未查过 → 补查


def test_scheduler_reads_sqlite_default_weekly():
    """无记录回落代码默认 weekly（B1 落点与调度链贯通）。"""
    from web.src.store import settings as settings_store
    assert settings_store().get("update_check_interval") == "weekly"


# ---------------- run 循环 ----------------

def test_run_loop_stops_on_stop():
    """stop() 后 run 循环退出（never 档空转休眠、不 CPU 空转）。"""
    async def scenario():
        sched = upd.AutoCheckScheduler(settings_reader=_reader("never"),
                                       sleeper=_RecordingSleeper())
        async def sleep_once(_):
            sched.stop()
        sched._sleep = sleep_once
        await asyncio.wait_for(sched.run(), timeout=2)
        return sched

    sched = asyncio.run(scenario())
    assert sched._stopped is True


class _RecordingSleeper:
    """占位 sleeper（被用例内 sleep_once 覆盖，不真等待）。"""

    async def __call__(self, _):
        await asyncio.sleep(0)
