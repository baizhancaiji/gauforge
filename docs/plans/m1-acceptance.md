# M1 验收记录（D1/D2 留痕 + C 阶段 GUI 走查）

> 依据 [m1-plan.md](m1-plan.md) §4.4/§4.5/§7 执行并留痕。走查环境：WSL2
> 单机，后端 `uv run python -m web.src.main`（真引擎），HQ 取仓库构建产物
> `target/release/hq`（server+worker，journal 落工作区），g16 为真机安装
> `~/g16`（金标准旁证：水分子/萘体系 B3LYP 等真实计算）。GUI 走查经
> Playwright MCP + Chromium 黑盒驱动（截图证据留存于本地
> `.playwright-mcp/shots/`，不入库）。

## 1. C 阶段收尾：六页 GUI 走查（§4.4 各页质量标准）

### 1.1 各页走查结论

| 页面 | 走查点 | 结论 |
|---|---|---|
| 候选页 | 多选导入含坏文件 → 整批原子 422 + 逐文件失败清单 | 通过 |
| 候选页 | 同名同内容重复导入 → 新建不同 id + duplicate 提示 | 通过 |
| 候选页 | 文件名自然序（字母先于数字）与 title 实时解析 | 通过 |
| 候选页 | 「-」剔除二次确认（danger 模态、不可恢复文案） | 通过 |
| 预览 | 五段分块卡（TITLE/LINK 0/ROUTE/CHARGE·MULT/MOLECULE/ADDITIONAL）、无编辑入口 | 通过 |
| 预览 | Link0 缺失「（无声明）」+ 琥珀注记（提交时按默认值补齐） | 通过 |
| 行内提交 | 确认框完整输入（纯文本含坐标、限高滚动） | 通过 |
| 行内提交 | Link0 黄警 + 设置缺省值回显（%NProcShared=4、%Mem=8 GB） | 通过 |
| 行内提交 | 满员 409 → 模态内红字「在途席位满员 — 请在待执行页移除席位或调高上限后再试」 | 通过 |
| 待执行页 | 容量仪表满格/超限示警、在途锁定区与等待区分离展示 | 通过 |
| 待执行页 | 等待区整席移除二次确认 → 任务退回候选（origin=returned_unrun） | 通过 |
| 待执行页 | 拖拽重排 → PUT /pending/order（原记录「锁定席位保持原位时放行」超前于前端实现——当时前端存在锁定席位即禁用全部拖拽，一审复核证伪；F-01 修复后含锁定席位场景复测通过，见 §1.5） | 复测通过 |
| 执行中页 | 通道卡真实读数：CPU 396%、RSS 14→126 MB 随采样跳变 | 通过 |
| 执行中页 | OPT STEP / SCF CYCLE 推进，进度末行与 run/<id>/input.log 一致 | 通过 |
| 执行中页 | 停止 danger 二次确认（文案含归因「手动停止」）→ 终态卡实时移除 | 通过 |
| 执行中页 | 对已终态执行停止 → 409 红字「仅运行中执行可停止」 | 通过 |
| 历史页 | 列表全字段（状态/归因/提交/结束/耗时/资源/出处） | 通过 |
| 历史页 | 详情抽屉（输入哈希、资源声明/补齐、chk 保全、HQ 任务号） | 通过 |
| 历史页 | 输入原文查看、输出查看与 `?download=true` 导出 | 通过 |
| 历史页 | failed 条目「重新排队」→ 沿用原任务 id 建席并派发 | 通过 |
| 历史页 | failed 条目「退回候选」→ 以 run/<id>/ 执行副本新建候选（origin=returned_failed） | 通过 |
| 历史页 | 归档动作 + 独立归档页路由（#/archive） | 通过 |
| 历史页 | 清理入口边界说明（只删正常结束超期 chk/rwf，永不触碰输出/输入/保全） | 通过 |
| 设置页 | 启动级参数只读展示（env 变量名回显）、运行级生效语义徽标与范围 | 通过 |
| 设置页 | 席位上限调小 → 挤出确认模态（窗口触及除外、在跑不追溯、退回候选） | 通过 |
| 队列页 | M2 占位渲染（「可从候选任务组合创建（M2）」） | 通过 |

### 1.2 走查发现并修复的缺陷

以下缺陷均为 GUI 走查实测暴露（单测因夹具时序/注入方式未能覆盖），
按「一缺陷一 fix 提交」随发现随修，进度两文件同步登记：

| # | 缺陷 | 根因 | 修复 |
|---|---|---|---|
| 1 | 引擎开启时应用启动即 ModuleNotFoundError | select_gateway 以同级相对导入引用 web/src/hq/ 下的 Gateway 实现 | 改 `..hq.` 导入；补工厂两分支回归测试 |
| 2 | 提交确认框完整输入永久「读取中」、Link0 黄警不出现 | openapi-fetch 默认按 JSON 解析 text/plain 响应，`#p` 开头文本触发 SyntaxError 使 Promise.all 整体失败 | 该请求显式 `parseAs: "text"`（契约本为 text/plain） |
| 3 | 真实任务永久停等不派发 | 双因：① sum mem 的 size 为 ResourceAmount 内部整数（MiB×10000+万分位）被当 MiB 原值，worker 内存虚高一万倍；② `--cpus 1` 违背 roadmap「worker 资源=启动探测」，1 核 worker 小于任何默认声明 | mem 解析除以 FRACTIONS_PER_UNIT；ensure_worker 默认自动探测（cpus 参数保留供测试） |
| 4 | 自动探测 worker 仍按 1 核记账 | 启动探测的 cpus 以核 id list 序列化（非 --cpus 的 range 闭区间），解析器误算 1 核 | worker_resources 按 kind 分派 list/range 两形状；补两形状回归 |
| 5 | succeeded 任务 .fchk 一律缺失（M1.11 落空） | `%Chk=h2o_opt`（无扩展名）时 g16 实际写出 `h2o_opt.chk`，resolve_chk 按字面路径寻址致 formchk「chk 不存在」跳过 | 无扩展名补 `.chk`、有扩展名按原样；以真实 run 产物验证 |
| 6 | execution.monitor 零事件、monitor_summary 恒 0 | HQ 在 submit 后立即 spawn g16，进程启动早于轮询记录的 started_at 1~2s，监控「cwd+启动时间」双重校验把真实进程树整体排除 | 双重校验基准改取派发时刻（note_started 于提交前注入，先入为主不覆盖）；补时序回归 |
| 7 | S3 重跑可被误判 S1 接管（续跑资产无保全） | journal 恢复后 worker 快速重连，waiting 相位与进程 create_time 证据可被启动对账时点双双错过 | 补判据③：server 本次生命周期重 spawn 且 started_at 早于 spawn 时刻 ⇒ 确定性判重跑（实测一次真实 crash 场景：归因 external_interrupt + protected/ 保全 + 新执行重定向全部生效） |
| 8 | GAUSS_SCRDIR 落到全局 ~/scratch | materialize 构建的 GAUSS_* 环境在 Gateway.submit 处被丢弃（签名无 env 参数） | Gateway 抽象/CLI（--env）/HTTP（POST /jobs env 字段，Rust 桥已支持）贯通；派发与 S3 重定向两路径接入；实测 /proc/<pid>/environ 与 -scrdir 生效 |
| 9 | 前端从未处理过任何 SSE 事件（Toast/快照/读数全哑，页面仅靠 8s REST 轮询兜底） | 服务端 SSE 帧为 CRLF 行尾（规范允许），前端解析器 `split("\n")` 后事件分隔空行为 `"\r"` 而非 `""`，dispatch 永不触发 | 逐行剥尾部 `\r` 后判定事件边界（M0 遗留，当时无浏览器走查故漏检） |
| 10 | 通道卡实时读数被周期性抹除 | 8s REST 基线轮询 push 整体覆盖卡片对象，monitor/progress 归 undefined | push 改合并语义：仅补齐身份字段，保留既有实时读数 |
| 11 | 窗口非空时等待区拖拽重排永不生效（PUT 409） | 后端存在任何锁定席位即全量 409，与 roadmap §2.1「未在执行的成员可重排」矛盾 | 改按 payload 下标判定：锁定席位保持原位即放行，移动即 409；补正反测试 |
| 12 | 历史详情输入/输出面板卡「读取中」；停止模态残留上次错误 | 同 #2 的 text/plain 解析问题；stopError 未在重开时清空 | parseAs:"text"；openStop 时清空 stopError |
| 13 | 窗口非空时等待区拖拽重排永不生效（前端存在锁定席位即禁用全部拖拽，与后端「锁定原位即放行」矛盾；§1.1 原记录因此不可复现） | 前端 canDrag 门控含 anyLocked 条件，后端 c6a0906e3 放行后前端未跟进（二审修复 F-01） | 门控改为锁定席位不可作拖源/落点，提交前本地校验锁定席位下标不变；含锁定席位场景走查复测通过（§1.5） |

### 1.3 记录在案、不在本轮修复的事项

- ~~favicon 404：装饰性资源缺失，不影响功能（低优先）~~ 已修复
  （声明空 favicon 消除 404 噪声，2026-09-25 二审前入库；二审复核据此移入
  已修复项）。
- ~~侧栏「HQ 未连接」为静态占位：m0-frontend-design §5 明示「M0 为静态
  占位」，M1 计划未排期其真实化，且契约 12 类事件无 HQ 连通性事件；
  真实化需契约增量，留 M2 决策~~ 已真实化（2026-09-25 M1 收尾提前落地，
  契约增量 hq.status 事件（13 类）+ system.snapshot `hq` 字段；引擎 tick
  以 workers 列表探测、翻转才推；侧栏三态「已连接/未连接/未启用」。走查：
  引擎关闭实例恒「未启用」、真 hq 实例「已连接」，停服实测 down 翻转
  （≤2s tick 周期）与 watchdog 自愈 up 回连均无刷新实时生效）。
- ~~挤出确认模态的「挤出 N 个席位」按新旧上限差计算，可能大于实际可挤
  席位数（如等待区已空）；文案精度问题，挤出行本身正确（自队尾、窗口
  触及除外）~~ 已修复（2026-09-25 M1 收尾，模态改从 pending 快照按
  apply_capacity_limit 同口径实时计算：min(超限幅度, 未锁定席位数)，
  零挤出时明示「暂不挤出席位」。走查三场景：在途 2/上限 3→1 计 1 非 2；
  在途 1/3→2 明示暂不挤出；引擎实例并行窗口 2 双跑 + 1 等待、3→1 计 1
  非 2，确认后等待席退回候选（origin=returned_unrun）、双锁定席临时
  超限，与计数一致）。
- 长寿命标签页跨服务重启：SSE 退避重连后经 system.snapshot 全量重建，
  快照/读数随之恢复（#9 修复后实测）；断连窗口内读数短暂缺席属预期。
- 候选自然序仅页内有序：自然序排序在前端页内执行（page_size=50，与后端
  同规则），跨页全局有序未保证，且前后端双实现无对照测试；登记为已知
  限制，M2 处理（统一取数端排序或扩契约），M1 不扩契约
  （2026-09-25 二审登记，裁决 K6）。

### 1.4 走查环境准备记录（与测试动作的区分）

- 样本文件（水分子、萘体系 .gjf；坏文件；多步文件）由走查脚本预置于
  `.playwright-mcp/samples/`（gitignored）；提交/停止/重排/设置保存等
  全部动作均经页面 GUI 完成，状态断言辅以只读 REST/SQLite 查询。
- 走查期间发现样本几何被脚本损坏导致 g16 报错（End of file in ZSymb），
  该意外验证了 failed→program_error 归因与 chk 保全（protected/）路径，
  随后以正确样本重跑。

### 1.5 设计规范 v2 落地复核（2026-09-25 二审修复补记，D-07/F-01）

走查环境：演示实例 `G16WEB_ENGINE=0 uv run python -m web.src.main`
（隔离 G16WEB_HOME，端口经设置库预置避开常驻实例）+ Playwright/Chromium
1440×800 黑盒驱动；锁定席位场景另起引擎实例（G16WEB_ENGINE=1、真 hq 取
`target/release/hq`、fake g16 `G16_FAKE="sleep=240;steps=4"` 制造长任务）。
截图不入库，结论与实测输出留痕如下。

**令牌对齐（D-01/D-06）**——`uv run python scripts/check_tokens.py`（新增
闸门，逐变量 diff tokens.css 与样板）：

```text
暗色 :root: tokens 71 变量 / 样板 71 变量
明亮 html[data-theme=light]: tokens 30 变量 / 样板 30 变量
check_tokens: OK — 逐变量 diff 为空
```

故障注入验证：改坏样板 `--side-width` 值 → 退出码 1，报
`[暗色 :root] --side-width 值不一致: tokens=216px 样板=220px`；还原后恢复通过。

**对比度实测（D-04）**——`uv run python scripts/check_contrast.py`（新增
闸门）：调色前亮色 failed 徽标实测 4.462 < 4.5 报错；`#c23a31 → #bd352b`
后全组合达标（亮色 failed 徽标 4.72:1，全表见设计 §2.1 实测回填值）。

**基础接管清单 6 项逐条**（getComputedStyle 实测）：

| # | 接管项 | 实测 |
|---|---|---|
| 1 | 滚动条 | `::-webkit-scrollbar` width 10px；thumb 亮色 rgb(174,188,200)（=--border-strong） |
| 2 | `::selection` | accent 25% 底：color(srgb 0.039 0.447 0.4 / 0.25)（亮色 accent #0a7266） |
| 3 | caret-color | rgb(10,114,102)（亮色 accent） |
| 4 | autofill 修正 | base.css `input:-webkit-autofill` 底色/text-fill-color 修正（代码核验；headless 无法触发真实 autofill） |
| 5 | color-scheme 随主题 | 亮色实测 `light`（默认暗色 `dark`，切换按钮即改） |
| 6 | `:focus-visible` 双环 | Tab 聚焦导航项：outline 1px accent offset 2px + inset 1px border-strong |

**reduced-motion 实测**——`page.emulateMedia({ reducedMotion: "reduce" })`：
running 灯点 `animation-duration: 1e-06s`、`animation-iteration-count: 1`，
按钮 `transition-duration: 1e-06s`（§6 硬规则成立，全部动效关闭）。

**并排走查结论**：六页与样板（assets/m0-ui-preview.html）逐页对照——候选
（表格+预览分块卡+Link0 琥珀注记）、队列（空态）、待执行（容量仪表+席位+
等待区分隔注记）、执行中（通道卡读数）、历史（筛选+空态）、设置（启动级
只读+运行级分组表单+生效语义徽标）布局骨架与组件形态一致；中文微标签
12.5px 档（F-06 整改后）、亮暗双主题切换、亮色 #bd352b failed 色渲染正确。

**F-01 锁定席位拖拽走查**（引擎实例，窗口触及 S02、等待区 S03/S04）：

1. S02 锁定态：左侧 2px 磷光条 + 泛光 + 「在途」标记 + 无移除按钮；
   `draggable="false"`（不可作拖源），等待席位 `draggable="true"`；
2. 拖 S04 → 锁定 S02：本地拒绝，页面提示「重排越界 — 锁定席位不可作落点」，
   未发 PUT（REST 核对顺序不变 [2,3,4]）；
3. 拖 S04 → 等待 S03：PUT /pending/order 放行，SSE 回推顺序 [2,4,3]，
   锁定席位下标不变（REST 核对 position 1,2,3）。

三步均复现通过，§1.1 对应行表述已据此修正。

## 2. D2 演练记录（S1/S3/并行双账）

见 §4（S3 演练替代方案已先行登记于 [m1-plan.md](m1-plan.md) §4.5 D2）。

## 3. D1 端到端走查（§7.1 十条留痕）

真 g16 环境（水分子 HF/B3LYP、萘体系 B3LYP 真实计算；产物抽查
「Normal termination」与 .log 内容一致性）。逐条结论：

| # | 验收项 | 结果 | 留痕 |
|---|---|---|---|
| 1 | 批量导入 3 份含重复 → 2 条新记录 + 重复识别提示（哈希+内容双校验） | 通过 | GUI：422 整批原子清单 / duplicate 提示截图；服务层单测锁定（同名同内容才 duplicate，同内容不同名不算） |
| 2 | 行内预览五段结构渲染、无编辑入口 | 通过 | 预览分块卡截图（TITLE/LINK 0/ROUTE/CHARGE·MULT/MOLECULE/ADDITIONAL） |
| 3 | 行内提交缺 %NProcShared/%Mem → 黄警并填默认值 → 确认入待执行 | 通过 | 黄警文案回显 %NProcShared=4、%Mem=8 GB（设置缺省值）；确认后席位出现 |
| 4 | 席位流转：重排 → SSE 推送无刷新更新；容量满第 4 席位拒绝 | 通过 | 拖拽触发 PUT /pending/order、经 pending.snapshot 回推更新；满员拒绝实测返回 409 PENDING_CAPACITY_FULL（契约与 §1 B5 一致；§7.1 本条「422」为计划笔误） |
| 5 | 实时监控：CPU%/MEM 采样跳变、优化步/SCF 推进且与 .out/.log 一致 | 通过 | 通道卡 CPU 396%（4 核）、RSS 14→126 MB；OPT STEP 4/SCF CYCLE 14，末行与 input.log「SCF Done: E(RB3LYP) = -386.948373122 A.U. after 14 cycles」一致 |
| 6 | 强制停止：二次确认 → HQ cancel → 终态推送 → 历史归因 manually_stopped | 通过 | 停止模态（含归因文案）→ 历史 failed/manually_stopped；chk 保全 protected/ |
| 7 | 失败归因：非零退出 → failed + program_error；skip_failed 两分支 | 通过 | 真 g16 报错（End of file in ZSymb）→ program_error；队列 skip_failed=false 分支实测（§4 演练）；skip_failed=true 分支由 test_failure_semantics 单测锁定，并经 test_e2e_queue_skip_failed_continues 真实栈端到端复核（成员 1 fake g16 非零退出落 program_error、成员 2 继续派发成功、队列 finished_with_failures 回退；2026-09-25 审查收尾补齐） |
| 8 | 并行双账：parallel_window=2 双任务同跑、声明账与 HQ 请求账一致、psutil 有读数 | 通过 | 双 exec 并发（hq_job 26/27 同刻 running），声明账 nproc 4/defaulted=False、mem 1GB 落库；HQ 请求账实测（历史 job 11 submits：cpus Compact 40000=4 核、mem Compact 10240000=1024 MiB×10000 内部单位，CLI→HQ 换算正确）；psutil 双卡读数 |
| 9 | 重启恢复：g16web 重启 S1 接管不重复提交；WSL2 重启 S3 归因+保全+重跑新目录 | 通过 | S1：仅重启 g16web（SIGTERM），HQ 存活，exec 28 同 hq_job_id 接管、进程树未动、监视器重挂；S3：按已登记替代方案以 SIGKILL 故障注入执行（§4） |
| 10 | 队列语义佐证：POST /queues 全生命周期 curl + 单测 | 通过 | 真实栈 curl：创建 2 成员队列 → 提交整队占席 → 派发（成员 1 先跑）→ 成员 1 failed/program_error → 成员 2 skipped/predecessor_failed → 队列回退 unsubmitted（rollback_count=1、last_failure 落库）→ 成员退回候选；skip_failed=true 与队列席位分支由单测覆盖（test_failure_semantics/test_pending_logic）；端到端整队 UI 验收随 M2 |

## 4. D2 演练执行记录

| 演练 | 执行 | 结果 |
|---|---|---|
| S1 g16web 重启接管 | 起长任务（萘 opt）→ 对 uvicorn 进程 SIGTERM（仅 g16web，start_new_session 设计使 HQ 存活）→ 重启 g16web | exec 28 同 hq_job_id 33 接管、不重复提交、started_at 保留、g16 进程树未动、席位保持锁定、监视器重挂后 execution.monitor 恢复（CPU 400% 读数） |
| S3 外部中断归因+保全+重定向（**SIGKILL 替代方案**，登记见 m1-plan §4.5） | exec 28 运行中（chk 已生成）→ SIGKILL 同时硬杀 g16web、HQ server、HQ worker 与 g16 子进程树（数据库/journal/checkpoint 停在半路）→ 重启 g16web（启动序列自行拉起 server/worker，journal 恢复 job 回退 waiting → worker 重连重跑） | ① 重跑判定成立（判据③：server 重 spawn 时刻晚于本地 started_at）② 原执行归因 external_interrupt 落历史 ③ chk 保全 protected/ 落库 chk_snapshot ④ 被取消的重跑后以**新执行目录**原样重提交（exec 29 / hq_job 34，GAUSS_SCRDIR=run/29/ 隔离）⑤ 席位由新执行延续 |
| 并行 2 双任务同跑与双账 | parallel_window=2 → 双任务提交 → 双通道卡同屏 | 同 §3 第 8 条 |

**演练中发现的缺陷均已修复入库**（见 §1.2 表 #6/#7/#11 与 S1 锚定修复）。

## 5. M1 DoD 核对（§7.2）

### 5.1 系统级判据

| 判据 | 结果 |
|---|---|
| `uv run pytest` 全绿（M0+M1 全量含契约回归） | 通过：225 passed（2026-09-25 二审复核值；二审修复批次补 elapsed_s 回归后全量 226 passed，见 §1.5） |
| `npm run build` + vue-tsc 零错误 | 通过（走查期间多次重建均零错误） |
| `cargo test --workspace` 全绿 | 通过：212/227/1 passed, 0 failed（构建需 cmake/libclang，经 pip 用户级安装补齐） |
| HQ 桥接判据（§2.1 五条） | ① curl 提交→查询→取消 JSON 等价 ✓ ② GET /events 生命周期单行 JSON 帧 ✓ ③ 经 HttpGateway 完整闭环集成测试 ✓（test_e2e_http_gateway_pipeline）④ 不传 --http-port 行为零变化 ✓（默认关，全部走查/单测走 CLI 路径）⑤ cargo test 全绿 ✓ |
| 双闸门：`scripts/validate_progress.py` | 通过（每次提交前逐次执行） |

### 5.2 不偏离核对（M1.1–M1.11 逐项）

| 工作项 | 状态 | 说明 |
|---|---|---|
| M1.1 批量导入 | 完成 | 整批原子/重复提示/自然序/拷贝入库与源独立 |
| M1.2 候选列表+预览+剔除 | 完成 | 来源标记与归因注记 |
| M1.3 行内提交 | 完成 | 黄警缺省值/满员拒绝/限高滚动 |
| M1.4 待执行队列页 | 完成 | 席位全语义（在途锁定/等待区重排/挤出/容量） |
| M1.5 派发 | 完成 | 窗口推进/补位保序/停等/双账/env 强制 SCRDIR/输入哈希（GAUSS_SCRDIR 缺陷走查修复） |
| M1.6 执行中页 | 完成 | psutil 采样/停滞只提示/停止二次确认（监控基准缺陷走查修复） |
| M1.7 失败语义与归因 | 完成 | 手动停止/程序报错/外部中断三类实测 + 队列分流 |
| M1.8 执行历史 | 完成 | 全字段/输入输出查看导出/归档不可删/重新排队/退回候选 |
| M1.9 SSE 进度+持久化+对账 | 完成 | 序号持久化/五场景对账（S3 判据走查加固） |
| M1.10 HQ HTTP/JSON+SSE 桥接 | 完成 | 五判据全过 |
| M1.11 formchk+清理边界 | 完成 | 无扩展名 %Chk 语义对齐后 .fchk 实测生成；清理永不触碰输出/输入/保全 |

**替代方案偏离声明**：S3 演练以 SIGKILL 故障注入替代真·WSL2 整机重启
（登记：m1-plan §4.5 D2，含语义等价性论证），真·整机重启验证留作用户
方便时的一次性补验，不阻塞 M1 验收。除此之外 M1 工作项与 §7.1 语义
逐条对应，无其他偏离。

### 5.3 提交序列核对（§6）

§6 计划 28 笔提交的内容均已落库：A（#1/#2 由计划文档与 roadmap 增补
提交承担）、B（#3–#14）、H（#15–#18）、B10/B11/HttpGateway（#19–#21）、
C（#22–#28）；实际序列按「H 与 B 并行泳道」推进，GUI 走查（C 收尾）与
D 阶段间穿插 13 笔走查缺陷 fix + 逐笔 chore(progress) 同步（AGENTS §九
实时登记要求，未集中补录），类型与拆分符合 conventional_commits 约定。
2026-09-25 二审复核：§6 表 28 笔与 §5.2 工作项对应关系经逐项核对成立；
M1 验收后的二审修复批次（docs/plans/m1-review2-fix-plan.md，D-01–D-08、
F-01–F-15）另行逐项独立提交并回填该清单状态，不计入本表。
