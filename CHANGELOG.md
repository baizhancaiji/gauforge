<!-- 本文件由 scripts/gen_changelog_md.py 从 CHANGELOG.jsonl 生成，勿手工编辑；再生成：uv run python scripts/gen_changelog_md.py -->

# 变更日志

## Unreleased（未发布）

### 新增

- 【api】M4 A4 契约 diff（任务链依赖与 chk 传递定稿，关闭 roadmap §7 开放事项 1）：Link0 符号引用文法两形态（@task:<id> 同队列成员/@exec:<执行id> resume 专用，引用即依赖单一真相）与 DAG 校验规则、错误码全集 29→35（DEPENDENCY_CYCLE/DEPENDENCY_UNREACHABLE/CHK_SOURCE_MISSING/RESUME_NOT_ELIGIBLE/WORKFLOW_STATE_INVALID/CREST_EXECUTABLE_MISSING）、Task.kind（g16|crest）与 crest 不入队/无增量解析/停滞告警不适用契约承载、PendingSeat 成员停等原因字段（dependency/resource，依赖守卫先于资源检查）、断点续跑端点对（POST /history/{id}/resume/preview 恒 200 五态 ineligible + POST /history/{id}/resume 幂等重探/满员 409）与 HistoryEntry.resumed_from/resumed_by 关联字段、组合流端点（POST /workflows/conformer-refinement 前置检查序 503/409/422 + GET /workflows 列表 + GET /workflows/{id} 状态与能量表跨容器聚合）与 WorkflowState 状态机/refine_queue_pending 布尔、GET /queues/{id}/energy-summary 能量表（末次 SCF 双单位 + 相对 kJ/mol 零点=查询范围最低）、设置项 crest_root/xtb_root 登记、mapping 增行（55 操作）与 sse.md execution.progress/execution.stalled 两行 crest 不适用补注（无新增事件，全集维持 15 类），前后端契约生成物再生
- 【web】迁移 v3 随 A4 契约批次落库：executions 加列 resumed_from（可空 TEXT JSON 断点续跑关联）与 workflows 组合流记录表（state 四态 CHECK + refine_queue_pending），HistoryEntry 响应接通 resumed_from 透传与 resumed_by 派生只读（按 resumed_from 反查）
- 【docs】A5 断点续跑与组合流设计定稿：crest 3.0.2 真机实测（甲醇/乙醇双样例）三结论落档——内嵌 tblite 引擎、XTB_PATH 环境变量全路径不消费（派发无需注入、风险 7 落定，含 --xnam xtb 外部模式同测）；构象能量锚点为 crest_conformers.xyz（非旧版 crest_ensemble.xyz，§2.3/§3.4/§4.7 随测修订）+ crest.energies（相对列实测 kcal/mol）；能量取数单一来源=注释行 Hartree 绝对能量、相对 kJ/mol 后端按 2625.4996 系数直算不经 kcal 中转；决策点 2 定案（自动提交+满员保留 unsubmitted+refine_queue_pending 布尔）与决策点 4 定案（resume 新建任务天然不触发哈希跳过），§4.2 增补 A5 定稿记录与用户授权执行口径
- 【web】crest 3.0.2 实测样例留存 fixtures（web/tests/fixtures/crest/：乙醇 4 构象全套——输入 str.xyz / crest_conformers.xyz / crest.energies / cre_members / stdout 头部锚点段 / 终态统计段），供 B10 ensemble 提取器单测与锚点回归
- 【web】B6 依赖模型与 DAG 校验：Link0 符号引用解析器（@task:<id>/@exec:<执行id> 两形态与文法残缺判定），队列创建/PATCH/提交三时点静态校验（crest 任务不入队 INVALID_MEMBERS 复用、移除被依赖成员拒绝 details 注明被谁依赖、@task 可达、依赖图无环含自环 DEPENDENCY_CYCLE、溯源 chk 已清理 CHK_SOURCE_MISSING 拒绝并提示重跑上游）与单任务席位载体校验（行内提交/历史重新排队 @task: 一律拒绝、@exec 三点校验：存在/终态/chk 溯源），test_error_codes 全集 29→35 同步；迁移 v4 tasks 加列 kind（g16|crest 默认 g16 CHECK 约束），迁移测试版本断言 3→4 并补 kind 用例
- 【rust】HTTP 提交参数支持 per-job 重试上限（crash_limit）：0=NeverRestart 禁用内部重试、n>0=MaxCrashes(n)、缺省=server 默认 MaxCrashes(5) 行为零变化（serde default），为 M4 重入语义定案落位（决策点 7 分支 b：含物化依赖的执行提交时禁用 HQ 内部重试，worker 失联即终态 failed、显式重跑经派发器重新物化）；实测核验 HTTP payload 原硬编码 CrashLimit::default() 不支持 per-job 设定，改动限于提交结构体加字段+server 应用+HTTP 层透传、不触调度核心；映射单测三分支覆盖，cargo test lib 212 通过（check_doc_path_on_disk 为上游文档站路径检查、本项目 docs 结构切割后既有失败与本次无关），hq release 产物重建
- 【web】B7 chk 物化器与探针：engine/materialize.py 派发前物化钩子（复制上游 chk 至本执行目录 dep-<id>.chk 并重写 %Chk=/%OldChk= 符号行、物化后零符号残留校验，复制语义保上游原件零改动）、溯源定位（当前输入哈希匹配的被沿用成功执行优先、回落最近成功执行；@exec 走 protected 保全优先回落保留期 input.chk）、formchk 有效性探针（临时目录执行、正常/损坏/空 fchk 段三分支、超时 120s 按探针失败）、派发器接线（物化失败=成员 failed(program_error) 经失败分流、含物化依赖执行提交 HQ 时 crash_limit=0 禁用内部重试——重入①，Gateway 三实现透传 crash_limit：HTTP 数字 0/NeverRestart、CLI never-restart 字符串形态）；FakeGateway 单测 10 用例（重写/零残留/上游零改动/缺源/哈希跳过溯源/@exec 资产/探针三分支/重入①提交参数/物化失败终态）
- 【web】B8 派发窗口依赖联动：advance 依赖守卫（先于窗口满与资源检查——roadmap §7.1 依赖未满足者不得进入窗口，保序不越位不变；停等原因 wait_reason 类级注册表经 pending.snapshot 暴露，dependency 优先于 resource）、skipped 传递闭包（前驱 failed/skipped → 下游即时 skipped 归因 predecessor_failed 既有语义复用、stderr 注明传递链——勾选跳过开关时三段链沿链传递至尾段、队列收束不悬挂防窗口死锁）、哈希跳过成员视为依赖满足且下游物化溯源其被沿用的历史 chk、重入②对账特判（物化依赖执行被 journal 恢复重跑时先于 S3 chk 分流处置：取消 HQ job、原执行 external_interrupt 落历史、以符号形式输入重新物化派发 crash_limit=0；物化依赖执行重跑识别容差收紧为 0——120s 盲区宁可重派不可静默，静默重跑其余通道已被重入① crash_limit=0 堵死）；FakeGateway 场景单测 9 用例（停等不越位/双停等叠加/失败联动/传递 skipped 收束/哈希跳过溯源/wait_reason 快照/重入②取消重派/盲区收紧/无依赖不误触）
- 【web】B9 断点续跑动作：resume 端点对（POST /history/{id}/resume/preview 无副作用恒 200 + POST /history/{id}/resume 幂等重探/422 RESUME_NOT_ELIGIBLE/满员 409 与普通提交同待遇），注入矩阵三分支（route token 化判定：含 Opt 一切变体归优化行注入 %OldChk=@exec:<原执行id>+Opt=Restart 保留原选项、Opt+Freq 并存归优化；非优化 SCF 追加 Guess=Read；freq 回落原样重跑弹窗明示）、ineligible 五态（无资产/chk 损坏/探针超时/类型不明/链内引用——链内引用为注入前置检测先于资产判定）、资产取数两路径与 B7 探针/物化器同源（protected 保全优先回落保留期 input.chk、formchk 临时目录探针）、confirm 新建任务（seat_task 形态不经候选、输入副本=注入改写文本、必过既有提交核验与 B6 载体校验）、迁移 v5 tasks.resume_of 任务级关联（派发建行时转移到执行记录 resumed_from、重复派发仍携带、freq 场景同承载）、原历史条目数据零变更（resumed_by 派生只读反查）；单测 14 用例（注入矩阵三分支/五态 HTTP 语义/幂等重探/满员零副作用/resumed_from 落库与物化链复用/resumed_by 反查/skipped 与归档不提供入口）
- 【web】B10 CREST 任务类型与组合流：组合流提交端点（POST /workflows/conformer-refinement 前置检查序=可执行探测 503 CREST_EXECUTABLE_MISSING→席位满员 409 整体拒绝零副作用→来源候选形态 422 WORKFLOW_STATE_INVALID+top_n∈[2,10] 422），crest 任务派发适配（程序=<crest_root>/crest+crest_input.xyz 输入物化+命令行 -T 线程参数+资源仅 cpus mem 不声明+环境无 GAUSS_*/XTB_PATH，不进 cclib 管道无 formchk/analysis、execution.progress 与停滞告警豁免），ensemble 最小提取器（锁 crest 3.0.2 实测格式 crest_conformers.xyz 注释行 Hartree 锚点+crest.energies kcal/mol 交叉验证哨兵、升序规约、锚文件落盘幂等），终态钩子链（提取→构象数边界 <2 记 failed 不生成队列→建精修队列 min(top_n,实际构象数) 判重不重建→自动提交满员保留 unsubmitted+refine_queue_pending，crest 离席为链尾满员判定含自身席位），程序化输入生成（模板坐标替换唯一场景+候选分子节提取+必过既有核验不绕行），迁移 v6（tasks.workflow_id/crest_nproc+workflows.top_n），启动对账 workflow 重推幂等（锚判重+队列判重+crest 执行反查）；单测 16 用例（前置检查序/派发适配/提取器 fixtures 回归与交叉验证/钩子链边界与幂等/对账重推）
- 【web】B11 能量表汇总与 workflow 查询端点（三端点）：GET /queues/{id}/energy-summary（队列成员恒 g16，行取 B1 解析末次 SCF 双单位——eV 透传解析层原值与 B1 同源不二次换算、method 摘要）、GET /workflows/{id}（状态 + energy_summary 跨容器后端聚合：crest 行 ensemble 最低构象代表 source=ensemble + 精修队列 g16 行混排，队列删除/放弃后停留 refining 仅 crest 行结果仍可查）、GET /workflows?limit=20 列表（updated_at 倒序单点同形——页面刷新恢复路径）；relative_kJ_mol 零点=查询范围最低能量（HARTREE_KJ_MOL=2625.4996 换算单点、物理基准单测断言），部分完成态零点随行集重算（接受漂移、未成功成员 source=none 相对值 null）；聚合在后端完成前端不拼两段数据；单测 4 用例（队列零点/部分完成态重算/workflow 混排与列表同形/队列删除后聚合）随 test_workflow_crest（B10/B11 同文件口径）

### 变更

- 【specs】roadmap 随 A4 关闭回填四处：§7 开放事项 1（任务间依赖与 chk 规范）标注已定稿关闭并落定稿要点（@prev 不纳入/依赖推导单一真相/三错误码/窗口联动/边界交互）、M4 段补注续跑入口含手动停止条目与新增端点按 DSH 可消费形态供 M5 复用、§6 backlog 程序化输入生成加注 M4 仅组合流内模板坐标替换、§8.6 补 M4 重入语义注记（含物化依赖执行不适用采纳重跑通则——禁用 HQ 内部重试 + journal 重跑者取消重派 + 120s 盲区保守处置）

### 修复

- 【web】workflow completed 状态可达（P1 整改）：精修队列收束 completed 时由派发器席位结算按 refine_queue_id 反查推进 workflow 行（终态判据=精修队列成功记 completed，m4-plan §2.3 实施定案），启动对账对 refining 行按「归属队列已 completed」补记、收束两写间崩溃窗口——组合流成功后 GET /workflows 系端点状态语义正确（C7 进度面板与 D3 走查 7 前置）
- 【web】上游重跑对下游哈希跳过的传导定案落地（P2 整改，m4-plan §8 决策点 6 按建议值定案关闭）：advance 哈希跳过判定前置守卫——直接前驱在下游最近成功执行之后产生过新执行（重跑）即视依赖已变、拒绝跳过随之重跑（溯源基线=下游最近 succeeded 执行 id，全局执行 id 单调可比、无须落库溯源记录），守卫后由既有依赖守卫按前驱最新终态照常处置；roadmap §7 事项 1 回填定案句
- 【api】组合流提交响应契约三方对齐（P3 整改）：POST /workflows/conformer-refinement 回传 {workflow_id, state, crest_task_id, seat_id} 四字段（crest 任务 id 与席位 id 供待执行面板定位；crest_execution_id 属 GET /workflows/{id} 单点响应、提交时点 crest 尚未派发恒不存在），openapi ConformerRefinementResponse 与 m4-plan §2.3 措辞随改、前后端契约生成物再生（models.py/contract.ts）
- 【web】组合流终态钩子建队中断回收（P4 整改）：queues().create 至成员校验之间异常（如模板 link0 含 @task: 被 validate_queue_members 防御拒绝）时回收半成品队列、成员任务行与输入副本、refine_queue_id 不落——对账重推不复制孤儿队列，「不重建已存在实体」判重失效窗口消除
- 【web】断点续跑入口对 succeeded 条目显式设防（P5 整改）：preview/confirm 同口径 404 无续跑入口（404 NOT_FOUND）——续跑=从断点恢复、成功条目无断点，重跑诉求由历史页「重新排队」承载；m4-plan §2.2 入口措辞随改
- 【web】断点续跑 Opt= 变体原子选项保留（P6 整改）：opt=(ts,calcfc)→Opt=(Restart,ts,calcfc)、opt=X→Opt=(Restart,X)、已含 Restart 项不重复注入（大小写不敏感）、括号残缺按裸 opt——对齐 §2.2 注入矩阵「Opt=Restart + 原选项」语义
- 【api】resume preview 契约对齐（二轮独立复核 N2/N3）：probe 无资产等探针未执行态恒返回对象 {formchk_ok:false, reason:no_resume_asset}（原返回 null、与 ResumeProbe 非空对象 schema 不符，openapi-core 实测报 InvalidData），ResumeProbe.reason 描述扩至无资产/归档态；preview/resume 两端点描述补 succeeded 条目 404 无续跑入口口径（重跑由「重新排队」承载）与 ineligible 恒 200 边界；前后端契约生成物再生

## v3.0.2（2026-10-12T09:42+0800 发布，patch）

### 变更

- 发布流程新增 progress.json context 刷新要求:发布时 context 必须提及最新已发布版本号并复核 next_steps/known_issues,validate_progress 闸门同步新增内容新鲜度校验(context 缺最新版本号、两清单类型不符即失败)——2026-10-04 实测 context 滞留 v2.2.1 横跨三次发布、next_steps 停留 m1 时代而闸门全绿,规范缺触发点与闸门缺校验为失修双重根因
- 【plans】M4 计划基线刷新（对照 roadmap 全面审查后 11 项修复）：目标版本 2.3.0→3.1.0（原号已被 2026-10-04 更新域发布占用，按 changelog-spec §1.7 minor 顺延）、开工闸门改状态语义、§0.5/§0.6 对齐 2026-10-04 清理边界修订（异常终止仅保 chk）与 v2.2.1/v3.0.0 契约演进、B8 停等标注与 §7.2 走查口径统一（执行中页最小标注并入 C5）、B9/B10 依赖补显式边（B6→B9、A4→B10）、crest 任务禁入队（INVALID_MEMBERS 复用，混排场景改由 workflow 聚合承载）、组合流构象数边界（<2 记 failed、2≤n<top_n 取 min）、S3 接管跟踪对物化依赖执行特判绕行+roadmap §8.6 回填登记、C7 挂载点与 crest 停滞告警/mem 记账/formchk 探针时延补注
- 【plans】M4 计划二轮审查修复 11 项（高2·中5·低4）：前驱 skipped→下游传递 skipped 裁决（勾选跳过开关三段链防窗口死锁、归因沿用 predecessor_failed 附传递链 details、走查 3 拆两分支、B8/测试矩阵/DoD 同步）；重入②触发判据与 S3 已知 120s 盲区交互登记（独立信号或保守处置随 A4 定案、风险 8 补失效模式、B8 补边界用例）；crest 长跑可观测性入风险表 9（墙钟上限提示）；次链工时标注更正为全路径 A4→A5→B9→C6→D3→D4（8.5）；A5 评审触及契约形状时随提交 2 追加增量 docs(api) diff 通路；skipped 条目不展示续跑入口；roadmap M4 段时序措辞提前回填（消除两文矛盾窗口）；sse.md crest 补注显式列项；走查 7 双满员构造说明；A5 fixtures 路径与 A4/A5 契约措辞更正
- 【plans】M4 计划三轮审查修复 11 项（高2·中4·低5）：组合流时序图前置检查顺序校正为可执行探测在前、与 §2.3/§4.7 正文一致（H1）；链内成员（输入含 @task: 引用）断点续跑 ineligible 裁决——原因四态扩五态增「链内引用」、引导队列回退重提、preview 注入前置检测、B9/测试矩阵/DoD/走查同步（H2）；C5 补 B8 依赖边（停等原因字段渲染，M1）；开工闸门条件 1 改可证实口径——unreleased 待冻结插波条目不阻塞、建议开工前先冻结 v3.0.2（M2）；%Chk=@task: 续用形态补两段链走查增测（M3）；新增端点按 DSH 可消费形态定稿并登记 M5 工具面回填（M4）；补无日历承诺口径（L1）；链式物化磁盘占用入风险表 10（L2）；resume confirm 幂等重探补齐（L3）；能量换算系数单点常量+物理基准值单测并入风险 2 应对（L4）；roadmap §6 backlog 程序化输入条目防误读加注登记（L5）——各处均带当日注记
- 【plans】M4 计划四轮审查修复 15 项（高2·中6·低7）：开工闸门与 B 批次闸门拆分——§0.4 条件 4/5（A4/A5 评审、开放事项 1 关闭）属 A 批次产出、开工时点不可能已满足，拆出作为 B6 起后端实现的批次闸门（H1）；组合流钩子链（crest 终态→提取→建队→自动提交）补重启/崩溃恢复语义——终态钩子幂等化（提取产物落盘为锚）、启动对账增 workflow 扫描重推未完成一步、建队/提交判重不重建，§2.3+风险表 11+§4.2 A5 定稿项（H2）；workflow 状态枚举草案（crest_running/refining/completed/failed 单向迁移、精修队列回退停留 refining）与 refine_queue_pending 独立布尔字段归属，A4 契约 diff 清单与 §8 决策点 2 措辞同步（M1）；停等原因字段（依赖停等/资源停等）补入 A4 契约 diff 登记清单（M2）；resume confirm 满员 409 PENDING_CAPACITY_FULL 语义（与重新排队同待遇、零副作用，M3）；§0.1「A4 批次回填 roadmap」过时措辞更正（回填已提前落地，M4）；§0.4 unreleased 计数更新为 8 条并明示 3 条计划文档条目随 v3.0.2 冻结入库的裁决（M5）；能量表零点漂移裁决——接受部分完成态相对值随零点重算、前端标注「随完成进度重算」（M6）；低级 7 项：依赖总览补 B6→C5 边（L1）、§4 四要素措辞限 B 批次齐备（L2）、workflow 记录生命周期（随执行产物保留、候选删除不级联删，L3）、归档条目不提供续跑入口（L4）、finalize 对 crest 终态按无 chk 跳过（L5）、§0.6 端点数确数 8（analysis 六端点+workspace-out+storage/usage，L6）、A 批次评审返工入风险表 12（L7）——各处均带当日注记
- 【plans】M4 计划五轮审查修复 6 项（中3·低3）：续用形态 %Chk=@task: 构造路径补注——C5 勾选仅承载 %OldChk 只读形态、续用行经 M2 队列编辑手写 Link0 生成（走查 1 增测同步落注，M1）；crest 任务行展示规格补定——kind 徽标 + execution.monitor 照常 + 进度位「无增量解析」占位提示（§4.9 C7 交付物 + 走查 7 增断言，M2）；开工闸门 unreleased 计数删硬计数、改以开工登记时 progress.json 实况为准（每轮审查修复自身追加 plans 条目使硬计数写入即过期，M3）；B11 交付物「端点对」更正为 3 端点（energy-summary + workflows 单点/列表，WBS 行同步，L1）；§2.2 续跑入口含手动停止条目登记随 A4 回填 roadmap M4 段补注、消除两文口径差（L2）；crest 成员 mem 不声明的窗口记账偏差入风险表 13（沿用 §2.3 实测越界再议裁决，L3）——各处均带当日注记
- 【plans】M4 计划六轮审查修复 9 项（中3·低6）：A4 契约 diff 清单补列组合流提交端点 POST /workflows/conformer-refinement（§2.1/§4.1/§2.3 三处对齐两 GET 端点登记注记，M1）；B9 验收与 DoD 4 的 ineligible 判定条件更正——无保全 chk 但有成功执行记录者按 §2.2 取数路径为 eligible，改「无任何续跑资产（无保全 chk 且无可溯源的成功执行 chk）」（M2）；测试矩阵补两用例——单任务席位载体 @task: 引用拒绝入 test_dependencies 与 §4.3 场景矩阵、无保全 chk 回落最近成功执行 input.chk 入 test_resume（M3）；低级 6 项：头部 v2.2.1 时序与计数更正（先于 v2.3.0、其后两发为 v3.0.0/v3.0.1，L1）、契约演进来源更正为 v3.0.0（v2.2.1 无契约变更，头部与 §0.6 两处，L2）、走查 7「§2.5」引用补锚为 roadmap §2.5（L3）、§3.3 决策流 ineligible 补链内引用前置判定与探针超时分支（五态对齐 §2.2，L4）、§1 注记补「亦不含 A 批次评审返工」使风险 12 引用成立（L5）、走查 6 增 skipped/归档条目不展示续跑入口断言（二轮 M5/四轮 L4 裁决的验收承载，L6）——各处均带当日注记
- 【plans】M4 计划七轮审查修复 6 项（中2·低4）：CHK_SOURCE_MISSING 恢复指引更正——删「经『从断点续跑』恢复」（上游为 succeeded 条目无续跑入口、resume 新建任务不恢复原链引用，逐路径不可达），改「重跑上游恢复 chk 来源（沿用原任务 id、下游引用不受影响）」，§2.1 与风险 1 应对同步（M1）；sse.md 契约补注对象更正——停滞告警为独立 execution.stalled 事件行，execution.progress 与 execution.stalled 两行各补注 crest 不适用，§2.1/§2.3 同步（M2）；走查 7 正文「§2.5」直接补锚 roadmap §2.5（修正六轮注记式补锚的不彻底，L1）；§3.3 图 ineligible 节点移除 422 码标注、改「preview 200·eligible=false」与 §2.2 HTTP 语义同构（L2）；§0.4 条件 2 hq 依赖范围改「B6–B8/e2e」与 §0.6/风险 5 对齐（L3）；DoD 5 与走查 4 的决策点 6 建议值补「随 A4 定案后复核」括注（L4）——各处均带当日注记
- 【plans】M4 计划八轮审查修复 12 项（中3·低9）并转定稿化修订风格：crest 终态钩子链（提取→建队→自动提交）定稿于席位释放之前执行、离席为链尾，走查 7 满员构造的时序前提落地（M1）；「roadmap M4.1/M4.4 原文」引用改指本文 §0.2 提炼编号、注入矩阵补注 %OldChk=@exec 属工程细化，「逐字对齐」措辞撤销（M2）；hq 依赖枚举 B6–B8 扩为 B6–B10（§0.4/§0.6，M3）；低级 9 项：走查 6 ineligible 措辞对齐五态并注明类型不明态单测承载（L1）、续用行构造路径改「M2 候选分块编辑（或失败回退队列编辑框）」（L2）、C6「新执行」改「新任务」+resumed_from 写入时点补注（L3）、「零 schema 变更」改「数据零变更」（L4）、S3「三分流」改「chk 分流判定」（L5）、workflow 补精修队列放弃/删除路径定稿与聚合用例（L6）、走查 9 标题去「并排」并限定口径引用（L7）、风险 1 补续跑侧幂等重探消解（L8）、A4 清单补列 resumed_by（L9）；同批全文清理历轮审查过程注记（14 处裁决/补注字样定稿化）、头部沿革罗列收敛为「已经基线刷新与八轮独立审查修订定稿（2026-10-12）」单行声明

### 修复

- GUI 升级接管自举缺口修复：apply 流水线在拉起接管脚本前先从 sha256 校验通过的载荷内提取新版 self_update.sh 原子覆盖部署目录旧版（晋升失败即中止、不回退旧版不拉起不自退）——接管脚本执行者恒为新版，旧脚本缺陷不再横跨一次升级（3.0.0→3.0.1 升级 uv not found 中止、服务死透事故根修；生效起点为本次发布后的下一次升级）
- 待执行页成员展示态按席位本周期判定：成员 state 只认席位提交时刻（含临界秒，同秒即时派发归属本周期）之后的执行行，回退重新提交后未派发成员即 staged——原全量执行历史判定（any running 优先、否则最近终态）让重提交成员读到上一周期 running/skipped 终态（2026-10-04 用户报障），跨周期全量执行历史归历史页所有
- 运行中对账缺口修复：watchdog 运行中重起 server 成功即触发一次对账（on_server_restart 回调复位对账闩、刷新 S3 判据③ server_spawn_ts，引擎线程串行重跑）——对账原先仅在 web 启动时跑一次，web 不重启时 HQ server/worker 意外断连、重起后 journal 恢复重跑完全无感知（计时器/进度静默错乱）
- server_spawn_ts 记账时机收紧：process.start() 改为探活成功且 server-dir 出现新编号子目录（上游 ServerDir::create 每 spawn 新建、先于客户端 RPC 可达）后才记账——原在 spawn 发起后立即记账，探测抖动误报死亡、spawn 实际失败时产生虚假 spawn 值（消费端判据③交叉验证 3.0.0/3.0.1 已兜底，本修收紧生产端）

## v3.0.1（2026-10-04T21:32+0800 发布，patch）

### 修复

- 修复 GUI 升级通道在 systemd 托管下升级后服务死透：接管脚本依赖刷新步骤按 PATH 调用 uv，而 unit 环境的 PATH 不含 uv 安装目录，uv not found 使编排中止——WebUI 不再拉回、update-state 卡 restarting（2026-10-04 客户端 2.3.0→3.0.0 升级事故）；现 uv 经 PATH 与常见安装位（~/.local/bin 等）依次定位，不可得或刷新失败均警告跳过（包体已落位，服务拉回不被阻断），nohup 回退拉起改直启 .venv/bin/python 与 unit ExecStart 同构、回退彻底免 uv
- 修复更新域测试版本基线在 tag 跨 major 后前提翻转：v2.x 段内自增基线随 v3.0.0 发布整体落后本地致 16 用例失败，改恒定远段 v999.0.0 对任何现实 tag 恒为「有更新」
- 修复停止回退队列删除后的幽灵候选：删除队列曾无条件退回全部成员，而手动停止时未启动成员已标 skipped 执行行——带执行记录的候选删除时先删输入文件、删行再撞 executions 外键必失败，留下文件已失、行仍可见且重复删除永不成功的幽灵行；现删除队列按执行记录分流（roadmap §2.4：已执行过含 failed/skipped 的成员只留历史，未执行者退回候选），候选删除遇执行记录转 finished 归历史所有（行与文件保留），无执行记录者先删行后删文件杜绝半途态

## v3.0.0（2026-10-04T20:32+0800 发布，major）

### 新增

- 待执行页队列席位成员拖拽重排：展开子表抽为 PendingSeatMembers 组件，成员行复用既有 usePointerSort 指针跟手拖拽（与席位行/队列编辑框同一动效纪律，子表行 pointerdown 阻断冒泡不误触席位拖拽），提交 PATCH /queues/{id} member_ids 全量有序原子（契约 #15），SSE pending.snapshot 即时刷新；门控按 m2 分级矩阵定稿——执行中席位（locked）整体不可拖、仅 staged 成员可作拖源/落点（正在执行/已完成成员为既定历史），后端 409 QUEUE_STATE_CONFLICT 兜底定制提示；错误码分支登记 FRONTEND_CODE_BRANCHES 白名单

### 变更

- 【engine】清理边界修订定稿：异常终止仅保全 chk 入 protected/（rwf 无续跑消费价值，不再保全），Gau-* 瞬态 scratch（rwf/int/d2e/skr/inp 等）与任意命名 .rwf 即终收尸删除（failed 终态管线与 S3 重定向同口径），帮 g16 收尸不留垃圾
- 【api】历史页手动清理拆双档：「清理 chk」默认档仅删成功且超保留期的顶层 chk，「清理所有」无视保留期清所有成功任务的 chk（失败任务的保全 chk 两档均保留）；POST /history/cleanup 新增 scope 参数（expired|all，缺省 expired），响应统计移除 removed_rwf 仅留 checked/removed_chk；前端清理入口改 split button（默认清理 chk，「清理所有」藏下拉）并配悬停提示区分两档，可清理量统计口径同步收窄为 chk **（破坏性变更）**
  - 迁移指引：依赖 /history/cleanup 响应 removed_rwf 字段的外部调用方：该字段已移除；scope 缺省 expired 与原超期档为同一边界，但 rwf 不再属于清理范围（异常终止时自动收尸）

### 修复

- 修复保存为队列后成员名称不显示：队列契约 Queue 增补成员明细 members（task_id/filename，title 实时解析不落库）并由队列视图聚合填充，队列页成员概览与编辑对话框改接契约来源（未提交队列原先无名称来源只能显 —）
- 修复历史页占用明细浮层无限高：明细超过可视窗口时底部条目不可达——浮层限高 max-height 略低于可视窗口（100vh − 8rem）超出内部滚动，表头粘性钉住（separate 边框模型同历史页表格手法），容器上下留白移交表头/脚注以保 sticky 贴滚动口
- 修复对账 S3 判据③误触发：更新窗口 web 拉起时 server_alive 探测抖动误报 HQ server 死亡，spawn 实际失败（旧 server 在线，新实例探测到后退出）仍记账 server_spawn_ts，判据③（started_at 早于 spawn_ts）随之误成立，把 journal 从未恢复重跑、job 一直存活的在跑执行误落历史为外部中断并原样重提交；判据③现以 HQ 侧提交时刻交叉验证——journal 恢复的 job 提交必早于新 server spawn，提交时刻不早于 spawn_ts 即否决判据③按 S1 接管；Gateway 增 job_submitted_at（CLI job info / HTTP GET /jobs/{id} 按需单查，概览列表无此字段），字段缺失或解析失败不否决（向后兼容）
- 修复待执行页等待席位点击行无法展开队列成员子表：可拖席位的拖拽按下处理 preventDefault 使后续 click 不再派发（锁定席位跳过拖拽处理反而可展开，两者行为倒挂），展开切换改由席位行 pointerup 统一判定——按压起于行主体、非行内按钮且未发生实质拖动才切换，成员子表内操作不误触席位展开，等待/在途席位行为一致

## v2.3.0（2026-10-04T12:48+0800 发布，minor）

### 新增

- 【scripts】升级路径自动补装新增根脚本：CLI update.sh 对部署目录缺失的根脚本补装（自身除外），WebUI self_update.sh 经 *.new 原子 mv 全量同步包内根脚本，旧目录原位升级不再缺 restart_g16web.sh/stop_all.sh（v2.2.0 起新增）
- 【scripts】新增 systemd 用户级托管：systemd_install.sh 生成 unit（.venv/bin/python 直启、PATH 预置 .venv/bin 保证 hq 可发现、KillMode=process 保持停 WebUI 不杀 HQ），restart_g16web.sh/self_update.sh/stop_all.sh 检测 G16WEB_SERVICE_UNIT 自动委托 systemctl，失败回退手动路径

## v2.2.1（2026-10-03T11:08+0800 发布，patch）

### 变更

- 默认主题改为亮色，主题选择经 localStorage 持久化并由 index.html 首帧预设，刷新不再闪暗色

### 修复

- 【web】修复测试基建 HQ 进程残留：stop 关闭补 watchdog 竞态消除与 SIGKILL 兜底，测试会话收尾对全部存活实例强制回收，pytest 退出后零僵尸进程
- 候选页空态文案补 .com 扩展名，导入本就支持 .gjf/.com 而文案漏列
- 待执行页 locked（在途）席位不再渲染 RUNNING 状态 chip，消除与「在途」标记的语义重复
- 执行中页出分行去圆点分隔回归文案纪律，队列/提交左对齐、启动右对齐含日期，已运行独立行左对齐

## v2.2.0（2026-10-02T16:43+0800 发布，minor）

### 新增

- 【docs】新增 M3 执行计划与全套契约定稿：27 项任务实施方案，分析概览/收敛/频率/轨道、cube 生成、工作区只读分析与空间占用共 8 端点及 5 新错误码
- 【web】新增结果解析能力：正常结束的计算自动解析出能量收敛、频率、轨道与热化学数据，异常与超时降级留档不阻断收尾
- 【web】新增分析结果入库：计算收尾即自动落盘分析数据并置位历史条目 result_ref，历史详情可直接读取
- 【web】新增分析读取端点：历史条目可分别读取概览、能量收敛、频率、轨道四类分析数据（仅正常结束可读、缺失块明示），工作区内 .out/.log 可路径输入直接只读分析
- 【web】新增轨道/静电势 cube 生成与下载端点：按参数生成等值面文件并幂等复用，cubegen 缺失或生成失败显式报错并携带 stderr 尾部
- 【web】新增解析回归闸门：金标准输出 10 份与构造异常样例 4 份常驻回归，覆盖解析异常、非正常结束、属性缺失三类降级路径
- 【web】新增空间占用统计与告警：总占用与各执行占用明细（可清理量单列），超过可配置阈值时仅警告不自动清理（运行级可调、0=禁用、即时生效）
- 【frontend】前端引入 3Dmol 与 ECharts 依赖并经镜像源本地打包，新增构建产物零外链审计闸门保障离线可用
- 【frontend】历史详情新增内嵌分析区：概览/收敛/频率/轨道四视图按块可用性展示，工作区输出文件可路径输入直接只读分析，异常执行明示不可分析原因
- 【frontend】分析视图接入图表：能量收敛三数据源可切换曲线（判据阈值参考线）与频率红外棒图表格联动，虚频红色标注，配色随明暗主题
- 【frontend】详情分析区新增轨道与静电势三维渲染：可选轨道生成等值面（正负双色、精细度可调）或静电势着色，3Dmol 经离线化副本本地打包
- 【frontend】历史页新增常驻空间占用面板：总占用读数、超阈琥珀警示与各执行占用明细可展开，手动清理后即时反映
- 【docs】登记 M3 D1 端到端走查记录：七条路径全过（真机 g16 全链路、强停失败样例抽查、result_ref 三态、占用面板越阈警示与清理即时反映、三处受控注入留痕）与 DoD 十条对照，缺陷一处随查随修
- 【docs】登记 M3 人工验收问题修复计划：历史页抽屉七项（分析板块按钮化并与预览互斥同区显示、预览窗贴可视区下缘、去抽屉单条导出、缺失块与 tab 去「缺」后缀改纯置灰、收敛图对数轴十的幂刻度与滑块底部布局、小尺寸下拉文字裁剪、轨道画布锚定视口左上）的问题概述、根因定位与修复方案落档
- 【docs】登记 M3 人工验收第二批修复计划（v2.1.0 部署反馈五项）：执行页监控读数卡死（SSE 看门狗自 abort 误判不重连）、抽屉去结果引用行、占用统计扩为工作区根整树口径（含契约描述修订）、设置页文案只留必要解释并去英文参数名、待执行页拖拽迁移 usePointerSort 跟手动效（含变高行扩展），逐项根因定位与修复方案落档
- 【api】新增服务重启端点契约（POST /system/restart）：202 受理编排、更新流程进行中 409 复用既有码，描述定界不杀 HQ 与 SSE 看门狗恢复
- 【web】新增服务一键重启：后端受理编排（detached 拉起脚本、202 先行延迟 SIGTERM 自退）与 restart_g16web.sh 复原式重启脚本（快照 /proc 原命令/环境/工作目录与端口，停止后按原上下文拉回并探活；HQ 不受影响），随发布包落位部署根
- 【frontend】设置页新增服务重启常驻入口：二次确认模态显示运行中执行说明，有执行时确认按钮改长按 3 秒（useLongPress 进度反馈、--veil-press 新令牌），重启期间锁定等待并随 SSE 恢复自动关闭，完成后清空待生效参数提示条
- 【web】新增全服务一键停止脚本 stop_all.sh：按端口停 WebUI 并按命令行特征停 HQ worker 与 server（先 WebUI 后 HQ 避免重拉与重连风暴），逐进程优雅停止兜底强杀，随发布包落位部署根

### 变更

- 【docs】修订并拆分 M3/M4 联合计划为两份独立计划：多轮审核裁决 25+15+17 项定稿落档，拆分残留与外链、错误码口径全部闭环
- 【docs】回填 A2/A3 设计定稿与金标准补齐：可解析现代实测输出 10 份与 fchk 16 份，补轨道自旋维度、对称性与极端降级样例
- 【docs】回填 M3 审核口径：降级分支语义、错误码、可空字段与告警阈值默认值定稿，开放事项与待确认事项部分关闭注记，文档类变更记录豁免口径落档
- 【web】空间占用统计收敛为目录树单遍历加执行行缓存，千级执行目录下统计耗时降至毫秒级且口径不变
- 【docs】回填 M3 计划三审口径：SCF 能量缺失降级分支补记，分析读取 404 口径校准（running/未知 id 无历史终态行返回 404）
- 【frontend】分析面板分块拉取状态打包为 useBlock 工厂并收敛判据系列公共形状，消除三处同形 loader 与逐字重复的参考线构建
- 【docs】占用统计契约口径描述修订：total_bytes 由 run/ 产物树扩为工作区根整树 apparent size，重跑两侧生成物
- 【web】待执行页席位重排迁移指针跟手动效（与队列编辑框一致）：拖拽组合式扩展变高行前缀和定位与逐行锁定门控，HTML5 DnD 组合式随唯一使用方迁移退役
- 【frontend】设置页重启入口按钮文案精简为「重启服务」（去尾缀省略号）

### 修复

- 【web】修复数值字段序列化非纯数值、工作区分析超时误报服务器错误、占用统计口径偏差（运行中与孤儿目录计入总占用与明细）三处问题
- 【api】补登记 cube 文件流 409 响应与工作区路径守卫三态语义，占用统计描述补全态口径
- 【docs】修正进度登记瑕疵：in_progress 恢复对象形态并加固类型校验，历史摘要收敛为行为视角短句
- 【frontend】补全工作区文件分析的轨道能量清单展示（此前仅提示文案），等值面入口置灰并注明无 fchk；频率面板补无频率块与无 IR 强度两层空态占位，归档切换即时刷新占用读数
- 【frontend】轨道面板组件卸载时显式释放 WebGL 上下文（WEBGL_lose_context），防连续切换执行累积上下文触浏览器上限
- 【frontend】分析区 UI 文案分隔符合规化（圆点改长破折号/斜杠），结果引用标签回正为真实值口径（B2 已落库非占位）
- 【web】存储统计路径拼接统一 pathlib（退役 os.path.join/relpath），单测口径不变全绿
- 【frontend】二审终审修正收口：轨道面板 v-else-if 两分支加 key 强制重建释放 WebGL（同型组件合并承载首次实现）且工作区模式轨道能量清单改为可展开浏览（选择器不禁用、生成/等值面入口维持置灰）；亮色主题浅淡强调文本调深一档过 4.5:1 并扩展对比度闸门覆盖 bg-inset 底组合；历史页残留圆点分隔符补清（共 6 处）
- 【frontend】修复能量收敛图 x 轴名被画布右缘裁剪不可读（默认末端定位文本外溢），改中置下挂并预留轴名空间（D1 走查发现）
- 【web】轨道画布容器自建定位上下文，渲染 MO/静电势的 3D 图不再锚到视口左上（vendored 3dmol 绝对定位画布改锚 .orb-viewer 自身）
- 【web】小尺寸下拉与代理输入框补水平 padding，24px 定高下中文下缘不再被裁（轨道面板类型/轨道下拉与设置页代理输入，同类定高控件全量排查无遗漏）
- 【web】缺失分析 tab 与可用数据块去「缺」后缀改纯置灰态，置灰样式与缺失原因悬浮说明保留
- 【web】收敛图对数纵轴改十的幂科学计数刻度（上标模拟、字号颜色走设计令牌）并修复滑块带底部布局（预留 dataZoom 与轴名空间、两端窗口数值可见，暗底文本色走令牌）
- 【web】历史详情抽屉动作行重组：分析板块改按钮开合与输入/输出预览互斥同区显示（默认收起、惰性挂载），预览改展示区本体拉伸贴抽屉下缘内部滚动，移除抽屉单条导出入口（工具条批量导出不变）
- 【web】SSE 断流自愈：重连判定收窄为仅认主动关闭标志，看门狗超时自中止后自动退避重连并重建快照基线，执行页监控读数不再冻结需手动刷新
- 【web】历史详情抽屉移除恒为 analysis.json 的结果引用行，后端字段与契约保留（排障/审计用）
- 【web】空间占用总读数口径扩为工作区根整树（含数据库与 hq 状态等非执行文件），执行明细分桶不变，占用面板注明口径；与 du -sb 工作区根对照一致
- 【web】设置页文案只留必要解释（13+2 项描述去生效语义括注与内部注记），页面去英文参数名与环境变量展示，重启提示条改显中文参数名
- 【web】修复设置页重启提示条永不出现（保存响应先收敛表单致变更对比恒等），对比提前至表单收敛前，提示条显中文参数名（走查随查随修）
- 【web】去除设置页枚举参数下方与下拉可选值重复的「取值」提示行，数值型范围提示保留

## v2.1.0（2026-09-29T17:25+08:00 发布，minor）

### 新增

- 【docs】新增版本标识与更新功能需求文档（version-update-spec.md）：侧栏动态版本行、设置页顶部更新卡（手动检查/立即更新/下载进度/运行守卫）、每日每周每月凌晨1:00自动检查与异常如实反馈规格，含依赖核查、REST/SSE 契约草案、改动面清单与七项决策点
- 【docs】新增版本更新实施计划（docs/plans/version-update-impl-plan.md）：需求分析（五功能/边界/十项技术约束/八条验收判据）、任务拆解（A–G 七批次 17 提交，每任务含产出与完成判据）、依赖图与关键路径（A1→D1→D2→E1→G1）及 11 项风险登记、四层测试方案（单测 4 新 5 扩/进程内集成/闸门回归/手动冒烟 9 项/本地 release 模拟演练）、发布流程（含固定名附件自举边界说明）与分层回滚策略；实施侧定稿：G16WEB_UPDATE_BASE 演练通道、枚举校验失败归 type 不扩词表、openapi info.version 动态覆盖防再漂移、自动检查 30s 轮询式调度、.update-check 伴生文件跨重启恢复
- 【api】契约预告更新域四端点与五错误码（status/check/apply/proxy 与 UPDATE_* 全集 19→24，SettingItem.range 增枚举结构，info.version 同步 2.1.0），前后端契约生成物再生
- 【api】SSE 契约新增 update.progress 与 update.phase 两事件（事件全集 15 类；下载进度 ~500ms 合并窗口取最新、阶段翻转即推），推送时机表与事件命名域清单同步
- 【web】版本单一事实来源解析链落地 config（部署目录 VERSION → git describe → CHANGELOG 最新 released 兜底，bare_version 剥 v 单点、失败兜底不炸启动），并登记更新通道默认值与运行级 update_check_interval 四档参数
- 【web】health 与 openapi 元数据改用版本单一事实来源：main.py/system.py 版本硬编码退役，/openapi.json info.version 运行时动态覆盖防再漂移（ssot 测试改剔除字段严格比对+独立断言）
- 【web】支持运行级参数枚举值域校验：update_check_interval 四档周期可正常保存，非法值按类型错误随整批拒绝并回显枚举载体
- 【web】新增更新检查能力：语义化版本严格比较、远端 release 探测与连接超时/无法连接/远端异常的逐字反馈、代理通道与最近检查结果伴生文件落盘恢复
- 【web】新增更新执行流程：任务运行中/重复触发/源码形态三守卫与同步预检、带实时速度的流式下载进度、sha256 校验中止、中断重试与跨重启状态恢复、下载校验完成后自动接管重启
- 【web】新增更新域四端点：状态查询/手动检查/触发更新/代理通道设置，部署形态判定驱动前端置灰、非法代理地址拒绝，受理后经 SSE 推送进度与阶段
- 【web】新增自动检查更新：每日/每周/每月/从不四档凌晨 1:00 锚定调度、错过窗口启动后短时补查、只发现不安装、设置保存即时生效
- 【web】侧栏新增动态版本行与更新可用圆点：health 单一事实来源下发带 v 形态直接渲染、断线重连重拉校对，版本行可点击（热区含圆点）跳转设置页更新卡，发现新版本时点亮 accent 圆点
- 【web】设置页新增置顶更新卡：八态显示状态机随 SSE 相翻转、立即更新按任务运行中/源码形态/流程进行中置灰并附逐字文案、下载进度条（左版本号/右实时速度换档）、代理通道三选一切换即时生效与非法 URL 即时校验；设置页同步调整为启动级两项水平两列、运行级枚举参数四选下拉、1080p 一屏预算收敛实测零滚动
- 【web】前端更新事件消费与服务重启强刷：感知服务重启中后断线转健康检查轮询（500ms、上限 120s），恢复后按版本变化强制刷新、更新失败如实展示原因、重启超时如实提示手动处置；多标签页各自轮询自然跟随
- 【api】契约增 UI 偏好域 /ui-preferences 两端点与 QueueSortKey/UiPreferences/UiPreferencesUpdate schema（GET 读全量、PUT 合并 upsert 整批校验、不发 SSE 事件），代理通道三处口径改工作区 .update-proxy，contract.ts 与 models.py 生成物再生
- 【web】UI 偏好域落地：迁移 v2 增 ui_prefs 键值表（工作区 SQLite 持久化、跨重启/更新不回默认）、UiPrefsRepo 与 store 访问器、GET/PUT /ui-preferences 路由（键白名单与值域 all-or-nothing 校验、未知键/越域值 400 INVALID_REQUEST）、config.UI_PREF_KEYS 单一来源
- 【web】前端列表排序规则持久化：新增 useSortPref 组合式（挂载拉取回填、变更即时单键写回、失败静默降级下次重拉校对、回填期间屏蔽写回），队列页 queues.sort 与历史/归档页 history.sort/archive.sort 分立接入，同组件跨路由复用实例时键切换重拉
- 【web】增量解析新增 SCF 轮次计数 scf_round（Cycle 1 行出现即新一轮、自 1 递增，截断重扫随进度状态重建），execution.progress 载荷与快照 progress 增 scf_round 字段（sse.md/openapi.yaml/models 契约同步，contract.ts 再生）
- 【frontend】SSE 客户端无帧看门狗：连续 60s（4×默认心跳 15s）无任何帧主动断开走退避重连并以快照重建基线，消除半开连接等场景「连接看似在线、读数实已冻结」的无提示失联
- 【api】契约增历史批量导出端点 POST /history/export（ids 集合请求体 → application/zip 打包下载，新增 HistoryExportRequest schema，400/404 错误响应），mapping.md 登记多选表格套件与导出映射、端点对照 39→40（history 8→9），前后端契约生成物再生
- 【web】历史批量导出端点落地：run/<id>/input.log 打包 ZIP，条目内 <stem>.out 正规扩展命名、同任务多次执行同名冲突组全部加三位补零执行 id 前缀、无输出条目跳过并在包内 _导出说明.txt 逐条登记、选中条目全部无输出 404、ids 非空正整数数组校验 400
- 【frontend】历史页表格接入候选页同款通用多选套件（复选框列、useMultiSelect 锚点驱动 Shift 范围/Ctrl+Shift 追加、Ctrl/Cmd 单选、Ctrl+A/Esc/方向键导航与滚动定位、勾选跨页保留）与工具条勾选批量导出 .out（POST export 经 blob 下载 zip、跨页勾选整体参与、修饰点击不开详情抽屉），抽屉单条导出按钮同步改名「导出 .out」

### 变更

- 【docs】版本更新需求文档评审修订（18 项口径对齐）：代理通道定稿上设置页（D4，更新卡内切换、读写 .update-proxy 不进 SQLite）、检查周期四档含从不（never）、update.phase 枚举增 available 并与显示状态机逐行对齐、新增部署目录 update-state 落盘标记写入/恢复/清理规则、self_update.sh 重启编排定稿（后端自退、脚本等待端口释放不杀进程）、登记第四处版本硬编码（openapi.yaml info.version）、package_release.sh 入包清单需追加 self_update.sh、SSE 断开时点/版本号形态/文案全角标点/错误码 19→24 等表述统一
- 【docs】版本更新需求文档补口径：版本行本身可点击、点击（热区含小圆点）跳转至设置页更新卡，hover 微反馈不占导航项形态，联动 §3.1/§6.2/§7.1
- 【docs】版本更新实施计划与需求文档按全面审查报告逐项修正：闸门级两项（test_error_codes 错误码全集 19→24 同步、openapi ssot 豁免改「剔除 info.version 严格比对+独立断言」防 pytest 必红）、契约补全（status 字段全集增 supported/proxy、SettingItem.range 增 enum 结构、apply 同步预检 502 回登需求）、验收补全（.update-check 伴生文件与「服务重启超时」文案回登需求、F2 按钮可用性矩阵、F3 强刷三分支与圆点全相映射、mapping 端点对照 33→37）、实现细化（下载重试策略与 httpx read 30s、update-state JSON 仅改 phase、self_update env 继承与端口判据、默认代理落盘无尾换行、1080p 预算含新增参数行）、偏差登记与一致性（30s 生效口径/根脚本自更新行为差异/版本来源措辞/测试先行差异登记、提交数 13→17、R5 下拉四选、需求 §3.7 引用与 §6.4 补登）
- 【docs】更新功能文档链补齐：mapping 增更新卡四行与侧栏版本行映射（端点对照 33→37）、roadmap 登记update_check_interval 与 G16WEB_UPDATE_BASE 及功能更新定位、deployment 升级章节改 WebUI 主/CLI 兜底并补伴生文件排障
- 【build】install.sh 安装链路镜像化：uv 自动安装器与托管 Python 解释器下载源改经 v4.gh-proxy.org 代理（GitHub 直连不再依赖），代理前缀可用 GAUFORGE_GH_PROXY 覆盖；两链路经本地实测验证
- 【docs】视图偏好域与代理通道工作区口径文档同步：mapping 端点对照 37→39（队列/历史/归档排序挂 ui-preferences）、version-update-spec 六处 .update-proxy 改工作区、deployment 升级章节注明部署目录旧位置自动搬迁、roadmap §2.5 增视图偏好条目
- 【web】更新代理配置迁工作区：proxy_path 改 G16WEB_HOME/.update-proxy（更新/重装部署目录不丢）、启动时一次性搬迁部署目录旧位置遗留（幂等、工作区已有则以工作区为准）、write_proxy 补目录创建；迁移三分支测试与既有 proxy 用例随改
- 【build】update.sh 代理配置改读工作区 ${G16WEB_HOME:-$HOME/g16web}/.update-proxy 与 WebUI 更新卡共用同一份（落盘前 mkdir -p，默认值与后端一致），覆盖范围注释同步
- 【frontend】执行中页 REST 基线轮询 8s→3s 并对账撤卡：REST 运行列表之外的卡与停滞告警一律移除（仅成功响应时执行，服务不可达窗口保持现状），SSE 事件丢失场景幽灵卡 ≤3s 自愈
- 【docs】设计令牌 --drawer-width 380px→520px 规格登记与样板同步（m0-frontend-design §2.3、m0-ui-preview.html）：历史详情抽屉单行键值行须同行容纳「提交/启动/结束」三时间戳，与候选页预览列 --preview-width 语义分立

### 修复

- 【web】修复 SSE fanout 重放窗口修剪后实时广播永久停摆：增量基准由「绝对已广播条数」（对固定 1024 容量列表 len 比较永假）改为事件 id——此前服务启动累计事件超 1024 条即全量静默丢失（心跳照常、连接看似正常），执行页幽灵卡与监控读数冻结的根因
- 【frontend】执行中页读数修复：execution.progress 可选字段判空渲染（scan 类任务无优化步时 OPT STEP 不再显示 NaN）、SCF 读数改「轮次-圈数」x-y 展示（标签 SCF RUN-CYCLE，旧载荷缺 scf_round 退单圈数值）
- 【frontend】历史详情抽屉紧凑化与预览可见性：全字段改单行键值行（dt 左/值右对齐，「提交/启动/结束」三时间戳以「/」分隔同行、资源 CPU/MEM 与监控峰值各并一行），抽屉 380→520px，打开输入/输出预览后自动滚入视野；最小支持视口 1280×720 下含全尺寸预览零滚动（此前字段双行堆叠，无预览即超高约 100px、预览区被裁切在视口外）
- 【web】历史单条输出导出附件名 .log 改 .out（G16 输出正规扩展；内容不变仍为 run/<id>/input.log）
- 【web】修复多结构任务提交核验压平结构交界双空行：QST2/QST3 输入经提交核验后，第二套结构电荷行前的双空行被规约为单空行，派发副本在部分发行版 G16 上被误并为单行读取而报 End of file in ZSymb；verify_and_normalize 登记多结构例外（下一附加节首行为电荷/多重度整数对时交界规约为恰双空行，其余交界仍恰一空行），同步 roadmap §2.7 规约条款并补 6 项核验测试（正反例/幂等/QST3 双交界/非多结构回归/Variables 共存/提交路径）

## v2.0.0（2026-09-28T02:06+08:00 发布，major）

### 变更

- 【repo】自有代码许可由 MIT 更换为 PolyForm Noncommercial 1.0.0（分层许可：内核 crates/ 完整保留上游 HyperQueue 的 MIT；README 新增 AI 使用声明） **（破坏性变更）**
  - 迁移指引：v1.0.0 及之前的发布按 MIT 存续；自 v2.0.0 起除 crates/ 内核（MIT）外的自有代码仅限非商业使用，商业使用需另行获得授权

## v1.0.0（2026-09-28T01:03+08:00 发布，major）

### 新增

- 【api】契约增补导入成队参数与提交响应规范化标记（queue_from_folder/folder_name、CandidateCreate.queue、SubmitResponse.normalized），mapping/sse 时机表同步
- 【api】错误码全集 19 码与两张 reason 词表落位 openapi.yaml 文件头作为 SSOT 载体（含 M1 私有码补录与实现码语义标注），ErrorBody.code 描述改指该清单
- 【core】新增关键词字典生成链（extract_keywords.py 读 gaussian-kb 结构化知识库产出 97 词条入库、parse.keywords 加载器缺失降级零警告），支撑 route 关键词拼写检查
- 【core】分块编辑保存真实化：parse/blocks 节定位与区间替换重组器（编辑不转换行尾、目标节末恰一空行规约）、services save_block 全流水（形态守卫七路径/逐节校验 422/round-trip 自证 500 拒绝落盘/原子写/全局写锁）、PUT blocks 端点消解占位节名、route 拼写检查（近邻命中才警告）
- 【core】提交前输入核验真实化：CRLF→LF 与空行规约器、三提交路径（行内/队列逐成员/历史重新排队）建席前统一核验，解析失败与多步拒绝 422 且不落盘、规范化原子写回并自证结构不变、响应携带 normalized 标记
- 【core】队列编辑全语义：PATCH 状态分级矩阵（unsubmitted 全量/submitted 仅成员/executing、completed 409）、member_ids 子集去重下限校验与移除分流四类（退回/脱离/failed、skipped 新候选同源复制）、回退编辑移除全部 failed/skipped 自动成功终结、在跑成员移除拒绝
- 【core】队列删除增强与 id 查重：DELETE 分级处置（submitted 席位撤销+退回、completed 成员只留历史、executing 409），队列 id 生成对照全库（含任务/执行记录历史引用）查重永不复用
- 【core】导入成队：POST /candidates 增 queue_from_folder/folder_name 参数与响应 queue/queue_fallback_reason 字段，受支持文件数 2–10 成队、越界回落全部候选并明示原因，成队事件序 created ×N → moved_out ×N → queues.changed(created)，前端契约生成物再生
- 【core】契约回归更新与整队生命周期 e2e：fake g16 全链路（创建/提交核验/中段失败分流/补位/回退归因/哈希跳过/重跑/自动成功）与 PUT blocks、PATCH member_ids、提交响应 normalized 的 openapi-core 零漂移校验
- 【web】预览编辑态真实化：BlockEditor 分块编辑器（link0/route/title/charge_mult/additional 双态、自动保存失焦或 800ms 防抖、422 错误描边注记不落盘、拼写警告琥珀注记、CRLF 中性注记、molecule 恒只读），行内提交与历史重新排队按响应 normalized 字段展示规范化注记
- 【web】候选页多选与队列组建：复选框列（全选/清空、已选计数）、「+ 队列」按钮（2–10 前置校验）、队列编辑对话框三模式组件（名称/成员移除与拖动排序/跳过开关、保存 primary + 直接提交 secondary 链式失败保留 unsubmitted、normalized 中性注记）与 useDragSort 公共拖拽组合式（待执行页同步切换）
- 【web】队列页真实化：手势分工（单击行首箭头展开/双击行开编辑对话框）、状态分级对话框接入（unsubmitted 全量、submitted 仅成员、executing/completed 只读附待执行页引导）、重新提交（normalized 注记/满员 409）、删除二次确认（状态分级文案、executing 不渲染）、失败成员归因列表与回退队列 failed/skipped 成员的 BlockEditor 分块编辑入口
- 【web】导入队列选项：文件夹导入「保存为队列」勾选与队列名预填（顶层目录名缺省可改），上送 queue_from_folder/folder_name，成队注记与越界回落 queue_fallback_reason 中性提示
- 【docs】M2 验收记录落盘：D1 九条路径走查留痕（fake g16 全链路 + Playwright 黑盒）、五笔运行时缺陷修复登记、设计一致性与系统级判据核对、M2.1–M2.7 不偏离核对
- 【web】标准表格底部套件 TablePager 落地候选/队列/历史三页：「共 n 项」计数右对齐统一口径（删除「n 项 — 共 n」双口径与历史页顶部重复计数）、分页控件绝对居中（首页/上一页/下一页/尾页线性 SVG 图标按钮）、页码输入框自然数过滤回车跳转 0 落首页超上限落尾页、总数小于分页大小时控件整体隐藏不占位；候选/历史接入真实页码取数修复超过分页大小直接截断且无分页样式的缺陷（筛选/排序回第 1 页、页码越界钳末页重取），队列前端切片分页，设置项 page_size 三页全局统一并随 settings.updated 即时跟随
- 【web】队列页顶部控制行（与历史页同款）：状态筛选（全部/未提交/已提交/执行中/已完成中文措辞）与排序（默认=回退置顶·创建时间新→旧；名称 A→Z/Z→A 走 zh localeCompare），/queues 全量返回前端过滤切片，筛选/排序变更回第 1 页并区分筛选空态文案
- 【web】候选页行点击接入 Shift 范围勾选（参照资源管理器范式补齐点行入口）：Shift+行点击从锚点行到目标行范围勾选（普通 Shift 替换式、Ctrl+Shift 追加式，锚点不动可反复调整）、预览选中目标行；普通行点击保持预览选中并同步锚点/焦点衔接键盘扩展，Shift 按下 mousedown 防文本选区
- 【web】候选页行点击修饰交互补全（修饰交互全在行上）：Ctrl/Cmd+行点击切换单项勾选并重置锚点（示例范式：Ctrl 点击重置锚点），与 Shift+行点击范围选择、Ctrl+Shift 追加范围、方向键导航构成完整行内多选；行点击入口不再依赖复选框

### 变更

- 【docs】设计文档增补表单控件与编辑态规格定稿（select/checkbox/toggle/编辑态描边裁决/自动保存触发/队列对话框布局/拖拽动效/手势分工），M2 移项销号
- 【docs】M2 计划登记修订说明五（B1 字典抽取源改用 gaussian-kb MCP 结构化知识库）并回填 A1 实地核查结论（94 页甄别剔除 8 篇文章页、词条=slug+标题变体、决策点 4/5 关闭）
- 【core】错误码治理落位：席位私有码替换为全集码（QUEUE_MEMBER_FLOOR/TASK_EXECUTED_IMMUTABLE）、导入 reason 对齐 INPUT_PARSE_FAILED、设置域 409 SETTING_READONLY / 422 SETTING_VALUE_INVALID 与 reason 词表对齐；test_error_codes 静态闸门（实现 ⊆ 契约 19 码、退役码零残留）
- 【docs】M2 计划登记修订说明六（B 阶段收尾）：决策点 7 关闭（%Mem 手册核查结论）、实施中修正的两处 M1 引擎缺陷与回退事件对齐登记
- 【api】契约登记 GET preview/input 跨形态守卫口径：id 跨形态延续（候选与失败回退队列成员可读，守卫与 PUT blocks 一致，其余形态 404），mapping 增补编辑初始化与 CRLF 检出映射行
- 【docs】roadmap M2 编辑条目字典抽取源随修订说明五回填（D1 一致性对照核验发现旧离线 HTML 路径残留，先改文档）
- 【docs】roadmap M2、m2-plan M2.2/§4.3、m0-frontend-design §4.6 回填创建态队列对话框不渲染队列 id 字段的表述（随创建态占位注记移除的人为修正同步文档）
- 【docs】m0-frontend-design §5 候选页布局行与 m2-plan C2 段增补「+ 队列」按钮右缘对齐左列列表、不落预览区右肩的布局规格（补设计文档未述锚点，计划外人为修正指定）
- 【web】前端硬编码度量与动效时长收口为设计令牌：新增复用度量 9 个、时长档 8 个、字距复位档 1 个（tokens.css 与样板 HTML 同步，check_tokens 89/89），12 文件约 50 处字面量改引令牌，BlockEditor 防抖升命名常量；值恒等替换视觉零回归
- 【docs】设计文档混排纪律 1 登记「保存为队列」12px 从属档例外（随工具条主从分级的人为修正同步）
- 【docs】设计文档回填视口固定布局纪律（100vh 锁定、body 无全局滚动条、侧栏 HQ 状态常驻、列表容器局部滚动、退场视图绝对定位离场）与标准表格底部套件规格（共 n 项右对齐、分页控件居中与显隐规则、SVG 图标、输入框交互与边界钳制），roadmap §2.5 分页大小标注三页全局统一（人为验收修正指定，修复前先行回填）
- 【web】候选页组建队列保存后留在候选页（原跳转队列页），对话框关闭、勾选清空、列表经 SSE 自动刷新（2026-09-27 验收修正）
- 【core】候选列表默认排序改为回退候选置顶+创建时间倒序（同秒批内 id 逆序，后导入在前），批内文件名自然序退役；契约 /candidates 描述与两侧生成物再生，排序测试改反例构造（导入序与时间序相反锁定排序键，并经纯 id 序退化验证失败）
- 【docs】roadmap M1 候选序表述与 M2 队列页段、m0-frontend-design §4.1 历史页措辞与 §5 候选/队列页布局行、m2-plan §4.3 C2 保存后行为，同步回填上述规格（2026-09-27 验收修正）
- 【web】候选页多选视觉补全：勾选行统一呈 accent 选中背景态（row--checked，与预览选中同源 7% 背景、hover 保持不回落灰调）——Shift 范围勾选后范围内每一行都有选中态颜色变化，不再只有鼠标点到的预览行变色；预览行左条/焦点行描边叠加以区分，明暗双主题经令牌自动适配
- 【web】品牌更名「Gaussian 16 管理工作台」：侧边栏品牌区改两行排布（首行 Gaussian 16、次行 管理工作台，电源指示灯改对齐首行），浏览器标签页标题同步同名
- 【repo】项目自立更名 GauForge：git 历史与上游 HyperQueue 切割（vendor 根提交 + 自有提交重放）、许可双轨拆分（根 LICENSE 本项目 / crates/LICENSE 上游）、tag 改裸 v 前缀，并以 1.0.0 声明首个稳定版 **（破坏性变更）**
  - 迁移指引：现有克隆需改用新仓库地址重新克隆或重设 remote；获取本项目版本改用裸 v 前缀标签（如 v1.0.0）；上游完整历史与旧 g16- 前缀 tag 见备份 bundle（~/gauforge-history-backup-20260928.bundle）

### 修复

- 【core】预览与原文端点对失败回退队列成员放行（读取守卫与 PUT blocks 一致，其余形态 404），补路由级断言回退成员 200、非回退成员 404
- 【web】队列对话框 MemberRow 类型导出移出 script setup（setup 内 export 引发模块初始化 ReferenceError，对话框 chunk 加载即崩溃、候选页组件树中断；浏览器实测复验通过）
- 【web】预览编辑器 taskId 的 immediate watch 移至编辑态声明之后（原声明序在 loadPreview→exitEditLocal 同步回调中触达未初始化 ref 抛 TDZ，预览卡恒卡「读取预览」；浏览器实测复验通过）
- 【core】候选原文端点保留 CRLF 行尾（_load_input 改字节读入，read_text 通用换行静默吞 \r 致前端 CRLF 检出注记永不触发，D1 走查实测暴露）并补路由级回归断言
- 【web】toast 自动消失按本条 id 而非最新序号（多条交叠时早期 toast 永不消失并遮挡工具条，D1 走查 GUI 实测暴露）
- 【web】队列编辑对话框保存校验按模式区分成员数下限（编辑态误用创建期 2–10 校验致剩 1 成员的合法编辑被禁存，D1 走查 GUI 实测暴露）
- 【web】候选页「+ 队列」按钮右缘与左列列表对齐（原被工具条 spacer 推至整页最右、落在预览区右肩，视觉归属错误；计划外人为修正）
- 【web】创建态队列编辑对话框移除「队列 ID/保存后生成」按钮样式占位注记（纯装饰不可点击、属实现注释不应上 UI；编辑/只读态真实 id 展示与后端生成逻辑不变；计划外人为修正）
- 【web】候选页双栏塌单列回归修复：令牌化重构删除页内变量 --preview-col 后 .duo 的 grid-template-columns 引用漏改，声明无效回退 none 致预览区落到表格下方；改引 --preview-width 并补全量悬空变量审计（83 引用全部有定义）
- 【web】候选页工具条导入组主从分级：「保存为队列」与两导入按钮间加竖分割线（组间距 12→25px）、复选框贴近宿主按钮（8px）并降字号至 12px 下限档，体现其对「导入文件夹」的从属（计划外人为修正）
- 【web】管理面板锁定视口高度与列表局部滚动：app-frame 100vh + overflow hidden + 网格行高 minmax(0,1fr)，长列表不再撑破面板、body 不再出现全局滚动条，侧栏 HQ 状态行常驻窗口底部；候选/队列/历史三页列表容器化（滚动包裹层吃剩余高度、粘性表头贴滚动容器顶、候选预览卡改随行高拉伸自管滚动），视图切换退场视图绝对定位离场防双视图挤压
- 【web】候选页粘性表头透明穿透修复：表格边框模型 collapse 改 separate（spacing 0）并给表头建自身层叠上下文，列表局部滚动后行内容不再画在表头背景上，明暗两主题实测穿透消失；发丝线全在单元格 border-bottom 上视觉不变
- 【web】队列页提交动作文案按回退标记分级：携带回退标记/回退次数的未提交队列（失败回退）显「重新提交」，新鲜未提交队列显「提交」，修复新鲜队列被误标重新提交的问题；整席移除回退按后端设计无回退标记视同新鲜，设计文档 §5 队列页规格同步回填
- 【web】队列编辑对话框拖拽排序动效重做：HTML5 DnD 改指针跟手画布式（usePointerSort 组合式），拿起项 transform 跟手、其余项迟滞换位让位/归位（--dur-drag 200ms 新令牌，行高/行距量测自 DOM 与令牌不硬编码），松手先滑入目标槽位、归位动画结束后才提交重排全程无跳变，成员超出限高触边自动滚屏，行内移除按钮不再被拖拽劫持；待执行页保留 HTML5 DnD，设计文档 §2.4/§4.6/§6 规格同步回填
- 【web】视觉修复三处：侧栏导航项中英上下分行、中文名 14px 升 18px 并扩命中区至 48px（新增 --nav-item-height 令牌）；展开/收起三角放大至 18px 并以弹性居中修正旋转基准，原地旋转不再绕点公转（队列页与待执行页同款）；队列页状态列/成员状态徽标/结束原因列改中文显示（queueStateLabel/taskStateLabel/finishReasonLabel 单一来源），原英文枚举保留为内部信号（chip 类名与 data-finish-reason 属性）
- 【web】修复分子说明以原子序数书写时化学式空缺（序数映射元素符号计入 Hill 式），预览卡 FORMULA 空值改显 — 占位防标签上浮错位
- 【web】候选页多选交互套件化：新增 useMultiSelect 公共组合式（锚点+焦点双状态驱动），复选框接 Shift 范围选择（Ctrl+Shift 追加、锚点不随 Shift 改动可反复调整）、上下方向键导航联动勾选与滚动定位、Ctrl+A 全选与 Esc 清空、翻页重置页内索引（勾选跨页保留），行点击预览与勾选锚点衔接；焦点行发丝描边与 Shift 按下防文本选区
- 【web】历史页状态列/详情抽屉状态徽标/状态筛选下拉改中文显示（taskStateLabel 单一来源，与队列页同纪律；筛选下拉文案 全部/成功/失败/跳过），原英文枚举保留为内部信号
- 【web】候选页多选交互修复：复选框点击不再 preventDefault——Chromium 的 checkbox 取消激活回滚发生在 Vue 渲染写入之后、覆盖 :checked 同步（实测计数已更新而复选框不亮、Shift 锚点范围选择视觉不生效），改为放行原生翻转并按 checkedIds 语义同步修正被点击项 DOM（该行 vnode 值未变时 Vue 跳过写 DOM 需自补）；Playwright 隔离实例实测锚点范围选择/范围调整/Ctrl+Shift 追加/Ctrl 切换/方向键导航/Shift+方向键扩展/Esc 清空全路径通过

## v0.1.0（2026-09-26T17:35+0800 发布，minor）

### 新增

- 【web】新增 G16 Web 后端骨架（config 两级参数/应用工厂/统一错误结构），可启动服务
- 【web】按 REST 契约补齐 mock 端点全表（system/settings/candidates/queues/pending/executions/history）
- 【web】新增 SSE broker 与 mock 推流（快照恢复/Last-Event-ID 重放/心跳）
- 【web】新增前端空壳工程（Vite+Vue3+TS、明暗双主题 tokens、六页视图与组件）
- 【web】新增 SSE 消费骨架与设置面板（流式解析/退避重连/Last-Event-ID/快照重建/设置读写）
- 【core】新增 SQLite 存储层（连接治理/顺序迁移/五域 DAL）与设置持久化，mock 内存设置退役
- 【core】新增输入分块解析器（§2.7 五段切块/Hill 记法/多步与坏文件容错）与文件名自然序（字母先于数字）
- 【core】新增 HQ Gateway 抽象与 CLI 实现（--output-mode json 子进程封装、轮询差分事件）及 HQ 进程管理（journal 落位/复用/看门狗重启/脱离父进程组）
- 【core】新增候选领域服务（导入逐文件校验与整批原子/inputs/<id> 副本与剔除/title 实时解析/重复导入 duplicate 提示）
- 【core】新增待执行席位领域服务（尾部追加/全量原子重排/整席移除退候选与队列回退/成员移除规则/容量满员与上限挤出/窗口锁定语义）
- 【api】候选/待执行端点真实化（multipart 导入/列表 title 注入/预览/剔除/行内提交/席位重排与移除/上限调小挤出），引入 python-multipart
- 【core】新增派发引擎（执行序列展开/并行窗口推进/哈希跳过/Link0 补齐与 GB→MiB 换算/声明资源停等不越位/run/<id>/ 物化与 g16 环境构建/终态映射与队列失败分流）及 FakeGateway、fake g16 夹具
- 【core】新增执行监控（psutil 进程树采样：cwd+启动时间双重校验定位、CPU 差值/RSS 汇总、2s 节流与峰值累计）、停滞状态机（翻转才推/冷启动宽限/时长累计，仅提示不终止）与手动停止真实化（stop→cancel→归因 manually_stopped）
- 【core】新增运行中增量解析（tail run/<id>/input.log 位点续传、优化步/SCF 迭代窄域识别、1s 合并窗口、execution.progress 事件与停滞基准喂入），fake g16 输出对齐金标准行式
- 【core】新增终态文件管线与历史端点真实化（formchk 转 fchk 失败不阻断、failed 保全快照入 protected/ 落库 chk_snapshot、手动清理仅删 succeeded 超期顶层 chk/rwf、历史列表/详情/输入输出/归档/重新排队/退回候选/清理统计）
- 【core】新增重启对账与引擎启动序列（§2.4 五场景：S1 接管与 started_at 回填、S2 终态幂等冻结、S3 重跑特征探测与 chk 保全重定向、S4 server 丢失外部中断、S5 重试不中途落历史；对账后发 system.snapshot；lifespan 挂载 HQ 进程管理与引擎线程，新增 G16WEB_ENGINE/G16WEB_HQ_BIN 启动级参数）
- 【core】SSE 事件总线真实化（事件唯一来源切领域事件总线、mock 推流剧本退役、序号 sse_seq 每事件短事务落库重启延续、fanout 按广播条数差量、system.snapshot 统一真实 store 载荷）
- 【rust】新增 HQ server 内嵌 axum HTTP 骨架（--http-port 默认关、GET /info，桥接任务复用 server 处理逻辑）
- 【rust】新增 HQ REST 端点集（jobs 提交/详情/批量/取消与 workers，复用 CLI 内部实现保证双路一致）
- 【rust】新增 GET /events SSE 事件桥接（四域事件单行 JSON 帧+15s 心跳，薄桥接不重放）
- 【core】新增 HttpGateway（HQ HTTP/SSE 桥接消费、断线重连）与 Gateway 工厂按可用性切换（G16WEB_HQ_HTTP_PORT，默认关）
- 【web】候选页真实化（文件/文件夹 multipart 导入与逐文件失败清单、自然序展示、来源徽标与归因注记、剔除二次确认；新增共享确认模态与前端自然序工具）
- 【web】只读预览真实化（分块卡按样板重排、Link0 缺失琥珀注记、parse_errors 逐条容错条、分子四格读数）
- 【web】行内提交流真实化（确认框完整输入限高滚动、Link0 缺失黄警含设置缺省值、满员 409 提示）
- 【web】待执行页真实化（拖拽重排/整席与成员移除二次确认/容量仪表超限示警/窗口边界与在途锁定态，pending.snapshot 驱动）
- 【web】执行中页真实化（通道卡 1Hz 节流读数、停滞琥珀灯行翻转与时长、停止 danger 二次确认）
- 【web】历史页真实化（输入/输出查看导出、重新排队与退回候选、独立归档页路由、清理统计回显、history.appended 驱动重拉）
- 【web】设置面板真实化（中性生效语义徽标、实际变更 on_restart 重启提示、席位上限调小挤出确认、范围提示）
- 【api】queues 端点真实化（队列创建/编辑/删除/提交切真实 queues/tasks/seats 存储与事件，整队占席走引擎派发路径，修复 mock 残留致 §7.1 第 10 条无法在真实栈成立）
- 【core】新增 HQ 连通性监控（引擎 tick 以 workers 列表探测 server 可达性，状态/在线数翻转才推 hq.status；system.snapshot 增 hq 字段供快照重建侧栏基线）
- 【web】侧栏 HQ 连接状态行真实化（hq.status 与快照 hq 字段驱动的三态 LED 与文案：已连接/未连接/未启用，替换 M0 静态占位）
- 【core】历史列表支持多排序（sort 参数：提交倒序默认/完成时间升降/文件名自然序升降），历史页工具条新增排序切换；取数端全量稳定排序后切片，跨页全局有序
- 【web】待执行页队列成员子表补全属性（队列内序号/任务 id/文件名/标题/资源声明含缺省补齐标记），契约 PendingSeat 及成员项同步扩字段（resources 提取为命名模式复用）
- 【docs】新增 M2 输入工程执行计划（WBS 四阶段/分块编辑与队列语义设计定稿/流程图三张/测试矩阵/提交序列/验收 DoD/风险预案）

### 变更

- 【web】区分待执行页容量仪表与席位行的视觉层级（仪表改内嵌读数槽、区间加分隔线）
- 【core】候选列表默认排序改为导入时间倒序（created_at 新批在上），同一秒导入的批内按文件名自然序；跨页全局有序机制不变
- 【web】历史页归档入口按钮文案「归档视图」改为「归档管理」
- 【web】设置页每个参数行布局互换：上方显示中文释义、下方小字注释显示参数名（含启动级只读参数）；范围与生效徽标保留
- 【web】调整前端字号阶梯整档上浮约 11%（2K 视口可读性：正文 13.5→15px 等七档同步），tokens/样板/设计文档三处同值，布局度量不变
- 【web】任务 id 展示全站统一三位零填充（候选/待执行/队列成员概览；padStart 只补齐不截断，≥1000 自然加宽），资源读数收敛为共享格式化函数
- 【web】提交确认框输入区读数改「完整输入」，括注实现语义（纯文本·含坐标）移回注释
- 【web】执行中页读数「WINDOW n」改「并行上限」（原英文代号随设置值变、语义歧义且与在跑/可用重复）
- 【web】执行中页按并行上限渲染槽位：在跑卡按执行 id 序占槽，空槽为虚线占位框（槽位号+横线+空闲），撤销整页空态；设计文档 §4.4/§4.5/页表同步
- 【docs】按裁决修订 M2 执行计划（新增提交前输入核验与错误码治理两项任务；编辑入口收窄为候选与失败回退队列；导入成队事件序列修正；验收与风险补强）
- 【docs】按 roadmap 一致性审查修复 M2 计划（依赖与提交归属补强、m0-plan 口径勘误登记、设计一致性补强；roadmap 回填错误码治理条目与 M1 托付项改期登记）
- 【docs】按一致性复审修复 M2 计划（提交响应规范化标记登记为第三处契约增量、C 阶段补「已自动规范化」注记承接全覆盖三条提交路径、目标段自动保存口径对齐、设计文档琥珀清单增补拼写警告注记、e2e 测试提交归属与引用勘误）

### 修复

- 【api】修正契约可空字段写法使 null 响应合法（finish_reason/cause 由 $ref+nullable 同级改为内联枚举含 null）
- 【web】对齐设置项契约命名与生效语义（10 项运行级 key/effect/range 修正并补 g16_root）
- 【web】修复 SSE 重放窗口下界与投递队满处理（超窗走快照重建、队满断连走恢复语义）
- 【web】补齐 mock 六页联演剧本（队列状态全流转、席位增减、派发、停滞告警置位/解除）
- 【web】修复前端快照重建残留与 Toast 命名规则（重建先清空旧态、队列成员取所属队列名并 15 字截断、消费 queue.status）
- 【web】移除历史抽屉遮罩硬编码色值（新增 --backdrop-dim 令牌并引用）
- 【docs】对齐设计文档与实现（--text-faint 实际色值、待执行页「在途」标记、SSE 剧本组织说明）
- 【web】修正演示种子污染真实设置库（get_state 不再自动写入 demo 参数，种子仅进引擎关闭的演示模式分支）
- 【rust】修复 HTTP 桥提交/取消后未 flush journal 致 kill -9 恢复丢任务（对齐 RPC 提交路径，消除 journal_flush_period 窗口丢失）
- 【core】修复重启对账 S3 判据：journal 恢复后 job 回退 waiting 即判重跑，不再误按 S1 接管
- 【core】补齐队列手动停止失败分流：未执行成员 skipped(queue_manually_stopped) 并整队回退
- 【web】对齐前端设计令牌与基础样式至 v2 设计规范（令牌值修正与补全、页面度量与缓动/字距令牌、基础接管清单、StateChip 两档响度、Noto Sans SC 自托管）
- 【web】修正 Link0 缺失指令名匹配与展示（后端 missing 为不带 % 前缀指令名，提交黄警缺省值回显此前永不命中）
- 【core】修正引擎启动序列 Gateway 工厂模块路径（误用同级相对导入致引擎开启即启动失败，补 select_gateway 两分支回归测试）
- 【core】修正 worker 资源记账单位与启动探测语义（sum mem 的 ResourceAmount 内部整数误当 MiB 致内存虚高一万倍、--cpus 1 违背启动探测语义致默认任务永久停等）
- 【web】提交确认框按文本读取 text/plain 完整输入（openapi-fetch 默认 JSON 解析抛错致确认框卡读取中、Link0 黄警不出现）
- 【core】兼容 worker cpus 自动探测的 list 序列化形状（原 range 闭区间解析误算 1 核，自动探测 worker 仍永久停等）
- 【core】修正 formchk 前置 chk 路径解析（对齐 g16 无扩展名 %Chk 自动追加 .chk 语义，此前 succeeded 任务 .fchk 一律缺失）
- 【core】修正执行监控双重校验基准（改取派发时刻，此前按轮询 started_at 过滤误杀真实 g16 进程树致监控读数与峰值恒零）
- 【core】S3 重跑判据补 server 重 spawn 确定性证据③（waiting 相位与进程证据可被启动对账时点错过致重跑误按接管、续跑资产无保全）
- 【core】g16 自洽环境随作业提交下发（GAUSS_* 全集经 Gateway env 传参贯通 CLI/HTTP 两实现，GAUSS_SCRDIR 强制 run/<执行id>/ 不再落到全局 scratch）
- 【web】SSE 解析器兼容 CRLF 行尾（此前前端从未真正处理过任何事件，读数/快照/Toast 全哑，页面仅靠 REST 轮询兜底）
- 【web】REST 基线轮询改合并语义（原整体覆盖卡片致 SSE 实时读数被周期性抹除）
- 【web】历史输入/输出查看按文本读取（text/plain 误按 JSON 解析致面板卡读取中）、停止模态重开清空残留错误
- 【core】席位重排放行锁定原位的等待区调整（原实现存在锁定席位即全量 409，窗口非空时等待区拖拽永不生效）
- 【core】S1 接管后监视器锚定改取 submitted_at（原以轮询 started_at 重锚致接管后进程树定位失败、读数全哑），locate 容差放宽至 30s
- 【docs】字号阶梯补 --text-2xs 档位并对齐可视化样板（纯拉丁微标签 10px 下限成 token，承载中文一律 --text-sm）
- 【web】六页硬编码字号收编 tokens 并修正中文微标签字号越限（4 处中文标签 10px 升 --text-sm，新增 --text-2xs 档承载纯拉丁微标签与刻度符号）
- 【web】声明空 favicon 消除控制台 404 噪声
- 【web】亮色主题 failed 徽标对比度达标（#c23a31 调至 #bd352b，新增 WCAG 对比度实测闸门）
- 【core】通道卡「已运行」恢复真实计时（elapsed_s 改取 now-started_at，此前硬编码 0 恒 0s）
- 【web】文件夹导入前端过滤受支持输入文件（.gjf/.com、跳过隐藏目录，过滤后为空提示且不发请求）
- 【web】待执行页等待区重排在窗口非空时生效（前端门控对齐后端锁定原位放行语义）
- 【api】候选导入响应契约补登 duplicate 字段并同步两侧生成物（前端去强转改走契约类型）
- 【web】中文微标签字号与字距全量整改（承载中文升 --text-sm、去 letter-spacing，StateChip/读数标签拆中文/拉丁两档）
- 【web】队列/历史/设置页视觉规范对齐（移除响应式残留、刷新改扫描线两态、行高对齐 40px、扫描线动效统一引用共用实现）
- 【web】挤出确认模态席位数改按实际可挤数计算（min(超限幅度, 未锁定席位数)，零挤出明示暂不挤出），替换按新旧上限差的虚高文案
- 【core】进度读数随快照恢复（executions_running 并入引擎已掌握的 progress）并在 S1 接管快进后补发一条 execution.progress，读数恢复不再受限于日志下一匹配行；截断重扫重置进度状态防陈值
- 【web】执行中页断连窗口读数降档并提示延迟（SSE 非 open 时 45% 降档+琥珀注记），快照重建改差量合并消除重建瞬间读数清空闪烁
- 【core】候选列表改为后端全局自然序排序后分页（切片前按 natural_key 稳定排序，跨页全局有序、并列保持 id 逆序）；前端废止页内排序并删除 naturalsort.ts 双实现
- 【web】修复设置保存后不实时生效：PUT /settings 触及待执行快照字段（席位上限/并行窗口）时无条件补发 pending.snapshot（原仅挤出席位场景发送），执行中页 WINDOW、待执行页 OCCUPIED 上限与侧栏灯排即时刷新，无需刷新页面
- 【web】前端消费 settings.updated 通知（脏计数驱动设置页重拉，多标签页同步；有未保存编辑时不覆盖输入）
- 【core】停滞告警阈值改为派发 tick 实时跟随设置（新任务生效，在跑不追溯；原引擎构造时固化、重启才生效）
- 【web】历史页废除 page_size=100 硬编码，省略参数由后端回落设置值（列表分页大小设置即时生效，与候选页同模式）
- 【web】修复 Link0 核数检测对 %nproc 早期同义形式与 %nprocshare 截断形式的误报（blocks 缺失判定与执行前缺省注入两处；检测取 %nproc 前缀超集，避免缺省注入与用户声明并存）
- 【web】Link0 核资源检测纳入 %CPU=proc-list（0,1,2 / 0-5 / 混合，绑定逻辑处理器语义）：视为已声明且不注入缺省 %NProcShared，记账核数 %nproc 优先、仅 %CPU 时按列表推导
- 【web】待执行页队列席位行去冗余（QUEUE 徽标旁不再重复 queue 字样），补展示队列名、成员数与提交时刻
- 【web】修复 GET /queues 回归契约（补 member_ids 聚合、last_failure 反序列化、SQLite 整数布尔还原），队列页真实数据下成员数列渲染崩溃
- 【web】修复测试运行污染工作区：SSOT models 再生比对改写临时目录（原原地再生自比较，每次 pytest 后 models.py 残留时间戳脏差异）
- 【web】修正候选页行内提交黄警文案与设计样板（「提交时」→「执行时」按默认值补齐，与派发/物化时补齐的实现时机一致）
