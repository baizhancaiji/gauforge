"""重启对账测试（m1-plan B10；§5 测试表 test_reconcile 断言逐条）。

- FakeGateway 编排五场景：S1 接管在跑（hq_job_id 匹配+状态回填）、
  S2 补齐终态（归因映射+monitor_summary 置空）、S3 journal 重跑检测
  （有 chk → 保全+归因外部中断+新执行目录重提交；无 chk → 接管）、
  S4 server 丢失（外部中断落历史）、S5 crash_limit 重试不误判
  （不中途落历史，仅最终终态入历史）；
- 终态行幂等冻结：对账闩成功一次后不再重复（无重复事件/无重复历史行）；
- 对账完成发 system.snapshot(server_restarted=true)；
- 启动序列：start_engine 挂载引擎线程并完成对账；lifespan 引擎开关。

隔离：SQLite 走 conftest autouse；config.HOME_DIR 重定向用例级 tmp_path；
S3 重跑特征（rerun_probe）按 plan §2.4 注入替换（默认探测另行单测；
真机 S1/S3 journal 联测随 H4 实测结论补齐，plan §2.4/§9 风险 2）。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.engine import runtime, startup
from web.src.engine.reconcile import detect_rerun, has_chk
from web.src.hq.gateway import GatewayError
from web.src.store import executions, queues, seats, settings, tasks
from web.src.store.db import now_iso

HQ = shutil.which("hq")

# chk 声明为相对路径：产物落在 run/<id>/ 内（S3 保全/重定向断言用）
CHK_LOCAL = ("%chk=w.chk\n%NProcShared=2\n%Mem=1GB\n\n"
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


def add_input(text: str, name: str = "h2o.gjf") -> int:
    tid = tasks().create_candidate(name, "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(text, encoding="utf-8")
    return tid


def submit_task(tid: int) -> int:
    sid = seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)
    return sid


def running_row() -> dict:
    rows = executions().list_by_state("running")
    assert len(rows) == 1
    return rows[0]


def restarted(gw, rec2, probe=None) -> Dispatcher:
    """模拟 g16web 重启：新 Dispatcher（监视器/位点等内存态全部丢失）。"""
    return Dispatcher(gw, emitter=lambda e, d: rec2.append((e, d)),
                      rerun_probe=probe)


def events(rec2, name: str) -> list[dict]:
    return [d for e, d in rec2 if e == name]


def seed_running(gw, disp, text: str = CHK_LOCAL) -> dict:
    """播种一条真实派发的在跑执行（含 started_at），返回其执行行。"""
    tid = add_input(text)
    submit_task(tid)
    disp.advance()
    row = running_row()
    gw.set_state(str(row["hq_job_id"]), "running")
    disp.tick()
    return running_row()


# ---------------- S1：g16web 重启，HQ 活着、job 在跑 → 接管 ----------------

def test_s1_takeover_preserves_running(gw, rec):
    row = seed_running(gw, Dispatcher(gw, emitter=lambda e, d: rec.append((e, d))))
    started = row["started_at"]
    rec2: list[tuple[str, dict]] = []
    d2 = restarted(gw, rec2)
    d2.reconcile()

    after = executions().get(row["id"])
    assert after["state"] == "running"  # 接管：不重复提交不落历史
    assert after["started_at"] == started  # 原启动时间保留
    assert executions().list_terminal()[1] == 0  # 不产生历史行
    assert seats().list_by_position()  # 席位保留
    assert tasks().get(row["task_id"])["form"] == "seat_task"
    assert not [e for e, _ in rec2 if e in ("task.status", "history.appended")]
    # 对账完成发全量重建快照
    snaps = events(rec2, "system.snapshot")
    assert snaps and snaps[-1]["server_restarted"] is True


def test_s1_backfills_started_at(gw, rec):
    # 派发后未及 tick（started_at 为空）即重启：job 已在跑 → 状态回填
    tid = add_input(CHK_LOCAL)
    submit_task(tid)
    Dispatcher(gw, emitter=lambda e, d: rec.append((e, d))).advance()
    row = running_row()
    assert row["started_at"] is None
    gw.set_state(str(row["hq_job_id"]), "running")

    rec2: list[tuple[str, dict]] = []
    restarted(gw, rec2).reconcile()

    after = executions().get(row["id"])
    assert after["state"] == "running"
    assert after["started_at"] is not None  # 状态回填（§5：hq_job_id 匹配）


# ---------------- S2：重启期间 job 已终态 → 按终态补齐历史 ----------------

def test_s2_finished_backfills_history(gw, rec):
    row = seed_running(gw, Dispatcher(gw, emitter=lambda e, d: rec.append((e, d))))
    gw.set_state(str(row["hq_job_id"]), "finished")

    rec2: list[tuple[str, dict]] = []
    restarted(gw, rec2).reconcile()

    after = executions().get(row["id"])
    assert after["state"] == "succeeded"
    assert after["finished_at"] is not None
    assert after["monitor_summary"] is None  # S2：监视器态丢失，置空
    assert events(rec2, "history.appended")[0]["state"] == "succeeded"
    assert not seats().list_by_position()  # 席位释放
    assert tasks().get(row["task_id"])["form"] == "finished"


def test_s2_canceled_maps_manually_stopped(gw, rec):
    row = seed_running(gw, Dispatcher(gw, emitter=lambda e, d: rec.append((e, d))))
    gw.set_state(str(row["hq_job_id"]), "canceled")

    restarted(gw, []).reconcile()

    after = executions().get(row["id"])
    assert after["state"] == "failed"
    assert after["cause"] == "manually_stopped"  # §8.7 归因映射


# ---------------- S3：journal 恢复重跑（有 chk → 重定向；无 chk → 接管） ----------------

def test_s3_rerun_with_chk_redirects(gw, rec):
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    run_d = config.HOME_DIR / "run" / str(row["id"])
    (run_d / "w.chk").write_bytes(b"checkpoint")  # 中断残留 chk
    (run_d / "Gau-24843.rwf").write_bytes(b"scratch")  # 中断残留瞬态
    gw.set_state(str(row["hq_job_id"]), "running")  # HQ 侧重跑中

    rec2: list[tuple[str, dict]] = []
    probe = lambda r, p: True  # noqa: E731 - 注入重跑特征（H4 实测前可替换）
    restarted(gw, rec2, probe).reconcile()

    # 原执行：外部中断落历史 + chk 保全（rwf/Gau-* 即终收尸）
    old = executions().get(row["id"])
    assert old["state"] == "failed"
    assert old["cause"] == "external_interrupt"
    assert old["chk_snapshot"] == {"protected": True, "location": "protected"}
    assert (run_d / "protected" / "w.chk").is_file()
    assert not (run_d / "Gau-24843.rwf").exists()  # 收尸不留垃圾
    # 重定向：新执行目录原样重提交（同一任务、同输入哈希、同声明资源）
    new = [e for e in executions().list_by_state("running")]
    assert len(new) == 1
    e2 = new[0]
    assert e2["task_id"] == row["task_id"]
    assert e2["input_hash"] == row["input_hash"]
    assert e2["resources"] == row["resources"]
    assert e2["hq_job_id"] != row["hq_job_id"]
    assert (config.HOME_DIR / "run" / str(e2["id"]) / "input.gjf").read_text(
        encoding="utf-8") == (run_d / "input.gjf").read_text(encoding="utf-8")
    assert gw.submitted[-1]["cwd"] == str(config.HOME_DIR / "run" / str(e2["id"]))
    assert gw.submitted[-1]["resources"] == {"cpus": 2, "mem_mib": 1024}
    # 席位不释放（任务由新执行延续）、队列语义不被触发
    assert seats().list_by_position()
    assert tasks().get(row["task_id"])["form"] == "seat_task"
    # 事件：原执行归因落历史 + 新执行 staged→running
    sts = events(rec2, "task.status")
    assert sts[0]["to"] == "failed" and sts[0]["cause"] == "external_interrupt"
    assert sts[-1]["execution_id"] == e2["id"] and sts[-1]["to"] == "running"
    assert events(rec2, "history.appended")[0]["execution_id"] == row["id"]


def test_s3_waiting_state_signature_redirects(gw, rec):
    """§2.4 ③ 特征①：journal 恢复后 job 回退 waiting（worker 未重连）——
    仅凭状态回退即判 S3 重跑，不误按 S1 接管（create_time 探针缺席）。"""
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    run_d = config.HOME_DIR / "run" / str(row["id"])
    (run_d / "w.chk").write_bytes(b"checkpoint")
    gw.set_state(str(row["hq_job_id"]), "waiting")  # H4 P1 特征：回退 waiting

    rec2: list[tuple[str, dict]] = []
    probe = lambda r, p: False  # noqa: E731 - 进程探测不可用（worker 未重连）
    restarted(gw, rec2, probe).reconcile()

    old = executions().get(row["id"])
    assert old["state"] == "failed"
    assert old["cause"] == "external_interrupt"  # S3 重跑成立：原执行落历史
    assert (run_d / "protected" / "w.chk").is_file()  # chk 保全
    assert len(executions().list_by_state("running")) == 1  # 新执行重提交
    assert gw.submitted[-1]["cwd"].startswith(str(config.HOME_DIR / "run"))


def test_s3_server_respawn_signature_redirects(gw, rec):
    """§2.4 ③ 特征③（GUI 走查实测加固）：HQ server 本次生命周期被重新
    spawn（journal 恢复）且本地 started_at 早于 server spawn——worker 快速
    重连时 waiting 相位与进程 create_time 证据可被对账时点双双错过，
    本判据确定性成立，不受对账时点竞态影响。"""
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    run_d = config.HOME_DIR / "run" / str(row["id"])
    (run_d / "w.chk").write_bytes(b"checkpoint")
    gw.set_state(str(row["hq_job_id"]), "running")  # 已回 running（相位错过）

    rec2: list[tuple[str, dict]] = []
    d2 = restarted(gw, rec2, probe=lambda r, p: False)
    d2.server_spawn_ts = (datetime.fromisoformat(row["started_at"])
                          + timedelta(seconds=1)).isoformat()
    d2.reconcile()

    old = executions().get(row["id"])
    assert old["state"] == "failed"
    assert old["cause"] == "external_interrupt"
    assert (run_d / "protected" / "w.chk").is_file()
    assert len(executions().list_by_state("running")) == 1  # 新执行重提交


def test_s1_not_flagged_when_server_reused(gw, rec):
    """server 复用（未重 spawn）时判据③不得触发：S1 保持接管语义。"""
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    started = row["started_at"]

    rec2: list[tuple[str, dict]] = []
    d2 = restarted(gw, rec2, probe=lambda r, p: False)
    # server_spawn_ts 早于 started_at（正常先起 server 后派发）→ 非 S3
    d2.server_spawn_ts = (datetime.fromisoformat(started)
                          - timedelta(seconds=60)).isoformat()
    d2.reconcile()

    after = executions().get(row["id"])
    assert after["state"] == "running"  # S1 接管
    assert after["started_at"] == started
    assert executions().list_terminal()[1] == 0


def test_s3_rerun_without_chk_adopts(gw, rec):
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    gw.set_state(str(row["hq_job_id"]), "running")

    probe = lambda r, p: True  # noqa: E731
    restarted(gw, [], probe).reconcile()

    after = executions().get(row["id"])
    assert after["state"] == "running"  # 无 chk：接管跟踪重跑（结局即原执行结局）
    assert len(gw.submitted) == 1  # 不重复提交
    assert executions().list_terminal()[1] == 0


def test_s3_queue_member_redirect_keeps_queue(gw, rec):
    import time as _t
    qid = f"q{int(_t.monotonic_ns() % 100000):05d}"
    tid = add_input(CHK_LOCAL, "member.gjf")
    queues().create(qid, name="t", skip_failed=True)
    tasks().enqueue(tid, qid, 0)
    queues().set_state(qid, "submitted")
    seats().append(kind="queue", queue_id=qid)
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    d1.advance()
    row = running_row()
    assert row["queue_id"] == qid
    run_d = config.HOME_DIR / "run" / str(row["id"])
    (run_d / "w.chk").write_bytes(b"checkpoint")
    gw.set_state(str(row["hq_job_id"]), "running")

    probe = lambda r, p: True  # noqa: E731
    restarted(gw, [], probe).reconcile()

    assert executions().get(row["id"])["cause"] == "external_interrupt"
    e2 = running_row()
    assert e2["queue_id"] == qid  # 新执行延续队列归属
    assert queues().get(qid)["state"] == "executing"  # 队列不回退
    assert seats().list_by_position()  # 队列席位保留


# ---------------- S4：HQ server 丢失 / 无对应 job → 外部中断 ----------------

def test_s4_job_lost_external_interrupt(gw, rec):
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    run_d = config.HOME_DIR / "run" / str(row["id"])
    (run_d / "w.chk").write_bytes(b"checkpoint")

    lost = FakeGateway(cpus=8)  # server 丢失：HQ 侧已无任何 job
    rec2: list[tuple[str, dict]] = []
    restarted(lost, rec2).reconcile()

    after = executions().get(row["id"])
    assert after["state"] == "failed"
    assert after["cause"] == "external_interrupt"
    assert after["chk_snapshot"] == {"protected": True, "location": "protected"}
    assert (run_d / "protected" / "w.chk").is_file()
    assert not seats().list_by_position()
    assert events(rec2, "history.appended")


def test_s4_zombie_running_without_job_id(gw, rec):
    # 派发中途崩溃遗留：running 行无 hq_job_id（从未提交成功）
    tid = add_input(CHK_LOCAL)
    submit_task(tid)
    eid = executions().create(task_id=tid, filename="h2o.gjf",
                              resources={"nproc": {"value": 1, "defaulted": True},
                                         "mem_gb": {"value": 1, "defaulted": True}})
    restarted(gw, []).reconcile()
    after = executions().get(eid)
    assert after["state"] == "failed"
    assert after["cause"] == "external_interrupt"


# ---------------- S5：worker 失联重试 → 不中途落历史，仅终态入历史 ----------------

def test_s5_retry_not_settled_until_terminal(gw, rec):
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    gw.set_state(str(row["hq_job_id"]), "running")

    probe = lambda r, p: True  # noqa: E731 - 重跑特征成立（重试者）
    rec2: list[tuple[str, dict]] = []
    d2 = restarted(gw, rec2, probe)
    d2.reconcile()
    assert executions().get(row["id"])["state"] == "running"  # 不中途落历史
    assert executions().list_terminal()[1] == 0

    # 重试者最终终态 → 恰一次入历史（S5 识别：同一执行行跟踪到底）
    gw.set_state(str(row["hq_job_id"]), "finished")
    d2.tick()
    after = executions().get(row["id"])
    assert after["state"] == "succeeded"
    assert len([h for h in events(rec2, "history.appended")
                if h["execution_id"] == row["id"]]) == 1


# ---------------- 幂等与健壮性 ----------------

def test_reconcile_is_idempotent_after_success(gw, rec):
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    gw.set_state(str(row["hq_job_id"]), "finished")
    rec2: list[tuple[str, dict]] = []
    d2 = restarted(gw, rec2)
    d2.reconcile()
    n_hist = len(events(rec2, "history.appended"))
    assert n_hist == 1
    assert d2.reconcile() == {}  # 闩生效：不再重复
    assert len(events(rec2, "history.appended")) == n_hist


def test_reconcile_unreachable_raises_and_no_latch(gw, rec):
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    gw.set_state(str(row["hq_job_id"]), "finished")
    d2 = restarted(gw, [])
    gw.fail_worker()
    with pytest.raises(GatewayError):
        d2.reconcile()
    assert executions().get(row["id"])["state"] == "running"  # 未冻结
    gw._unreachable = False  # 恢复后同实例重试成功（引擎线程重试语义）
    d2.reconcile()
    assert executions().get(row["id"])["state"] == "succeeded"


def test_snapshot_payload_shape(gw, rec):
    rec2: list[tuple[str, dict]] = []
    restarted(gw, rec2).reconcile()
    snap = events(rec2, "system.snapshot")[-1]
    assert set(snap) == {"pending", "executions_running", "queues_summary",
                         "hq", "server_restarted"}
    assert snap["server_restarted"] is True
    assert set(snap["pending"]) == {"seats", "capacity", "window_size"}


# ---------------- 默认重跑探测（H4 实测后回填修正的特征实现） ----------------

def test_detect_rerun_defaults(tmp_path):
    assert has_chk(tmp_path) is False
    (tmp_path / "w.chk").write_bytes(b"x")
    assert has_chk(tmp_path) is True
    # 无进程匹配 cwd / 无 started_at → 不判定为重跑（保守按 S1 接管）
    assert detect_rerun({"started_at": now_iso()}, tmp_path) is False
    assert detect_rerun({"started_at": None}, tmp_path) is False


def test_detect_rerun_process_gap(tmp_path, monkeypatch):
    import web.src.engine.reconcile as rec_mod
    proc = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(10)"],
                            cwd=str(tmp_path))
    try:
        base = now_iso()  # 本地记录的启动时刻（早于重跑进程）
        time.sleep(0.05)
        assert detect_rerun({"started_at": base}, tmp_path) is False  # 容差内
        assert detect_rerun({"started_at": base}, tmp_path,
                            tolerance_s=-1.0) is True  # 差距超容差 → 重跑
    finally:
        proc.kill()
        proc.wait()
    monkeypatch.setattr(rec_mod, "psutil", None)
    assert detect_rerun({"started_at": now_iso()}, tmp_path) is False


# ---------------- 启动序列：引擎挂载与 lifespan 开关 ----------------

class FakePM:
    """进程管理器替身（测试不 spawn 真 HQ）。"""

    def __init__(self, root: Path) -> None:
        self.hq_path = "hq-fake"
        self.server_dir = root / "hq"
        self.server_spawn_ts = None  # 未 spawn 真 server：S3 判据③不成立

    def start(self) -> bool:
        return True

    def ensure_worker(self, cpus: int = 1) -> int:
        return 1


def test_start_engine_mounts_and_reconciles(gw, rec, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENGINE_ENABLED", True)
    # 预置一条重启期间已终态的在跑记录：start_engine 应完成对账冻结
    d1 = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    row = seed_running(gw, d1)
    gw.set_state(str(row["hq_job_id"]), "finished")

    d = startup.start_engine(gateway=gw, process_manager=FakePM(tmp_path))
    try:
        assert runtime.get_dispatcher() is d  # 引擎已挂载（stop 端点可达）
        assert executions().get(row["id"])["state"] == "succeeded"
    finally:
        d.stop()
        runtime.set_dispatcher(None)
    monkeypatch.setattr(config, "ENGINE_ENABLED", False)


def test_start_engine_survives_hq_unavailable(gw, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENGINE_ENABLED", True)

    class BadPM(FakePM):
        def start(self) -> bool:
            raise GatewayError("server 启动超时")

    d = startup.start_engine(gateway=gw, process_manager=BadPM(tmp_path))
    try:
        assert runtime.get_dispatcher() is d  # 降级挂载（watchdog 兜底重试）
    finally:
        d.stop()
        runtime.set_dispatcher(None)
    monkeypatch.setattr(config, "ENGINE_ENABLED", False)


def test_lifespan_engine_toggle(monkeypatch):
    from web.src.main import build_app

    calls: list[str] = []

    class Dummy:
        def stop(self) -> None:
            pass

    monkeypatch.setattr(startup, "start_engine",
                        lambda *a, **kw: calls.append("start") or Dummy())
    monkeypatch.setattr(config, "ENGINE_ENABLED", True)
    with TestClient(build_app()) as client:
        assert client.get("/api/v1/system/health").status_code == 200
    assert calls == ["start"]

    monkeypatch.setattr(config, "ENGINE_ENABLED", False)
    calls.clear()
    with TestClient(build_app()) as client:
        assert client.get("/api/v1/system/health").status_code == 200
    assert calls == []  # 关闭态不挂引擎（M0 演示模式不变）


# ---------------- 真 hq 联测：S1 接管一例（hq 不在 PATH 时跳过） ----------------

@pytest.mark.skipif(HQ is None, reason="hq 不在 PATH")
def test_s1_real_hq_takeover(tmp_path):
    from web.src.hq.cli_gateway import CliGateway
    from web.src.hq.process import HqProcessManager

    ws = tmp_path / "hqws"
    mgr = HqProcessManager(HQ, ws)
    mgr.start()
    try:
        mgr.ensure_worker(cpus=1)
        gw = CliGateway(HQ, str(ws / "hq"))
        tid = add_input(CHK_LOCAL)
        submit_task(tid)
        run_d = config.HOME_DIR / "run" / "901"
        run_d.mkdir(parents=True)
        jid = gw.submit(["bash", "-c", "sleep 30"], cwd=str(run_d),
                        name="b10probe")
        eid = executions().create(task_id=tid, filename="h2o.gjf",
                                  resources={"nproc": {"value": 1,
                                                       "defaulted": True},
                                             "mem_gb": {"value": 1,
                                                        "defaulted": True}},
                                  state="running")
        executions().update_hq_job_id(eid, int(jid))
        for _ in range(40):  # 等 job 真正 Running
            job = {j["id"]: j for j in gw.jobs()}.get(jid)
            if job and job["state"] == "running":
                break
            time.sleep(0.25)
        assert job and job["state"] == "running"

        d = Dispatcher(gw, run_root=config.HOME_DIR / "run")
        try:
            d.reconcile()
            after = executions().get(eid)
            assert after["state"] == "running"  # 接管：不重复提交
            assert after["started_at"] is not None  # 状态回填
            assert len(gw.jobs()) == 1  # 无第二次提交
        finally:
            d.stop()
        gw.cancel(jid)  # 清理：取消在跑作业
    finally:
        mgr.stop()


@pytest.mark.skipif(HQ is None, reason="hq 不在 PATH")
def test_s3_real_hq_journal_rerun(tmp_path):
    """真机 S3 联测（H4 实测结论回填，plan §2.4）：journal 恢复后 job id 延续、
    任务回退重跑；重跑特征成立且 run/<id>/ 无 chk → 接管跟踪重跑、不落历史。"""
    from web.src.hq.cli_gateway import CliGateway
    from web.src.hq.process import HqProcessManager

    ws = tmp_path / "hqws"
    mgr = HqProcessManager(HQ, ws)
    mgr.start()
    try:
        mgr.ensure_worker(cpus=1)
        gw = CliGateway(HQ, str(ws / "hq"))
        tid = add_input(CHK_LOCAL)
        submit_task(tid)
        run_d = config.HOME_DIR / "run" / "903"
        run_d.mkdir(parents=True)
        jid = gw.submit(["bash", "-c", "sleep 30"], cwd=str(run_d),
                        name="b10s3")
        eid = executions().create(task_id=tid, filename="h2o.gjf",
                                  resources={"nproc": {"value": 1,
                                                       "defaulted": True},
                                             "mem_gb": {"value": 1,
                                                        "defaulted": True}},
                                  state="running")
        executions().update_hq_job_id(eid, int(jid))
        job = None
        for _ in range(40):  # 等 job 真正 Running
            job = {j["id"]: j for j in gw.jobs()}.get(jid)
            if job and job["state"] == "running":
                break
            time.sleep(0.25)
        assert job and job["state"] == "running"

        # S3 模拟：本地 started_at 停留在「故障前」（回溯 5 分钟 > 判定容差 120s，
        # 等效 WSL2 重启间隙），随后 kill -9 server；journal 已由进程管理器传入，
        # 看门狗自动带 journal 重启 server + worker → 任务重跑（H4 P1 特征）
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        executions().set_started_at(eid, past)
        proc = mgr._server_proc
        proc.kill()
        proc.wait()
        job = None
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                job = {j["id"]: j for j in gw.jobs()}.get(jid)
            except GatewayError:
                job = None
            if job and job["state"] == "running":  # 恢复 + 重跑已在跑
                break
            time.sleep(0.5)
        assert job is not None, "journal 恢复后 job 应延续（H4 P1：id 延续）"
        assert job["state"] == "running"

        d = Dispatcher(gw, run_root=config.HOME_DIR / "run")
        try:
            summary = d.reconcile()
            after = executions().get(eid)
            assert after["state"] == "running"  # 无 chk：接管跟踪重跑，不落历史
            assert eid in summary["takeover"]
            assert detect_rerun(after, run_d), \
                "重跑进程 create_time 应显著晚于本地 started_at（H4 特征）"
        finally:
            d.stop()
        gw.cancel(jid)  # 清理：取消重跑作业
    finally:
        mgr.stop()
