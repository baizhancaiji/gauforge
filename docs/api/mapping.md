# G16 Web 工作台 · 界面元素 → 端点映射

> 状态：契约定稿。依据 [m0-plan.md](../plans/m0-plan.md) §2.5。REST 契约见
> [openapi.yaml](openapi.yaml)；SSE 见 [sse.md](sse.md)。
> 走查判据：每个界面元素至少一行；每个端点至少被一个元素引用（无孤儿）。

## 01 候选任务

| 界面元素 | 端点 | 事件（SSE） |
|---|---|---|
| 导入文件/文件夹（文件选择与拖拽） | POST /api/v1/candidates（files[]/mode，M1） | `candidates.changed(created)` ×N |
| 导入勾选「保存为队列」（M2，队列名=文件夹名） | POST /api/v1/candidates（queue_from_folder/folder_name，M2） | `candidates.changed(created)` ×N → `candidates.changed(moved_out)` ×N → `queues.changed(created)`（越界回落时仅 `created` ×N） |
| 候选列表（id/文件名/title/来源标记/失败归因） | GET /api/v1/candidates | `candidates.changed` → 重拉当前页 |
| 行点击 → 右侧只读预览（分块 + 原子数/分子式） | GET /api/v1/candidates/{id}/preview | — |
| 行内「提交」确认框完整输入 | GET /api/v1/candidates/{id}/input | — |
| 确认框 Link0 黄色警告 | preview 响应 `blocks.link0.missing` | — |
| 行内「提交」动作 | POST /api/v1/candidates/{id}/submit | `pending.snapshot` |
| 「编辑」分块保存（M2） | PUT /api/v1/candidates/{id}/blocks/{section} | —（保存响应即新态） |
| 「编辑」初始化与 CRLF 检出（M2） | GET preview / GET input（id 跨形态延续：候选与失败回退队列成员可读，守卫与 PUT blocks 一致） | — |
| 「-」剔除 | DELETE /api/v1/candidates/{id} | `candidates.changed` |

## 02 队列

| 界面元素 | 端点 | 事件（SSE） |
|---|---|---|
| 队列列表（id/名称/成员数/状态/回退标记） | GET /api/v1/queues | `queues.changed` → 重拉 |
| 列表排序下拉（默认序/名称升降序，选择经 ui-preferences 跨会话记忆） | GET·PUT /api/v1/ui-preferences（键 `queues.sort`） | — |
| 行展开成员概览（任务/分子式/状态/失败归因） | GET /api/v1/queues/{id} | — |
| 「创建队列」（M2） | POST /api/v1/queues | `queues.changed(created)` |
| 「编辑队列」（改名/重排/移除成员，M2） | PATCH /api/v1/queues/{id} | `queues.changed(updated)` |
| 「删除队列」（二次确认，M2） | DELETE /api/v1/queues/{id} | `queues.changed(deleted)` → `candidates.changed` |
| 「直接提交」（M2） | POST /api/v1/queues/{id}/submit | `queue.status` → `pending.snapshot` |

## 03 待执行

| 界面元素 | 端点 | 事件（SSE） |
|---|---|---|
| 容量仪表 + 窗口读数 | GET /api/v1/pending | `pending.snapshot` |
| 席位列表（S 号/类型/成员概览/窗口边界） | GET /api/v1/pending | `pending.snapshot` |
| 席位内成员移除（未执行，M1） | DELETE /api/v1/pending/seats/{seat_id}/members/{task_id} | `pending.snapshot` |
| 整席移除（单任务退候选/队列回退，M1） | DELETE /api/v1/pending/seats/{seat_id} | `pending.snapshot` |
| 整席重排（M1） | PUT /api/v1/pending/order | `pending.snapshot` |

## 04 执行中

| 界面元素 | 端点 | 事件（SSE） |
|---|---|---|
| 在跑通道卡列表（并行同屏） | GET /api/v1/executions | — |
| 通道卡读数（CPU/MEM/OPT STEP/SCF） | GET /api/v1/executions/{id} | `execution.monitor`/`execution.progress`/`execution.stalled` |
| 停滞告警行 | — | `execution.stalled` |
| 手动停止（二次确认，M1） | POST /api/v1/executions/{id}/stop | `task.status`/`history.appended` |
| 顶栏状态灯排（在跑/排队/告警） | — | `execution.progress`/`pending.snapshot`/`execution.stalled` |

## 05 历史

| 界面元素 | 端点 | 事件（SSE） |
|---|---|---|
| 历史表格（终态/归因/耗时/资源/队列归属） | GET /api/v1/history | `history.appended` → 重拉当前页 |
| 排序切换（提交时间/完成时间/文件名，升降；`sort` 参数；选择经 ui-preferences 跨会话记忆，历史页与归档页键分立） | GET /api/v1/history?sort=…；GET·PUT /api/v1/ui-preferences（键 `history.sort`/`archive.sort`） | 同上（重拉当前页） |
| 行点击 → 详情抽屉（全字段 + input_hash/监控摘要/chk 快照/result_ref） | GET /api/v1/history/{id} | — |
| 查看输入原文 | GET /api/v1/history/{id}/input | — |
| 输出预览 / 导出 | GET /api/v1/history/{id}/output | — |
| 归档 | POST /api/v1/history/{id}/archive | — |
| 重新排队（M1） | POST /api/v1/history/{id}/requeue | `pending.snapshot` |
| 退回候选（M1） | POST /api/v1/history/{id}/return-candidate | `candidates.changed(created)` |
| 手动触发 chk/rwf 清理（M1） | POST /api/v1/history/cleanup | — |

## 06 设置

| 界面元素 | 端点 | 事件（SSE） |
|---|---|---|
| 启动级只读区（锁定图标 + 值） | GET /api/v1/settings | — |
| 运行级分组表单（生效语义徽标；自动检查更新周期 update_check_interval 四选，v2.1.0） | GET /api/v1/settings | — |
| 「保存」 | PUT /api/v1/settings | `settings.updated` |
| 更新卡状态显示与页面恢复（八态状态机、不渲染卡片标题，v2.1.0） | GET /api/v1/update/status | `update.phase`/`update.progress` |
| 更新卡「检查更新」（v2.1.0） | POST /api/v1/update/check | `update.phase` |
| 更新卡「立即更新」（三守卫置灰：running/进行中/源码形态，v2.1.0） | POST /api/v1/update/apply | `update.phase`/`update.progress` |
| 更新卡代理通道切换（直连/默认代理/自定义 URL，读写工作区 .update-proxy，v2.1.0） | PUT /api/v1/update/proxy | — |
| 队列/历史/归档页排序规则持久化（跨重启/更新/断联不回默认，键 `queues.sort`/`history.sort`/`archive.sort`） | GET·PUT /api/v1/ui-preferences | — |

## 系统级（跨页）

| 界面元素 | 端点 | 事件（SSE） |
|---|---|---|
| 健康/启动冒烟 | GET /api/v1/system/health | — |
| SSE 实时事件订阅 | GET /api/v1/events | 全事件 |
| 侧栏电源灯（服务在线态） | — | `system.heartbeat` / `system.snapshot` |
| 侧栏 HQ 连接状态行（LED + 已连接/未连接/未启用） | — | `hq.status` / `system.snapshot`（`hq` 字段） |
| 侧栏品牌区版本行（含更新可用 accent 小圆点，点击跳设置页更新卡；v2.1.0） | GET /api/v1/system/health（版本号）；GET /api/v1/update/status（圆点明灭恢复） | `update.phase` |

## 端点覆盖对照（无孤儿检查）

全部 39 个操作均已在上表被至少一个界面元素引用：
candidates(7 个操作) · queues(6) · pending(4) · executions(3) · history(8) ·
settings(2) · system/events(3) · update(4) · ui-prefs(2)。—— 由 A5
walkthrough 逐条核对（update(4) 为 v2.1.0 功能更新契约预告，端点实施见实施
计划 D3；ui-prefs(2) 为视图偏好持久化域）。