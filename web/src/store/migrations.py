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
-- 真幂等种子（无唯一约束，OR IGNORE 挡不住脚本重跑重复插入）
INSERT INTO sse_seq (counter) SELECT 0 WHERE NOT EXISTS
  (SELECT 1 FROM sse_seq);
"""

MIGRATIONS: dict[int, str] = {1: SCHEMA_V1}

# v2（2026-09-29）：ui_prefs 表——前端视图偏好键值（列表排序规则等，
# GET/PUT /ui-preferences），工作区持久化、跨重启/更新不回默认值。
SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS ui_prefs (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""
MIGRATIONS[2] = SCHEMA_V2

# v3（2026-10-12，M4 A4 契约 diff 随行落库）：
# - executions 加列 resumed_from：断点续跑关联（可空 TEXT JSON，
#   {task_id, execution_id}=原执行；仅经「从断点续跑」新建的执行携带，
#   创建时写入；原历史条目数据零变更——「已续跑」经 resumed_by 派生只读
#   （响应时按本列反查），不落库）。
# - workflows 表：组合流记录（GET /workflows 系端点数据源；B10/B11 消费），
#   state 与 refine_queue_pending 形状对齐契约 Workflow/WorkflowState。
SCHEMA_V3 = """
ALTER TABLE executions ADD COLUMN resumed_from TEXT;

CREATE TABLE IF NOT EXISTS workflows (
  workflow_id TEXT PRIMARY KEY,
  source_candidate_id INTEGER NOT NULL,
  state TEXT NOT NULL
      CHECK (state IN ('crest_running','refining','completed','failed')),
  refine_queue_pending INTEGER NOT NULL DEFAULT 0,
  crest_execution_id INTEGER,
  refine_queue_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""
MIGRATIONS[3] = SCHEMA_V3

# v4（2026-10-12，M4 B6）：tasks 加列 kind——任务类型（契约 TaskKind：
# g16|crest，历史行默认 g16）。crest 任务仅由组合流程序化生成（B10），
# 禁止组队（B6 校验 INVALID_MEMBERS）。
SCHEMA_V4 = """
ALTER TABLE tasks ADD COLUMN kind TEXT NOT NULL DEFAULT 'g16'
    CHECK (kind IN ('g16','crest'));
"""
MIGRATIONS[4] = SCHEMA_V4

# v5（2026-10-12，M4 B9）：tasks 加列 resume_of——续跑任务的任务级关联
# （可空 TEXT JSON {task_id, execution_id}=原执行；confirm 时写入，
# 派发创建执行记录时转移到执行行 resumed_from 并保留于任务行——重复
# 派发（重新排队续跑任务）关联仍在，重启不丢。freq 回落原样重跑任务
# 的文本无 @exec 引用，关联同样经此列承载）。
SCHEMA_V5 = """
ALTER TABLE tasks ADD COLUMN resume_of TEXT;
"""
MIGRATIONS[5] = SCHEMA_V5

# v6（2026-10-12，M4 B10）：组合流派发承载——
# - tasks.workflow_id：crest 任务归属的组合流（workflow 行 id；g16 行 NULL）；
# - tasks.crest_nproc：crest 任务核数（组合流 payload.crest.nproc，
#   派发资源声明与 HQ cpus 请求来源；g16 行 NULL）；
# - workflows.top_n：组合流精修构象数（终态钩子建队成员上限
#   min(top_n, 实际构象数)）。
SCHEMA_V6 = """
ALTER TABLE tasks ADD COLUMN workflow_id TEXT;
ALTER TABLE tasks ADD COLUMN crest_nproc INTEGER;
ALTER TABLE workflows ADD COLUMN top_n INTEGER;
"""
MIGRATIONS[6] = SCHEMA_V6


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
