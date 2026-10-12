"""派发窗口依赖联动测试（M4 B8，m4-plan §4.5/§5 test_dispatch_deps）。

覆盖：依赖停等不越位（窗口保序）、依赖+资源双停等叠加先判依赖、
前驱 failed → 下游即时 skipped（predecessor_failed）、前驱 skipped →
下游传递 skipped（勾选跳过开关三段链防死锁、队列收束）、哈希跳过成员
的 chk 可被下游溯源物化、停等原因快照字段（wait_reason）、重入②
（journal 重跑者取消+新执行 id 重新物化派发）、重入②盲区边界
（物化依赖执行容差收紧为 0）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.engine.reconcile import Reconciler
from web.src.store import executions, queues, seats, settings, tasks
from web.src.store.db import now_iso

TAIL = "#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\nH 1 0.96\n\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


@pytest.fixture()
def gw() -> FakeGateway:
    return FakeGateway(cpus=8, mem_mib=16384)


@pytest.fixture()
def disp(gw) -> Dispatcher:
    rec: list = []
    return Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))


def _mk(text: str, name: str) -> int:
    tid = tasks().create_candidate(name, "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(text, encoding="utf-8")
    return tid


def _mk_queue(members: list[int], skip_failed: bool = False) -> str:
    qid = "Q" + "".join(chr(65 + i) for i in range(5))
    queues().create(qid, name="t", skip_failed=skip_failed)
    for pos, tid in enumerate(members):
        tasks().enqueue(tid, qid, pos)
    sid = seats().append(kind="queue", queue_id=qid)
    queues().set_state(qid, "submitted")
    return qid


def _succeed(task_id: int, chk: bytes = b"up", **kw) -> int:
    eid = executions().create(
        task_id=task_id, filename="x.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}}, **kw)
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True)
    (run_d / "input.chk").write_bytes(chk)
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at=now_iso())
    return eid


def _running_row(task_id: int, job_id: str) -> dict:
    """造 running 执行行（重入②场景：已派发、已 started）。"""
    eid = executions().create(
        task_id=task_id, filename="x.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    executions().update_hq_job_id(eid, int(job_id))
    executions().set_started_at(eid, now_iso())
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True)
    (run_d / "input.gjf").write_text("%chk=dep-1.chk\n" + TAIL,
                                      encoding="utf-8")
    return executions().get(eid)


# ---------------- 窗口守卫 ----------------

def test_dependency_wait_holds_window(disp, gw):
    """依赖停等不越位：a 在跑、b 依赖 a、c 无依赖——b 停等时 c 不入窗口
    （保序），wait_reason=dependency 可观测。"""
    a = _mk("%chk=a.chk\n" + TAIL, "a.gjf")
    b = _mk(f"%OldChk=@task:{a}\n" + TAIL, "b.gjf")
    c = _mk("%chk=c.chk\n" + TAIL, "c.gjf")
    _mk_queue([a, b, c])
    disp.advance()
    assert len(gw.submitted) == 1  # 仅 a
    assert Dispatcher.wait_reasons.get(b) == "dependency"
    assert c not in Dispatcher.wait_reasons
    assert executions().list_by_task(c) == []


def test_dependency_gate_beats_resource_wait(disp, gw):
    """双停等叠加先判依赖：b 依赖在跑的 a 且声明资源超空闲 → 停等原因
    为 dependency（而非 resource）。"""
    a = _mk("%chk=a.chk\n%NProcShared=6\n%Mem=10GB\n" + TAIL, "a.gjf")
    b = _mk(f"%OldChk=@task:{a}\n%NProcShared=6\n%Mem=10GB\n" + TAIL,
            "b.gjf")
    _mk_queue([a, b])
    disp.advance()
    assert len(gw.submitted) == 1
    assert Dispatcher.wait_reasons.get(b) == "dependency"


def test_predecessor_failed_skips_downstream(disp, gw):
    """前驱 failed → 下游即时 skipped（predecessor_failed），未勾跳过开关
    （既有失败中止路径）。"""
    a = _mk("%chk=a.chk\n" + TAIL, "a.gjf")
    b = _mk(f"%OldChk=@task:{a}\n" + TAIL, "b.gjf")
    qid = _mk_queue([a, b])
    disp.advance()  # a 派发
    a_row = executions().list_by_task(a)[-1]
    disp._on_terminal(a_row, "failed", "program_error")  # 注入失败
    states = {e["task_id"]: (e["state"], e["cause"])
              for e in executions().list_all()}
    assert states[a][0] == "failed"
    assert states[b] == ("skipped", "predecessor_failed")
    assert queues().get(qid)["state"] == "unsubmitted"  # 失败中止回退


def test_skipped_propagates_transitively(disp, gw):
    """勾选跳过开关三段链：a failed → b skipped（gate settle）→ c 传递
    skipped（直接前驱 b=skipped）→ 队列收束回退、无成员悬挂。"""
    a = _mk("%chk=a.chk\n" + TAIL, "a.gjf")
    b = _mk(f"%OldChk=@task:{a}\n" + TAIL, "b.gjf")
    c = _mk(f"%OldChk=@task:{b}\n" + TAIL, "c.gjf")
    qid = _mk_queue([a, b, c], skip_failed=True)
    disp.advance()  # a 派发（b 依赖停等、c 不越位）
    disp._on_terminal(executions().list_by_task(a)[-1], "failed",
                      "program_error")
    disp.advance()  # b：gate settle → skipped；c：gate settle（b=skipped）
    disp._settle_queue_seat(qid)
    states = {e["task_id"]: e["state"] for e in executions().list_all()}
    assert states[a] == "failed"
    assert states[b] == "skipped"
    assert states[c] == "skipped"
    q = queues().get(qid)
    assert q["state"] == "unsubmitted"
    assert q["finish_reason"] == "finished_with_failures"


def test_hash_skip_member_satisfies_dependency_and_feeds_materialization(
        disp, gw):
    """哈希跳过视为依赖满足，且下游物化溯源其被沿用的历史 chk。"""
    u = _mk("%chk=u.chk\n" + TAIL, "u.gjf")
    d = _mk(f"%OldChk=@task:{u}\n" + TAIL, "d.gjf")
    from web.src.engine.workspace import content_hash, resolve_link0
    text = (config.HOME_DIR / "inputs" / str(u)).read_text(encoding="utf-8")
    h = content_hash(resolve_link0(text, 4, 8.0)["completed_text"])
    _succeed(u, b"reused-chk", input_hash=h)
    _mk_queue([u, d])
    disp.advance()  # u 哈希跳过（沿用）；d 依赖满足（succeeded）→ 物化派发
    states = {e["task_id"]: e["state"] for e in executions().list_all()}
    assert states[u] == "succeeded"
    assert states[d] == "running"
    dep = next(s for s in gw.submitted if s["name"] == "d.gjf")
    assert dep["crash_limit"] == 0
    dep_chk = Path(dep["cwd"]) / f"dep-{u}.chk"
    assert dep_chk.read_bytes() == b"reused-chk"


def test_upstream_rerun_blocks_downstream_hash_skip(disp, gw, monkeypatch):
    """§8 决策点 6（定案=建议值）：上游重跑产生新执行 → 视依赖已变，
    下游拒绝哈希跳过、随之重跑（新执行记录；下游输入未变、哈希仍一致）。"""
    u = _mk("%chk=u.chk\n" + TAIL, "u.gjf")
    d = _mk(f"%OldChk=@task:{u}\n" + TAIL, "d.gjf")
    from web.src.engine.workspace import content_hash, resolve_link0
    text = (config.HOME_DIR / "inputs" / str(u)).read_text(encoding="utf-8")
    h = content_hash(resolve_link0(text, 4, 8.0)["completed_text"])
    _succeed(u, b"old-chk", input_hash=h)
    qid = _mk_queue([u, d])
    disp.advance()  # 周期 1：u 哈希跳过（沿用），d 派发
    d_eid = executions().list_by_task(d)[-1]["id"]
    disp._on_terminal(executions().get(d_eid), "succeeded", None)
    assert queues().get(qid)["state"] == "completed"
    # 上游显式重跑（重新排队语义）：新执行 id、输入未变（哈希一致）。
    # 提交时间戳强置为严格更晚（真实场景为稍后重提）：避免周期 1/2 同秒
    # ——updated_at 不变则执行周期水位不重置、d 被误判本周期已执行
    # （m2-plan §5 秒级时间戳同秒竞态，测试确定性规避）
    import web.src.store.queues_repo as _qr
    _real_now = _qr.now_iso
    monkeypatch.setattr(
        _qr, "now_iso",
        lambda: (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(
            timespec="seconds"))
    _succeed(u, b"new-chk", input_hash=h)
    seats().append(kind="queue", queue_id=qid)
    queues().set_state(qid, "submitted")
    disp.advance()  # 周期 2：d 拒绝哈希跳过 → 重新派发
    d_execs = executions().list_by_task(d)
    assert d_execs[-1]["id"] > d_eid and d_execs[-1]["state"] == "running"
    # u 自身哈希跳过照常（其结果仍是当前输入的有效结果，无新执行记录）
    assert len(executions().list_by_task(u)) == 2


def test_wait_reason_in_snapshot(disp, gw):
    """停等原因经 pending.snapshot 可见（契约 wait_reason 字段）。"""
    from web.src.services.pending import snapshot
    a = _mk("%chk=a.chk\n" + TAIL, "a.gjf")
    b = _mk(f"%OldChk=@task:{a}\n" + TAIL, "b.gjf")
    _mk_queue([a, b])
    disp.advance()
    snap = snapshot()
    views = {m["task_id"]: m for s in snap["seats"] for m in s["members"]}
    assert views[a]["wait_reason"] is None
    assert views[b]["wait_reason"] == "dependency"


# ---------------- 重入②（journal 重跑者取消 + 重新物化） ----------------

def _remat_setup(disp, gw, tmp_path):
    """u 预置成功执行（哈希匹配 → 哈希跳过），d 依赖 u 并被派发物化。
    返回 (上游任务 id, 下游任务 id, 下游执行行)。"""
    u = _mk("%chk=u.chk\n" + TAIL, "u.gjf")
    d = _mk(f"%OldChk=@task:{u}\n" + TAIL, "d.gjf")
    from web.src.engine.workspace import content_hash, resolve_link0
    text = (config.HOME_DIR / "inputs" / str(u)).read_text(encoding="utf-8")
    h = content_hash(resolve_link0(text, 4, 8.0)["completed_text"])
    _succeed(u, b"up-chk", input_hash=h)
    _mk_queue([u, d])
    disp.advance()  # u 哈希跳过；d 派发（物化 + crash_limit=0）
    d_row = executions().list_by_task(d)[-1]
    executions().set_started_at(d_row["id"], now_iso())  # running 事件回填
    return u, d, executions().get(d_row["id"])


def test_reentry_rematerialize_on_journal_rerun(disp, gw, tmp_path):
    """重入②：物化依赖执行被 journal 恢复重跑（job 回退 waiting）→
    对账取消 HQ job、原执行 external_interrupt 落历史、以符号形式输入
    重新物化派发（新执行 id、crash_limit=0、dep chk 重建）。"""
    u, d, row = _remat_setup(disp, gw, tmp_path)
    old_eid = row["id"]
    gw.set_state(str(row["hq_job_id"]), "waiting")  # journal 恢复重跑特征①
    summary = Reconciler(disp).run()
    assert summary["rematerialize"] == [old_eid]
    assert str(row["hq_job_id"]) in gw.canceled
    old = executions().get(old_eid)
    assert old["state"] == "failed" and old["cause"] == "external_interrupt"
    new = executions().list_by_task(d)[-1]
    assert new["id"] != old_eid and new["state"] == "running"
    new_run = config.HOME_DIR / "run" / str(new["id"])
    new_text = (new_run / "input.gjf").read_text(encoding="utf-8")
    assert "@task:" not in new_text  # 重新物化后零符号残留
    assert (new_run / f"dep-{u}.chk").read_bytes() == b"up-chk"


def test_reentry_tolerance_tightened(disp, gw, tmp_path, monkeypatch):
    """盲区边界：物化依赖执行不吃 120s 容差豁免——特征①③屏蔽后由
    detect_rerun(tolerance_s=0.0) 收紧识别（宁可重派、不可静默）。"""
    import web.src.engine.reconcile as rec_mod
    u, d, row = _remat_setup(disp, gw, tmp_path)
    gw.set_state(str(row["hq_job_id"]), "running")  # 特征①不成立
    calls: list[float] = []

    def fake_probe(execution, run_dir, *, tolerance_s=120.0):
        calls.append(tolerance_s)
        return True  # 模拟收紧后识别（进程 create_time 晚于 started_at）

    monkeypatch.setattr(rec_mod, "detect_rerun", fake_probe)
    disp.server_spawn_ts = None  # 判据③不成立
    summary = Reconciler(disp).run()
    assert 0.0 in calls  # 收紧容差被使用
    assert summary["rematerialize"] == [row["id"]]


def test_reentry_not_triggered_without_deps(disp, gw, tmp_path):
    """无物化依赖的执行重跑特征按既有对账处置（takeover/redirect），
    不被重入②特判拦截。"""
    w = _mk("%chk=w.chk\n" + TAIL, "w.gjf")
    _mk_queue([w])
    disp.advance()
    row = executions().list_by_task(w)[-1]
    gw.set_state(str(row["hq_job_id"]), "waiting")
    summary = Reconciler(disp).run()
    assert summary["rematerialize"] == []
    # S3 chk 分流需 run 目录存在 chk：fake 未产出 → 无 chk 走接管
    assert executions().get(row["id"])["state"] == "running"
