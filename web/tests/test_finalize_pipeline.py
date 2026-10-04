"""终态文件管线测试（m1-plan §4.3 B9；§5 测试表对应断言逐条）。

- resolve_chk：%Chk 声明（相对/绝对/引号/大小写）与无声明回落 input.chk；
- make_fchk：fake formchk 脚本成功转换 / 非零退出 / 二进制缺失 / chk 缺失
  均记日志返回 None 不阻断；
- protect_transient：顶层 chk 移入 protected/（保全仅 chk，2026-10-04 修订
  定稿），大小写不敏感、同名防御、非瞬态文件（.out/.log/输入）永不触碰；
- reap_scratch：异常终止收尸——顶层 Gau-* 与任意命名 .rwf 即终即删，
  .chk/.out/.log/输入与 protected/ 永不触碰；
- cleanup_expired / cleanup_all：双档「清理 chk」——前者仅清「succeeded 且
  超保留期」顶层 .chk，后者无视保留期清所有 succeeded 顶层 .chk；failed 与
  protected/ 两档均不在清理范围；
- Dispatcher 集成：succeeded 走 formchk 且无快照、failed 保全 chk 并收尸
  瞬态、formchk 失败不阻断终态落库。

隔离：SQLite 走 conftest autouse；config.HOME_DIR 重定向用例级 tmp_path。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway, finalize
from web.src.store import executions, seats, settings, tasks
from web.src.store.db import now_iso

SIMPLE = "%chk=w.chk\n\n#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"
PLAIN = "#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """触盘面（inputs/、run/、g16_root）整体隔离到 tmp_path。"""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


def write_input(run_dir: Path, text: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.gjf").write_text(text, encoding="utf-8")


def make_formchk(root: Path, script: str) -> None:
    """在 g16_root 放置 fake formchk 脚本（参数同真 formchk：chk out）。"""
    root.mkdir(parents=True, exist_ok=True)
    f = root / "formchk"
    f.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    f.chmod(0o755)


# ---------------- resolve_chk ----------------

def test_resolve_chk_relative_and_case(home):
    rd = home / "run" / "1"
    write_input(rd, "%Chk=sub/w.chk\n\n#p\n\nt\n\n0 1\nO\n")
    assert finalize.resolve_chk(rd) == rd / "sub" / "w.chk"  # 相对 run/<id>/


def test_resolve_chk_absolute_and_quotes(home):
    rd = home / "run" / "1"
    write_input(rd, '%chk="/tmp/abs x.chk"\n\n#p\n\nt\n\n0 1\nO\n')
    assert finalize.resolve_chk(rd) == Path("/tmp/abs x.chk")
    write_input(rd, "%chk='/tmp/y.chk'\n\n#p\n\nt\n\n0 1\nO\n")
    assert finalize.resolve_chk(rd) == Path("/tmp/y.chk")


def test_resolve_chk_fallback(home):
    rd = home / "run" / "1"
    write_input(rd, PLAIN)  # 无 %Chk 声明 → 回落 input.chk
    assert finalize.resolve_chk(rd) == rd / "input.chk"
    missing = home / "run" / "2"  # input.gjf 缺失同回落（formchk 届时失败）
    assert finalize.resolve_chk(missing) == missing / "input.chk"


def test_resolve_chk_appends_ext_when_missing(home):
    # 回归（GUI 走查发现）：g16 对无扩展名 %Chk 自动追加 .chk
    # （实测 run/<id>/ 产物 h2o_opt.chk 旁证），解析须对齐，否则
    # formchk 因「chk 不存在」被跳过，succeeded 任务无 .fchk 产物。
    rd = home / "run" / "1"
    write_input(rd, "%Chk=h2o_opt\n\n#p\n\nt\n\n0 1\nO\n")
    assert finalize.resolve_chk(rd) == rd / "h2o_opt.chk"
    write_input(rd, "%Chk=/tmp/water.v1\n\n#p\n\nt\n\n0 1\nO\n")
    assert finalize.resolve_chk(rd) == Path("/tmp/water.v1")  # 有扩展名按原样


# ---------------- make_fchk ----------------

def test_make_fchk_converts(home):
    root = home / "g16"
    make_formchk(root, 'cp "$1" "$2"\n')
    rd = home / "run" / "3"
    write_input(rd, "%chk=my.chk\n\n#p\n\nt\n\n0 1\nO\n")
    (rd / "my.chk").write_bytes(b"CHKDATA")
    out = finalize.make_fchk(rd, root)
    assert out == rd / "input.fchk"
    assert out.read_bytes() == b"CHKDATA"


def test_make_fchk_nonzero_exit_not_blocking(home):
    root = home / "g16"
    make_formchk(root, 'echo boom >&2\nexit 3\n')
    rd = home / "run" / "4"
    write_input(rd, "%chk=w.chk\n\n#p\n\nt\n\n0 1\nO\n")
    (rd / "w.chk").write_bytes(b"X")
    assert finalize.make_fchk(rd, root) is None


def test_make_fchk_missing_binary_and_chk(home):
    root = home / "g16"  # 无 formchk 二进制 → OSError
    rd = home / "run" / "5"
    write_input(rd, "%chk=w.chk\n\n#p\n\nt\n\n0 1\nO\n")
    (rd / "w.chk").write_bytes(b"X")
    assert finalize.make_fchk(rd, root) is None
    make_formchk(root, 'cp "$1" "$2"\n')
    rd2 = home / "run" / "6"
    write_input(rd2, "%chk=absent.chk\n\n#p\n\nt\n\n0 1\nO\n")
    assert finalize.make_fchk(rd2, root) is None  # chk 不存在 → 跳过
    assert not (rd2 / "input.fchk").exists()


# ---------------- protect_transient（仅保 chk） / reap_scratch（收尸） ----------------

def test_protect_transient_moves_top_level(home):
    """保全边界修订定稿（2026-10-04）：仅 chk 入 protected/；
    rwf 不再保全（留顶层，由收尸删除），.out/.log/输入永不触碰。"""
    rd = home / "run" / "7"
    rd.mkdir(parents=True)
    (rd / "a.chk").write_bytes(b"1")
    (rd / "A2.CHK").write_bytes(b"3")  # 大小写不敏感
    (rd / "b.RWF").write_bytes(b"2")
    (rd / "input.gjf").write_text(PLAIN, encoding="utf-8")
    (rd / "input.log").write_text("log", encoding="utf-8")
    snap = finalize.protect_transient(rd)
    assert snap == {"protected": True, "location": "protected"}
    prot = rd / "protected"
    assert (prot / "a.chk").is_file() and (prot / "A2.CHK").is_file()
    assert (rd / "input.gjf").is_file() and (rd / "input.log").is_file()
    assert not (rd / "a.chk").exists() and not (rd / "A2.CHK").exists()
    assert (rd / "b.RWF").is_file()  # rwf 不保全：留顶层待收尸


def test_reap_scratch_removes_gau_and_rwf(home):
    """异常终止收尸：Gau-*（任意扩展名）与任意命名 .rwf 即终即删，
    不留垃圾；.chk/.out/.log/输入与 protected/ 永不触碰。"""
    rd = home / "run" / "10"
    rd.mkdir(parents=True)
    gau = ("Gau-24843.rwf", "Gau-24843.inp", "Gau-24843.d2e",
           "Gau-24843.int", "Gau-24843.skr")
    for i, name in enumerate(gau):
        (rd / name).write_bytes(bytes([i]))
    (rd / "input.rwf").write_bytes(b"6")  # 命名 rwf 同收
    (rd / "keep.chk").write_bytes(b"c")
    (rd / "input.out").write_bytes(b"o")
    (rd / "input.log").write_bytes(b"l")
    (rd / "input.gjf").write_bytes(b"g")
    prot = rd / "protected"
    prot.mkdir()
    (prot / "snap.chk").write_bytes(b"s")
    assert finalize.reap_scratch(rd) == len(gau) + 1
    for name in (*gau, "input.rwf"):
        assert not (rd / name).exists()
    assert (rd / "keep.chk").is_file()
    assert (rd / "input.out").is_file() and (rd / "input.log").is_file()
    assert (rd / "input.gjf").is_file()
    assert (prot / "snap.chk").is_file()  # 保全子目录不触碰


def test_reap_scratch_empty_and_missing(home):
    empty = home / "run" / "11"
    empty.mkdir()
    assert finalize.reap_scratch(empty) == 0
    assert finalize.reap_scratch(home / "run" / "404") == 0  # 目录缺失（skipped）


def test_protect_transient_defenses(home):
    empty = home / "run" / "8"
    empty.mkdir()
    assert finalize.protect_transient(empty) == {"protected": False,
                                                 "location": None}
    assert finalize.protect_transient(home / "run" / "404") == {
        "protected": False, "location": None}  # 目录缺失（skipped 等）
    rd = home / "run" / "9"
    prot = rd / "protected"
    prot.mkdir(parents=True)
    (prot / "w.chk").write_bytes(b"old")
    (rd / "w.chk").write_bytes(b"new")
    snap = finalize.protect_transient(rd)
    assert snap == {"protected": True, "location": "protected"}
    assert (prot / "w.chk").read_bytes() == b"old"  # 同名防御不覆盖
    assert (prot / "w.1.chk").read_bytes() == b"new"


# ---------------- cleanup_expired ----------------

def test_cleanup_expired_scope(home):
    run_root = home / "run"
    old = (datetime.now().astimezone()
           - timedelta(days=30)).isoformat(timespec="seconds")
    files = {"11": {"input.chk": b"c", "input.rwf": b"r",
                    "input.log": b"l", "input.gjf": b"g"},
             "12": {"input.chk": b"c"},   # succeeded 未超期
             "13": {"a.chk": b"c"}}       # failed 不在清理范围
    for eid, fs in files.items():
        d = run_root / eid
        d.mkdir(parents=True)
        for name, data in fs.items():
            (d / name).write_bytes(data)
    (run_root / "11" / "protected").mkdir()
    (run_root / "11" / "protected" / "p.chk").write_bytes(b"p")
    (run_root / "14").mkdir()  # succeeded 但无瞬态件
    entries = [
        {"id": 11, "state": "succeeded", "finished_at": old},
        {"id": 12, "state": "succeeded", "finished_at": now_iso()},
        {"id": 13, "state": "failed", "finished_at": old},
        {"id": 14, "state": "succeeded", "finished_at": old},
        {"id": 15, "state": "skipped", "finished_at": old},  # 无 run 目录
    ]
    stats = finalize.cleanup_expired(entries, run_root, 7,
                                     datetime.now().astimezone())
    assert stats == {"checked": 3, "removed_chk": 1}
    d11 = run_root / "11"
    assert not (d11 / "input.chk").exists()
    # rwf 不属清理范围（异常终止时收尸；正常结束目录正常无 rwf 残留）
    assert (d11 / "input.rwf").is_file()
    # .log/.gjf/protected/ 永不触碰
    assert (d11 / "input.log").is_file() and (d11 / "input.gjf").is_file()
    assert (d11 / "protected" / "p.chk").is_file()
    assert (run_root / "12" / "input.chk").is_file()  # 未超期不动
    assert (run_root / "13" / "a.chk").is_file()      # failed 不清


def test_cleanup_all_ignores_retention(home):
    """「清理所有」档：无视保留期立即清所有 succeeded 顶层 .chk；
    failed 的 chk（含 protected/）依旧保留，非 chk 瞬态不属两档清理。"""
    run_root = home / "run"
    old = (datetime.now().astimezone()
           - timedelta(days=30)).isoformat(timespec="seconds")
    for eid in ("21", "22", "23", "24"):
        (run_root / eid).mkdir(parents=True)
    (run_root / "21" / "input.chk").write_bytes(b"c")  # 超期
    (run_root / "22" / "fresh.chk").write_bytes(b"c")  # 未超期也清
    (run_root / "23" / "a.chk").write_bytes(b"c")      # failed 保留
    (run_root / "23" / "protected").mkdir()
    (run_root / "23" / "protected" / "s.chk").write_bytes(b"s")
    (run_root / "24" / "Gau-1.rwf").write_bytes(b"r")  # 非 chk 不属清理
    entries = [
        {"id": 21, "state": "succeeded", "finished_at": old},
        {"id": 22, "state": "succeeded", "finished_at": now_iso()},
        {"id": 23, "state": "failed", "finished_at": old},
        {"id": 25, "state": "succeeded", "finished_at": old},  # 无 run 目录
    ]
    stats = finalize.cleanup_all(entries, run_root)
    assert stats == {"checked": 2, "removed_chk": 2}
    assert not (run_root / "21" / "input.chk").exists()
    assert not (run_root / "22" / "fresh.chk").exists()
    assert (run_root / "23" / "a.chk").is_file()
    assert (run_root / "23" / "protected" / "s.chk").is_file()
    assert (run_root / "24" / "Gau-1.rwf").is_file()


# ---------------- Dispatcher 终态集成 ----------------

def seed_dispatch(disp: Dispatcher) -> tuple[int, Path]:
    """派发一个单任务席位，返回 (eid, run 目录)。"""
    tid = tasks().create_candidate("h2o.gjf", "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(SIMPLE,
                                                       encoding="utf-8")
    seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)
    disp.advance()
    row = executions().list_by_state("running")[0]
    return row["id"], config.HOME_DIR / "run" / str(row["id"])


def test_dispatcher_succeeded_runs_formchk(home):
    root = home / "g16"
    make_formchk(root, 'cp "$1" "$2"\n')
    disp = Dispatcher(FakeGateway(cpus=8))
    eid, rd = seed_dispatch(disp)
    (rd / "w.chk").write_bytes(b"CHK")
    disp._gw.set_state("1", "finished")
    disp.tick()
    e = executions().get(eid)
    assert e["state"] == "succeeded"
    assert (rd / "input.fchk").read_bytes() == b"CHK"
    assert e["chk_snapshot"] is None  # 正常结束无保全快照
    assert not (rd / "protected").exists()


def test_dispatcher_failed_protects_chk_and_reaps_scratch(home):
    """异常终止：chk 入 protected/，rwf 不再保全、连同 Gau-* 即终收尸。"""
    disp = Dispatcher(FakeGateway(cpus=8))
    eid, rd = seed_dispatch(disp)
    (rd / "w.chk").write_bytes(b"1")
    (rd / "w.rwf").write_bytes(b"2")
    (rd / "Gau-24843.inp").write_bytes(b"3")
    disp._gw.set_state("1", "failed")
    disp.tick()
    e = executions().get(eid)
    assert e["state"] == "failed" and e["cause"] == "program_error"
    assert e["chk_snapshot"] == {"protected": True, "location": "protected"}
    assert (rd / "protected" / "w.chk").is_file()
    assert not (rd / "w.chk").exists()
    assert not (rd / "w.rwf").exists()          # 不保全、即终删除
    assert not (rd / "protected" / "w.rwf").exists()
    assert not (rd / "Gau-24843.inp").exists()  # 收尸不留垃圾


def test_dispatcher_succeeded_formchk_failure_not_blocking(home):
    # g16_root 无 formchk 二进制：转换失败仅记日志，终态照常落库
    disp = Dispatcher(FakeGateway(cpus=8))
    eid, rd = seed_dispatch(disp)
    (rd / "w.chk").write_bytes(b"1")
    disp._gw.set_state("1", "finished")
    disp.tick()
    e = executions().get(eid)
    assert e["state"] == "succeeded"
    assert not (rd / "input.fchk").exists()
    assert not (rd / "protected").exists()
