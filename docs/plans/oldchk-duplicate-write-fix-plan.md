# 程序写入 %oldchk 重复累积修复（单槽位覆写） · 实施计划（目标 3.7.0）

> 状态：**待执行**
> 排期口径：单人实施，任务粒度=一个可审查提交；规模标记 S（≤半天）/ M（约一天）。
> 行号锚点为计划落盘时点（HEAD=5df5e779）实际行号前端**以符号名为准**。
> 执行纪律：文档一提交 → 实现三提交（后端续算单槽、后端回退剥离、前端 @task 单槽，
> 契约注记随各自实现提交）→ 实测验收留痕 → 进度同步，共五提交；每提交单类变更
> （AGENTS §5.1）。
> 报障定性：2026-11-13 报障（3.5.0）。用户裁定：用户明文 1 条 + 程序接续 1 条共存
> （L4 黄警）**可接受**；程序自身重复写入**不可接受**——本计划只消程序侧累积，
> 不动 L4 警告与用户明文行。
> 版本口径：本批全为 fix 与契约注记（无 added），按 changelog-spec §1.7 单独发布
> 应为 3.6.1；「目标 3.7.0」仅在与含 added 批次（chk-export、link1-multistep）并窗
> 发布时成立——T6 进度同步时按实际并窗情况落定版本号。

## 1. 缺陷分析与现行行为核查

### 1.1 现象（报障场景）

队列 A、B 两任务，B 源文件自写 `%oldchk=D1_DgpC_Monomer_Opt.chk`；队列编辑勾选
「接续前置 chk」→ 程序向 B 的 Link0 追加 `%oldchk=@task:170`，出现两条 `%oldchk`，
核验报 L4 `link0_directive_duplicate` 黄警（报障截图即此形态）。用户问：停止退回
候选后再次回退-重提，是否会第三次写入 `%oldchk`？

### 1.2 现行 `%oldchk` 写入路径全查（HEAD=5df5e779 实测核查）

| # | 路径 | 位置 | 是否写 %oldchk | 幂等性 |
|---|---|---|---|---|
| 1 | 队列编辑勾选「接续前置 chk」保存 | `QueueEditorModal.vue` `persistLinkChanges`（L210-233）→ PUT blocks/link0 | ✅ 追加 `@task:<前驱>` | **仅同前驱幂等**：`removeOldChkTaskRef`（L34）只删「打开时前驱」精确匹配行（L218，`initTarget` 口径）；写后内容同基线则跳写（L220） |
| 2 | 停止/移除席位/队列删除退回候选 | `pending.py:204,238`、`queues.py:69,220` → `tasks_repo.return_to_candidate`（L120） | ❌ 只改库（form/origin），不动输入 | — |
| 3 | 提交核验规范化 | `verify.verify_and_store` | ❌ 只规范化换行/空行原子写回 | — |
| 4 | 派发物化 | `materialize.materialize_chk`（L126） | ❌ 只重写 `run/<eid>/input.gjf` 执行副本（`@task:`→`dep-<X>.chk`、`@exec:`→`dep-exec-<eid>.chk`，L142/150），零残留、不回写候选输入 | — |
| 5 | 断点续算注入 | `resume._apply_injections`（L135-148） | ✅ 无条件 `lines.insert(i, "%oldchk=@exec:<eid>")` | ❌ 不清旧 `@exec` 行，续算链每级 +1 |
| 6 | 失败/skipped 成员移除新建候选 | `queues._dispatch_removed_member` → `candidates.copy_execution_input`（`queues.py:85` 唯一调用方） | ⚠️ 间接：以执行副本为源，副本含物化明文 `%oldchk=dep-*.chk` | ❌ 每轮 fail→退回→重提 +1 条明文 |
| 7 | 历史页「退回候选」（succeeded/failed/skipped 终态编辑再提交入口） | `history.return_candidate`（L211-238，内联 read_bytes→write_bytes 复制 L224/231，**不经** `copy_execution_input`） | ⚠️ 间接：以执行副本为源（缺执行副本回落任务输入副本，L220-222），含物化明文 `%oldchk=dep-*.chk` | ❌ 同 #6，回退→重提→再失败循环每轮 +1 条明文 |

### 1.3 对用户问题的结论

- **原样重复同一周期不累积**：停止退回走 `return_to_candidate`（沿用原 id、输入
  不动，路径 #2），重建队列同序同前驱再勾选 → remove+push 同内容同基线跳写 →
  **不会第三次写入**。两条 `%oldchk`（用户明文 + `@task:170`）与 L4 黄警每轮照旧，
  属已接受共存形态。
- **但「至多 2 条」不变式现行只是窄路径上的巧合**，三条变体会突破：
  - **β 前驱变化**：重建队列/重排/换前驱后，陈旧 `@task:` 引用因 `initTarget` 只认
    「打开时前驱」而永不被清——勾选→追加新引用成 3 条；取消勾选→`initTarget=null`
    使 L218 清除前置不成立，同样残留；
  - **γ 执行副本回退**：失败/停止成员移除（#6）与历史页退回候选（#7）走新 id
    候选（执行副本为源，含 `dep-*.chk` 明文）→ 再勾选接续成 3 条；
    fail→退回→重提循环每轮 +1；
  - **δ 续算链**：二级续跑源文本已含旧 `%oldchk=@exec:<eid1>`，再注入
    `@exec:<eid2>` 成 2 条程序行（叠加用户明文可至 3 条）。

### 1.4 根因

程序写入无「单槽位」不变式：三处注入/回填点（前端勾选追加、续算插入、物化明文
随执行副本回填候选——移除分流与历史退回候选两条入口）一律 append/insert，从不
覆写自身历史写入；幂等性只在前端「同前驱」窄路径上由 remove+push 巧合达成，
未成不变式。

## 2. 修正方案

### 2.0 目标不变式（单槽位语义）

| 槽位 | 文法 | 托管方 | 保证 |
|---|---|---|---|
| 用户槽 | `%oldchk=<普通路径>` | 用户 | 程序永不增删改（含执行副本回退路径） |
| @task 槽 | `%oldchk=@task:<n>` | 队列编辑勾选框 | Link0 至多 1 条，写入=整槽覆写 |
| @exec 槽 | `%oldchk=@exec(:<eid>)?` | 续算 | Link0 至多 1 条，写入=整槽覆写 |
| 物化明文 | `%oldchk=dep(-exec)?-<n>.chk` | 物化器（执行副本私有名法） | 不入候选：副本回退候选时剥离 |

L4 `link0_directive_duplicate` 黄警保留原样（`web/src/parse/link0_rules.py` 的
`link0_directive_duplicate` 分支，L129-135）——用户槽+程序槽 2 条共存的可见性
机制，报障场景即此形态，已裁定可接受。

### 2.1 （根治 β）：前端 @task 槽位整槽覆写

`web/frontend/src/components/QueueEditorModal.vue`：

- `removeOldChkTaskRef`（L34-38）→ `removeAllOldChkTaskRefs(lines)`：过滤**全部**
  `^%oldchk\s*=\s*@task:\d+$`（忽略大小写、trim 后匹配）行，不再按目标精确匹配；
  L18-19 模块注释与 L33 函数注释同步（「精确撤销勾选写入」→「单槽位整槽覆写」）。
- `persistLinkChanges`（L217-220）：dirty 成员一律先
  `lines = removeAllOldChkTaskRefs(lines)` 再按 `st.checked` 追加；删除 L218 的
  `initTarget` 前置条件。
- `loadLinkStates`（L179-186）：`checked` 判定复用既有导出 `oldChkTaskRefTargets`
  （现为死导出）改写为 `targets.includes(prevId)`；`LinkState.initTarget` 字段退役
  （全文件仅 L218 一处消费），接口注释（L102 一带）同步。
- 行为边界（D1 已采纳）：仅 dirty 成员产生写请求（不动勾选=零写，维持现状）；
  @task 槽为工作台托管槽位——`@task:` 文法在队列成员输入中本被 DAG 校验约束为
  队内上游引用（手写跨队引用建队即被拒，`dependencies.py` 校验兜底），故用户
  手写 `@task:` 引用只在用户操作该成员勾选框时才被整槽覆写接管。整槽覆写清除
  的是该成员全部 `@task:` 引用——指向非勾选写入目标（重排前的旧前驱、手写的
  非紧邻前序成员引用）的合法引用与其对应 DAG 依赖边一并消失、调度序随之变化
  （现行为为叠加保留）；D1 裁决仅覆盖「仅 dirty 产生写请求」的写请求时机，
  依赖边消失后果在此明示，不可达/成环仍由 DAG 校验兜底（§2.5）。

### 2.2 （根治 δ）：续算 @exec 槽位覆写

`web/src/services/resume.py` `_apply_injections`（L135-148）：Link0 区间 `[start, i)`
内先剥离匹配 `^%oldchk\s*=\s*@exec(?::\d+)?$`（忽略大小写、每行 trim 后匹配）
的行再于块尾插入本次 `%oldchk=@exec:<eid>`；明文 `%oldchk=` 行不动。剥离口径
取忽略大小写：@exec 槽与 @task 槽同为托管槽（§2.1 同口径），手写大写形（如
`%OldChk=@Exec:5`）经 blocks link0 编辑与单席位载体校验（`parse_link0_refs`
大小写不敏感解析）放行可合法入库，敏感匹配将残留旧行致 δ 不收敛；
`chained_ref`（`@task:` 注入前置拒绝，`_evaluate`）不变——@task 槽与 @exec 槽
无交集，互不触碰。模块 docstring
单点行分支的过时表述随本任务对齐（L23「Link0 追加 `%oldchk=@exec`」→ 恒
`%oldchk=@exec:<eid>`，与 L147-148 实际注入一致，opt/scf 两分支同形）。

### 2.3 （根治 γ）：执行副本回退剥离物化明文行（双路径单点收口）

dep 行剥离收敛在 `web/src/services/candidates.py` `copy_execution_input`
（L251-263，现返回 bytes）单点，两条回退路径共用：

- **剥离本体**：run 副本读取后逐行剥离匹配 `^%oldchk\s*=\s*dep(-exec)?-\d+\.chk$`
  的行（物化器私有名法，`web/src/engine/materialize.py:142,150` 两处产出）。
  匹配口径：每行 trim 后全行正则匹配、**大小写敏感**——物化器 `_rewrite_line`
  前缀 casefold 恒产出小写 head（`materialize.py:123`），空格变体由 `\s*` 覆盖，
  故敏感匹配足以覆盖全部物化产出；大写变体不匹配属有意为之，与托管槽剥离的
  忽略大小写口径（§2.1/§2.2）差异留痕于此：@task/@exec 槽由程序写入托管，须
  不问大小写全清（手写大写托管形态经编辑与载体校验放行可合法入库，敏感剥离
  将残留致 β/δ 不收敛），dep 名法是物化器私有产物恒小写，用户手写大写 dep
  形态按用户槽保护不剥离。撞名边界留痕：用户手写**小写** `%oldchk=dep-<n>.chk`
  （合法用户槽路径）与物化产物文法不可区分、会被一并剥离——极低概率边界，与
  chk-export 批「dep-* 名法不可一刀切过滤」教训同源，不另设防。任务输入副本
  回落分支同口径过筛；
- **快路径保字节**：无 dep 行命中时原 bytes 原样返回，不 decode/encode 往返
  （规避 BOM/CRLF 边差）——回落分支常态无 dep 行，「逐字节不变」判据经快路径
  天然成立；有命中时方按行剥离重组；
- **历史退回候选改经单点**：`web/src/services/history.py` `return_candidate`
  （L211-238）现内联 read_bytes→write_bytes 复制（L224/231），改为复用
  `copy_execution_input` 取数后落盘，删除内联复制逻辑——兑现 m2-plan §9 风险 5
  「不另写复制逻辑」约定（`copy_execution_input` docstring 已声明两路共用同一
  复制源语义，现状恰相悖）；源不可读的 `not_found("input")` 语义保留在
  `return_candidate` 侧（OSError 兜底不变）；
- **队列移除分流**（`queues._dispatch_removed_member` → `copy_execution_input`）
  零改动直接受益。

采纳理由：dep 文件落位 run 目录、随保留期清理，回退候选携带必然悬空；剥离后
γ 循环收敛为「用户明文 1 条 + @task 1 条」。

边界（γ×δ 交互）：续跑任务（route 含 `Opt=Restart`）的执行副本退回候选，剥离
`dep-exec-*` 行后重提交仍必败（Restart 无 chk 源可挂）；剥离前同样必败（dep
悬空）。剥离仅使失败形态更近真实，非回归，不另做兜底。

### 2.4 契约与文档

- `docs/api/openapi.yaml`：队列编辑「接续前置 chk」注记（L2228 一带，PUT blocks
  形态守卫）补单槽位语义；候选回退语义（L2802 一带，「退回候选」端点
  summary/description）补 dep 行剥离口径（历史退回候选与队列移除分流两路同
  口径）；续算注入注记（L719-732 一带，`ResumeInjection` description）补 @exec
  槽覆写语义，其中「非优化 SCF=Link0 追加 `%oldchk=@exec`」裸形表述一并对齐为
  恒 `@exec:<eid>`（与 resume.py 实际注入一致）；
- 生成链范围：本批只动 schema/端点级 description，二者不入 `gen_models.py`
  生成产物、Pydantic models 无需再生成（若实施触及 `ResumeInjection` 属性级
  description，则须重跑 `gen_models.py`，`test_openapi_ssot` 零 diff 闸门兜底）；
  `contract.ts` 按 chk-materialize 批先例随实现提交跑 `npm run gen:types`
  再生成。

### 2.5 明确不做（边界）

- 不在 PUT blocks/link0 后端对 `%oldchk` 条数设硬闸：候选分块编辑是自由编辑面，
  L4 黄警即可见性机制，报障场景的 2 条共存本就经此放行；
- 不改 L4 警告文案/触发口径；
- 不动 `%chk=@task:` 续用形态（无前端生成入口，物化器已覆盖；本计划只约束
  `%oldchk` 程序写入）；执行副本回退候选中悬空的 `%chk=dep-<X>.chk` 明文同不
  剥离（§2.3 剥离正则只匹配 `%oldchk` 槽，两槽不对称有意为之）——G16 对缺失
  `%chk` 宽容（目标文件不存在时自动新建）、对缺失 `%oldchk` 致命（无旧 chk
  可读即失败），剥离只收敛 `%oldchk` 槽；
- 不引入前端单测基建（vitest 等）：维持仓库现状，前端行为以浏览器实测脚本承载
  （同 drag-sort 计划先例）；
- 不做「陈旧引用 UI 预警」类增强：勾选保存即收敛，DAG 校验对不可达引用兜底报错
  （`dependencies.py:172` 直接前驱推导 + `validate_queue_members`）。

## 3. 任务分解与提交序列

| 任务 | 内容 | 提交 | 规模 |
|---|---|---|---|
| T1 | 本计划落盘并提交 | `docs(plan): 登记程序写入 %oldchk 重复累积修复计划` | S |
| T2 | §2.2 根治 δ（续算 @exec 槽位覆写）+ resume.py docstring L23 过时单点行表述对齐 + `test_resume.py` 用例（链式续跑恰 1 条 `@exec:<新eid>`；含明文 fixture：明文行保留、L4 重复黄警按「明文 + @exec」2 条共存形态照常产出；无明文 fixture：warnings 零 `%oldchk` 重复项）+ openapi 续算注记（含 SCF 裸形对齐） | `fix(web): 续算注入改为覆写旧 %oldchk=@exec 引用消除链式累积` | S |
| T3 | §2.3 根治 γ（执行副本回退剥离物化明文行，双路径单点收口：`copy_execution_input` 剥离 + `return_candidate` 改经该函数）+ 用例——`test_history_api.py` 既有 return-candidate 用例（`test_return_candidate_from_failed` 等内容源断言处）扩展 dep 剥离断言（执行副本源新建候选不含 `dep-*` 行、明文行保留）、新建 `test_candidates_copy.py` 直测（dep 行剥离、明文行保留、回落分支快路径逐字节不变）、`test_e2e_queue_lifecycle.py` 既有移除分流用例扩展 γ 链路闭环断言 + openapi 回退注记 | `fix(web): 执行副本回退候选剥离物化 dep 明文依赖行` | M |
| T4 | §2.1 根治 β（前端 @task 槽位整槽覆写）+ openapi 队列编辑注记 | `fix(frontend): 队列接续勾选改单槽覆写消除陈旧 %oldchk 累积` | M |
| T5 | 实测验收（§4 判据全绿，留痕落状态行；前置确认 `target/release/hq` 在位——AGENTS §6.1 第 4 条，缺失时 e2e 用例静默跳过、通过数虚高）；`uv run pytest`、`validate_progress.py` 与前端三闸门照跑 | （无独立提交，证据落 T6 状态行） | M |
| T6 | CHANGELOG.jsonl unreleased + progress.json 同步 + 状态行回填「已实施并验收」注明留痕位置 | `chore(progress): 同步 %oldchk 单槽覆写修复批次进度` | S |

## 4. 验收判据

浏览器实测（隔离实例口径同 drag-sort 计划 §1.2：独立 `G16WEB_HOME`、
`G16WEB_ENGINE=0`、playwright-core 直连 chromium headless）：

1. **报障场景重演**：候选 B 自写 `%oldchk=D1....chk` → 成队勾选接续保存 → GET
   input 断言恰 2 条 `%oldchk`（1 明文 + 1 `@task:<A>`）→ 提交 → 停止退回
   （本条退回=席位撤销/队列删除同 id 口径，§1.2 路径 #2；历史退回候选为新建
   id，归 #5/#6 判据）→ 重建队列（同序同前驱）：不动勾选保存断言零 PUT
   （network 断言）且仍恰 2 条；复勾同前驱保存断言仍恰 2 条；
2. **β 收敛**：重排使 B 前驱换为 C 后勾选保存 → 断言恰 1 条 `@task:<C>`、旧
   `@task:<A>` 被清、明文行原样、成员携带的 `%chk=@task:X` 续用形态行原样
   （剥离与覆写只及 `%oldchk` 槽，依赖边不受勾选动作影响）；
3. **取消勾选**：含陈旧 `@task:` 引用成员取消勾选保存 → 断言 @task 槽清空、
   明文行原样；
4. **δ 收敛**（pytest）：二级续跑文本恰 1 条 `%oldchk=@exec:<最新eid>`；含明文
   fixture 断言用户明文行保留、L4 `link0_directive_duplicate` 黄警按「明文 +
   @exec」2 条共存形态照常产出（§2.0 裁定可接受的共存形态）；无明文 fixture
   断言 warnings 零 `%oldchk` 重复项；
5. **γ 收敛**（pytest）：执行副本源回退候选不含 `dep-*` 行、明文行保留——历史
   退回候选（`test_history_api.py`）与 `copy_execution_input` 直测
   （`test_candidates_copy.py`）承载；任务副本回落分支快路径输出逐字节不变；
6. **γ 链路闭环**（pytest）：`test_e2e_queue_lifecycle.py` 既有移除分流用例扩展
   ——移除 failed 成员 → 新候选 → 复勾接续 → 提交 → 候选恰 2 条 `%oldchk`
   （1 明文 + 1 `@task`）、run 副本恰 1 条 dep 行（本轮物化产物），无跨轮累积；
7. 全量 `uv run pytest` 通过数不低于 3.6.0 冻结基线（893 passed，以当次全量
   为准）且当次全量 skipped 为 0；
8. 闸门：`validate_progress.py`、`audit_frontend_offline.sh`、`check_tokens.py`、
   `check_contrast.py`、`gen_changelog_md.py --check`、`check_plan_status.py`
   （发布前）全绿。
