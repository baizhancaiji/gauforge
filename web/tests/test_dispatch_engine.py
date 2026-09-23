"""派发引擎测试（m1-plan B6；§5 测试表 test_dispatch_engine 断言逐条）。

- FakeGateway 驱动：哈希跳过、Link0 补齐注入、资源停等不越位、
  并行窗口=2 双任务同时 dispatched、补位保序、失败分流语义；
- run/<id>/ 物化结构与 g16 环境；hq_job_id 回填；
- fake g16（tests/fake_g16.py）经真 CliGateway 跑通「提交→运行→终态→
  历史」首条链路（hq 不在 PATH 时跳过）。

隔离：SQLite 走 conftest autouse；config.HOME_DIR 重定向用例级 tmp_path
（inputs/ 与 run/ 均不触真实工作区）。
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.engine.workspace import content_hash, g16_env, resolve_link0
from web.src.store import executions, queues, seats, settings, tasks
from web.src.store.db import now_iso

HQ = shutil.which("hq")

SIMPLE = "%chk=/tmp/w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"
DECLARED = ("%chk=/tmp/w.chk\n%NProcShared=2\n%Mem=1GB\n\n"
            "#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """引擎触盘面（inputs/<id>、run/<id>、g16_root）整体隔离到 tmp_path。"""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


@pytest.fixture()
def rec() -> list[tuple[str, dict]]:
    return []


@pytest.fixture()
def gw() -> FakeGateway:
    return FakeGateway(cpus=8)


@pytest.fixture()
def disp(gw, rec) -> Dispatcher:
    return Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))


def add_input(text: str, name: str = "h2o.gjf") -> int:
    tid = tasks().create_candidate(name, "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(text, encoding="utf-8")
    return tid


def submit_task(tid: int) -> int:
    sid = seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)
    return sid


def make_queue(members: list[int], *, skip_failed: bool = False) -> str:
    qid = f"q{int(time.monotonic_ns() % 100000):05d}"
    queues().create(qid, name="t", skip_failed=skip_failed)
    for pos, tid in enumerate(members):
        tasks().enqueue(tid, qid, pos)
    queues().set_state(qid, "submitted")  # 提交动作（append_queue 同语义）
    seats().append(kind="queue", queue_id=qid)
    return qid


def running_rows():
    return executions().list_by_state("running")


def last(rec, ev):
    hits = [d for e, d in rec if e == ev]
    return hits[-1] if hits else None


def drain(disp):
    disp.tick()


# ---------------- Link0 解析补齐（workspace） ----------------

def test_link0_defaults_injected(home):
    r = resolve_link0(SIMPLE, 4, 8)
    assert r["nproc"] == {"value": 4, "defaulted": True}
    assert r["mem_gb"] == {"value": 8.0, "defaulted": True}
    # 补齐行注入在 Link0 区尾（%chk 行之后、route 之前），route 紧随无空行
    assert r["completed_text"].splitlines()[1] == "%NProcShared=4"
    assert r["completed_text"].splitlines()[2] == "%Mem=8GB"


def test_link0_declared_kept_and_units(home):
    r = resolve_link0(DECLARED, 4, 8)
    assert r["nproc"] == {"value": 2, "defaulted": False}
    assert r["mem_gb"] == {"value": 1.0, "defaulted": False}
    # G16 单位换算：MB→GB（1024 进制）、MW→GB（word=8B）
    assert resolve_link0("%Mem=512MB\n\n#p\n\nt\n\n0 1\nO\n", 4, 8)["mem_gb"] == {
        "value": 0.5, "defaulted": False}
    assert resolve_link0("%Mem=2MW\n\n#p\n\nt\n\n0 1\nO\n", 4, 8)["mem_gb"] == {
        "value": 2 * 8 * 1024 / 1024**3, "defaulted": False}


def test_g16_env_construction(home):
    root = home / "g16"
    env = g16_env(root, home / "run" / "7")
    assert env["GAUSS_EXEDIR"] == ":".join(
        [f"{root}/bsd", f"{root}/private/bsd", str(root)])
    assert env["GAUSS_SCRDIR"] == str(home / "run" / "7")  # 强制 SCRDIR
    assert env["PATH"].startswith(f"{root}/bsd:{root}:")
    assert env["LD_LIBRARY_PATH"].startswith(f"{root}/bsd:")


# ---------------- 串行派发：物化/提交/回填 ----------------

def test_serial_dispatch_materialize_and_backfill(home, gw, disp, rec):
    tid = add_input(SIMPLE)
    submit_task(tid)
    disp.advance()
    rows = running_rows()
    assert len(rows) == 1
    e = rows[0]
    # hq_job_id 回填（首个提交 job id = "1"）
    assert e["hq_job_id"] == 1
    # run/<id>/ 物化结构：input.gjf 含补齐行
    rd = config.HOME_DIR / "run" / str(e["id"])
    text = (rd / "input.gjf").read_text(encoding="utf-8")
    assert "%NProcShared=4" in text and "%Mem=8GB" in text
    # input_hash 对补齐后副本内容计算
    assert e["input_hash"] == content_hash(text)
    assert e["resources"] == {"nproc": {"value": 4, "defaulted": True},
                              "mem_gb": {"value": 8.0, "defaulted": True}}
    # 提交形态：program=g16（g16_root 派生绝对路径）、cwd=run/<id>/、
    # 资源双账第二账（nproc→cpus、%Mem GB→MiB）
    sub = gw.submitted[0]
    assert sub["command"] == [str(home / "g16" / "g16"), "input.gjf"]
    assert Path(sub["cwd"]) == rd
    assert sub["resources"] == {"cpus": 4, "mem_mib": 8192}
    # 事件：task.status(staged→running)
    ev = last(rec, "task.status")
    assert ev == {"task_id": tid, "execution_id": e["id"], "from": "staged",
                  "to": "running", "ts": ev["ts"]}


def test_window_one_serializes(disp, rec):
    t1, t2 = add_input(SIMPLE, "a.gjf"), add_input(SIMPLE, "b.gjf")
    submit_task(t1)
    submit_task(t2)
    disp.advance()
    assert len(running_rows()) == 1  # 窗口 1：只派队头
    drain(disp)
    assert len(running_rows()) == 1


def test_parallel_window_two_dispatched(disp, rec):
    settings().set("parallel_window", 2)
    t1, t2 = add_input(SIMPLE, "a.gjf"), add_input(SIMPLE, "b.gjf")
    submit_task(t1)
    submit_task(t2)
    disp.advance()
    rows = running_rows()
    assert len(rows) == 2  # 并行窗口=2：双任务同时 dispatched
    starts = [d for e, d in rec if e == "task.status" and d["to"] == "running"]
    assert {d["task_id"] for d in starts} == {t1, t2}


# ---------------- 资源停等（不越位） ----------------

def test_resource_stall_blocks_no_overtake(rec):
    gw = FakeGateway(cpus=2)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    big = add_input("%NProcShared=8\n\n#p\n\nt\n\n0 1\nO\n", "big.gjf")
    small = add_input("%NProcShared=1\n\n#p\n\nt\n\n0 1\nO\n", "small.gjf")
    submit_task(big)
    submit_task(small)
    disp.advance()
    # 大声明任务 8 > 空闲 2：窗口停在其上等待，不越位派发其后小任务
    assert running_rows() == []
    assert gw.submitted == []


def test_stall_releases_after_finish(rec):
    gw = FakeGateway(cpus=4)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    a = add_input("%NProcShared=4\n\n#p\n\nt\n\n0 1\nO\n", "a.gjf")
    b = add_input("%NProcShared=2\n\n#p\n\nt\n\n0 1\nO\n", "b.gjf")
    submit_task(a)
    submit_task(b)
    disp.advance()
    assert len(running_rows()) == 1  # a 占满 worker，b 停等
    drain(disp)
    assert len(running_rows()) == 1
    gw.set_state("1", "finished")  # a 结束释放 → b 补位
    disp.tick()
    rows = running_rows()
    assert len(rows) == 1 and rows[0]["task_id"] == b


def test_running_claims_block_second_task(rec):
    gw = FakeGateway(cpus=2)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    a = add_input("%NProcShared=2\n\n#p\n\nt\n\n0 1\nO\n", "a.gjf")
    b = add_input("%NProcShared=1\n\n#p\n\nt\n\n0 1\nO\n", "b.gjf")
    submit_task(a)
    submit_task(b)
    disp.advance()
    assert len(running_rows()) == 1  # a 恰好占满 2 cpus
    drain(disp)
    assert len(running_rows()) == 1  # b 停等：空闲 0，不越位


def test_mem_stall_with_worker_mem(rec):
    gw = FakeGateway(cpus=8, mem_mib=2048)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    a = add_input("%Mem=2GB\n\n#p\n\nt\n\n0 1\nO\n", "a.gjf")
    b = add_input("%Mem=1GB\n\n#p\n\nt\n\n0 1\nO\n", "b.gjf")
    submit_task(a)
    submit_task(b)
    disp.advance()
    assert len(running_rows()) == 1  # mem 2GB 占满 worker 2GiB
    drain(disp)
    assert len(running_rows()) == 1  # b 停等（mem 维度），不越位


# ---------------- 补位保序（并行 2 下前 2 结束不越位） ----------------

def test_refill_preserves_order(disp, rec):
    settings().set("parallel_window", 2)
    ids = [add_input(SIMPLE, f"{n}.gjf") for n in "abc"]
    for tid in ids:
        submit_task(tid)
    disp.advance()
    assert len(running_rows()) == 2
    disp.advance()
    assert len(running_rows()) == 2  # c 未进窗（前 2 未结束，保序）
    # a 结束 → c 立即补位；b 仍在跑
    gw_job_a = next(e["hq_job_id"] for e in running_rows()
                    if e["task_id"] == ids[0])
    disp._gw.set_state(str(gw_job_a), "finished")
    disp.tick()
    rows = running_rows()
    assert len(rows) == 2
    assert {e["task_id"] for e in rows} == {ids[1], ids[2]}


# ---------------- 哈希跳过 ----------------

def test_hash_skip_reuses_result(gw, disp, rec):
    tid = add_input(SIMPLE)
    submit_task(tid)
    disp.advance()
    gw.set_state("1", "finished")
    disp.tick()  # 跑完进历史
    n_hist = sum(1 for e, _ in rec if e == "history.appended")
    assert executions().list_by_task(tid)[-1]["state"] == "succeeded"
    # 重新提交（沿用原 id）：输入未变 → 沿用既有结果不新增执行记录
    tasks().to_seat_task(tid)
    seats().append(kind="task", task_id=tid)
    n_events = len(rec)
    disp.advance()
    # 不派发不建记录；唯一事件 = 席位离席的 pending.snapshot
    assert [e for e, _ in rec][n_events:] == ["pending.snapshot"]
    assert len(executions().list_by_task(tid)) == 1
    assert tasks().get(tid)["form"] == "finished"  # 席位离席、状态保持 succeeded
    assert seats().count() == 0


def test_hash_change_reruns(gw, disp, rec):
    tid = add_input(SIMPLE)
    submit_task(tid)
    disp.advance()
    gw.set_state("1", "finished")
    disp.tick()
    # 输入变更（route 不同 → 补齐后文本哈希不同）→ 重新执行
    (config.HOME_DIR / "inputs" / str(tid)).write_text(
        DECLARED, encoding="utf-8")
    tasks().to_seat_task(tid)
    seats().append(kind="task", task_id=tid)
    disp.advance()
    assert len(executions().list_by_task(tid)) == 2


# ---------------- 终态处理与席位释放 ----------------

def test_terminal_success_releases_seat(gw, disp, rec):
    tid = add_input(SIMPLE)
    submit_task(tid)
    disp.advance()
    eid = running_rows()[0]["id"]
    gw.set_state("1", "running")
    disp.tick()
    assert running_rows()[0]["started_at"] is not None  # running 时补启动时间
    gw.set_state("1", "finished")
    disp.tick()
    e = executions().get(eid)
    assert e["state"] == "succeeded" and e["cause"] is None
    assert e["finished_at"] is not None
    assert seats().count() == 0 and tasks().get(tid)["form"] == "finished"
    hist = [d for ev, d in rec if ev == "history.appended"]
    assert hist[-1]["execution_id"] == eid and hist[-1]["state"] == "succeeded"


def test_terminal_failed_maps_program_error(gw, disp, rec):
    tid = add_input(SIMPLE)
    submit_task(tid)
    disp.advance()
    gw.set_state("1", "failed")
    disp.tick()
    e = executions().list_by_task(tid)[-1]
    assert e["state"] == "failed" and e["cause"] == "program_error"


# ---------------- 队列失败分流 ----------------

def test_queue_abort_on_failure(disp, rec):
    m1, m2, m3 = (add_input(SIMPLE, f"m{i}.gjf") for i in (1, 2, 3))
    qid = make_queue([m1, m2, m3], skip_failed=False)
    disp.advance()  # 派 m1
    assert last(rec, "queue.status")["to"] == "executing"  # 首成员派发→执行中
    gw_job = running_rows()[0]["hq_job_id"]
    disp._gw.set_state(str(gw_job), "failed")  # m1 失败
    disp.tick()
    # 未启动成员即时 skipped(predecessor_failed)，本周期内不再派发
    states = {t: (executions().list_by_task(t) or [{}])[-1].get("state")
              for t in (m2, m3)}
    assert states == {m2: "skipped", m3: "skipped"}
    rows = executions().list_by_task(m2)
    assert rows[-1]["cause"] == "predecessor_failed"
    # 队列回退：unsubmitted + abort_on_failure + 回退标记/次数 + last_failure
    q = queues().get(qid)
    assert q["state"] == "unsubmitted"
    assert q["finish_reason"] == "abort_on_failure"
    assert q["rollback_flag"] == 1 and q["rollback_count"] == 1
    assert q["last_failure"]["failure_positions"] == [m1]
    assert q["last_failure"]["members"][0] == {
        "task_id": m1, "state": "failed", "cause": "program_error"}
    # 事件序：queue.status(executing→unsubmitted) + pending.snapshot
    qev = [d for e, d in rec if e == "queue.status"]
    assert qev[-1]["from"] == "executing" and qev[-1]["to"] == "unsubmitted"
    assert qev[-1]["finish_reason"] == "abort_on_failure"
    assert any(e == "pending.snapshot" for e, _ in rec[-4:])
    # 席位释放（无在跑成员）
    assert seats().count() == 0
    # 回退后残余成员不再派发
    disp.tick()
    assert running_rows() == []


def test_queue_skip_failed_continues(disp, rec):
    m1, m2, m3 = (add_input(SIMPLE, f"m{i}.gjf") for i in (1, 2, 3))
    qid = make_queue([m1, m2, m3], skip_failed=True)
    disp.advance()
    disp._gw.set_state("1", "failed")  # m1 失败
    disp.tick()
    disp.tick()
    # 勾选跳过：m2 继续派发（不即时 skipped）
    assert len(running_rows()) == 1
    m2_exec = executions().list_by_task(m2)
    assert m2_exec and m2_exec[-1]["state"] == "running"
    disp._gw.set_state("2", "finished")  # m2 成功
    disp.tick()  # m2 收尾 → m3 补位
    assert len(running_rows()) == 1
    disp._gw.set_state("3", "finished")  # m3 成功
    disp.tick()
    # 队列跑完（m1 failed + m2/m3 succeeded）→ finished_with_failures 回退
    q = queues().get(qid)
    assert q["state"] == "unsubmitted"
    assert q["finish_reason"] == "finished_with_failures"
    assert q["rollback_count"] == 1
    assert q["last_failure"]["failure_positions"] == [m1]
    assert seats().count() == 0


def test_queue_success_completes(disp, rec):
    m1, m2 = (add_input(SIMPLE, f"m{i}.gjf") for i in (1, 2))
    qid = make_queue([m1, m2])
    disp.advance()
    disp._gw.set_state("1", "finished")
    disp.tick()  # m1 成功 → m2 补位
    disp._gw.set_state("2", "finished")
    disp.tick()  # m2 成功 → 队列完成
    q = queues().get(qid)
    assert q["state"] == "completed"
    assert q["finish_reason"] == "success" and q["last_failure"] is None
    assert seats().count() == 0


# ---------------- fake g16 经真 CliGateway 首条链路（hq 不在 PATH 跳过） ----------------

@pytest.mark.skipif(HQ is None, reason="hq 不在 PATH")
def test_fake_g16_first_pipeline(tmp_path, monkeypatch):
    """fake g16（正常退出）→ 真 CliGateway：提交→运行→终态→历史首条链路。"""
    from web.src.hq.cli_gateway import CliGateway
    from web.src.hq.process import HqProcessManager

    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    shutil.copy(Path(__file__).parent / "fake_g16.py", fakebin / "g16")
    settings().set("g16_root", str(fakebin))
    settings().set("link0_default_nproc", 1)
    settings().set("parallel_window", 1)

    ws = tmp_path / "hqws"
    mgr = HqProcessManager(HQ, ws)
    mgr.start()
    mgr.ensure_worker(cpus=1)
    records: list[tuple[str, dict]] = []
    disp = Dispatcher(CliGateway(HQ, str(mgr.server_dir)),
                      emitter=lambda e, d: records.append((e, d)))
    try:
        tid = add_input(SIMPLE)
        submit_task(tid)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            disp.tick()
            if executions().list_by_task(tid):
                break
            time.sleep(0.2)
        assert executions().list_by_task(tid), "派发未发生"
        eid = executions().list_by_task(tid)[-1]["id"]
        while time.monotonic() < deadline:
            disp.tick()
            if executions().get(eid)["state"] != "running":
                break
            time.sleep(0.2)
        # 跑完进历史：succeeded + history.appended
        e = executions().get(eid)
        assert e["state"] == "succeeded", e
        assert any(d.get("execution_id") == eid and d.get("state") == "succeeded"
                   for ev, d in records if ev == "history.appended")
        # fake g16 产物与物化结构
        rd = config.HOME_DIR / "run" / str(eid)
        assert (rd / "input.gjf").is_file()
        assert (rd / "input.log").is_file()  # input.gjf → 同名 .log
    finally:
        mgr.stop()
