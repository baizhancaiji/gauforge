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
| 待执行页 | 拖拽重排 → PUT /pending/order（锁定席位保持原位时放行） | 通过 |
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

### 1.3 记录在案、不在本轮修复的事项

- favicon 404：装饰性资源缺失，不影响功能（低优先）。
- 侧栏「HQ 未连接」为静态占位：m0-frontend-design §5 明示「M0 为静态
  占位」，M1 计划未排期其真实化，且契约 12 类事件无 HQ 连通性事件；
  真实化需契约增量，留 M2 决策。
- 挤出确认模态的「挤出 N 个席位」按新旧上限差计算，可能大于实际可挤
  席位数（如等待区已空）；文案精度问题，挤出行本身正确（自队尾、窗口
  触及除外）。
- 长寿命标签页跨服务重启：SSE 退避重连后经 system.snapshot 全量重建，
  快照/读数随之恢复（#9 修复后实测）；断连窗口内读数短暂缺席属预期。

### 1.4 走查环境准备记录（与测试动作的区分）

- 样本文件（水分子、萘体系 .gjf；坏文件；多步文件）由走查脚本预置于
  `.playwright-mcp/samples/`（gitignored）；提交/停止/重排/设置保存等
  全部动作均经页面 GUI 完成，状态断言辅以只读 REST/SQLite 查询。
- 走查期间发现样本几何被脚本损坏导致 g16 报错（End of file in ZSymb），
  该意外验证了 failed→program_error 归因与 chk 保全（protected/）路径，
  随后以正确样本重跑。

## 2. D2 演练记录（S1/S3/并行双账）

见 §4（S3 演练替代方案已先行登记于 [m1-plan.md](m1-plan.md) §4.5 D2）。

## 3. D1 端到端走查（§7.1 十条留痕）

（随 D1 执行填充）

## 4. D2 演练执行记录

（随 D2 执行填充）

## 5. M1 DoD 核对（§7.2）

（随 D3 填充）
