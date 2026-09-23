"""增量解析测试（m1-plan §4.3 B8；§5 测试表 test_progress_parse 断言）。

- 金标准回归：~/g16/tests/ 4 份 .out 喂入，优化步/SCF 迭代/SCF 收敛计数
  与人工核对基线一致（grep -c "Step number"/" Cycle "/"SCF Done"，
  2026-09-24 实测；经空文件首读消耗 catch-up 后按进度候选行逐行追加）；
- 位点续传（追加只读增量）、首读快进不推事件（重启重扫不风暴）、
  1s 合并窗口（窗口内多条推最新值，注入时钟）、截断静默重扫、
  半行缓冲、文件缺失缺席、last_line 200 字符截断；
- Dispatcher 集成：tick 产出 execution.progress 载荷 + 停滞同周期解除。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway, ProgressTracker
from web.src.store import executions, seats, settings, tasks
from web.src.store.db import now_iso

GOLD = Path.home() / "g16" / "tests"
# 人工核对基线：(文件名, 优化步数, SCF 迭代行数, SCF Done 行数)
GOLD_CASES = [
    ("anisoles0.out", 1, 750, 85),
    ("anisoles1.out", 1, 513, 97),
    ("phenoxyls0.out", 1, 19, 1),
    ("phenoxyls1.out", 1, 759, 73),
]

SIMPLE = "%chk=/tmp/w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"

CYCLE1 = " Cycle   %d  Pass 1  IDiag  1:\n"
STEP1 = " Step number   %d out of a maximum of  20\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text)


def fresh_tracker(tmp_path, window_s: float = 0.0,
                  clock=None) -> tuple[ProgressTracker, Path, int]:
    """空日志 + 空首读（消耗 catch-up）→ 其后追加全部按增量识别。"""
    log = tmp_path / "input.log"
    log.touch()
    tr = ProgressTracker(window_s=window_s, **({"clock": clock}
                                               if clock else {}))
    assert tr.step(1, log) is None
    return tr, log, 1


def count_changes(emissions: list[dict], key: str) -> int:
    """相邻发射中该字段取值变化的次数（= 该类进度行条数；基线 None）。"""
    prev = None
    n = 0
    for e in emissions:
        v = e.get(key)
        if v != prev:
            n += 1
            prev = v
    return n


def count_true_transitions(emissions: list[dict], key: str) -> int:
    prev = False
    n = 0
    for e in emissions:
        v = e.get(key) is True
        if v and not prev:
            n += 1
        prev = v
    return n


# ---------------- 金标准回归（4 份 .out） ----------------

def feed_gold(src: Path, dst: Path, tracker: ProgressTracker,
              eid: int) -> list[dict]:
    """按进度候选行逐行追加（非候选行批量追加以加速），返回发射序列。"""
    emissions: list[dict] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            append(dst, "".join(buf))
            buf.clear()

    for ln in src.open(encoding="utf-8", errors="replace"):
        if ("Cycle" in ln or "Step number" in ln or "SCF Done" in ln):
            flush()
            append(dst, ln)
            f = tracker.step(eid, dst)
            if f is not None:
                emissions.append(f)
        else:
            buf.append(ln)
    flush()
    append(dst, "\n")  # 补齐文件末尾可能的半行
    f = tracker.step(eid, dst)
    if f is not None:
        emissions.append(f)
    return emissions


@pytest.mark.skipif(not GOLD.is_dir(), reason="金标准目录缺失")
@pytest.mark.parametrize("name,exp_opt,exp_cycle,exp_done", GOLD_CASES)
def test_gold_standard_regression(tmp_path, name, exp_opt, exp_cycle,
                                  exp_done):
    tr, log, eid = fresh_tracker(tmp_path)
    emissions = feed_gold(GOLD / name, log, tr, eid)
    assert emissions, "金标准未识别到任何进度"
    assert count_changes(emissions, "opt_step") == exp_opt
    assert emissions[-1]["opt_step"] == 1
    assert count_changes(emissions, "scf_cycle") == exp_cycle
    assert count_true_transitions(emissions, "converged") == exp_done
    assert emissions[-1]["converged"] is True


# ---------------- 位点续传 / 快进 / 节流 / 容错 ----------------

def test_offset_resume_reads_only_new_lines(tmp_path):
    tr, log, eid = fresh_tracker(tmp_path)
    append(log, STEP1 % 1)
    f = tr.step(eid, log)
    assert f["opt_step"] == 1
    append(log, CYCLE1 % 1)
    assert tr.step(eid, log)["scf_cycle"] == 1  # 只读增量
    append(log, CYCLE1 % 2)
    assert tr.step(eid, log)["scf_cycle"] == 2
    assert tr.step(eid, log) is None  # 无新数据不重扫不发射


def test_catchup_swallows_initial_content(tmp_path):
    log = tmp_path / "input.log"
    log.write_text(CYCLE1 % 1 + CYCLE1 % 2, encoding="utf-8")
    tr = ProgressTracker(window_s=0)
    assert tr.step(1, log) is None  # 首读快进：历史行不推事件（重启重扫）
    append(log, CYCLE1 % 3)
    f = tr.step(1, log)
    assert f is not None and f["scf_cycle"] == 3  # 其后增量正常推


def test_merge_window_coalesces_to_latest(tmp_path):
    class Clock:
        t = 1000.0

        def __call__(self):
            return self.t

    clk = Clock()
    tr, log, eid = fresh_tracker(tmp_path, window_s=1.0, clock=clk)
    append(log, CYCLE1 % 1)
    f = tr.step(eid, log)
    assert f["scf_cycle"] == 1 and f["converged"] is False
    clk.t += 0.5
    append(log, CYCLE1 % 2)
    assert tr.step(eid, log) is None  # 窗口内仅更新状态
    clk.t += 0.6  # 距上次发射 1.1s
    append(log, CYCLE1 % 3)
    f = tr.step(eid, log)
    assert f["scf_cycle"] == 3  # 合并窗口内多条推最新值


def test_truncated_file_rescans_silently(tmp_path):
    tr, log, eid = fresh_tracker(tmp_path)
    append(log, STEP1 % 1 + CYCLE1 % 1 + CYCLE1 % 2)
    assert tr.step(eid, log)["scf_cycle"] == 2
    # 截断重写（文件缩短）：静默重扫不推事件
    log.write_text(STEP1 % 1, encoding="utf-8")
    assert tr.step(eid, log) is None
    append(log, CYCLE1 % 6)
    assert tr.step(eid, log)["scf_cycle"] == 6  # 重扫后 offset 正常续传


def test_partial_line_buffered_until_complete(tmp_path):
    tr, log, eid = fresh_tracker(tmp_path)
    append(log, (CYCLE1 % 1).rstrip("\n"))  # 无换行：半行
    assert tr.step(eid, log) is None
    append(log, "\n")
    assert tr.step(eid, log)["scf_cycle"] == 1  # 补齐后识别


def test_missing_file_returns_none(tmp_path):
    tr = ProgressTracker(window_s=0)
    assert tr.step(1, tmp_path / "nope.log") is None


def test_last_line_truncated_to_200(tmp_path):
    tr, log, eid = fresh_tracker(tmp_path)
    append(log, (STEP1 % 1).rstrip("\n") + " " * 250 + "\n")  # 单行 >200 字符
    f = tr.step(eid, log)
    assert len(f["last_line"]) == 200


def test_converged_resets_on_new_scf(tmp_path):
    tr, log, eid = fresh_tracker(tmp_path)
    append(log, CYCLE1 % 1
           + " SCF Done:  E(RB-HF-LYP) =  -1.0     A.U. after    3 cycles\n")
    f = tr.step(eid, log)
    assert f["converged"] is True
    append(log, CYCLE1 % 1)  # 新一轮 SCF 自 Cycle 1 重启
    assert tr.step(eid, log)["converged"] is False


# ---------------- Dispatcher 集成 ----------------

def add_input(text: str, name: str = "h2o.gjf") -> int:
    tid = tasks().create_candidate(name, "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(text, encoding="utf-8")
    return tid


def test_dispatcher_emits_progress_and_releases_stall(home):
    rec: list[tuple[str, dict]] = []
    gw = FakeGateway(cpus=8)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    disp._progress = ProgressTracker(window_s=0)  # 测试内免 1s 窗口
    tid = add_input(SIMPLE)
    seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)
    disp.advance()
    eid = executions().list_by_state("running")[0]["id"]
    log = home / "run" / str(eid) / "input.log"

    log.write_text(CYCLE1 % 1, encoding="utf-8")
    disp.tick()  # 首读快进：历史行不产生事件
    assert not [d for e, d in rec if e == "execution.progress"]

    # 预置停滞态：新进度喂入后同周期解除（_progress_step 先于 _monitor_step）
    stall = disp._monitor._entry(eid)["stall"]
    stall.stalled = True
    stall.since = now_iso()
    append(log, CYCLE1 % 2)
    disp.tick()

    prog = [d for e, d in rec if e == "execution.progress"]
    assert len(prog) == 1
    p = prog[0]
    assert p["execution_id"] == eid and p["task_id"] == tid
    assert p["scf_cycle"] == 2 and p["converged"] is False
    assert "last_line" in p and "ts" in p
    flips = [d for e, d in rec if e == "execution.stalled"]
    assert any(d["stalled"] is False for d in flips)  # 停滞解除
