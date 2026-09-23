"""顺序迁移（m1-plan §2.2）：schema_version 表 + 版本化 DDL。

M1 起版本 1；DDL 全部 IF NOT EXISTS 保证半途崩溃后重跑幂等。
"""
from __future__ import annotations

from .db import Database

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS queues (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  skip_failed INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'unsubmitted'
      CHECK (state IN ('unsubmitted','submitted','executing','completed')),
  rollback_flag INTEGER NOT NULL DEFAULT 0,
  rollback_count INTEGER NOT NULL DEFAULT 0,
  last_failure TEXT,
  finish_reason TEXT
      CHECK (finish_reason IS NULL OR finish_reason IN
             ('success','abort_on_failure','finished_with_failures','manually_stopped')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT NOT NULL,
  origin TEXT NOT NULL
      CHECK (origin IN ('imported','returned_unrun','returned_failed','returned_succeeded')),
  failure_note TEXT,
  queue_id TEXT REFERENCES queues(id),
  position INTEGER,
  time_limit_s INTEGER NOT NULL DEFAULT 0,
  form TEXT NOT NULL DEFAULT 'candidate'
      CHECK (form IN ('candidate','queue_member','seat_task','finished')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_form ON tasks(form);
CREATE INDEX IF NOT EXISTS idx_tasks_queue_id ON tasks(queue_id);

CREATE TABLE IF NOT EXISTS seats (
  seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('task','queue')),
  task_id INTEGER REFERENCES tasks(id),
  queue_id TEXT REFERENCES queues(id),
  position INTEGER NOT NULL,
  locked INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seats_position ON seats(position);

CREATE TABLE IF NOT EXISTS executions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  queue_id TEXT,
  state TEXT NOT NULL DEFAULT 'running'
      CHECK (state IN ('running','succeeded','failed','skipped')),
  submitted_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  input_hash TEXT,
  resources TEXT,
  hq_job_id INTEGER,
  filename TEXT NOT NULL,
  cause TEXT
      CHECK (cause IS NULL OR cause IN
             ('manually_stopped','program_error','external_interrupt',
              'predecessor_failed','queue_manually_stopped')),
  monitor_summary TEXT,
  chk_snapshot TEXT,
  archived INTEGER NOT NULL DEFAULT 0,
  result_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_executions_task_id ON executions(task_id);
CREATE INDEX IF NOT EXISTS idx_executions_state ON executions(state);
CREATE INDEX IF NOT EXISTS idx_executions_archived ON executions(archived);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sse_seq (
  counter INTEGER NOT NULL
);
INSERT OR IGNORE INTO sse_seq (counter) VALUES (0);
"""

MIGRATIONS: dict[int, str] = {1: SCHEMA_V1}


def run_migrations(db: Database) -> None:
    with db.tx() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (0)")
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        current = row["version"] if row is not None else 0
    for version in sorted(MIGRATIONS):
        if version <= current:
            continue
        db.script(MIGRATIONS[version])
        db.run("UPDATE schema_version SET version = ?", (version,))
