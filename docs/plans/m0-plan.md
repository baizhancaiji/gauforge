# M0 · 契约与骨架 — 详细执行计划

> 状态：执行计划（依据 [roadmap.md](../specs/roadmap.md) §3 M0 制定）。
> 本文是 M0 的任务分解与设计基线：§2/§3 为 API 与 SSE 两份契约的**设计规范**
> （M0 阶段 A 的直接输入，落盘为 `docs/api/openapi.yaml` 与 `docs/api/sse.md`），
> §4–§8 为实施、走查、提交与验收方案。
> 本文与 roadmap 冲突时以 roadmap 为准；契约一经定稿，变更一律走文档 diff（roadmap §4）。

## 0. 目标、范围与依据

**目标**（= roadmap M0 定义）：API 契约定稿落盘 `docs/api/`，覆盖 §2.1 全部领域
对象、六类页面数据需求与 SSE 事件契约；后端骨架按契约实现、全部端点返回契约
一致的内存 mock；前端空壳连 mock 数据渲染六类页面。

**不做**（非目标，属 M1/M2）：SQLite 持久化、真实导入/执行/停止语义、g16 与 HQ
集成、分块编辑、队列真实生命周期。M0 的端点对这些动作**返回可演示的 mock 结果**，
语义按契约定义完备。

**依据**：roadmap §2.1（领域模型与状态机）、§2.4–§2.7（路径/配置/字段/输入
结构）、§3 M0 工作项 1–8、§8（HQ 实地认知对契约的约束）。

## 1. 任务分解与追踪（WBS）

四个阶段，任务编号贯穿全文引用。规模：S ≈ 半天内，M ≈ 1 天，L ≈ 2 天。

| 编号 | 任务 | 产出物 | 验收标准（可验证） | 依赖 | 规模 | 对应 roadmap 工作项 |
|---|---|---|---|---|---|---|
| A1 | 契约载体骨架 | `docs/api/openapi.yaml`（info/servers/公共 components 骨架）、`docs/api/sse.md`（骨架） | YAML 可被 openapi-core 加载；两文件入库 | — | S | 1 |
| A2 | 领域对象 schema 定稿 | openapi.yaml `components/schemas`：7 对象（6 实体 schema + Result 占位决议，§2.2）+ 公共约定（id/分页/错误/分块结构） | 每个 schema 有 description 与字段级「赋值时机/可空」标注；字段集对照 roadmap §2.6 走查通过（含 Candidate 输入副本引用派生注记） | A1 | M | 2 |
| A3 | REST 端点清单定稿 | openapi.yaml `paths`（§2.3 全表）+ `docs/api/mapping.md`（界面元素→端点映射） | 全部端点有请求/响应 schema 与错误码；映射表无缺失、无孤儿端点 | A2 | M | 3 |
| A4 | SSE 事件契约定稿 | `docs/api/sse.md`（本文 §3 规范的正式版：全集枚举、载荷 schema、推送时机表、重连语义） | 每事件有触发条件、载荷字段表、频率/节流约定；Last-Event-ID 语义闭环 | A2 | M | 4 |
| A5 | 契约走查（留记录） | `docs/api/walkthrough.md` | §6 走查清单逐条通过并留记录 | A3, A4 | M | 5 |
| B1 | 后端骨架与配置 | `web/src/config.py`、`web/src/main.py`（应用工厂）、目录骨架 | `uv run uvicorn web.src.main:app` 可启动；/api/v1/system/health 返回 200 | A5 | S | 6 |
| B2 | 契约生成链 | `web/scripts/gen_models.py`（openapi.yaml → `web/src/models/` pydantic 模型） | 生成产物入库且可重生成；`uv run pytest` 可发现 | B1 | M | 6 |
| B3 | REST mock 端点 | `web/src/routers/`（system/settings/candidates/queues/pending/executions/history） | §2.3 全表端点返回契约一致 mock；契约测试全绿 | B2 | L | 6 |
| B4 | SSE broker 与 mock 推流 | `web/src/sse.py` + mock 事件剧本 | mock 流按 §3.7 剧本推流；SSE 契约测试全绿 | B2 | M | 6 |
| B5 | 静态挂载与冒烟 | main.py 挂载 `web/frontend/dist` | 构建产物经后端可直接访问六页 | B3, B4 | S | 6 |
| C1 | 前端工程初始化 | `web/frontend/`（Vite+Vue3+TS+router+pinia）+ `tokens.css`/`base.css` | `npm run build` 通过；设计令牌按 [m0-frontend-design.md](m0-frontend-design.md) §2 全量落地（含明暗双主题变量组与切换），对比度实测记录 | A5 | M | 7 |
| C2 | 契约生成 TS 类型与 client | `openapi-typescript` + `openapi-fetch` 接入构建 | 类型由 `docs/api/openapi.yaml` 生成并入库 | C1 | S | 7 |
| C3 | 六页空壳组件 | 候选/队列/待执行/执行中/历史/设置 页面组件 | 六页按设计规范 §5 布局渲染后端 mock 数据（字段全展示）；组件只引用 tokens、无硬编码色值字号 | C2 | L | 7 |
| C4 | SSE 消费骨架 + 设置面板读写 | EventSource 封装（自动重连+Last-Event-ID）+ 设置页读写 + 状态灯排/通道卡读数接线 | mock 事件流驱动执行中页读数跳变与状态灯排；设置面板可改值并回显 | C2, B4 | M | 7 |
| D1 | 验收走查 | 走查记录（对照 §8 验收标准逐条执行留痕） | §8 全部条目通过 | B5, C4 | S | 8 |
| D2 | 进度同步与提交整理 | `CHANGELOG.jsonl`/`progress.json` 更新 | `validate_progress.py` 通过；提交序列符合 §7 | 全部 | S | 8 |

依赖关系：A1→A2→(A3,A4)→A5→(B*,C*)→D。B 与 C 可并行推进。

## 2. API 契约设计规范（A2/A3 输入）

### 2.1 公共约定

| 约定项 | 定稿值（M0 落盘时按此，偏离须在 walkthrough 记录原因） |
|---|---|
| 路径前缀 | `/api/v1`；资源名用复数 kebab-case（`pending` 为固定单数，指待执行队列这一唯一资源） |
| 数据格式 | 请求/响应一律 `application/json; charset=utf-8`；导入与输入/输出原文端点除外（multipart / `text/plain`） |
| 时间 | ISO 8601 带时区偏移、秒级，如 `2026-09-23T08:30:00+08:00`；耗时用秒数（`*_s` 后缀，number） |
| task/candidate id | 自增正整数（SQLite `AUTOINCREMENT` 天然满足全库永不复用，roadmap §2.1 派发去重）；JSON 中为 integer |
| queue id | 随机 6 位 base32（大写、去 `0/O/1/I` 易混淆字符，如 `AB2CDE`）；生成时对照全库查重 |
| execution id | 自增正整数；`run/<执行id>/` 目录名由其派生 |
| 布尔语义 | 开关类字段一律明确布尔（如 `skip_failed`），不用 0/1 |
| 空值 | 可空字段显式 `null`，不省略键（除 timestamp 类可选字段按 schema 标注） |
| 分页 | `?page=1&page_size=50`（默认 50=设置项 `page_size`，上限 200）；响应信封 `{"items":[],"page":1,"page_size":50,"total":123}`；单机数据量小，用 offset 式，不做 cursor |
| 排序 | 列表默认按业务时间倒序（最新在前）：候选按 id 倒序、历史按 id 倒序；待执行/在跑按席位/启动顺序正序 |
| 幂等 | GET 幂等；POST 动作类端点（提交/停止/归档/重排队/退回候选）不承诺幂等，重复调用按状态机返回 409 或当下语义 |
| 状态码 | 仅用 200/201/204/400/404/409/422/500；语义见 §2.1.1 |

#### 2.1.1 统一错误结构与错误码全集

所有非 2xx 响应体：

```json
{
  "error": {
    "code": "QUEUE_MEMBER_RANGE",
    "message": "队列成员数须为 2–10",
    "details": {"actual": 11, "min": 2, "max": 10}
  }
}
```

`code` 为 SCREAMING_SNAKE_CASE 全集枚举（契约定稿后新增错误码 = 契约 diff）：

| code | HTTP | 触发场景（示例端点） |
|---|---|---|
| `INVALID_REQUEST` | 400 | 畸形请求体/参数（全局兜底） |
| `NOT_FOUND` | 404 | 资源不存在（details 带 `resource`、`id`） |
| `VALIDATION_FAILED` | 422 | 字段级校验失败（details.errors 数组，逐字段给原因） |
| `QUEUE_MEMBER_RANGE` | 422 | 创建队列成员数越界（POST /queues） |
| `QUEUE_MEMBER_FLOOR` | 409 | 移除成员将低于下限 1（PATCH /queues/{id}、席位内移除） |
| `QUEUE_STATE_CONFLICT` | 409 | 状态机不允许：执行中删除/编辑队列、成功队列重提交、未提交队列整席移出等 |
| `QUEUE_MEMBER_LOCKED` | 409 | 已提交队列的未执行成员不可改名/编辑内容 |
| `TASK_EXECUTED_IMMUTABLE` | 409 | 已执行成员在非回退队列中不可移除 |
| `SEAT_WINDOW_LOCKED` | 409 | 席位已被并行窗口触及，不可整席重排/移除 |
| `PENDING_CAPACITY_FULL` | 409 | 在途席位满员，拒绝新提交/重新排队 |
| `TASK_STATE_CONFLICT` | 409 | 执行状态机不允许（如对已终态执行 stop） |
| `INPUT_PARSE_FAILED` | 422 | 导入/预览时输入解析失败（details 带节名与行号） |
| `INPUT_MULTISTEP_UNSUPPORTED` | 422 | 含 `--Link1--` 的多步输入拒绝导入（见 §9 决策点 1） |
| `SETTING_VALUE_INVALID` | 422 | 设置值越界/类型错误（details 逐项） |
| `SETTING_READONLY` | 409 | 试图修改启动级参数 |
| `INTERNAL_ERROR` | 500 | 服务端异常（message 不泄露内部细节） |

### 2.2 领域对象 schema（字段级定义）

通用规则（落盘到 openapi.yaml 每个 schema 的 description）：

- 每字段标注赋值时机：`C`=创建必填、`T`=状态流转更新、`F`=终态补齐后冻结、
  `O`=可空；对应 roadmap §2.6 字段生命周期表。
- 以下对象中 `*_at` 时间戳字段（`created_at`/`updated_at`）为 §2.6 清单的
  **补充字段提案**（列表排序与展示需要，见 §9 决策点 8），走查时逐条确认。

枚举全集（契约 components 固化）：

| 枚举 | 取值 | 说明 |
|---|---|---|
| `TaskState` | `staged / running / succeeded / failed / skipped` | 任务粒度状态机（roadmap §2.1）；`archived` 是历史条目标记不是任务态 |
| `QueueState` | `unsubmitted / submitted / executing / completed` | `completed`=成功唯一稳定终态；失败自动回退为 `unsubmitted` |
| `QueueFinishReason` | `success / abort_on_failure / finished_with_failures / manually_stopped` | 最近一次执行结束原因 |
| `CandidateOrigin` | `imported / returned_unrun / returned_failed / returned_succeeded` | 来源标记 |
| `FailureCause` | `manually_stopped / program_error / external_interrupt / predecessor_failed / queue_manually_stopped` | 终态归因；succeeded 为 null |
| `SeatKind` | `task / queue` | 待执行席位类型 |

#### Candidate（创建即完整，此后不变）

| 字段 | 类型 | 时机 | 说明 |
|---|---|---|---|
| `id` | integer | C | 与后续 Task 同 id（跨形态延续，§2.6 ③） |
| `filename` | string | C | 导入文件名（退回候选沿用任务文件名） |
| `origin` | CandidateOrigin | C | 来源标记 |
| `failure_note` | string? | C | 仅 `returned_failed`：归因附注（原因+失败位置）；其余 null |
| `created_at` | string(datetime) | C | 补充字段提案 |
| `title` | string? | — | **不落库**，列表/详情响应中实时解析注入（§2.6 ①）；解析失败为 null |

`GET /candidates` 响应逐项含 `title`（后端现解析）；不设独立 title 字段存储。

输入副本引用（roadmap §2.6 Candidate 属性）：由 id 派生 `inputs/<id>`，契约
**不单独暴露字段**——需要文件位置处后端由 id 推导即可，入 API 徒增第二事实来源。

#### Task（零自有属性，纯关系；无独立端点，作为嵌套表示）

| 字段 | 类型 | 时机 | 说明 |
|---|---|---|---|
| `id` | integer | C | 同候选 id |
| `queue_id` | string? | C/T | 归属队列；直接提交者为 null |
| `position` | integer | T | 队列内顺序（0 起） |
| `time_limit_s` | integer | C/T | 墙钟上限，默认 0=不限制；M0 契约占位（M1 派发映射 HQ time_limit，M2 提交时设置） |
| `state` | TaskState | T | 派生展示字段：取最近一次执行状态，从未派发且在席为 `staged` |

#### Queue

| 字段 | 类型 | 时机 | 说明 |
|---|---|---|---|
| `id` | string | C | 随机短 id |
| `name` | string | C/T | 默认 `yyyymmddhhmmss` 时间戳 |
| `member_ids` | [integer] | C/T | 有序成员（创建校验 2–10；此后只减不增、≥1） |
| `skip_failed` | boolean | C/T | 跳过失败任务开关 |
| `state` | QueueState | T | 四态流转 |
| `rollback_flag` | boolean | T | 失败回退标记 |
| `rollback_count` | integer | T | 回退次数，0 起 |
| `last_failure` | object? | T | `{finish_reason, failure_positions:[task_id], members:[{task_id,state,cause}]}`；队列成功终态时清 null |
| `finish_reason` | QueueFinishReason? | T | 最近一次执行结束时写入 |
| `created_at` / `updated_at` | datetime | C/T | 补充字段提案 |

#### PendingQueue（席位；`GET /pending` 响应）

| 字段 | 类型 | 时机 | 说明 |
|---|---|---|---|
| `seat_id` | integer | C | 席位标识（追加自增） |
| `kind` | SeatKind | C | 单任务 / 整条队列 |
| `task_id` | integer? | C | kind=task 时 |
| `queue_id` | string? | C | kind=queue 时 |
| `position` | integer | T | 席位顺序（0 起） |
| `members` | [{task_id, filename, state}] | T | kind=queue 时的成员概览（复用 Task 派生态）；kind=task 为单元素 |
| `locked` | boolean | T | 并行窗口已触及（头部区）→ 不可整席重排/移除 |

响应附全局字段：`capacity: {limit, occupied, available}`、`window_size`（当前并行执行数）。

#### Execution（运行中；`GET /executions`）

| 字段 | 类型 | 时机 | 说明 |
|---|---|---|---|
| `id` | integer | C | 派发时创建；`run/<id>/` 派生 |
| `task_id` | integer | C | |
| `queue_id` | string? | C | |
| `state` | TaskState | T | 运行视图只出现 `running`（staged 由 /pending 表达） |
| `submitted_at` / `started_at` | datetime | C/T | started_at 于 running 补 |
| `input_hash` | string? | C | 派发时计算（`sha256:<hex>`）；skipped 无（null） |
| `resources` | object | C | `{nproc:{value,defaulted},mem_gb:{value,defaulted}}`——Link0 声明与补齐标记（§2.6） |
| `hq_job_id` | integer? | T | 提交 HQ 后回填（M1 起；M0 mock 给演示值） |
| `filename` | string | C | 冗余自任务，列表展示用 |
| `monitor` | object? | T | 运行中实时：`{cpu_percent,mem_rss_mb,elapsed_s}`（psutil，§8.4） |
| `progress` | object? | T | `{opt_step?,scf_cycle?,converged?,last_line?}`——增量解析注入 |

#### HistoryEntry（终态冻结；`GET /history`）

Execution 全部字段的超集，追加：

| 字段 | 类型 | 时机 | 说明 |
|---|---|---|---|
| `finished_at` | datetime | F | |
| `cause` | FailureCause? | F | succeeded 为 null |
| `wall_time_s` | number | F | started_at→finished_at 派生 |
| `monitor_summary` | object? | F | **仅 succeeded**：`{cpu_peak_percent,mem_peak_mb,stall_alerts,stall_total_minutes}`（§2.6 ②） |
| `chk_snapshot` | object | F | `{protected:boolean,location?:string}`——非正常终止保全快照标记与位置 |
| `archived` | boolean | F→ | 冻结后唯一可变字段 |
| `result_ref` | string? | — | M3 占位，恒 null |

注：skipped 条目无 `run/` 目录 → `input`/`output` 端点回落任务输入副本 / 返回 404（契约注明）。

#### Result（M3 占位）

M0 不设独立端点、不列字段——占位形态即 `HistoryEntry.result_ref`（恒 null）
加本节决议：Result 字段全集随 M3 契约 diff 一次性扩展（roadmap §2.6 原则 3）；
M0 走查仅核对「引用位存在、语义指向结果分析管道」（§2.1：仅正常结束的执行
进入管道）。

#### 设置项（`GET/PUT /settings`）

响应分组两级（roadmap §2.5），每项含元数据供前端数据驱动渲染：

```json
{
  "startup": [
    {"key": "workspace_root", "value": "/home/u/g16web", "env_var": "G16WEB_HOME", "editable": false},
    {"key": "bind_address", "value": "127.0.0.1", "env_var": "G16WEB_BIND_ADDR", "editable": false}
  ],
  "runtime": [
    {"key": "listen_port", "value": 8300, "value_type": "integer", "range": {"min": 1, "max": 65535},
     "editable": true, "effect": "on_restart", "description": "监听端口（保存后下次重启生效）"},
    {"key": "pending_seat_limit", "value": 3, "value_type": "integer", "range": {"min": 1, "max": 10},
     "editable": true, "effect": "immediate_retroactive", "description": "在途席位上限（调小即时生效并自队尾挤出）"}
  ]
}
```

`effect` 枚举：`immediate`（即时）/ `immediate_retroactive`（即时且追溯，仅席位上限）/
`new_submissions`（其后新提交生效）/ `on_restart`（重启生效）。

运行级参数全集（M0 契约逐项标注生效语义，即 roadmap §7.4 的落地）：

| key | 默认 | 范围 | effect |
|---|---|---|---|
| `listen_port` | 8300 | 1–65535 | on_restart |
| `pending_seat_limit` | 3 | 1–10 | immediate_retroactive |
| `parallel_window` | 1 | 1–6 | new_submissions（在跑不追溯，窗口按新值收敛） |
| `chk_rwf_retention_days` | 7 | ≥1 | new_submissions |
| `stall_threshold_minutes` | 10 | ≥1 | new_submissions |
| `page_size` | 50 | 1–200 | immediate |
| `sse_heartbeat_seconds` | 15 | ≥5 | immediate |
| `link0_default_nproc` | 4 | ≥1 | new_submissions |
| `link0_default_mem_gb` | 8 | ≥1 | new_submissions |
| `g16_root` | `~/g16` | 路径 | new_submissions |

`PUT /settings` 请求体 `{"values": {<key>: <value>, ...}}`：**全有或全无**——任一项
校验失败整批拒绝（422，details 逐项）；成功返回更新后全集。

#### 输入分块结构（预览与 M2 编辑共用）

预览响应（`GET /candidates/{id}/preview`，分块结构依据 roadmap §2.7）：

```json
{
  "candidate_id": 12,
  "filename": "water.gjf",
  "blocks": {
    "link0": {"lines": ["%Chk=water.chk", "%NProcShared=4"], "missing": ["%Mem"]},
    "route": "# B3LYP/6-31G(d) Opt",
    "title": "water optimization",
    "charge_mult": "0 1",
    "molecule": {"atom_count": 3, "formula": "H2O1", "variables_present": true, "constants_present": false},
    "additional_sections": []
  }
}
```

- `molecule.formula`：元素统计（Hill 记法：有 C 时 C、H、其余字母序；无 C 时
  全字母序；计数 1 显式，如 `H2O1`、`C6H6O1`），单任务与队列成员的预览/
  成员概览均展示（后端解析分子说明节统计，M0 mock 给演示值）。
- `additional_sections`：可选附加输入节的有序数组（由 route 关键词触发：Gen、
  Guess=Alter、SCRF=Read 等，roadmap §2.7），每项
  `{"lines": [string], "terminator_blank": boolean}`——`terminator_blank` 标注
  该节是否需要终止空行（以手册 Section Ordering 表逐节为准，Guess=LowSymm 等
  个别例外为 false）。
- **重组不变式**（A2 落盘时写入契约 description，预览与 M2 编辑保存共用）：
  除 Link 0 外每节末尾恰好一个空行（含文件末节与文件末尾）；Link 0 之后不加
  空行；分子节 `Variables:`/`Constants:` 区之间的空行分隔不得丢失或增删。
- 可编辑节（M2）：`link0 / route / title / charge_mult / additional_sections[i]`；
  `molecule`（含原子坐标）不可编辑——结构编辑交由上游 GaussView（roadmap M2）。
- `link0.missing` 驱动行内提交确认框的黄色警告（缺 `%NProcShared`/`%Mem` 时提示
  按默认值补齐，M1）。
- 坐标原文不在预览 JSON；完整输入走 `GET /candidates/{id}/input`（`text/plain`）。
- 解析失败的节给 `null` + 顶层 `parse_errors: [{section, line, message}]`（不 422，
  预览尽力而为；导入端点才严格校验）。

### 2.3 REST 端点清单（全表，M0 全部提供 mock 响应）

标注「实施」列 = 语义真实化所在里程碑；M0 一律 mock。SSE 端点见 §3。

| # | 方法与路径 | 用途 | 实施 |
|---|---|---|---|
| 1 | GET /api/v1/system/health | 健康检查：`{status:"ok",version,uptime_s}` | M0 |
| 2 | GET /api/v1/settings | 读全部设置（两级分组） | M0（mock 值可改可回显） |
| 3 | PUT /api/v1/settings | 批量写运行级设置 | M0 mock / M1 持久化 |
| 4 | GET /api/v1/candidates | 分页列表（`?origin=&page=&page_size=`；含实时 title） | M0 |
| 5 | POST /api/v1/candidates | 导入（multipart `files[]`；批量、文件夹导入参数 `mode=files|folder`） | M1 |
| 6 | GET /api/v1/candidates/{id} | 详情 | M0 |
| 7 | GET /api/v1/candidates/{id}/preview | 分块预览（§2.2 结构） | M0 |
| 8 | GET /api/v1/candidates/{id}/input | 完整输入纯文本（提交确认框用） | M0 |
| 9 | PUT /api/v1/candidates/{id}/blocks/{section} | 分块编辑保存（单节原子保存、CRLF→LF 自动转换；候选形态与回退队列成员共用此端点——id 跨形态延续；section ∈ `link0/route/title/charge_mult/additional-<n>`，`molecule` 不可编辑；校验分级见 §9 决策点 11） | M2 |
| 10 | DELETE /api/v1/candidates/{id} | 剔除候选（删除任务实体唯一入口） | M0 mock / M1 |
| 11 | POST /api/v1/candidates/{id}/submit | 行内提交（经待执行队列；满员 409） | M1 |
| 12 | GET /api/v1/queues | 队列列表 | M0 |
| 13 | POST /api/v1/queues | 创建（成员 2–10 校验） | M2 |
| 14 | GET /api/v1/queues/{id} | 详情（含成员概览与失败记录） | M0 |
| 15 | PATCH /api/v1/queues/{id} | 更新 `{name?/member_ids?/skip_failed?}`（全量有序、原子） | M2 |
| 16 | DELETE /api/v1/queues/{id} | 删除队列（二次确认在前端） | M2 |
| 17 | POST /api/v1/queues/{id}/submit | 直接提交（保存并进入执行） | M2 |
| 18 | GET /api/v1/pending | 待执行席位 + 容量 + 窗口信息 | M0 |
| 19 | PUT /api/v1/pending/order | 整席重排 `{seat_order:[seat_id,...]}`（全量、原子） | M1 |
| 20 | DELETE /api/v1/pending/seats/{seat_id} | 整席移除（单任务退候选 / 队列回退未提交） | M1 |
| 21 | DELETE /api/v1/pending/seats/{seat_id}/members/{task_id} | 席位内移除未执行成员 | M1 |
| 22 | GET /api/v1/executions?state=running | 在跑列表（并行同屏、按 id 键控，含 monitor/progress） | M0 |
| 23 | GET /api/v1/executions/{id} | 执行详情 | M0 |
| 24 | POST /api/v1/executions/{id}/stop | 手动停止（二次确认在前端；归因 manually_stopped） | M1 |
| 25 | GET /api/v1/history | 分页列表（`?state=&queue_id=&archived=false&page=&page_size=`） | M0 |
| 26 | GET /api/v1/history/{id} | 详情（终态冻结字段全量） | M0 |
| 27 | GET /api/v1/history/{id}/input | 输入原文（`run/<id>/` 内实际执行副本；skipped 回落任务副本） | M0 |
| 28 | GET /api/v1/history/{id}/output | 输出纯文本预览（`?download=true` 触发导出；截断容错 `errors="replace"`） | M0 |
| 29 | POST /api/v1/history/{id}/archive | 归档（唯一冻结后可变操作） | M0 mock / M1 |
| 30 | POST /api/v1/history/{id}/requeue | 重新排队（原样重跑；满员 409） | M1 |
| 31 | POST /api/v1/history/{id}/return-candidate | 退回候选（新 id、带来源标记） | M1 |
| 32 | POST /api/v1/history/cleanup | 手动触发过期 chk/rwf 清理（返回清理统计） | M1 |
| 33 | GET /api/v1/events | SSE 事件流（`text/event-stream`，契约见 sse.md） | M0 |

### 2.4 代表性端点详细定义

全部 33 个端点的逐一定义在 A3 落盘 openapi.yaml 时按本节模板完成；此处给出
四类代表样例（列表分页 / 动作 / 详情 / 分块编辑保存），作为格式基线。

**GET /api/v1/candidates**（列表）

- 参数：`origin`（可选，CandidateOrigin 过滤）、`page`（int，默认 1 ≥1）、
  `page_size`（int，默认取设置 `page_size`，1–200）。
- 200 响应：

```json
{
  "items": [
    {"id": 12, "filename": "water.gjf", "origin": "imported", "failure_note": null,
     "created_at": "2026-09-23T08:00:00+08:00", "title": "water optimization"}
  ],
  "page": 1, "page_size": 50, "total": 1
}
```

- 错误：400 `INVALID_REQUEST`（参数类型/越界）。

**POST /api/v1/candidates/12/submit**（动作，M1 实施）

- 请求体：`{"time_limit_s": 0}`（可选，默认 0）。
- 200 响应：`{"seat_id": 5, "task_id": 12}`（已入待执行队列）。
- 错误：404 `NOT_FOUND`；409 `PENDING_CAPACITY_FULL`；409 `TASK_STATE_CONFLICT`
  （候选已非候选态）。

**GET /api/v1/executions/42**（详情）

- 200 响应：

```json
{
  "id": 42, "task_id": 12, "queue_id": null, "state": "running",
  "filename": "water.gjf",
  "submitted_at": "2026-09-23T08:10:00+08:00", "started_at": "2026-09-23T08:10:02+08:00",
  "input_hash": "sha256:ab12…",
  "resources": {"nproc": {"value": 4, "defaulted": false}, "mem_gb": {"value": 8, "defaulted": true}},
  "hq_job_id": 107,
  "monitor": {"cpu_percent": 380.2, "mem_rss_mb": 512.3, "elapsed_s": 1234},
  "progress": {"opt_step": 5, "scf_cycle": 3, "converged": false, "last_line": " Step number   5"}
}
```

- 错误：404 `NOT_FOUND`。

**PUT /api/v1/candidates/12/blocks/route**（分块编辑保存，M2 实施）

- 请求体：`{"lines": ["# B3LYP/6-31G(d) Opit"]}`（该节原文行数组；后端自动
  CRLF→LF，按 §2.2 重组不变式写回 `inputs/12`）。
- 200 响应：更新后的完整预览结构（§2.2 blocks）+ `warnings:
  [{"line": 1, "keyword": "Opit", "kind": "keyword_spell", "suggestion": "Opt"}]`
  ——关键词拼写检查为非阻断警告（§9 决策点 11）。
- 错误：404 `NOT_FOUND`；400 `INVALID_REQUEST`（section=`molecule` 或未知节）；
  409 `QUEUE_MEMBER_LOCKED`（已提交/执行中队列成员不可编辑内容）；422
  `VALIDATION_FAILED`（必要格式校验失败，details 逐行给原因）。

### 2.5 界面元素 → 端点映射表（落盘 `docs/api/mapping.md`）

六页逐页建表（A3 产出正式版），格式：`页面 → 界面元素 → 端点（+事件）`。
示例（候选任务页）：

| 界面元素 | 端点 | 事件（SSE） |
|---|---|---|
| 候选列表（id/文件名/title/来源标记） | GET /candidates | `candidates.changed` → 重拉当前页 |
| 行点击 → 右侧关键信息预览 | GET /candidates/{id}/preview | — |
| 行内「提交」确认框完整输入 | GET /candidates/{id}/input | — |
| 确认框 Link0 黄色警告 | preview 响应 `blocks.link0.missing` | — |
| 行内「提交」动作 | POST /candidates/{id}/submit | `pending.snapshot` |
| 「编辑」分块保存（M2） | PUT /candidates/{id}/blocks/{section} | —（保存响应即新态） |
| 「-」剔除 | DELETE /candidates/{id} | `candidates.changed` |

走查判据：每个界面元素至少一行；每个端点至少被一个元素引用（无孤儿）。

## 3. SSE 事件契约设计规范（A4 输入）

### 3.1 端点、帧格式与公共约定

- 端点：`GET /api/v1/events`，`Accept: text/event-stream`；响应头
  `Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache`、
  `X-Accel-Buffering: no`。
- **单流全事件**：一条连接承载全部事件，前端按 `event` 字段分发；不设 topic
  订阅参数（单机单用户，流量小，避免过度设计）。
- 帧格式（W3C SSE；`id` 为全局单调递增事件序号，字符串形式）：

```
id: 128
event: execution.progress
data: {"execution_id":42,"task_id":12,"opt_step":5,"scf_cycle":3,"ts":"2026-09-23T08:20:01+08:00"}
```

- 公共约定：`data` 为单行 JSON；执行类载荷一律**按执行 id 键控**（`execution_id`
  必含，并行执行下多任务同屏，roadmap M0 工作项 4）；所有载荷含 `ts`；
  `event`/`id` 走帧头，data 内不重复。
- 事件命名规范：`<域>.<对象>.<动作|性质>`，小写点分，域 ∈
  {system, candidates, queues, queue, pending, task, execution, history, settings}。

### 3.2 事件全集枚举（12 类）

分三类语义：**数据事件**（载荷即最新状态，可直接渲染）、**通知事件**（触发
客户端重拉 REST）、**保活/恢复事件**。

| 事件 | 类 | 触发条件（何时推） | 载荷字段（类型） | 频率/节流 |
|---|---|---|---|---|
| `system.heartbeat` | 保活 | 定时 | `ts` | 每 `sse_heartbeat_seconds`（默认 15s，设置项即时生效） |
| `system.snapshot` | 恢复 | 重连且 Last-Event-ID 超出重放窗口 / 首次连接（可选主动）/ 序号无法识别 | `pending`（席位全量，同 GET /pending）、`executions_running[]`（精简执行对象）、`queues_summary[]`（id/state/rollback_flag/rollback_count）、`server_restarted: boolean` | 仅按需 |
| `candidates.changed` | 通知 | 候选增（导入/历史退回候选，新 id）、删（剔除）、转化（入队/提交移出）、退回（席位移除/挤出/成员移除退回候选形态，id 延续） | `action: created/deleted/moved_out/moved_in`、`candidate_id?` | 变更即推 |
| `queues.changed` | 通知 | 队列创建/删除/成员构成或名称变更 | `action: created/updated/deleted`、`queue_id?` | 变更即推 |
| `queue.status` | 数据 | 队列状态流转（含失败回退、成功终结） | `queue_id`、`from`、`to`、`finish_reason?`、`failure_positions?: [task_id]`、`rollback_count?`、`ts` | 变更即推 |
| `pending.snapshot` | 数据 | 席位任何变化（追加/整席移除/重排/成员移除/挤出/锁定变化） | 同 GET /pending 响应体 | 变更即推；全量快照式（席位≤10，快照防止漏中间态） |
| `task.status` | 数据 | 任务状态转换：staged→running（派发，此时执行记录已建）、running→succeeded/failed、→skipped（失败中止即时/手动停止） | `task_id`、`execution_id?`（staged 无）、`queue_id?`、`from`、`to`、`cause?: FailureCause`（终态时）、`ts` | 变更即推 |
| `execution.progress` | 数据 | 增量解析发现新优化步/SCF 迭代 | `execution_id`、`task_id`、`opt_step?`、`scf_cycle?`、`converged?`、`last_line?`（截断 200 字符）、`ts` | **每 execution 至多 1 条/s**（1s 合并窗口内多条则推最新值） |
| `execution.monitor` | 数据 | psutil 采样完成（采样周期 2s，M1 实测校准） | `execution_id`、`cpu_percent`、`mem_rss_mb`、`elapsed_s`、`ts` | 2s/条，随采样直推 |
| `execution.stalled` | 数据 | 超过停滞阈值无新优化步/SCF 迭代（置位）/恢复新进度（解除） | `execution_id`、`task_id`、`stalled: boolean`、`threshold_minutes`、`last_progress_ts`、`ts` | 状态翻转即推（同一停滞期开始/解除各一条） |
| `history.appended` | 数据 | 执行到达终态、历史条目落库 | `execution_id`、`task_id`、`queue_id?`、`state`、`cause?`、`ts` | 变更即推 |
| `settings.updated` | 通知 | PUT /settings 成功 | `keys: []`、`ts` | 变更即推（多标签页同步） |

### 3.3 推送时机表（逐事件「何时推什么」速查）

| 时点（业务动作） | 触发的事件（按序） |
|---|---|
| 导入文件 | `candidates.changed(created)` |
| 行内提交成功 | `candidates.changed(moved_out)` → `pending.snapshot` |
| 队列保存（创建） | `candidates.changed(moved_out)` ×N（成员转任务）→ `queues.changed(created)` |
| 队列直接提交 | `queue.status(unsubmitted→submitted)` → `pending.snapshot` |
| 队列编辑（PATCH） | `queues.changed(updated)`（+退回成员 `candidates.changed(moved_in)`） |
| 队列删除 | `queues.changed(deleted)` → `candidates.changed(moved_in)` ×N（未执行成员；在待执行则 `pending.snapshot`） |
| 提交被拒（满员） | 无事件（HTTP 409 直接返回） |
| 派发启动任务 | （队列席位首成员派发）`queue.status(submitted→executing)` → `task.status(staged→running, execution_id)` → `pending.snapshot`（席位成员态变化） |
| 任务正常结束 | `task.status(→succeeded)` → `history.appended(succeeded)` → 若队列席位清空 `pending.snapshot` |
| 任务失败（未勾跳过） | `task.status(→failed, cause)` → 同队列未启动成员逐个 `task.status(→skipped, predecessor_failed)` → `queue.status(executing→unsubmitted, finish_reason=abort_on_failure)` + `queues.changed` → `pending.snapshot`（在跑成员收尾结束后席位释放） |
| 任务失败（勾选跳过） | `task.status(→failed)` → `queue.status`（队列结束时分流）→ `history.appended` ×N |
| 手动停止队列 | 在跑成员逐个 `task.status(→failed, manually_stopped)` → 未执行成员 `task.status(→skipped, queue_manually_stopped)` → `queue.status(→unsubmitted, manually_stopped)` → `pending.snapshot` |
| 席位重排/移除 | `pending.snapshot`（+被移除者：单任务 `candidates.changed(moved_in)`、队列 `queue.status(→unsubmitted)`） |
| 席位上限调小挤出 | `pending.snapshot` + 尾部席位逐个退回事件（`candidates.changed(moved_in)`/`queue.status(→unsubmitted)`） |
| 运行中 | 持续 `execution.monitor`（2s）、`execution.progress`（≤1s/条）、停滞时 `execution.stalled` |
| 归档历史条目 | 无专门事件（归档为冻结后唯一可变标记，归档列表属拉取型页面，按需重拉）；`history.appended` 不重发 |
| 历史重新排队 | `pending.snapshot`（追加席位；历史条目本身不变） |
| 历史退回候选 | `candidates.changed(created)`（新 id、带来源标记） |
| chk/rwf 清理 | 无事件（响应携带清理统计，拉取型） |

### 3.4 连接管理

- **并发连接**：不限流（单机单用户、多标签页场景 ≤ 个位数）；每连接独立订阅与
  有界发送队列。
- **心跳保活**：定时推 `system.heartbeat`；写失败（连接已死）即清理订阅。
- **背压/慢消费**：每连接服务侧有界队列 256 条；溢出即主动断开该连接（客户端
  重连走 §3.5 恢复语义），保证不拖慢事件生产者、不静默丢事件。
- **连接关闭**：客户端断开即取消订阅、释放资源（FastAPI StreamingResponse 的
  finally 语义）。
- **超时**：连接无应用层空闲超时（有心跳）；上游代理场景由 `X-Accel-Buffering: no`
  规避缓冲（dev 直连 uvicorn 无代理，部署文档注明）。
- **认证**：无（仅绑 127.0.0.1，安全边界即 roadmap §5）。

### 3.5 断线重连与 Last-Event-ID 续传

1. 每个事件帧带全局单调递增 `id`（服务端计数器，M0 内存版、M1 持久化）。
2. 服务端维护**重放窗口**：最近 1024 条或 5 分钟（先到为准）。
3. 客户端重连（浏览器 EventSource 自动携带 `Last-Event-ID`；自实现重连同样透传）：
   - `Last-Event-ID` 在窗口内 → 严格按序重放缺失事件，再接续实时流；
   - 超出窗口 / 缺失 / 服务端重启后序号无法识别 → 先推 `system.snapshot`
     （当前全量状态），客户端以快照重建基线后接续增量。
4. 重连退避（前端骨架实现）：1s → 2s → 5s → 10s 封顶；收到任意事件即复位。
5. 丢失容忍分级：状态类（task/queue/pending/history）必须可靠（重放 + 快照双
   兜底）；进度/监控类可丢（客户端以最新值覆盖渲染，重连后快照补齐）。
6. 列表型资源（候选/历史分页数据）不入快照——客户端收到通知事件后按需重拉
   REST 当前页。

### 3.6 异常处理机制

| 异常场景 | 行为 |
|---|---|
| 单事件序列化失败 | 跳过该条、记录日志，不影响连接与其他事件 |
| 事件生产者抛异常 | broker 捕获隔离，订阅者不受影响 |
| 客户端半开连接 | 心跳写失败检测，清理订阅 |
| 服务端重启 | 序号归零 → 客户端重连收到 `system.snapshot(server_restarted=true)` 全量重建 |
| 增量解析/psutil 采样瞬时失败 | 该周期 progress/monitor 事件缺席，下一周期恢复；连续失败转 `execution.stalled` 判定输入（M1） |
| 客户端事件处理 JS 异常 | 前端骨架全局捕获，断开重连一次自愈（不影响服务端） |

### 3.7 M0 mock 推流剧本（B4 实现规格）

启动后循环演示（周期 30s，可 `web/tests` 中加速驱动）：

1. `pending.snapshot`（新增队列席位）
2. `task.status` staged→running（含 execution_id）
3. `execution.monitor` 每 2s × 5
4. `execution.progress` 每 1s × 5（opt_step 递增）
5. `execution.stalled` 置位 → 解除（演示一次）
6. `task.status` →succeeded
7. `history.appended`
8. `queue.status` executing→completed（finish_reason=success）
9. 空闲段由 `system.heartbeat` 填充

要求：剧本数据与 REST mock 数据同源（同一内存状态对象），前端六页与事件流
展示一致。

## 4. 后端骨架实施方案（B1–B5）

### 4.1 目录结构

```text
web/
├── src/
│   ├── config.py          # 全部默认值（§2.2 设置项清单 + 启动级读取 G16WEB_* 环境变量）
│   ├── main.py            # 应用工厂；挂载路由；静态挂载 frontend/dist
│   ├── models/            # 由 openapi.yaml 生成的 pydantic 模型（生成产物，入库）
│   ├── routers/           # system / settings / candidates / queues / pending / executions / history / events
│   ├── sse.py             # broker：订阅、有界队列、心跳、重放窗口、序号
│   └── mock/              # 内存状态对象 + 事件剧本（REST 与 SSE 同源）
├── scripts/gen_models.py  # openapi.yaml → models/ 生成脚本
├── tests/                 # 见 §4.3
└── frontend/              # 见 §5
```

### 4.2 契约生成链（SSOT 策略）

- `docs/api/openapi.yaml` 为**唯一事实来源**；`datamodel-code-generator` 生成
  pydantic 模型（B2），路由 `response_model` 引用生成模型——后端不可能漂离契约。
- FastAPI 对外暴露的 `/openapi.json` **直接回读落盘 yaml**（自定义
  `app.openapi`），不用框架自省生成——前端与工具始终看到契约原文。
- 生成命令纳入 `web/scripts/gen_models.py`（uv run 单行调用；输出路径参数化，
  默认 `web/src/models/`）。实施时经 context7 核对 datamodel-code-generator
  当前版本用法（AGENTS 8.3：不可仅凭记忆写代码）。

### 4.3 测试矩阵（先测试后实现，提交顺序见 §7）

| 测试文件 | 覆盖 | 断言要点 |
|---|---|---|
| `test_contract_rest.py` | 参数化 §2.3 全表端点 | 状态码；响应体逐端点对照 openapi.yaml schema（openapi-core 校验）；错误端点返回统一错误结构 |
| `test_contract_sse.py` | `/api/v1/events` | 帧格式（id 单调、event 合法、data 单行 JSON）；载荷对照 §3.2 字段；心跳出现；带 Last-Event-ID 重连获得按序重放；超窗获得 system.snapshot；慢消费 256 溢出断连 |
| `test_settings.py` | 设置读写 | PUT 合法值生效回显；越界 422 逐项 details；改 startup 项 409 SETTING_READONLY |
| `test_openapi_ssot.py` | 生成链 | /openapi.json 与落盘 yaml 等价；models/ 与 yaml 再生成无 diff（防手改漂移） |

SSE 测试的时序断言一律用轮询等待（超时阈值放宽），不用 sleep 死等，保证稳定。

### 4.4 实施注意（仓库铁律落地）

- 路径一律 `pathlib.Path` + `/`；显式 `encoding="utf-8"`；uv 依赖单行安装。
- 依赖清单：`fastapi`、`uvicorn`、`sse-starlette`、`openapi-core`、`pyyaml`、
  `httpx`（测试客户端）、`pytest`（dev：`datamodel-code-generator`）——写入
  仓库根 `requirements.txt` / dev 组。
- M0 无 SQLite、无 HQ、无 g16 调用；config.py 仍按 §2.5 两级参数全集落齐默认值。

## 5. 前端空壳实施方案（C1–C4）

**视觉与 UX 设计的单一来源**：[m0-frontend-design.md](m0-frontend-design.md)
（「实验台仪器面板」方向：深色墨蓝底、磷光青唯一强调、等宽读数、状态徽标信号
系统、通道卡/席位行/状态灯排三个记忆点），可视化样板
[assets/m0-ui-preview.html](assets/m0-ui-preview.html) 供并排走查比对。该规范
即 roadmap §1 原则 7「视觉基调 M0 定稿」的定稿载体，随 A5 走查一并确认。

- 工程：`web/frontend/`，Vite + Vue3 + TS + vue-router + pinia；
  `src/styles/tokens.css`（设计令牌单一来源）+ `base.css`（框架/背景纹理）
  随 C1 建立；3Dmol.js 仅入依赖清单（M3 使用）。
- 契约生成：`openapi-typescript` 生成类型 + `openapi-fetch` 薄 client（同源
  契约，杜绝手写类型漂移）；生成脚本入 `package.json scripts`，产物入库。
- 路由与页面：`/candidates` `/queues` `/pending` `/executions` `/history`
  `/settings` 六页空壳，按设计规范 §5 的逐页布局渲染后端 mock 全字段
  （验证契约完整可消费）。样板已覆盖六页全部视图与组件墙，实现时逐页对照；
  四种页面原型（表格/席位/通道卡/表单）共享布局骨架。
- SSE 消费骨架（C4）：pinia store 内管理 EventSource；自动重连退避（§3.5）；
  `Last-Event-ID` 透传；`system.snapshot` 全量重建；按 event 分发到各 store；
  顶栏状态灯排与执行中通道卡读数由事件流驱动。
- 设置面板：数据驱动渲染（读 GET /settings 元数据），运行级可编辑、启动级只读
  展示；保存调 PUT 并提示各项生效语义（on_restart 提示需重启）。
- 验证：`npm run build` 与 typecheck 零错误；dev 冒烟六页 + SSE 演示；
  与样板并排走查视觉一致（tokens 同源）。

## 6. 契约走查方案（A5，留记录 `docs/api/walkthrough.md`）

1. **状态机走查**：roadmap §2.1 全部转换与整队语义逐条列行——每条注明承载
   端点/事件，打勾；重点核对：队列失败两分支、手动停止、席位挤出、哈希跳过（跳过属 M1 派发行为，契约体现在历史 input_hash 字段与重提交语义描述）、
   退回候选五条路径、删除边界、分块编辑边界（两入口共用端点、`molecule`
   不可编辑、拼写检查非阻断、重组空行不变式）。
2. **六页映射检查**：mapping.md 无缺失元素、无孤儿端点（判据见 §2.5）。
3. **M1 验收路径纸面走通**：批量导入→列表→预览→行内提交→进度→强制停止→
   历史→重启恢复，每步列出所用端点与事件，标注 M1 实施项。
4. **字段生命周期对照**：§2.6 表逐字段在 schema 标注核对；补充字段提案
   （created_at 等）逐条决议。
5. **SSE 语义闭环**：§3.3 推送时机表逐行核对触发条件与载荷完备性；重连三分支
   （窗口内/超窗/重启）演练路径写明。

## 7. 提交序列与进度同步

按「文档 → 测试 → 实现 → 进度同步」自然顺序拆分（每提交可构建可回滚）：

| # | 提交 | type |
|---|---|---|
| 1 | 制定本计划（docs/plans/m0-plan.md） | docs |
| 2 | openapi.yaml 骨架 + 公共约定 + 领域对象 schema | docs |
| 3 | openapi.yaml 全部 paths + mapping.md | docs |
| 4 | sse.md 事件契约定稿 | docs |
| 5 | walkthrough.md 走查记录（含开放决策点决议） | docs |
| 6 | 契约测试脚手架（rest/sse/settings/ssot，先红） | test |
| 7 | config.py + 应用工厂 + 目录骨架 | feat(web) |
| 8 | 契约生成链（gen_models.py + models/ 产物） | build(web) |
| 9 | REST mock 端点全表 | feat(web) |
| 10 | SSE broker + mock 推流 | feat(web) |
| 11 | 静态挂载与启动入口 | feat(web) |
| 12 | 前端工程初始化 + 契约生成 | build(frontend) |
| 13 | 六页空壳组件 | feat(frontend) |
| 14 | SSE 消费骨架 + 设置面板 | feat(frontend) |
| 15 | 验收走查记录 + 进度同步 | docs / chore |

进度同步节点（AGENTS §九）：每个阶段完成（A 末、B 末、C 末、D 末）同步一次
`CHANGELOG.jsonl` unreleased 行与 `progress.json`；feat 类提交产生用户可见行为
变化才记 changes 条目，docs/test/build 不记录（changelog-spec §1.4）。提交前
逐文件 `git add`，跑 `uv run pytest` 与 `validate_progress.py` 双闸门。

## 8. 验收标准（M0 DoD，D1 逐条执行留痕）

1. **契约完备**：只看 `docs/api/`（openapi.yaml + sse.md + mapping.md +
   walkthrough.md），能完整说出系统全部能力（六页全部操作、状态机全部流转、
   SSE 全部事件与恢复语义）——由走查记录佐证。
2. **后端契约一致**：`uv run pytest`（web/tests 全绿，含 33 端点契约校验与
   SSE 帧校验）。
3. **前端六页可用**：`uv run uvicorn web.src.main:app` 启动后，浏览器访问六页
   均渲染 mock 数据（候选/队列/待执行/执行中/历史/设置），视觉与
   [m0-frontend-design.md](m0-frontend-design.md) 及样板一致（并排走查）。
4. **SSE 演示**：执行中页在 mock 事件流驱动下实时变化（进度步进、监控刷新、
   通道卡读数跳变）；断开网络后重连，状态自愈（重放或快照）。
5. **设置面板读写**：展示全部设置项（两级分组、生效语义标注），运行级可修改、
   mock 值回显；越界值报 422。
6. **闸门通过**：`uv run python scripts/validate_progress.py` OK；前端
   `npm run build` 零错误。
7. **进度同步**：CHANGELOG.jsonl unreleased 与 progress.json 一致且反映 M0 交付。

## 9. 开放决策点（A2–A5 期间定稿，此处给建议值）

| # | 决策点 | 建议值 | 理由 |
|---|---|---|---|
| 1 | 多步任务（`--Link1--`）导入 | M0 契约拒绝：`INPUT_MULTISTEP_UNSUPPORTED`；M4 随任务链重估 | 单步闭环未稳前不引入；roadmap §2.7 要求 M0 明确 |
| 2 | 监听地址环境变量名 | `G16WEB_BIND_ADDR` | 与 `G16WEB_HOME` 同前缀，语义直白 |
| 3 | 列表排序默认 | 候选/历史按 id 倒序（新在前） | 与「最新优先」直觉一致，免排序参数 |
| 4 | SSE 重放窗口 | 1024 条或 5 分钟（先到为准） | 心跳 15s 下 5 分钟 ≈ 20 帧心跳+状态事件，1024 容量余量充足 |
| 5 | 错误信封字段名 | `error.code/message/details` | 与多数框架一致，DSH 工具易解析 |
| 6 | 前端 client 方案 | openapi-typescript + openapi-fetch | 同作者、零运行时依赖、类型安全；orval 生成物过重 |
| 7 | pydantic 模型生成 | datamodel-code-generator | 事实标准；对 OpenAPI 3.1 支持需实测，异常则降 3.0.3 |
| 8 | §2.6 之外补充字段 | Candidate/Queue 加 created_at(+updated_at) | 列表排序与展示需要；走查逐条确认后定稿 |
| 9 | monitor 采样周期 | 2s 固定（不做设置项） | §2.5 未列该参数，不过度设计；M1 实测校准 |
| 10 | 归档列表页面归属 | history?archived=true 复用列表端点 | 归档是历史的筛选视图，不设独立资源（前端归档页为独立展示页，M1 路由增设，不改契约） |
| 11 | 编辑保存校验分级与拼写检查字典 | 必要格式校验阻断（422）；关键词拼写检查非阻断警告（200 + warnings）。字典为后端本地文件（离线知识库程序化抽取，路径属部署级配置），M2 实施细节，M0 契约不列为设置面板项 | roadmap M2 未定义阻断语义；警告级允许用户知情保存（如字典未收录的新关键词）；不扩 §2.5 运行级参数全集 |

## 10. 风险与对策

| 风险 | 对策 |
|---|---|
| OpenAPI 3.1 工具链兼容问题（生成器/校验器） | 决策点 7：实测不过则整体降 3.0.3（契约内容不受影响） |
| SSE 异步测试时序不稳 | 轮询断言 + 放宽超时；剧本加速驱动参数化 |
| mock 状态与事件剧本不一致（前后端展示漂移） | REST 与 SSE 同一内存状态对象（§3.7），ssot 测试锁定 |
| WSL2 下 npm 依赖安装慢/失败 | 锁版本 lockfile；必要时换镜像源，文档记录 |
| 契约评审发现字段遗漏导致返工 | A5 走查在 B/C 动手**之前**作为闸门（依赖序强制） |
| 33 端点全 mock 工作量超预期 | B3 按 router 分组提交（§7 #9 可再拆），逐组过契约测试 |
