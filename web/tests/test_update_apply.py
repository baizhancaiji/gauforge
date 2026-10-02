"""apply 执行流程单测（D2）。

覆盖：三守卫矩阵（源码形态 / running 在场 / 进行中互斥）、已最新幂等 200、
同步预检两 502（不进异步）、状态机全流转（downloading→installing→restarting）、
进度节流（时钟序列注入）、sha256 失败中止（现有文件分毫未动）、下载重试
（丢弃重试 / 重试上限 / 4xx 不重试）、update-state 落盘与恢复三分支及消费
清理、detached 拉起调用参数（monkeypatch Popen / 自退）。

文案断言逐字引用 services/update.py 模块常量（单一来源防漂移，全角标点）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess

import httpx
import pytest

from web.src import config
from web.src.errors import ApiError
from web.src.mock import get_state
from web.src.services import update as upd


@pytest.fixture(autouse=True)
def deploy_root(tmp_path, monkeypatch):
    """默认部署形态（VERSION + bin/hq）；伴生文件指向临时部署目录。"""
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    (tmp_path / "VERSION").write_text("v2.0.0", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "hq").write_bytes(b"\x7fELF")
    yield tmp_path


@pytest.fixture(autouse=True)
def fresh_service():
    upd.reset_service()
    get_state().event_history.clear()
    yield
    upd.reset_service()
    get_state().event_history.clear()


@pytest.fixture(autouse=True)
def no_launch(monkeypatch):
    """拉起与自退替换为记录调用（测试不真 Popen / 不真 SIGTERM）。"""
    calls = {"popen": None, "terminate": 0}

    def fake_popen(args, **kwargs):
        calls["popen"] = {"args": list(args), "kwargs": kwargs}
        return None

    def fake_terminate():
        calls["terminate"] += 1

    monkeypatch.setattr(upd.UpdateService, "_popen",
                        staticmethod(fake_popen))
    monkeypatch.setattr(upd.UpdateService, "_self_terminate",
                        staticmethod(fake_terminate))
    yield calls


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(upd, "_sleep", lambda s: sleeps.append(s))
    yield sleeps


class FakeRelease:
    """本地伪装 release：VERSION / .sha256 / 固定名包三附件按路径响应。"""

    def __init__(self, version: bytes | None = None, tar: bytes = b"PAYLOAD"):
        if version is None:  # 缺省即「必然比本地新」：tag 后基线上移不翻转前提
            from .conftest import newer_version
            version = newer_version().encode()
        self.version = version
        self.tar = tar
        self.tar_chunks: list[bytes] | None = None  # 流式分块（进度测试用）
        self.sha_line = (f"{hashlib.sha256(tar).hexdigest()}  "
                         f"{config.UPDATE_ASSET}\n").encode()
        self.calls: list[str] = []
        self.version_exc: Exception | None = None
        self.sha_status = 200
        self.tar_status = 200
        self.tar_exc: Exception | None = None
        self.tar_exc_times = 0  # 前 N 次 asset 请求抛 tar_exc（重试场景）

    def client(self) -> httpx.Client:
        outer = self

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url.endswith("/VERSION"):
                outer.calls.append("VERSION")
                if outer.version_exc is not None:
                    raise outer.version_exc
                return httpx.Response(200, content=outer.version)
            if url.endswith(".sha256"):
                outer.calls.append("sha256")
                return httpx.Response(outer.sha_status, content=outer.sha_line)
            outer.calls.append("asset")
            if outer.tar_exc is not None and \
                    outer.calls.count("asset") <= outer.tar_exc_times:
                raise outer.tar_exc
            body = (iter(outer.tar_chunks)
                    if outer.tar_chunks is not None else outer.tar)
            return httpx.Response(outer.tar_status, content=body,
                                  headers={"content-length":
                                           str(len(outer.tar))})
        return httpx.Client(transport=httpx.MockTransport(handler))


def _events() -> list[dict]:
    return [{"event": e["event"],
             "data": json.loads(e["data"]) if isinstance(e["data"], str)
             else e["data"]}
            for e in get_state().event_history]


def _phases() -> list[dict]:
    return [e["data"] for e in _events() if e["event"] == "update.phase"]


def _progress() -> list[dict]:
    return [e["data"] for e in _events() if e["event"] == "update.progress"]


def _make_running_execution() -> None:
    from web.src import store
    tid = store.tasks().create_candidate("running.gjf", "imported")
    store.executions().create(
        task_id=tid, filename="running.gjf",
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})


def _write_state(target: str, phase: str, deploy_root) -> None:
    (deploy_root / "update-state").write_text(
        json.dumps({"target_version": target, "phase": phase,
                    "started_at": "2026-09-28T12:00:00+08:00"}),
        encoding="utf-8")


# ---------------- 守卫矩阵 ----------------

def test_apply_unsupported_source_form(deploy_root):
    (deploy_root / "VERSION").unlink()
    with pytest.raises(ApiError) as ei:
        upd.get_service().apply()
    assert ei.value.code == "UPDATE_UNSUPPORTED"
    assert ei.value.http == 409
    assert ei.value.message == "当前为源码运行模式，请通过 git 更新"
    assert _phases() == []  # 守卫在状态机外，不翻相


def test_apply_blocked_running(deploy_root):
    _make_running_execution()
    with pytest.raises(ApiError) as ei:
        upd.get_service().apply(FakeRelease().client())
    assert ei.value.code == "UPDATE_BLOCKED_RUNNING"
    assert ei.value.http == 409
    assert ei.value.message == "为保证运行稳定性，任务执行期间禁止更新"


def test_apply_in_progress_mutex_wins_over_running(deploy_root):
    """重复触发优先于 running 判定（互斥在前，重复点击提示准确）。"""
    svc = upd.get_service()
    svc.apply(FakeRelease().client())  # 受理第一发（持互斥，未跑流水线）
    _make_running_execution()
    with pytest.raises(ApiError) as ei:
        svc.apply(FakeRelease().client())
    assert ei.value.code == "UPDATE_IN_PROGRESS"
    assert ei.value.message == "更新流程进行中，请勿重复触发"


# ---------------- 幂等与同步预检 ----------------

def test_apply_up_to_date_idempotent_200():
    release = FakeRelease(version=b"v2.0.0")
    svc = upd.get_service()
    st = svc.apply(release.client())
    assert st["phase"] == "up_to_date"
    assert st["message"] == "当前版本已最新！"
    assert [p["phase"] for p in _phases()] == ["up_to_date"]


def test_apply_precheck_check_failed_502():
    release = FakeRelease()
    release.version_exc = httpx.ConnectTimeout("boom")
    svc = upd.get_service()
    with pytest.raises(ApiError) as ei:
        svc.apply(release.client())
    assert ei.value.code == "UPDATE_CHECK_FAILED"
    assert ei.value.http == 502
    assert ei.value.message == "连接超时，请检查网络"
    assert svc.phase == "failed"
    assert "asset" not in release.calls and "sha256" not in release.calls


def test_apply_precheck_sha_failed_502():
    release = FakeRelease()
    release.sha_status = 404
    svc = upd.get_service()
    with pytest.raises(ApiError) as ei:
        svc.apply(release.client())
    assert ei.value.code == "UPDATE_DOWNLOAD_FAILED"
    assert ei.value.http == 502
    assert ei.value.message == "更新服务器返回异常（HTTP 404）"
    assert "asset" not in release.calls  # 预检失败不进异步


def test_apply_precheck_failure_keeps_previous_check_state():
    upd.record_check(success=True, latest_version="v2.0.5", had_update=True)
    release = FakeRelease()
    release.version_exc = httpx.ConnectError("down")
    with pytest.raises(ApiError):
        upd.get_service().apply(release.client())
    st = upd.load_check_state()
    assert st["latest_version"] == "v2.0.5"  # 探测失败保留上一份成功值


# ---------------- 受理与全流转 ----------------

def test_apply_accepted_full_pipeline(deploy_root, no_launch):
    release = FakeRelease()
    svc = upd.get_service()
    st = svc.apply(release.client())
    assert st["phase"] == "downloading"
    state = json.loads(
        (deploy_root / "update-state").read_text(encoding="utf-8"))
    assert state["target_version"] == release.version.decode()
    assert state["phase"] == "downloading"
    assert state["started_at"]
    asyncio.run(svc.run_pending())
    names = [e["event"] for e in _events()]
    assert names[0] == "update.phase"
    assert "update.progress" in names
    tail = [e["data"]["phase"] for e in _events()
            if e["event"] == "update.phase"]
    assert tail == ["downloading", "installing", "restarting"]
    progress = _progress()
    assert progress[-1]["version"] == release.version.decode()
    assert progress[-1]["percent"] == 100
    assert all("speed_bps" in p and "ts" in p for p in progress)
    # detached 拉起参数：列表参数、部署目录 cwd、脱离进程组、日志重定向
    popen = no_launch["popen"]
    assert popen["args"] == ["bash", str(deploy_root / "self_update.sh")]
    assert popen["kwargs"]["cwd"] == str(deploy_root)
    assert popen["kwargs"]["start_new_session"] is True
    assert popen["kwargs"]["stdin"] == subprocess.DEVNULL
    assert popen["kwargs"]["stdout"] is not None
    assert no_launch["terminate"] == 1
    # 校验通过的载荷已移交部署目录伴生文件（脚本解压覆盖后清理）
    assert (deploy_root / upd.PAYLOAD_NAME).read_bytes() == b"PAYLOAD"
    # 流水线结束后 update-state 翻至 restarting（done 由脚本收尾置写）
    state = json.loads(
        (deploy_root / "update-state").read_text(encoding="utf-8"))
    assert state["phase"] == "restarting"
    # 互斥随流水线结束释放
    assert svc._apply_mutex.acquire(blocking=False)
    svc._apply_mutex.release()


def test_apply_sha256_mismatch_aborts_untouched(deploy_root):
    release = FakeRelease()
    release.sha_line = f"{'0' * 64}  {config.UPDATE_ASSET}\n".encode()
    svc = upd.get_service()
    svc.apply(release.client())
    before = {(deploy_root / "VERSION").read_bytes(),
              (deploy_root / "bin" / "hq").read_bytes()}
    asyncio.run(svc.run_pending())
    assert svc.phase == "failed"
    assert [p["phase"] for p in _phases()] == ["downloading", "failed"]
    failed = [p for p in _phases() if p["phase"] == "failed"][-1]
    assert failed["message"] == \
        "更新包校验失败，已中止（现有版本未受影响）"
    state = json.loads(
        (deploy_root / "update-state").read_text(encoding="utf-8"))
    assert state["phase"] == "failed"
    after = {(deploy_root / "VERSION").read_bytes(),
             (deploy_root / "bin" / "hq").read_bytes()}
    assert before == after  # 现有文件分毫未动


# ---------------- 下载重试 ----------------

def test_apply_retry_exhausted(deploy_root, no_sleep):
    release = FakeRelease()
    release.tar_exc = httpx.ConnectError("reset")
    release.tar_exc_times = 10  # 恒失败
    svc = upd.get_service()
    svc.apply(release.client())
    asyncio.run(svc.run_pending())
    assert svc.phase == "failed"
    assert [p["phase"] for p in _phases()] == ["downloading", "failed"]
    failed = [p for p in _phases() if p["phase"] == "failed"][-1]
    assert failed["message"] == ("下载中断：无法连接更新服务器，请检查网络"
                                 "（重试已达上限，已停止更新）")
    assert release.calls.count("asset") == 4  # 首次 + 3 次重试
    assert no_sleep == [1.0, 2.0, 4.0]  # 指数退避


def test_apply_4xx_no_retry(deploy_root, no_sleep):
    release = FakeRelease()
    release.tar_status = 403
    svc = upd.get_service()
    svc.apply(release.client())
    asyncio.run(svc.run_pending())
    assert svc.phase == "failed"
    failed = [p for p in _phases() if p["phase"] == "failed"][-1]
    assert failed["message"] == "更新服务器返回异常（HTTP 403）"
    assert release.calls.count("asset") == 1  # 4xx 不重试
    assert no_sleep == []


def test_apply_retry_recovers(deploy_root, no_sleep):
    release = FakeRelease()
    release.tar_exc = httpx.ConnectTimeout("blip")
    release.tar_exc_times = 2  # 前 2 次中断、第 3 次成功
    svc = upd.get_service()
    svc.apply(release.client())
    asyncio.run(svc.run_pending())
    assert svc.phase == "restarting"  # 重试后全流程走通
    assert release.calls.count("asset") == 3
    assert no_sleep == [1.0, 2.0]


# ---------------- 进度节流（时钟序列注入） ----------------

def _run_with_clock(release: FakeRelease, svc: upd.UpdateService,
                    ticks: list[float], chunk_bytes: list[bytes]) -> list[dict]:
    """注入预设单调时钟序列与分块流；_consume_stream 依次消费
    （起点 + 每 chunk + 终值各消耗一个时钟值）。"""
    tar = b"".join(chunk_bytes)
    release.tar = tar
    release.tar_chunks = chunk_bytes  # 保证 iter_bytes 逐块 yield
    release.sha_line = (f"{hashlib.sha256(tar).hexdigest()}  "
                        f"{config.UPDATE_ASSET}\n").encode()
    seq = iter(ticks)
    real = upd._monotonic
    upd._monotonic = lambda: next(seq)  # type: ignore[assignment]
    try:
        svc.apply(release.client(), chunk_size=25)
        asyncio.run(svc.run_pending())
    finally:
        upd._monotonic = real  # type: ignore[assignment]
    return _progress()


def test_progress_throttle_within_window():
    """窗口内多条推最新：0.1s 步进（<500ms 窗口）→ 循环内不推、仅终值一条。"""
    svc = upd.get_service()
    progress = _run_with_clock(FakeRelease(), svc,
                               ticks=[0.0, 0.1, 0.2, 0.3, 0.4, 0.45],
                               chunk_bytes=[bytes(25)] * 4)
    assert len(progress) == 1
    assert progress[0]["percent"] == 100


def test_progress_emits_per_window():
    """0.6s 步进（>500ms 窗口）→ 每 chunk 一条 + 终值收口。"""
    svc = upd.get_service()
    release = FakeRelease()
    progress = _run_with_clock(release, svc,
                               ticks=[0.0, 0.6, 1.2, 1.8, 2.4, 3.0],
                               chunk_bytes=[bytes(25)] * 4)
    assert [p["percent"] for p in progress] == [25, 50, 75, 100, 100]
    assert all(p["version"] == release.version.decode() for p in progress)


# ---------------- update-state 恢复（§3.4 三分支） ----------------

def test_recover_done_reached(monkeypatch, deploy_root):
    monkeypatch.setattr(config, "APP_VERSION", "v2.1.1")
    _write_state("v2.1.1", "done", deploy_root)
    svc = upd.get_service()
    svc.recover_from_disk()
    st = svc.status()
    assert st["phase"] == "done"
    assert st["message"] == "v2.1.1 更新完成"
    assert not (deploy_root / "update-state").exists()  # 消费后删除
    assert svc.status()["phase"] == "done"  # 内存相保持


def test_recover_done_unreached(monkeypatch, deploy_root):
    monkeypatch.setattr(config, "APP_VERSION", "v2.1.1")
    _write_state("v2.2.0", "done", deploy_root)
    svc = upd.get_service()
    svc.recover_from_disk()
    st = svc.status()
    assert st["phase"] == "failed"
    assert st["message"] == ("更新流程曾中断（目标版本 v2.2.0 未达成），"
                             "请重新执行更新或通过 CLI update.sh 恢复")
    assert not (deploy_root / "update-state").exists()


def test_recover_interrupted_phases(monkeypatch, deploy_root):
    monkeypatch.setattr(config, "APP_VERSION", "v2.1.1")
    for phase in ("downloading", "installing", "restarting", "failed"):
        upd.reset_service()
        _write_state("v2.1.1", phase, deploy_root)
        svc = upd.get_service()
        svc.recover_from_disk()
        st = svc.status()
        assert st["phase"] == "failed", phase
        assert "更新流程曾中断" in st["message"]
        assert not (deploy_root / "update-state").exists()


def test_recover_no_state_noop():
    svc = upd.get_service()
    svc.recover_from_disk()
    assert svc.phase == "idle"
    assert _phases() == []
