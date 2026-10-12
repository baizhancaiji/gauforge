# M4 验收记录（D3 走查留痕 + D 阶段缺陷修复）

> 依据 [m4-plan.md](m4-plan.md) §4.10/§7.2 执行并留痕。走查日期：2026-10-12。
> 走查环境：WSL2 单机（12 核），**真机 g16 + 真机 crest 3.0.2 全链路**——HQ
> server/worker 真实派发（`target/release/hq`，**经 `G16WEB_HQ_BIN` 显式指
> 向仓库构建产物**——PATH 上残留 2026-06-03 上游旧版 `~/opt/hyperqueue/hq`
> 会抢占解析，重入①所需的 per-job crash_limit 仅新内核支持，走查实例一律
> 以环境变量钉死新内核），执行、收尾（formchk/解析）与 crest 构象搜索均由
> 真机承担（`~/g16`、`~/opt/crest-3.0.2`，A5 实测锚点同源）。隔离工作区
> `/tmp/m4acc/home`（`G16WEB_HOME`），独立实例 `127.0.0.1:8398`（内联
> uvicorn，引擎开）。GUI 走查经浏览器黑盒驱动（截图留存
> `.playwright-mcp/`，前缀 `m4-p1-*/p5-*/p6-*/p7-*/p8-*`，不入库），关键
> 断言一律以服务端 API 为准（m3 走查教训沿用）。本记录随走查实时登记，
> 非收尾集中补录。
>
> 走查期运行级设置改动逐条留痕（走查后即时恢复）：`parallel_window`
> 1→2（依赖停等图注的可观测需要 window≥2——window=1 时保序停等语义为
> 「窗口满」、wait_reason 恒 null，见路径 1 注）；`pending_seat_limit`
> 3→1→3（路径 7 满员受控）；`crest_root` →空目录→恢复（路径 8）。

## 0. 走查环境准备记录（与走查动作的区分）

- 隔离工作区 `/tmp/m4acc/home`（`run/`、`inputs/`、`hq/` 布局由服务首次
  启动生成）；样本与现场不入库、可重建（本节即重建口径）。
- 真机样本 `/tmp/m4acc/samples/`（经 API/GUI 导入候选，任务 id 以
  `候选#N` 标注）：水分子链样本（w_opt/w_freq/w_sp/w_opt2/w_opt3）、
  慢优化样本（bz_deep_opt/bz_deep_opt2 拉伸苯 6-311+g(2d,p)、
  naph_deep_opt/naph_deep_res 拉伸萘 6-311+g(2d,p)，后者约 5 分钟——
  本机 g16 对常规小分子秒级完成，强停/停等窗口一律以拉伸几何+重基组
  构造）、续跑目标（naph_td TD(nstates=6) 单点、bz_freq_slow 频率）、
  组合流候选（etoh 乙醇、meoh 甲醇、etoh2 乙醇副本）、失败注入
  （w_opt_bad 伪关键字）、校验场景样本（cyc_a/cyc_b/dang/xq_ref/
  single_ref/fwd_a/fwd_b/exec_ref）。
- 前端构建产物为走查前 `npm run build` 重建（C 阶段整改全量在位）。

## 1. D3 走查发现并修复的缺陷（随查随修，一缺陷一提交）

| # | 缺陷 | 归因 | 修复 | 复验 |
|---|---|---|---|---|
| ① | 窗口停等图注永不及 UI：依赖/资源停等原因（wait_reason）仅在 REST 直读可见，待执行页成员子表恒显示「等待」 | `Dispatcher.wait_reasons` 逐 tick 重算，但 `pending.snapshot` 推送仅挂在席位增删（`_release_seat_task`/`_settle_queue_seat`）——停等的出现与解除都不触发推送，SSE 驱动的前端拿不到带 wait_reason 的快照 | `advance()` 改包装层：原因集相对上一轮（`last_wait_reasons` 类级注册表）变化即推送 pending.snapshot（出现与解除双向）；测试 `test_wait_reason_change_pushes_snapshot`（变化推/稳定不重推/窗口满解除推） | 修复实例重启后：拉伸苯成员等资源图注上屏（title「声明资源大于当前空闲 — 窗口停等资源释放」，m4-p1-wait-reason-annotation.png）；依赖停等图注同路径渲染（QD 链成员 29 于上游 5 分钟 naph 深优期间 REST 捕获 `wait_reason=dependency`，GNWHKD 链成员 30 同证） |
| ② | 勾选跳过开关的三段链队列收束悬挂：前驱 failed → 传递 skipped 全部落齐后队列永停 `executing`、席位不释放 | 传递 skipped 为本地落库（无 HQ 终态事件），而 `_settle_queue_seat` 仅挂 `_on_terminal` 调用；单测以手工 `disp._settle_queue_seat(qid)` 调用掩盖了生产缺失的自动触发（违反 DoD 5「队列收束不死锁」） | `advance()` 收集本轮发生 gate settle 的队列 id，主体结束后逐队追加幂等结算；单测 `test_skipped_propagates_transitively` 去除手工结算调用并增席位释放断言 | 修复后重提 fail-skip2 链：opt failed → freq skipped（←44=failed）→ sp 传递 skipped（←45=skipped，服务端日志 `[dispatch] 依赖联动 skipped：task=46 ← 45=skipped`）→ 队列自动收束 `unsubmitted/finished_with_failures`、席位释放。修复前残留的悬挂席位经隔离工作区 DB 级恢复注入清除（复刻结算动作：队列置 unsubmitted/finished_with_failures、删席位行——走查专用，已留痕） |
| ③ | 能量表 g16 行能量恒空（队列端点与 workflow 聚合同病）：真实管道全行 `energy_hartree=null/source=none`，而组合流主链明明解析成功 | `energy.py::_latest_analysis` 按扁平 `{"summary": …}` 读 analysis.json，B1 落盘 SSOT 为 `{"result": {"summary": …}}` 嵌套（`method` 亦在 result 层）；单测夹具用扁平形状喂入、与 SSOT 漂移致缺陷逃逸全部闸门 | `energy.py::_g16_row` 改按 SSOT 嵌套读取（能量取 `result.summary`、方法名取 `result.method`）；`test_workflow_crest` 夹具改 SSOT 形状并注明教训 | 修复实例重启后（analysis.json 在盘、查询期读取）：`GET /queues/RNXJK3/energy-summary` 与 `GET /workflows/3CVE67` 的 g16 行能量/双单位/相对 kJ/mol 全部就位（-155.034290/-155.033799 Ha，相对 0/1.29 kJ/mol，零点=聚合范围最低） |

## 2. D3 端到端走查（§7.2 九条留痕，对照 roadmap M4 验收段）

| # | 验收项 | 结果 | 留痕 |
|---|---|---|---|
| 1 | 依赖链三段 + 续用形态两段链 | 通过（停等可观测性经缺陷①修复后达成） | §2.1、m4-p1-\* |
| 2 | 依赖校验错误码矩阵 | 通过（九场景） | §2.2 |
| 3 | 失败联动两分支 | 通过（传递 skipped 收束经缺陷②修复后达成） | §2.3 |
| 4 | 哈希跳过溯源 + 上游重跑传导 | 通过 | §2.4 |
| 5 | 断点续跑 opt | 通过 | §2.5、m4-p5-\* |
| 6 | 续跑 sp/freq + ineligible | 通过（sp 续跑物理边界登记见 §2.6 注） | §2.6、m4-p6-\* |
| 7 | 组合流 | 通过（能量表取数经缺陷③修复后达成） | §2.7、m4-p7-\* |
| 8 | 可执行缺失 503 | 通过 | §2.8、m4-p8-\* |
| 9 | 闸门 | 通过 | §2.9 |

### 2.1 路径 1（依赖链三段 + 续用形态）

**主链（三段）**：队列编辑框勾选「接续前置 chk」建队——成员行勾选经分块
编辑端点写入 `%OldChk=@task:1`/`%OldChk=@task:2`（落盘核对 `inputs/2`、
`inputs/3` 逐字一致），拖拽调整成员序为 [001,002,003] 且勾选提示随拖拽
位置动态更新（重排不改既有 id 引用语义在位）；UI 提交队列 BSH76G →
三成员逐级 succeeded（水分子 opt 4s/freq 4s/sp 2s）。

- 物化断言：`run/2/dep-1.chk` 与 `run/1/input.chk` sha256 逐位相等
  （c8325cbe…，复制语义）；`run/3/dep-2.chk` 与 freq 执行自有
  `input.chk`（961f396e…）相等（溯源=上游最近成功执行）；物化后
  `input.gjf` 内 `%OldChk=dep-N.chk` 重写、`@task:`/`@exec:` 残留数 0。
- 上游原件零改动：`run/1/input.chk` 在下游两轮物化后哈希不变（复制
  只读；续用形态重写语义另见下行）。
- 停等可观测：window=1 时链式后继的等待属「保序窗口满」语义
  （wait_reason=null，advance 队首 break 不触及后继——与 §2.1 契约
  一致）；`parallel_window` 调 2 后，QD 链（SCYKGZ，[拉伸萘深优 5min，
  续用成员 %Chk=@task:27]）在跑首成员期间后继成员 REST 快照
  `wait_reason=dependency`（依赖守卫先于资源检查——同轮资源占满时
  另一席位成员落 `wait_reason=resource`，优先序实证）。缺陷①修复后
  GUI 图注上屏（等资源截图；等依赖同渲染路径）。

**续用形态（两段）**：队列 JPF37G [候选#20 bz_wait_opt（苯 6-311+g(d,p)
opt），候选#26 w_opt3（Link0 手写 `%Chk=@task:20`——经候选分块编辑端点
写入，即 §7.2 构造说明的同一载体）] → 双 succeeded。

- `run/5/input.gjf` 重写为 `%Chk=dep-20.chk`（零残留）；dep chk 被 G16
  重写实证：`run/5/dep-20.chk`（912b08de…）≠ 复制源
  `run/4/input.chk`（a6877705…）——续用形态下 dep chk 即本任务 chk
  目标、运行中被 G16 改写；上游原件 `run/4/input.chk` 全程未动。
- 「opt2 failed 后重跑重取」分支：本机 g16 对水/苯秒级完成，运行中
  停窗不可构造；以等价证据承载——三轮回退重提（§2.4 R2/R3）中每轮
  新执行目录的 dep 副本均由物化器重新复制（新 run 目录内 dep 文件
  只能来自本轮派发复制），重取语义另由 `test_materialize` 单测承载。
  如实登记：该子分支未获真机独立留痕。

### 2.2 路径 2（依赖校验错误码矩阵，API 层）

| 场景 | 结果 |
|---|---|
| 环（#11↔#12） | 422 `DEPENDENCY_CYCLE`，message 含环路径「#11→#12→#11」 |
| 自环（成员自引用） | 422 `DEPENDENCY_CYCLE`（自引用） |
| 悬引用（@task:99999） | 422 `DEPENDENCY_UNREACHABLE`（details task_id/line/ref） |
| 跨队列引用（@task:1 指向他队列成员） | 422 `DEPENDENCY_UNREACHABLE` |
| 前向引用（引用序后成员） | 422 `DEPENDENCY_UNREACHABLE`（P1-3 整改语义在位） |
| PATCH 移除被依赖成员 | 422 `DEPENDENCY_UNREACHABLE`，details `depended_by` |
| 单任务席位行内提交含 @task: | 422 `DEPENDENCY_UNREACHABLE`（限队列成员间） |
| @exec 文法入队列成员 | 422 `DEPENDENCY_UNREACHABLE`（resume 专用文法） |
| crest 成员组队拒绝 | 单测承载（`test_dependencies`；live 现场无 pending crest 任务可组队，crest 恒单任务席位） |
| 溯源 chk 清理后重提交 | 422 `CHK_SOURCE_MISSING`：受控删除上游最近成功执行（#42）的 `input.chk`（模拟保留期清理）→ 重提交被拒，details 注明 `upstream_task_id/execution_id`，message 引导「重跑上游恢复 chk 来源」 |

### 2.3 路径 3（失败联动两分支）

- **未勾选跳过**（fail-noskip）：伪关键字 opt（候选#38）2s program_error
  → freq/sp 即时 skipped（归因 `predecessor_failed`，GUI 历史抽屉
  「前驱失败」）→ 队列 `abort_on_failure` 即刻回退（unsubmitted +
  rollback_flag），无成员悬挂。
- **勾选跳过**（fail-skip2，缺陷②修复后）：opt failed → freq skipped
  （←44=failed）→ sp 传递 skipped（←45=skipped；服务端日志
  `[dispatch] 依赖联动 skipped：task=46 ← 45=skipped` 传递链在案）→
  队列跑完记 `finished_with_failures`、席位自动释放、无成员悬挂。
- **入口排除**：skipped 条目（#031）抽屉无「从断点续跑」按钮；归档
  条目（#029 归档后）按钮消失、后端 preview 同口径
  （`eligible=false`、`probe.reason=archived`）。

### 2.4 路径 4（哈希跳过溯源 + 上游重跑传导）

同一队列 AJ2FHW [47 opt，48 sp（%OldChk=@task:47），49 伪关键字 sp]
三轮回退重提：

- **R1**：A✓ B✓ C✗ → 回退（rollback_flag）。
- **R2**（编辑 B 输入加 `pop=reg` 后重提）：A **无新执行**（哈希跳过、
  沿用 #34）；B 新执行 #37 且 `run/37/dep-47.chk` 与被沿用的
  `run/34/input.chk` sha256 逐位相等（49db7bf3…）——**哈希跳过成员的
  chk 可被下游溯源物化**实证；C 再败回退。
- **R3**（编辑 A 输入 `%nprocshared=4` 后重提）：A 重跑（新执行 #39）；
  B 输入未变、哈希跳过判定被前置守卫阻断（决策点 6 定案：
  `_upstream_rerun_since`——直接前驱新执行即视依赖已变）→ B 随之重跑
  （新执行 #40）；C 再败回退。**上游重跑对下游的传导**实证。

### 2.5 路径 5（断点续跑 opt）

拉伸萘 opt（naph_deep_res，6-311+g(2d,p)，solo 直提）运行 3m37s 时
API 层强停 → `failed/manually_stopped`，chk 保全 `protected/` 落盘。

- 历史 #010 抽屉「从断点续跑」→ 弹窗（m4-p5-resume-dialog-opt.png）：
  探针通过、注入清单「Link0 追加 %OldChk=@exec:10 + ROUTE 改写为
  `#p Opt=Restart b3lyp/6-311+g(2d,p)`（原方法保留）」、统一 diff 逐字
  展示；确认 → 注记「已创建续跑任务 #31（源自 #10）— 已入待执行队列」。
- 新任务 #31 派发：`run/13/dep-exec-10.chk` ← protected 保全 chk 复制、
  `%OldChk=dep-exec-10.chk` 重写零残留；**Opt=Restart 真机跑通**
  （2m04s，`input.log` 首行 `#p Opt=Restart b3lyp/6-311+g(2d,p)` +
  Normal termination）。
- 双向关联：新条目 #13「续跑自 #10（任务 28）」、原条目 #10「已续跑
  #13」（GUI 抽屉字段，m4-p5-resumed-from-drawer.png）；`resumed_from`
  落库、`resumed_by` 派生只读反查（API `resumed_by=[13]`）。

### 2.6 路径 6（续跑 sp 与 freq + ineligible）

- **freq 回落**：bz_freq_slow 强停 → preview 弹窗琥珀明示「freq 任务无
  中断续跑语义 — 将按原样重跑（新建任务并保留「续跑自」关联）」（无
  注入无 diff，m4-p6-resume-dialog-freq-fallback.png）→ 确认 → 原样
  重跑 succeeded（条目 #19，`resumed_from={8,15}` 关联保留）。
- **sp 续跑（Gu ess=Read）**：TD(nstates=6) 萘单点强停（20s，初始
  CPHF 段）→ preview「任务类型：单点能」+ 注入 `%OldChk=@exec:17` +
  route 追加 `Guess=Read`（m4-p6-resume-dialog-scf.png）→ 确认 → 新
  任务正确物化派发（`dep-exec-17.chk` + Guess=Read）——**G16 l401
  报错 "Basis set data is not on the checkpoint file" 终态
  program_error**。归因：20s 极早中断的 chk 尚未写入基组数据块，
  `Guess=Read` 物理不可行——机制链路（探针/注入矩阵/物化/派发/落
  历史）全部按契约执行，属 G16 chk 内容时点的物理边界（与计划 §2.2
  「中断点已过优化段」同类的真机核验观察项），非实现缺陷；如实登记。
  更晚中断点的 Guess=Read 续跑语义由 `test_resume` 注入矩阵单测承载。
- **ineligible 场景**：succeeded 条目 preview/confirm 404（无续跑入口，
  P5 整改口径）；chk 损坏（受控写垃圾后还原）→ `chk_corrupted`；
  无任何续跑资产（受控移除保全 chk）→ `no_resume_asset`；链内引用
  （链成员 %OldChk=@task:36 强停条目）→ `eligible=false/reason=
  chained_ref` 且 `probe=null`（注入前置检测先于探针）；探针超时/
  类型不明由 `test_resume` 单测承载（§7.2 注明口径）。

### 2.7 路径 7（组合流）

**主链（乙醇，一键全链）**：候选行「组合流」入口 → 对话框（crest 核数
默认 link0_default_nproc=4、Top N=2、精修模板 route 预填，
m4-p7-combo-dialog.png）→ 一键提交 → workflow 3CVE67
`crest_running`（提交响应 `{workflow_id, state, crest_task_id, seat_id}`
四字段在位）→ crest 执行 #45 真机 18s succeeded（监控峰值 CPU 399%/
MEM 18MB 照常；`MEM 0 GB（声明）` 记账口径；chk 未保全——不进
formchk/保全路径）→ 终态钩子提取 `crest_conformers.xyz`（乙醇 4 构象，
A5 锚点同源）→ 精修队列 RNXJK3（top-2）**自动提交** → 成员
refine-01/02（模板坐标替换程序化输入、`#p B3LYP/6-31G(d) Opt Freq`）
→ 精修队列收束 → workflow **completed**（P1 整改的 completed 联动
实测可达）。

- 能量表（缺陷③修复后）：`GET /workflows/3CVE67` 后端跨容器聚合——
  crest 行（source=ensemble，-11.394339 Ha）+ g16 行（source=analysis，
  双单位，相对 kJ/mol 0/1.29），零点=聚合范围最低；GUI WorkflowDrawer
  进度面板（四态徽标/元信息行顿号分隔/能量表混排，m4-p7-workflow-
  drawer-energy.png）；页面刷新后经 `GET /workflows` 列表恢复面板
  （本节抽屉即刷新后重开）。
- crest 任务行规格：历史行 CREST 徽标 + 「4C / 0G」；执行中页运行态
  进度位实时捕获「无增量解析 — CREST 任务不产生 g16 进度流，运行读数
  见 CPU/内存」占位（非空白非报错，m4-p7-crest-no-incremental-
  placeholder.png）；crest 抽屉无「从断点续跑」（succeeded 无断点）。

**<2 不成队分支**：甲醇 #53（A5 实测单构象）→ workflow ZV983D
**failed**、不生成精修队列（refine_queue_id=null）、crest 原文可查
（crest_conformers.xyz 等 21 文件在 run 目录）；服务端日志「构象数不足
（1 < 2）」。苯环候选第三次实证同分支。计划 §7.2 原文样例「甲醇」经
A5 实测为单构象，成队主链由乙醇承载（4 构象）、<2 分支由甲醇/苯环
实证——样例替换如实登记。

**满员受控两场景**（`pending_seat_limit` 3→1）：

- **精修自动提交满员**：乙醇副本 #58 一键提交（提交时席位空闲、受理）
  → crest 任务占用唯一席位期间终态钩子建队 → 在途计数含 crest 自身
  席位 → 精修队列 RC2BQU（成员 60/61）保留 **unsubmitted** +
  workflow FJJRHJ `refine_queue_pending=true`（state=refining 叠加
  布尔，非枚举值）；前端提示「未自动提交 — 可在队列页手动提交」
  （m4-p7-refine-pending-hint.png）→ 恢复 limit=3 手动提交 → 队列
  执行收束 → workflow **completed**（能量行 0/0.99 kJ/mol）。
- **组合流提交满员**：单任务占满唯一席位 → 一键提交 409
  `PENDING_CAPACITY_FULL`「在途席位满员」，整体拒绝零副作用
  （workflow 行数前后 3→3，无半成品记录）。

### 2.8 路径 8（可执行缺失）

`crest_root` 暂切空目录 `/tmp/m4acc/nocrest` → 组合流一键提交：GUI
对话框红色警示「crest 可执行不可用 — 请检查运行级设置 crest_root 后
重试」（m4-p8-crest-503-dialog.png）；API 503 `CREST_EXECUTABLE_MISSING`
（details 回显 `crest_root` 与 `expected=<root>/crest`）；workflow 行数
不变（零副作用）。恢复设置后即恢复可用。

### 2.9 路径 9（闸门）

全量 `uv run pytest` 696 通过（基线 695 + 缺陷①新增推拉断言用例 1 例，
缺陷②为既有用例修订；零跳过，`target/release/hq` 在位——e2e 无静默跳
过）；五项脚本闸门
（validate_progress/check_tokens/check_contrast/gen_changelog_md
--check/audit_frontend_offline）全过；`npm run build`（vue-tsc 零错
误，走查前基线已建，缺陷①②③均为后端改动无前端重建需求）；
`npm run gen:types` 再生零 diff。本批三个缺陷修复为纯后端（dispatcher/
energy）+ 测试，无契约形状变更。

## 3. M4 DoD 对照（§7.1 九条）与 D4

| DoD | 结果 | 留痕 |
|---|---|---|
| 1 一键「构象搜索 + top N 精修」+ 能量表聚合可查增量刷新 | 通过 | 路径 7（3CVE67/FJJRHJ 双 workflow） |
| 2 三段 chk 依赖链跑通（停等可见/逐级物化/上游零改动）+ 续用形态两段链 | 通过 | 路径 1 |
| 3 依赖校验错误码 + 移除被依赖拒绝 + CHK_SOURCE_MISSING | 通过 | 路径 2 |
| 4 断点续跑（opt Restart/sp Guess=Read/freq 回落/ineligible 原因明确/双向关联） | 通过（sp 极早中断物理边界登记） | 路径 5/6 |
| 5 派发联动（失败 skipped/传递 skipped 收束/哈希跳过溯源/上游重跑传导） | 通过 | 路径 3/4 |
| 6 crest/xtb 缺失显式 503 | 通过 | 路径 8 |
| 7 全量测试与全部闸门通过（hq 在位/offline/build） | 通过 | 路径 9 |
| 8 工作项销号 M4.1–M4.5 | 销号依据：M4.1（路径 1/3/4，关闭 roadmap §7 事项 1 的实施面）、M4.2（路径 7/8）、M4.3（路径 1/2/4 + 停等可观测）、M4.4（路径 5/6）、M4.5（路径 7 能量表） | §2 各路径 |
| 9 3.1.0 冻结五步、tag v3.1.0 本地落位 | D4 执行（AGENTS.md §5.2；不推送远端） | — |

**D4 交接要点**：确认 unreleased changes 完整 → 冻结 3.1.0（version/
date/semver，minor=含 added）→ 追加空 unreleased 行 → progress.json
清空 unreleased、更新 latest_released_version → 本地打 tag v3.1.0
（不推送远端，推送须用户当次授权）。

## 4. 走查后现场恢复

- 运行级设置复位：`pending_seat_limit=3`、`crest_root=~/opt/crest-3.0.2`
  已即时恢复；`parallel_window` 走查期调 2（依赖停等可观测需要），
  收口时复位 1。
- 受控注入全部还原或留痕：chk15 损坏写垃圾已还原（哈希前后一致）、
  entry 20 保全 chk 移除已放回、exec42 input.chk 删除为 CHK_SOURCE_
  MISSING 场景原件（模拟保留期清理，不还原即场景本体）、悬挂席位
  DB 级恢复注入已留痕（§1 缺陷②）。
- 走查实例 `127.0.0.1:8398` 与隔离工作区 `/tmp/m4acc/`（含
  logs/server.log 全程日志、samples/ 样本）保留备查，可整体删除重建
  （本记录 §0 即重建口径）。
