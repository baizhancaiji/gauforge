"""HQ Gateway 与进程管理测试（m1-plan B4：真 hq 二进制本地 server+worker 集成）。

无 pbs/slurm 依赖；hq 不在 PATH 时跳过真机集成用例。
HttpGateway 单测（m1-plan §5 test_hq_gateway：HttpGateway 提交/查询/停止
四端点薄桥接 + SSE 事件映射）经 httpx.MockTransport 离线驱动，不跳过。
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import httpx
import pytest

from web.src.hq.cli_gateway import CliGateway
from web.src.hq.gateway import GatewayError, derive_job_state, worker_resources
from web.src.hq.http_gateway import HttpGateway
from web.src.hq.process import HqProcessManager

HQ = shutil.which("hq")

skip_no_hq = pytest.mark.skipif(HQ is None, reason="hq 不在 PATH")


@pytest.fixture(scope="module")
def hq_env(tmp_path_factory):
    if HQ is None:
        pytest.skip("hq 不在 PATH")
    ws: Path = tmp_path_factory.mktemp("hqws")
    mgr = HqProcessManager(HQ, ws)
    mgr.start()
    mgr.ensure_worker(cpus=1)
    yield {"ws": ws, "mgr": mgr, "server_dir": mgr.server_dir}
    mgr.stop()


@skip_no_hq
def test_journal_lands_in_workspace(hq_env):
    journal = hq_env["ws"] / "hq" / "server.journal"
    assert journal.is_file() and journal.stat().st_size > 0


@skip_no_hq
def test_server_reuse_on_second_start(hq_env):
    first = hq_env["mgr"]
    second = HqProcessManager(HQ, hq_env["ws"])
    # 已有 server 在跑：复用不新起（返回 False），健康检查通过
    assert second.start() is False
    assert second.health_check()["server"] is True


@skip_no_hq
def test_worker_online(hq_env):
    workers = hq_env["mgr"].workers()
    assert any(w["online"] for w in workers)


@skip_no_hq
def test_submit_query_cancel(hq_env):
    gw = CliGateway(HQ, hq_env["server_dir"])
    jid = gw.submit(["bash", "-c", "sleep 60"], cwd=str(hq_env["ws"]),
                    name="b4probe")
    assert jid.isdigit()

    jobs = {j["id"]: j for j in gw.jobs()}
    assert jid in jobs
    assert jobs[jid]["name"] == "b4probe"
    assert jobs[jid]["state"] in ("waiting", "running")

    gw.cancel(jid)
    state = None
    for _ in range(20):
        job = {j["id"]: j for j in gw.jobs()}.get(jid)
        if job and job["state"] == "canceled":
            state = "canceled"
            break
        time.sleep(0.25)
    assert state == "canceled"

    # 事件迭代：状态变化被轮询捕获（submitted → canceled）
    events = gw.poll_events()
    assert any(e["type"] == "job_state" and e["job_id"] == int(jid)
               for e in events)


@skip_no_hq
def test_cancel_unknown_job_raises(hq_env):
    gw = CliGateway(HQ, hq_env["server_dir"])
    with pytest.raises(GatewayError):
        gw.cancel(999999)


def test_worker_resources_mem_fractions_units():
    # 回归（GUI 走查发现）：sum size 是 ResourceAmount 内部整数
    # （MiB×10000 + 万分位，tako amount.rs FRACTIONS_PER_UNIT=10_000），
    # 非 MiB 原值。158830898 → 15883 MiB（本机 worker 实测线缆值）。
    cfg = {"resources": {"resources": [
        {"name": "cpus", "start": 0, "end": 11},
        {"name": "mem", "size": 158830898}]}}
    assert worker_resources(cfg) == (12, 15883)


def test_derive_job_state_pure():
    # 纯函数：task_stats → 单一状态（canceled > failed > finished > running > waiting）
    assert derive_job_state({"canceled": 0, "failed": 0, "finished": 0,
                             "running": 0, "waiting": 2}, None) == "waiting"
    assert derive_job_state({"canceled": 0, "failed": 0, "finished": 1,
                             "running": 1, "waiting": 0}, None) == "running"
    assert derive_job_state({"canceled": 0, "failed": 0, "finished": 2,
                             "running": 0, "waiting": 0}, None) == "finished"
    assert derive_job_state({"canceled": 0, "failed": 1, "finished": 1,
                             "running": 0, "waiting": 0}, None) == "failed"
    assert derive_job_state({"canceled": 1, "failed": 0, "finished": 0,
                             "running": 0, "waiting": 0}, None) == "canceled"
    assert derive_job_state({"canceled": 0, "failed": 0, "finished": 0,
                             "running": 0, "waiting": 1}, "by user") == "canceled"


# ---------------- HttpGateway：REST 薄桥接（MockTransport 离线驱动） ----------------

def fake_hq_handler(request: httpx.Request) -> httpx.Response:
    """对齐 server 侧 JSON 形状（format_job_info / format_worker_info）。"""
    path = request.url.path
    if request.method == "GET" and path == "/info":
        return httpx.Response(200, json={"version": "test", "uptime_seconds": 1})
    if request.method == "POST" and path == "/jobs":
        body = json.loads(request.content)
        assert body["args"] == ["g16", "input.gjf"]
        assert body["cwd"] == "/run/1"
        assert body["resources"] == {"cpus": 2, "mem_mib": 1024}
        return httpx.Response(200, json={"id": 7, "name": body.get("name")})
    if request.method == "GET" and path == "/jobs":
        return httpx.Response(200, json=[{
            "id": 7, "name": "b4http", "task_count": 1, "is_open": False,
            "task_stats": {"running": 0, "finished": 1, "failed": 0,
                           "canceled": 0, "aborted": 0, "waiting": 0},
            "cancel_reason": None,
        }])
    if request.method == "POST" and path == "/jobs/7/cancel":
        return httpx.Response(200, json={"id": 7, "canceled_tasks": 1,
                                         "already_finished": False})
    if request.method == "POST" and path == "/jobs/404/cancel":
        return httpx.Response(404, json={"error": "job 404 not found"})
    if request.method == "GET" and path == "/workers":
        return httpx.Response(200, json=[{
            "id": 3,
            "configuration": {"hostname": "wsl",
                              "resources": {"resources": [
                                  {"name": "cpus", "start": 0, "end": 3},
                                  {"name": "mem", "size": 158830000}]}},
            "ended": None,
        }])
    return httpx.Response(500, json={"error": "unmocked"})


def wait_events(gw: HttpGateway, n: int, deadline_s: float = 5.0) -> list[dict]:
    """轮询等待 helper（deadline 5s，禁止裸 sleep，§5 SSE 异步断言约定）。"""
    got: list[dict] = []
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        got += gw.poll_events()
        if len(got) >= n:
            return got
        time.sleep(0.05)
    return got


def test_http_gateway_rest_endpoints():
    gw = HttpGateway("http://test",
                     transport=httpx.MockTransport(fake_hq_handler))
    try:
        assert gw.info()["version"] == "test"
        assert gw.submit(["g16", "input.gjf"], cwd="/run/1", name="b4http",
                         resources={"cpus": 2, "mem_mib": 1024}) == "7"
        jobs = gw.jobs()
        assert jobs == [{"id": "7", "name": "b4http", "state": "finished",
                         "task_count": 1,
                         "task_stats": {"running": 0, "finished": 1,
                                        "failed": 0, "canceled": 0,
                                        "aborted": 0, "waiting": 0}}]
        workers = gw.workers()
        # HQ range 闭区间：start=0 end=3 → cpus=4（worker_resources 共享解析）
        assert workers == [{"id": "3", "online": True, "hostname": "wsl",
                            "cpus": 4, "mem_mib": 15883}]
        gw.cancel("7")
    finally:
        gw.close()


def test_http_gateway_error_raises():
    gw = HttpGateway("http://test",
                     transport=httpx.MockTransport(fake_hq_handler))
    try:
        with pytest.raises(GatewayError):
            gw.cancel("404")
    finally:
        gw.close()


def test_http_gateway_sse_event_mapping():
    frames = b"""event: task_started
data: {"task_id": {"job_id": 7, "job_task_id": 0}}

event: task_notify
data: {"task_id": {"job_id": 7, "job_task_id": 0}, "message": "aa"}

event: job_completed
data: {"job_id": 7}

"""
    handler = fake_hq_handler

    def sse_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/events":
            return httpx.Response(200, content=iter([frames]),
                                  headers={"content-type":
                                           "text/event-stream"})
        return handler(request)

    gw = HttpGateway("http://test", transport=httpx.MockTransport(sse_handler))
    try:
        events = wait_events(gw, 2)
        assert events == [
            {"type": "job_state", "job_id": 7, "state": "running",
             "prev_state": None},
            {"type": "job_state", "job_id": 7, "state": "finished",
             "prev_state": "running"},
        ]
        assert gw.poll_events() == []  # 差分：无新变化不重复产出
    finally:
        gw.close()


def test_http_gateway_submit_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/jobs"
        return httpx.Response(422, json={"error": "args must not be empty"})

    gw = HttpGateway("http://test", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(GatewayError):
            gw.submit([])
    finally:
        gw.close()
