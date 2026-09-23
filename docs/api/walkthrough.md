# G16 Web 工作台 · M0 契约走查记录

> 状态：走查记录（M0 工作的 A5 产出）。对照 [m0-plan.md](../plans/m0-plan.md) §6
> 五条逐项执行，并记录 §9 开放决策点定稿决议。走查是 B/C 编码动手前的闸门。

## 1. 状态机走查（¥roadmap §2.1 全部转换）

队列四态 `unsubmitted → submitted → executing → completed`（失败自动回退为
unsubmitted，非单向）：

| # | 转换 | 承载端点 | 承载事件 | 备注 |
|---|---|---|---|---|
| Q1 | unsubmitted → submitted（队列直接提交） | POST /queues/{id}/submit | `queue.status(unsubmitted→submitted)` → `pending.snapshot` | M2 实施 |
| Q2 | submitted → executing（席位首成员派发） | —（派发引擎） | `queue.status(submitted→executing)` → `task.status(staged→running)` | M1 派发 |
| Q3 | executing → completed（成功，全部成员 succeeded） | — | `task.status(→succeeded)`×N → `history.appended` → `queue.status(→completed, success)` | 含队列席位清空 `pending.snapshot` |
| Q4 | executing → unsubmitted（失败回退，两分支） | — | 未勾跳过：`task.status(→failed)` → 未启动成员 `task.status(→skipped, predecessor_failed)` → `queue.status(→unsubmitted, abort_on_failure)` | 手动停止：`→manually_stopped` |
| Q5 | completed（成功）删除边界 | — | 不提供回退/重提交 | 唯一稳定终态 |

任务五态 `staged / running / succeeded / failed / skipped`：

| # | 转换 | 承载事件 |
|---|---|---|
| T1 | staged → running（派发，执行记录已建） | `task.status(staged→running, execution_id)` |
| T2 | running → succeeded（正常结束） | `task.status(→succeeded)` → `history.appended` |
| T3 | running → failed（归因：手动停止/程序报错/外部中断） | `task.status(→failed, cause)` → `history.appended` |
| T4 | → skipped（前序失败即时 / 队列手动停止） | `task.status(→skipped, predecessor_failed|queue_manually_stopped)` |
| T5 | 任意终态 → archived | POST /history/{id}/archive（无专门事件，拉取型） |

整队与边界语义核对（roadmap §2.1 定稿条款）：

- 队列失败两分支（未勾/勾选跳过）→ Q4 覆盖，两条路径均记失败并回退为未提交 ☑
- 手动停止整队 → 在跑成员 failed(manually_stopped) + 未执行成员 skipped
  (queue_manually_stopped) + queue →unsubmitted(manually_stopped) ☑
- 席位挤出（容量调小，只作用于窗口未触及席位，在跑不追溯）→ `pending.snapshot`
  + 尾部席位逐个退回事件 ☑
- 哈希跳过（id 复用去重，M1 派发行为）→ 契约体现在历史 `input_hash` 字段
  （`sha256:<hex>` 或 null）与重提交语义；哈希跳过本身不产生新执行记录 ☑
- 退回候选五条路径（历史退回/删队列/整席移除/队列内移除未执行/回退队列移除
  failed·skipped）→ 均以 `origin` 来源标记区分（imported / returned_*) ☑
  见 Candidate schema 与 return-candidate 端点。
- 删除边界 → 候选「-」为删除任务实体唯一入口（DELETE /candidates/{id}）☑
- 分块编辑边界 → 两入口共用 PUT /candidates/{id}/blocks/{section}（id 跨形态延续）；
  `molecule` 不可编辑（400）；拼写检查非阻断（200 + warnings）；重组空行不变式
  写入 InputPreview description ☑

## 2. 六页映射检查

- [mapping.md](mapping.md) 六页逐页建表；每个界面元素至少一行、33 个操作均被引用
  （无孤儿端点，见 mapping.md 末尾覆盖对照）。☑

## 3. M1 验收路径纸面走通

批量导入→列表→预览→行内提交→进度→强制停止→历史→重启恢复：

| 步骤 | 端点 | 事件 | M1 实施 |
|---|---|---|---|
| 批量导入 3 份（含重复导入验证 id 唯一） | POST /candidates (multipart) | `candidates.changed(created)` | M1 |
| 候选列表（id/文件名/title） | GET /candidates | — | M0 |
| 点击行只读预览关键信息 | GET /candidates/{id}/preview | — | M0 |
| 行内提交（确认框含坐标；缺 %NProcShared/%Mem 黄警） | POST /candidates/{id}/submit | `pending.snapshot` | M1 |
| 实时优化步/SCF | — | `execution.progress` | M1（自写增量解析） |
| 强制停止（二次确认） | POST /executions/{id}/stop | `task.status(→failed, manually_stopped)` → `history.appended` | M1 |
| 历史可查且归因正确；被提交者移出候选列表 | GET /history | `candidates.changed(moved_out)` | M0/M1 |
| 重启 g16web 全部状态恢复 | GET /events (+system.snapshot) | `system.snapshot(server_restarted=true)` | M1（SQLite + journal 对账） |

## 4. 字段生命周期对照（roadmap §2.6）

- 字段集一次定死：openapi.yaml 7 对象 schema 全部字段含「创建/流转/终态补齐/可空」
  时机标注（description）☑
- 三项已定稿落为字段：
  - ① title 实时解析、不落库 → Candidate.title（响应注入，nullable）☑
  - ② 监控摘要仅记 succeeded → HistoryEntry.monitor_summary（仅 succeeded）☑
  - ③ id 跨形态延续 + 派发去重 → Candidate.id == Task.id；历史退回候选新建 id ☑
- §2.6 之外补充字段提案（m0-plan 决策点 8）：Candidate.Created + Queue.created_at/
  updated_at 已采纳并落库 ☑

## 5. SSE 语义闭环

- §3.3 推送时机表逐行核对触发条件与载荷完备性（见 sse.md §2/§3）☑
- 重连三分支演练路径：窗口内重放 / 超窗 system.snapshot / 服务端重启
  system.snapshot(server_restarted=true)（sse.md §5）☑
- 丢失容忍分级、背压 256 溢出断连、心跳写失败清理（sse.md §4–§6）☑

## 6. 开放决策点决议（m0-plan §9 定稿）

| # | 决策点 | 决议 |
|---|---|---|
| 1 | 多步任务导入 | 采纳建议：M0 契约拒绝（`INPUT_MULTISTEP_UNSUPPORTED`），M4 随任务链重估 |
| 2 | 监听地址环境变量 | `G16WEB_BIND_ADDR`（与 G16WEB_HOME 同前缀） |
| 3 | 列表排序默认 | 候选/历史按 id 倒序；待执行/在跑按席位/启动顺序正序 |
| 4 | SSE 重放窗口 | 1024 条或 5 分钟（先到为准） |
| 5 | 错误信封字段名 | `error.code/message/details` |
| 6 | 前端 client 方案 | openapi-typescript + openapi-fetch |
| 7 | pydantic 模型生成 / OpenAPI 版本 | datamodel-code-generator；**选 OpenAPI 3.0.3**（保全生成器/校验器兼容，契约语义不受影响） |
| 8 | §2.6 之外补充字段 | 已采纳（见 §4 本记录） |
| 9 | monitor 采样周期 | 2s 固定，不做设置项 |
| 10 | 归档列表页面归属 | history?archived=true 复用列表端点（前端归档页 M1 独立路由） |
| 11 | 编辑校验分级与拼写字典 | 必要格式校验阻断（422）；拼写检查非阻断警告（200+warnings）；字典为部署级本地文件，M2 实施 |

## 7. 走查结论

A1–A5 全部通过，B/C 阶段可启动。

## 8. M0 D1 验收走查（六页 mock 联演，2026-09-23）

对照 [m0-plan.md](../plans/m0-plan.md) §8 验收标准逐条留痕。环境：
`uv run uvicorn web.src.main:app`（mock 模式，127.0.0.1:8300，构建后前端静态托管），
浏览器实测 + curl 逐帧核验。

| # | 验收项（m0-plan §8） | 结果 | 留痕 |
|---|---|---|---|
| 1 | 契约完备（A5 走查） | 通过 | 本记录 §1–§7（此前已入库） |
| 2 | 后端契约一致 | 通过 | `uv run pytest` 23 passed（33 端点契约校验 + SSE 帧校验） |
| 3 | 前端六页可用 | 通过 | 候选页 8 条 job*.gjf（IMPORTED 徽标/预览按钮）、行内只读预览卡（title/route/charge·mult/原子统计分块）、队列卡片（状态徽标 COMPLETED—SUCCESS）、待执行席位 S13/S28 + 容量仪表 OCCUPIED 2/6、历史 12 条（状态筛选 全部/SUCCEEDED/FAILED/SKIPPED + 归因/耗时列）、设置面板两级分组。全程 console 零报错 |
| 4 | SSE 演示 | 通过 | 通道卡经 task.status 事件实时出现；curl -N 抓流 36s 逐帧核验：system.snapshot → task.status(staged→running) → execution.monitor×5（cpu 52→88 / mem 405→505 递增）→ execution.progress×5（opt_step 1→5）→ stalled(true) → progress(6) → stalled(false) → task.status(→succeeded) → history.appended → pending.snapshot（席位释放）→ system.heartbeat，与剧本时序一致。浏览器侧读数窗口约 4s（0.4s 加速演示），肉眼捕获不完整以 curl 逐帧为准 |
| 5 | 设置面板读写 | 通过 | 越界值 999 → 422「值越界或非法：out_of_range」+ 字段级错误提示；合法值保存成功「设置已保存」 |
| 6 | 闸门通过 | 通过 | `uv run python scripts/validate_progress.py` OK；`npm run build` 零错误（此前已验） |
| 7 | 进度同步 | 通过 | CHANGELOG.jsonl unreleased 与 progress.json 反映 M0 全部交付 |

备注：执行中页左下「HQ 未连接」灯为 M0 mock 预期表现（无真实 HQ 后端，
hq 连接状态真实化属 M1 B4/B11 范畴），不计为缺陷。

结论：M0 DoD 全部通过，D1 走查完成，满足 M1 开工前置条件。