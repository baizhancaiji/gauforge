"""SQLite 持久化层测试（m1-plan §5 test_store_sqlite.py，B1）。

覆盖：迁移（schema_version/幂等）、WAL 生效、全表 CRUD、form 形态转换
（对照 §2.1 状态机）、单连接写锁下并发读写不死锁。
"""
from __future__ import annotations

import threading

import pytest

from web.src.store import Database, run_migrations
from web.src.store.executions_repo import ExecutionsRepo
from web.src.store.queues_repo import QueuesRepo
from web.src.store.seats_repo import SeatsRepo
from web.src.store.settings_repo import SettingsRepo
from web.src.store.tasks_repo import TasksRepo


@pytest.fixture()
def db(tmp_path):
    """文件库（WAL 可生效）+ 已迁移。"""
    d = Database(tmp_path / "test.db")
    run_migrations(d)
    yield d
    d.close()


@pytest.fixture()
def repos(db):
    return {
        "settings": SettingsRepo(db),
        "tasks": TasksRepo(db),
        "queues": QueuesRepo(db),
        "seats": SeatsRepo(db),
        "executions": ExecutionsRepo(db),
    }


# ---------------- 迁移 ----------------

def test_migration_sets_version(db):
    row = db.one("SELECT version FROM schema_version")
    assert row is not None and row["version"] == 7  # v7: 组合流精修模板表


def test_migration_idempotent(db):
    run_migrations(db)  # 重复执行不报错、版本不变
    assert db.one("SELECT version FROM schema_version")["version"] == 7


def test_v4_tasks_kind_column(db):
    # v4（M4 B6）：tasks.kind 任务类型（g16|crest，默认 g16）
    cols = {r["name"] for r in db.query("PRAGMA table_info(tasks)")}
    assert "kind" in cols
    db.run("INSERT INTO tasks (filename, origin, form, created_at,"
           " updated_at) VALUES ('a.gjf', 'imported', 'candidate',"
           " '2026-10-12T00:00:00+08:00', '2026-10-12T00:00:00+08:00')")
    row = db.one("SELECT kind FROM tasks")
    assert row["kind"] == "g16"  # 默认 g16（历史行口径）
    db.run("UPDATE tasks SET kind = 'crest'")
    with pytest.raises(Exception):  # 非法 kind 被 CHECK 拒绝
        db.run("UPDATE tasks SET kind = 'bogus'")


def test_v3_resumed_from_and_workflows(db):
    # v3（M4 A4 随行落库）：executions.resumed_from 可空列 + workflows 表
    cols = {r["name"] for r in db.query(
        "PRAGMA table_info(executions)")}
    assert "resumed_from" in cols
    db.run(
        "INSERT INTO workflows (workflow_id, source_candidate_id, state,"
        " created_at, updated_at) VALUES ('wf0001', 1, 'crest_running',"
        " '2026-10-12T00:00:00+08:00', '2026-10-12T00:00:00+08:00')")
    row = db.one("SELECT * FROM workflows WHERE workflow_id = 'wf0001'")
    assert row is not None and row["refine_queue_pending"] == 0
    with pytest.raises(Exception):  # 非法 state 被 CHECK 拒绝
        db.run("UPDATE workflows SET state = 'bogus' WHERE workflow_id = 'wf0001'")


def test_v7_combo_templates_seed(db):
    # v7（插波 3.2.0）：combo_templates 表 + 5 行种子（INSERT OR IGNORE 幂等）
    rows = db.query("SELECT * FROM combo_templates ORDER BY template_id")
    assert [r["template_id"] for r in rows] == [1, 2, 3, 4, 5]
    from web.src import config
    assert all(r["route"] == config.COMBO_TEMPLATE_INITIAL_ROUTE
               for r in rows)
    assert all(r["nproc"] is None and r["mem_gb"] is None and r["cpu"] is None
               for r in rows)  # link0 三字段初始全空
    assert [r["template_id"] for r in rows if r["is_default"] == 1] == [1]
    assert all(r["updated_at"] for r in rows)


def test_wal_mode_file_db(db):
    assert db.one("PRAGMA journal_mode")["journal_mode"] == "wal"


def test_foreign_keys_on(db):
    assert db.one("PRAGMA foreign_keys")["foreign_keys"] == 1


# ---------------- 全表 CRUD ----------------

def test_settings_crud(repos):
    s = repos["settings"]
    s.set("page_size", 100)
    assert s.get("page_size") == 100
    assert s.get("not_written", "fallback") == "fallback"  # 无记录回落
    s.set("page_size", 200)  # upsert
    assert s.get("page_size") == 200


def test_queues_crud(repos):
    q = repos["queues"]
    q.create("QAAAAA", name="demo", skip_failed=True)
    got = q.get("QAAAAA")
    assert got["name"] == "demo" and got["skip_failed"] == 1
    assert got["state"] == "unsubmitted" and got["rollback_count"] == 0
    q.set_state("QAAAAA", "executing")
    assert q.get("QAAAAA")["state"] == "executing"
    q.delete("QAAAAA")
    assert q.get("QAAAAA") is None


def test_tasks_crud_and_list(repos):
    t = repos["tasks"]
    tid = t.create_candidate("a.gjf", "imported")
    assert t.get(tid)["form"] == "candidate"
    assert [x["id"] for x in t.list_by_form("candidate")] == [tid]
    t.delete(tid)
    assert t.get(tid) is None


def test_seats_crud(repos):
    t = repos["tasks"]
    s = repos["seats"]
    tid = t.create_candidate("a.gjf", "imported")
    sid = s.append(kind="task", task_id=tid)
    rows = s.list_by_position()
    assert rows[0]["seat_id"] == sid and rows[0]["position"] == 0
    s.set_locked(sid, True)
    assert s.get(sid)["locked"] == 1
    s.remove(sid)
    assert s.get(sid) is None


def test_seats_order_persists_across_restart(tmp_path):
    """席位序列（用户拖拽重排结果）跨服务重启保持：写库重开连接后
    list_by_position 顺序一致（工作区持久化、更新/重启不回默认，2026-09-29）。"""
    t1 = TasksRepo(Database(tmp_path / "p.db"))
    run_migrations(t1._db)
    s1 = SeatsRepo(t1._db)
    ids = sorted(t1.create_candidate(f"{i}.gjf", "imported") for i in range(3))
    sids = [s1.append(kind="task", task_id=tid) for tid in ids]
    s1.reorder([sids[2], sids[0], sids[1]])  # 模拟用户重排
    t1._db.close()

    t2 = TasksRepo(Database(tmp_path / "p.db"))
    run_migrations(t2._db)
    s2 = SeatsRepo(t2._db)
    assert [r["seat_id"] for r in s2.list_by_position()] == \
        [sids[2], sids[0], sids[1]]
    assert [r["position"] for r in s2.list_by_position()] == [0, 1, 2]
    t2._db.close()


def test_executions_crud(repos):
    t = repos["tasks"]
    e = repos["executions"]
    tid = t.create_candidate("a.gjf", "imported")
    eid = e.create(task_id=tid, filename="a.gjf",
                   resources={"nproc": {"value": 4, "defaulted": True},
                              "mem_gb": {"value": 8.0, "defaulted": False}})
    row = e.get(eid)
    assert row["state"] == "running"
    assert row["resources"]["nproc"]["defaulted"] is True
    e.finalize(execution_id=eid, state="succeeded",
               finished_at="2026-01-01T00:00:00+00:00",
               cause=None, monitor_summary={"cpu_peak_percent": 90})
    row = e.get(eid)
    assert row["state"] == "succeeded"
    assert row["monitor_summary"]["cpu_peak_percent"] == 90
    assert [x["id"] for x in e.list_by_state("succeeded")] == [eid]


# ---------------- form 形态转换（对照 §2.1 状态机） ----------------

def test_form_transition_candidate_to_queue_member(repos):
    repos["queues"].create("QAAAAA", name="q")
    t = repos["tasks"]
    tid = t.create_candidate("a.gjf", "imported")
    t.enqueue(tid, queue_id="QAAAAA", position=0)
    row = t.get(tid)
    assert row["form"] == "queue_member"
    assert row["queue_id"] == "QAAAAA" and row["position"] == 0


def test_form_transition_candidate_to_seat_task(repos):
    t = repos["tasks"]
    tid = t.create_candidate("a.gjf", "imported")
    t.to_seat_task(tid)
    row = t.get(tid)
    assert row["form"] == "seat_task"
    assert row["queue_id"] is None and row["position"] is None


def test_form_transition_seat_task_to_finished(repos):
    t = repos["tasks"]
    tid = t.create_candidate("a.gjf", "imported")
    t.to_seat_task(tid)
    t.to_finished(tid)
    assert t.get(tid)["form"] == "finished"


def test_form_transition_queue_member_back_to_candidate(repos):
    repos["queues"].create("QAAAAA", name="q")
    t = repos["tasks"]
    tid = t.create_candidate("a.gjf", "imported")
    t.enqueue(tid, queue_id="QAAAAA", position=3)
    t.return_to_candidate(tid, origin="returned_unrun", failure_note=None)
    row = t.get(tid)
    assert row["form"] == "candidate"
    assert row["queue_id"] is None and row["position"] is None
    assert row["origin"] == "returned_unrun" and row["failure_note"] is None


def test_form_transition_finished_requeue_keeps_id(repos):
    """历史「重新排队」沿用原任务 id（§2.2 形态规则第 5 条）。"""
    t = repos["tasks"]
    tid = t.create_candidate("a.gjf", "imported")
    t.to_seat_task(tid)
    t.to_finished(tid)
    t.to_seat_task(tid)  # requeue：沿用原 id
    row = t.get(tid)
    assert row["id"] == tid and row["form"] == "seat_task"


# ---------------- 并发 ----------------

def test_concurrent_read_write_no_deadlock(db):
    """多线程交替读写（单连接 + 全局写锁）不死锁且计数一致。"""
    s = SettingsRepo(db)
    t = TasksRepo(db)
    for i in range(5):
        t.create_candidate(f"f{i}.gjf", "imported")

    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(30):
                s.set("page_size", n * 1000 + i)
                assert len(t.list_by_form("candidate")) == 5
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert not errors
    assert s.get("page_size") in {k * 1000 + 29 for k in range(4)}
