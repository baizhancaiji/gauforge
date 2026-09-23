"""HQ Gateway 与进程管理测试（m1-plan B4：真 hq 二进制本地 server+worker 集成）。

无 pbs/slurm 依赖；hq 不在 PATH 时跳过集成用例。
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from web.src.hq.cli_gateway import CliGateway
from web.src.hq.gateway import GatewayError, derive_job_state
from web.src.hq.process import HqProcessManager

HQ = shutil.which("hq")

pytestmark = pytest.mark.skipif(HQ is None, reason="hq 不在 PATH")


@pytest.fixture(scope="module")
def hq_env(tmp_path_factory):
    ws: Path = tmp_path_factory.mktemp("hqws")
    mgr = HqProcessManager(HQ, ws)
    mgr.start()
    mgr.ensure_worker(cpus=1)
    yield {"ws": ws, "mgr": mgr, "server_dir": mgr.server_dir}
    mgr.stop()


def test_journal_lands_in_workspace(hq_env):
    journal = hq_env["ws"] / "hq" / "server.journal"
    assert journal.is_file() and journal.stat().st_size > 0


def test_server_reuse_on_second_start(hq_env):
    first = hq_env["mgr"]
    second = HqProcessManager(HQ, hq_env["ws"])
    # 已有 server 在跑：复用不新起（返回 False），健康检查通过
    assert second.start() is False
    assert second.health_check()["server"] is True


def test_worker_online(hq_env):
    workers = hq_env["mgr"].workers()
    assert any(w["online"] for w in workers)


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


def test_cancel_unknown_job_raises(hq_env):
    gw = CliGateway(HQ, hq_env["server_dir"])
    with pytest.raises(GatewayError):
        gw.cancel(999999)


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
