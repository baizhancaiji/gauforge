# G16 Web 工作台 · SSE 事件契约（M0）

> 状态：契约定稿。依据 [m0-plan.md](../plans/m0-plan.md) §3。REST 契约见
> [openapi.yaml](openapi.yaml)；界面元素映射见 [mapping.md](mapping.md)。
> 本文档为 SSE 事件唯一事实来源，变更一律走文档 diff（roadmap §4）。

## 1. 端点、帧格式与公共约定

- 端点：`GET /api/v1/events`，`Accept: text/event-stream`；响应头
  `Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache`、
  `X-Accel-Buffering: no`。
- **单流全事件**：一条连接承载全部事件，前端按帧头 `event` 字段分发；不设
  topic 订阅参数（单机单用户、流量小，避免过度设计）。
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

## 2. 事件全集枚举（12 类）

分三类语义：**数据事件**（载荷即最新状态，可直接渲染）、**通知事件**
（触发客户端重拉 REST）、**保活/恢复事件**。

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

## 3. 推送时机表（逐事件「何时推什么」速查）

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

## 4. 连接管理

- **并发连接**：不限流（单机单用户、多标签页场景 ≤ 个位数）；每连接独立订阅与
  有界发送队列。
- **心跳保活**：定时推 `system.heartbeat`；写失败（连接已死）即清理订阅。
- **背压/慢消费**：每连接服务侧有界队列 256 条；溢出即主动断开该连接（客户端
  重连走 §5 恢复语义），保证不拖慢事件生产者、不静默丢事件。
- **连接关闭**：客户端断开即取消订阅、释放资源（FastAPI StreamingResponse 的
  finally 语义）。
- **超时**：连接无应用层空闲超时（有心跳）；上游代理场景由 `X-Accel-Buffering: no`
  规避缓冲（dev 直连 uvicorn 无代理，部署文档注明）。
- **认证**：无（仅绑 127.0.0.1，安全边界即 roadmap §5）。

## 5. 断线重连与 Last-Event-ID 续传

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

## 6. 异常处理机制

| 异常场景 | 行为 |
|---|---|
| 单事件序列化失败 | 跳过该条、记录日志，不影响连接与其他事件 |
| 事件生产者抛异常 | broker 捕获隔离，订阅者不受影响 |
| 客户端半开连接 | 心跳写失败检测，清理订阅 |
| 服务端重启 | 序号归零 → 客户端重连收到 `system.snapshot(server_restarted=true)` 全量重建 |
| 增量解析/psutil 采样瞬时失败 | 该周期 progress/monitor 事件缺席，下一周期恢复；连续失败转 `execution.stalled` 判定输入（M1） |
| 客户端事件处理 JS 异常 | 前端骨架全局捕获，断开重连一次自愈（不影响服务端） |

## 7. M0 mock 推流剧本

启动后循环演示（周期 30s，可在 `web/tests` 中加速驱动）。实现按旅程组织：
首轮走「队列旅程」（队列席位 提交→执行→成员依次派发/读数/收尾→完成→
席位释放，即步骤 8 的全流转 + 成员级步骤 2–7），后续轮走「单任务滚动
旅程」（步骤 1–7：收尾最旧执行腾席 → 新候选入席 → 派发 → 读数 → 停滞 →
成功 → 席位释放），席位容量守恒：

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