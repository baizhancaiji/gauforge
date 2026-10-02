"""SSE 事件总线真实化测试（m1-plan B11；§5 测试表 test_sse_events 逐条）。

- 15 类事件全部由真实动作触发（REST 端点 + 引擎 FakeGateway 流；M0 mock
  推流剧本已退役；update 两事件由检查/apply 真实动作触发，D5），并经
  emit→重放窗口→fanout→broker 交付为帧；
- seq 全局单调递增；服务重启后延续（sse_seq 持久化，重连不误判、超窗仍走
  快照）；
- Last-Event-ID 窗口内按序重放；
- 心跳间隔生效（sse_heartbeat_seconds）。

SSE 异步断言约定（m1-plan §5）：统一轮询等待 helper（deadline 5s），禁裸
sleep；事件序断言仅限同 execution 内。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.main import app
from web.src.mock import get_state
from web.src.services import update as update_svc
from web.src.sse import _replay_or_snapshot, broker, event_stream
from web.src.store import executions, queues, seats, settings, tasks
from web.src.store.db import now_iso

SIMPLE = "%chk=w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"

# 领域事件全集（15 类除去 system.heartbeat/system.snapshot，后两者见专测）
DOMAIN_EVENTS = {
    "candidates.changed", "queues.changed", "queue.status",
    "pending.snapshot", "task.status", "execution.progress",
    "execution.monitor", "execution.stalled", "history.appended",
    "settings.updated", "hq.status", "update.progress", "update.phase",
}

# 契约 sse.md §2 事件全集（15 类，零漂移载体）
CONTRACT_EVENT_FULL_SET = {
    "system.heartbeat", "system.snapshot", *DOMAIN_EVENTS,
}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


@pytest.fixture(autouse=True)
def clean_event_bus():
    """事件总线隔离：MockState 是跨用例单例，历史窗口须每用例清空
    （SQLite 走 conftest 隔离，序号每用例自然归零）。"""
    st = get_state()
    st.event_history.clear()
    broker._subscribers.clear()
    broker._counter = 0
    yield
    st.event_history.clear()
    broker._subscribers.clear()


@pytest.fixture()
def gw() -> FakeGateway:
    return FakeGateway(cpus=8)


@pytest.fixture()
def update_channel(tmp_path, monkeypatch):
    """更新域测试通道：部署形态布局 + 本地伪装 release（v2.1.1）+
    拉起/自退替换桩（不真 Popen、不真 SIGTERM、不触真实网络）。"""
    (tmp_path / "VERSION").write_text("v2.0.0", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "hq").write_bytes(b"\x7fELF")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    tar = b"GAUFORGE-FAKE-TAR"
    sha = (f"{hashlib.sha256(tar).hexdigest()}  "
           f"{config.UPDATE_ASSET}\n").encode()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/VERSION"):
            # 必然比本地新（tag 后基线上移不翻转前提，conftest helper）
            from .conftest import newer_version
            return httpx.Response(200, content=newer_version().encode())
        if url.endswith(".sha256"):
            return httpx.Response(200, content=sha)
        return httpx.Response(200, content=tar,
                              headers={"content-length": str(len(tar))})

    monkeypatch.setattr(
        update_svc, "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(update_svc.UpdateService, "_popen",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(update_svc.UpdateService, "_self_terminate",
                        staticmethod(lambda: None))
    return tmp_path


def make_disp(gw) -> Dispatcher:
    """引擎事件走生产发射通路（emit → 重放窗口 → fanout → broker）。"""
    return Dispatcher(gw, emitter=lambda e, d: get_state().emit(e, d))


def wait_until(pred, *, deadline_s: float = 5.0) -> bool:
    """轮询等待 helper（m1-plan §5：deadline 5s，禁裸 sleep）。"""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def history(name: str | None = None) -> list[dict]:
    return [e for e in get_state().event_history
            if name is None or e["event"] == name]


def add_input(text: str = SIMPLE, name: str = "h2o.gjf") -> int:
    tid = tasks().create_candidate(name, "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(text, encoding="utf-8")
    return tid


def submit_seat(tid: int) -> None:
    seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)


def drain_queue(q) -> list:
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except asyncio.QueueEmpty:
            return out


# ---------------- 13 类事件：真实动作触发 + 管道端到端交付 ----------------

def test_domain_events_from_real_actions(gw, update_channel):
    settings().set("stall_threshold_minutes", 0.01)  # 停滞翻转秒级可观测
    settings().set("update_check_interval", "never")  # 调度协程空转，事件确定性归本用例动作
    disp = make_disp(gw)
    disp.tick()  # HQ 连通性探测 → hq.status(up)（首个 tick 定初值）

    with TestClient(app) as client:  # lifespan 拉起 fanout
        sub_id = broker.subscribe()
        try:
            q = broker._subscribers[sub_id]
            # ① 导入 → candidates.changed(created)
            r = client.post("/api/v1/candidates", files=[
                ("files", ("h2o.gjf", SIMPLE.encode(), "text/plain"))])
            assert r.status_code == 201
            tid = r.json()["files"][0]["id"]
            # ② 行内提交 → candidates.changed(moved_out) + pending.snapshot
            assert client.post(
                f"/api/v1/candidates/{tid}/submit").status_code == 200
            # ③ 派发 → task.status(staged→running)
            disp.advance()
            row = executions().list_by_state("running")[0]
            eid = row["id"]
            run_d = config.HOME_DIR / "run" / str(eid)
            gw.set_state(str(row["hq_job_id"]), "running")
            disp.tick()  # started_at 回填 + 监视器播种
            # ④ psutil 采样：真实子进程驻留 run/<id>/ → execution.monitor
            proc = subprocess.Popen(
                [sys.executable, "-c", "import time;time.sleep(8)"],
                cwd=str(run_d))
            try:
                assert wait_until(lambda: disp.tick() or bool(
                    history("execution.monitor")))
                # ⑤ 增量解析：先写首行并 tick（首读快进吞掉既有内容），
                #    再追加新行 → execution.progress（B8 位点续传语义）
                (run_d / "input.log").write_text(
                    " Step number   1 out of a maximum of   5\n",
                    encoding="utf-8")
                disp.tick()
                with (run_d / "input.log").open("a", encoding="utf-8") as fh:
                    fh.write(" Step number   2 out of a maximum of   5\n")
                assert wait_until(lambda: disp.tick() or bool(
                    history("execution.progress")))
                # ⑥ 停滞：超阈值（0.01min）无新进度 → execution.stalled
                assert wait_until(lambda: disp.tick() or bool(
                    history("execution.stalled")))
                # ⑦ 正常结束 → task.status(succeeded) + history.appended
                gw.set_state(str(row["hq_job_id"]), "finished")
                disp.tick()
                assert history("history.appended")
                # ⑧ 队列席位派发 → queue.status(submitted→executing)
                qid = "q00001"
                queues().create(qid, name="t", skip_failed=False)
                m = add_input(name="member.gjf")
                tasks().enqueue(m, qid, 0)
                queues().set_state(qid, "submitted")
                seats().append(kind="queue", queue_id=qid)
                disp.advance()
                assert history("queue.status")
                # ⑨ 队列创建端点（真实 queues/tasks 存储：成员须为真实候选）
                qc = client.post("/api/v1/candidates", files=[
                    ("files", ("qm1.gjf", SIMPLE.encode(), "text/plain")),
                    ("files", ("qm2.gjf", SIMPLE.encode(), "text/plain"))])
                assert qc.status_code == 201
                qm = [f["id"] for f in qc.json()["files"]]
                assert client.post("/api/v1/queues", json={
                    "name": "q", "member_ids": qm}).status_code == 201
                # ⑩ 设置保存 → settings.updated
                assert client.put("/api/v1/settings", json={
                    "values": {"listen_port": 8301}}).status_code == 200
                # 收尾 ⑧ 派发的席位任务：清空 running（更新守卫放行）
                seat_row = executions().list_by_state("running")[0]
                gw.set_state(str(seat_row["hq_job_id"]), "finished")
                disp.tick()
                # ⑪ 检查更新 → update.phase(checking→available；只发现不安装)
                assert client.post("/api/v1/update/check").status_code == 200
                # ⑫ 立即更新（受理 202）→ update.progress（下载）+
                #    update.phase(downloading→installing→restarting)，
                #    后台流水线在 portal loop 运行、脚本由替换桩接管
                assert client.post("/api/v1/update/apply").status_code == 202

                frames: list = []
                got = wait_until(lambda: (
                    frames.extend(drain_queue(q)),
                    {f.event for f in frames} >= DOMAIN_EVENTS)[1])
                assert got, (
                    "15 类领域事件应由真实动作触发并经 broker 交付",
                    sorted({f.event for f in frames}))
                # update.phase 流转终态：后台流水线跑至 restarting
                phase_names = lambda: [json.loads(f.data)["phase"]
                                       for f in frames + drain_queue(q)
                                       if f.event == "update.phase"]
                assert wait_until(lambda: "restarting" in phase_names())
                assert wait_until(lambda: any(
                    f.event == "update.progress" for f in frames))
            finally:
                proc.terminate()
                proc.wait()
            # 帧序全局严格递增（fanout 按历史序广播）
            ids = [int(f.id) for f in frames]
            assert ids == sorted(ids) and len(ids) == len(set(ids))
            # 同 execution 内：task.status(running) 早于 history.appended
            same = [f for f in frames
                    if f.event in ("task.status", "history.appended")
                    and json.loads(f.data).get("execution_id") == eid]
            kinds = [(f.event, json.loads(f.data)["to" if f.event ==
                      "task.status" else "state"]) for f in same]
            assert kinds.index(("task.status", "running")) \
                < kinds.index(("history.appended", "succeeded"))
        finally:
            broker.unsubscribe(sub_id)


# ---------------- system.snapshot：真实 store 数据源 ----------------

def test_snapshot_serves_real_store(gw):
    disp = make_disp(gw)
    tid = add_input()
    submit_seat(tid)
    disp.advance()
    eid = executions().list_by_state("running")[0]["id"]

    async def first_frame():
        sub_id = broker.subscribe()
        try:
            await _replay_or_snapshot(sub_id, None)
            return await asyncio.wait_for(
                broker._subscribers[sub_id].get(), 3.0)
        finally:
            broker.unsubscribe(sub_id)

    frame = asyncio.run(asyncio.wait_for(first_frame(), 5.0))
    assert frame.event == "system.snapshot"
    data = json.loads(frame.data)
    assert [e["id"] for e in data["executions_running"]] == [eid]
    assert data["pending"]["capacity"]["occupied"] == 1
    assert data["server_restarted"] is False


# ---------------- seq：单调 + 重启延续（sse_seq 持久化） ----------------

def test_seq_monotonic_and_continues_across_restart(gw):
    disp = make_disp(gw)
    tid = add_input()
    submit_seat(tid)
    disp.advance()
    old_ids = [e["id"] for e in history()]
    assert old_ids == sorted(old_ids) and len(old_ids) == len(set(old_ids))
    assert len(old_ids) > 0

    # 模拟服务重启：内存重放窗口丢失，sse_seq 持久化留存
    max_old = max(old_ids)
    get_state().event_history.clear()
    from web.src.store import sse_seq
    assert sse_seq().current() == max_old  # 计数已落库

    row = executions().list_by_state("running")[0]
    gw.set_state(str(row["hq_job_id"]), "finished")
    disp.tick()  # 重启后首个真实动作
    new_ids = [e["id"] for e in history()]
    assert new_ids and min(new_ids) > max_old, \
        "重启后序号应延续而非归零（重连客户端不触发误判）"

    # 重连携带重启前的 Last-Event-ID：窗口已失 → 超窗走快照（server_restarted）
    async def reconnect():
        sub_id = broker.subscribe()
        try:
            await _replay_or_snapshot(sub_id, str(old_ids[0]))
            return await asyncio.wait_for(
                broker._subscribers[sub_id].get(), 3.0)
        finally:
            broker.unsubscribe(sub_id)

    frame = asyncio.run(asyncio.wait_for(reconnect(), 5.0))
    assert frame.event == "system.snapshot"
    assert json.loads(frame.data)["server_restarted"] is True


# ---------------- Last-Event-ID：窗口内按序重放 ----------------

def test_replay_within_window_by_last_event_id(gw):
    disp = make_disp(gw)
    tid = add_input(name="a.gjf")
    submit_seat(tid)
    disp.advance()  # 真实派发 → task.status(staged→running)
    row = executions().list_by_state("running")[0]
    gw.set_state(str(row["hq_job_id"]), "finished")
    disp.tick()  # 真实终态 → task.status(succeeded) + history.appended
    #             + pending.snapshot（席位释放）

    events = history()
    assert len(events) >= 3
    last_id = events[0]["id"]

    async def replay():
        sub_id = broker.subscribe()
        try:
            await _replay_or_snapshot(sub_id, str(last_id))
            q = broker._subscribers[sub_id]
            out = []
            while not q.empty():
                out.append(await q.get())
            return out
        finally:
            broker.unsubscribe(sub_id)

    frames = asyncio.run(asyncio.wait_for(replay(), 5.0))
    assert frames, "窗口内重放应有帧"
    ids = [int(f.id) for f in frames]
    assert ids == sorted(ids)
    assert all(i > int(last_id) for i in ids)
    assert len(frames) == len([e for e in events if e["id"] > last_id])


# ---------------- 心跳：间隔生效（空闲段保活） ----------------

def test_heartbeat_interval():
    settings().set("sse_heartbeat_seconds", 1)

    async def collect() -> list:
        agen = event_stream(None)
        try:
            first = await asyncio.wait_for(agen.__anext__(), 3.0)
            second = await asyncio.wait_for(agen.__anext__(), 3.0)
            return [first, second]
        finally:
            await agen.aclose()

    frames = asyncio.run(asyncio.wait_for(collect(), 8.0))
    assert frames[0].event == "system.snapshot"  # 首帧快照基线
    assert frames[1].event == "system.heartbeat"  # ≈1s 空闲后保活帧


# ---------------- 契约零漂移：sse.md §2 事件全集（15 类） ----------------

def test_sse_md_event_full_set():
    """sse.md §2 事件全集与本地全集一致（15 类，零漂移载体）。"""
    import re
    text = (config.CONTRACT_PATH.parent / "sse.md").read_text(
        encoding="utf-8")
    section = text.split("## 2. 事件全集枚举")[1].split("## 3.")[0]
    events = set(re.findall(r"\| `([a-z]+\.[a-z]+)` \|", section))
    assert events == CONTRACT_EVENT_FULL_SET, sorted(events)
