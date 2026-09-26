"""整队端到端生命周期测试（m2-plan §5「D 前置」，随提交 #12 落盘）。

fake g16 整队全链路：创建（改名/排序）→直接提交（含提交核验规范化）→
中段失败（未勾跳过：后续 skipped+predecessor_failed、执行序列越过队列
补位）→回退（标记/次数/归因落库）→编辑失败成员（blocks 保存）→重提交→
哈希跳过（上次成功未变成员无新执行记录）+重跑（已变者新执行）→移除全部
failed/skipped→自动成功；SSE 事件序符合 sse.md §3。

依赖真 hq（hq 不在 PATH 时跳过；AGENTS §6.1 第 4 条 hq 产物前置检查）。
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.engine import Dispatcher
from web.src.hq.cli_gateway import CliGateway
from web.src.hq.process import HqProcessManager
from web.src.main import app
from web.src.mock import get_state
from web.src.services.candidates import import_files, save_block
from web.src.store import executions, queues, seats, settings, tasks

HQ = shutil.which("hq")
client = TestClient(app)

BASE = "%mem=1GB\n#p hf/sto-3g\n\nt{}\n\n0 1\nO 0 0 0\n\n"


def _inp(n: int, *, fail: bool = False, crlf: bool = False) -> str:
    text = BASE.format(n)
    if fail:
        text = text.replace("#p hf/sto-3g",
                            "#p hf/sto-3g\n! FAKE: exit=1")  # route 内嵌失败
    if crlf:
        text = text.replace("\n", "\r\n")
    return text


@pytest.mark.skipif(HQ is None, reason="hq 不在 PATH")
def test_e2e_queue_full_lifecycle(tmp_path, monkeypatch):
    """工作区隔离（HOME_DIR → tmp）必须先于任何导入写盘。"""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    (tmp_path / "inputs").mkdir()
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    shutil.copy(Path(__file__).parent / "fake_g16.py", fakebin / "g16")
    settings().set("g16_root", str(fakebin))
    settings().set("link0_default_nproc", 1)
    monkeypatch.setenv("G16_FAKE", "sleep=0.1;steps=1")

    # 导入三成员：m0 规范化样本（CRLF）、m1 失败样本、m2 失败样本
    m0 = import_files([("m0.gjf", _inp(0, fail=False, crlf=True).encode())])[0]["id"]
    m1 = import_files([("m1.gjf", _inp(1, fail=True).encode())])[0]["id"]
    m2 = import_files([("m2.gjf", _inp(2, fail=True).encode())])[0]["id"]

    # 创建（2–10 校验）→ 改名/排序（PATCH）
    r = client.post("/api/v1/queues", json={
        "name": "e2e队", "member_ids": [m1, m0, m2], "skip_failed": False})
    assert r.status_code == 201
    qid = r.json()["id"]
    r = client.patch(f"/api/v1/queues/{qid}",
                     json={"name": "e2e队改", "member_ids": [m0, m1, m2]})
    assert r.status_code == 200
    assert r.json()["member_ids"] == [m0, m1, m2]

    # 直接提交：提交核验规范化 m0（CRLF）→ normalized=true
    r = client.post(f"/api/v1/queues/{qid}/submit")
    assert r.status_code == 200
    assert r.json()["normalized"] is True
    assert b"\r" not in (tmp_path / "inputs" / str(m0)).read_bytes()

    # 队列后置一个单任务席位（验证失败回退后执行序列越过队列补位）
    solo = import_files([("solo.gjf", _inp(9).encode())])[0]["id"]
    r = client.post(f"/api/v1/candidates/{solo}/submit")
    assert r.status_code == 200

    records: list[tuple[str, dict]] = []
    ws = tmp_path / "hqws"
    mgr = HqProcessManager(HQ, ws)
    mgr.start()
    mgr.ensure_worker(cpus=1)
    disp = Dispatcher(CliGateway(HQ, str(mgr.server_dir)),
                      emitter=lambda e, d: records.append((e, d)))

    def run_until(pred, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            disp.tick()
            if pred():
                return
            time.sleep(0.1)
        raise AssertionError(
            "等待超时: "
            f"queue={queues().get(qid)['state']}/{queues().get(qid)['rollback_count']}"
            f" seats={seats().count()}"
            f" running={executions().list_by_state('running')}"
            f" workers={disp._gw.workers()}")

    try:
        # ---- 第一轮：m0 成功 → m1 失败 → m2 skipped + 整队回退 → solo 补位
        run_until(lambda: queues().get(qid)["state"] == "unsubmitted"
                  and bool(queues().get(qid)["rollback_flag"]))
        run_until(lambda: seats().count() == 0 and executions().list_by_task(solo)
                  and executions().list_by_task(solo)[-1]["state"] == "succeeded")

        # 归因落库：回退标记/次数/last_failure.members
        q = queues().get(qid)
        assert q["finish_reason"] == "abort_on_failure"
        assert int(q["rollback_count"]) == 1
        lf = q["last_failure"]
        assert lf["members"] == [{"task_id": m1, "state": "failed",
                                  "cause": "program_error"}]
        # 执行结局：m0 succeeded / m1 failed / m2 skipped(predecessor_failed)
        assert executions().list_by_task(m0)[-1]["state"] == "succeeded"
        e1 = executions().list_by_task(m1)
        assert len(e1) == 1 and e1[-1]["state"] == "failed"
        e2 = executions().list_by_task(m2)
        assert len(e2) == 1 and e2[-1]["state"] == "skipped"
        assert e2[-1]["cause"] == "predecessor_failed"
        # 提交核验规范化后的输入进入执行（run 副本无 \r）
        run0 = tmp_path / "run" / str(executions().list_by_task(m0)[-1]["id"])
        assert b"\r" not in (run0 / "input.gjf").read_bytes()
        # SSE 序（sse.md §3 任务失败行）：failed → skipped → queue.status →
        # queues.changed → pending.snapshot
        evs = [(ev, d) for ev, d in records]

        def seq(items):
            pos = -1
            for ev, d in items:
                start = pos + 1
                hit = next((i for i in range(start, len(evs))
                            if evs[i][0] == ev and (not ev or True)
                            and _match(d, evs[i][1])), None)
                if hit is None:
                    return False
                pos = hit
            return True

        assert seq([
            ("task.status", {"execution_id": e1[-1]["id"], "to": "failed"}),
            ("task.status", {"execution_id": e2[-1]["id"], "to": "skipped"}),
            ("queue.status", {"queue_id": qid, "to": "unsubmitted",
                              "finish_reason": "abort_on_failure"}),
            ("queues.changed", {"queue_id": qid}),
            ("pending.snapshot", {}),
        ])

        # ---- 回退编辑失败成员（blocks 保存，id 跨形态延续）：移除失败注入
        route_text = "#p hf/sto-3g opt"
        r = client.put(f"/api/v1/candidates/{m1}/blocks/route",
                       json={"lines": [route_text]})
        assert r.status_code == 200, r.text
        assert r.json()["blocks"]["route"] == route_text
        assert "FAKE" not in (tmp_path / "inputs" / str(m1)).read_text()

        # ---- 第二轮重提交：m0 哈希跳过 / m1 重跑成功 / m2 失败 → 回退 #2
        n_exec_m0 = len(executions().list_by_task(m0))
        r = client.post(f"/api/v1/queues/{qid}/submit")
        assert r.status_code == 200
        assert r.json()["normalized"] is False  # 已规范：无变化零操作
        run_until(lambda: int(queues().get(qid)["rollback_count"]) == 2)

        # 哈希跳过：m0 无新执行记录（状态保持 succeeded）
        assert len(executions().list_by_task(m0)) == n_exec_m0
        assert executions().list_by_task(m0)[-1]["state"] == "succeeded"
        # 已变者重跑：m1 新执行且成功；m2 重跑失败
        e1b = executions().list_by_task(m1)
        assert len(e1b) == 2 and e1b[-1]["state"] == "succeeded"
        e2b = executions().list_by_task(m2)
        assert len(e2b) == 2 and e2b[-1]["state"] == "failed"

        # ---- 移除全部 failed/skipped 成员 → 自动成功
        r = client.patch(f"/api/v1/queues/{qid}", json={"member_ids": [m0, m1]})
        assert r.status_code == 200
        q = queues().get(qid)
        assert q["state"] == "completed"
        assert q["finish_reason"] == "success"
        assert q["last_failure"] is None  # 成功终态清 null
        # failed 成员移除分流：以实际执行副本新建候选（returned_failed）
        spawned = [c for c in tasks().list_by_form("candidate")
                   if c["origin"] == "returned_failed"]
        assert len(spawned) == 1 and spawned[0]["id"] != m2
        # 自动成功事件（路由层经事件总线发）：queue.status(→completed, success)
        auto = [json.loads(e["data"]) for e in get_state().event_history
                if e["event"] == "queue.status"
                and json.loads(e["data"]).get("to") == "completed"
                and json.loads(e["data"]).get("finish_reason") == "success"]
        assert auto, "缺少自动成功 queue.status 事件"
        # 不可再提交（成功终态）
        r = client.post(f"/api/v1/queues/{qid}/submit")
        assert r.status_code == 409
    finally:
        mgr.stop()


def _match(pred: dict, data: dict) -> bool:
    return all(data.get(k) == v for k, v in pred.items())
