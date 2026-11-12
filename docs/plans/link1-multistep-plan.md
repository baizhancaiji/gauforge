# G16 多步任务（--Link1--）支持 · 实施计划

> 状态：**待执行**
> 排期口径：单人实施，任务粒度 = 一个可审查提交；规模标记 S（≤半天）/
> M（1–1.5 天）/ L（2 天+）。净工期估算 **35–54 人日**（批次表 §4 批头区间
> 合计，上限按半天取整；S/M/L 为量级标记，批头区间为含各项实现与直接测试的
> 工期估算），
> 提交与发布口径：每个工作项一个功能提交（实现与直接测试同属该功能变更，
> 文档批次单独提交）；发布前按 AGENTS.md §5.2 跑 `check_plan_status.py`。
> 版本与依赖口径：本计划为新增功能（`added` → minor），版本号随发布按
> changelog-spec §1.7 口径核定；B4/B12 的 `resolve_chk` 改造依赖
> chk-materialize-fix-plan T4（`resolve_chk` 由 `finalize.py` 迁入
> `engine/workspace.py`）先行完成，以迁移后形态开工（该计划目标 3.5.0，
> 本计划不先于 3.5.0 落地）；实施期间各 patch 发布按显式计划路径跑
> `check_plan_status.py`，B13 回填终态后纳入无参全量扫描。
> 实施顺序：契约文档（B1）→ 输入侧（B2–B6）→ 监控（B7–B9）→ 结果与产物
> （B10–B12）→ 收尾（B13）。

## 1. 定稿语义基线（实测闭合，实施依据）

以下语义为本计划的**实施前提**，均已实机定谳（证据见 §8 附录；例外：S1
段数上限为产品设定值，见表内标注）；实施中不得按未确权的假设另行设计。

| # | 语义 | 实施含义 |
|---|---|---|
| S1 | 单文件多段：`--Link1--` 行分隔 job 步，**其前恰好一个空行**；每段独立 Link0（可省）/route/title/电荷多重度/分子说明/附加节结构；段数上限 **10**（产品设定值，非 §8 实测结论；B1 契约定稿时补出处核对或复核该值）| 解析器按段循环；段间空行规约成文；超限即拒（短路形态见 §3.1 `stage_violations`）|
| S2 | 段边界日志**双形态**：形态一（CVL/h2o 等历史日志）`(Enter …/l1.exe)` + `Link1:  Proceeding to internal job step number N.`；形态二（q5 金标准对，受控跑）Link 1 每段重新 exec，第 k 次 `Entering Link 1 = …l1.exe PID= <新PID>` | 监控锚点双形态兼容：段 k 开始 = `Proceeding` 行**或**第 k 次 `Entering Link 1`（二者取先）；段 k 完成 = 第 k 条 `Normal termination`；中止 = `Error termination` |
| S3 | **Link0 不跨段继承**：段未声明 `%chk`/`%nprocshared`/`%mem` 回落默认/无 chk（实测段 2 全部 `Leave Link` 回落 800MB 默认）；读 chk 类关键字（`Geom=AllCheck`、`Geom=Checkpoint`、`Guess=Read/TCheck`、`SCRF=Check` 等，封闭词表由 B1 对照官方手册页定稿）在**无可读 chk 源**（无 `%chk` 且无 `%oldchk`）的段**直接失败**（l101 `NtrErr FileIO` → Error termination 非零退出）；逐段覆盖（`%oldchk`+`%chk`）正常；`%oldchk` 单独声明亦为可读源（Link 0 复制 oldchk 至当前 chk——未声明 `%chk` 时为 scratch `Gau-<pid>.chk`——该段正常完成且不向作业管理路径落盘 chk） | 三条衍生规则：①校验阻断（B3，多步文件任意段含段 1；单步文件维持现状不阻断）②缺省注入逐段化（B4 前置）③formchk 目标 = 末个声明 `%chk` 的段（B4 前置选择，B12 复核） |
| S4 | cclib 切段口径：按 `Normal termination` 切边界，段 k>1 前拼原始文件头（首条 route echo 前全部行，必须含 `Gaussian 16:` 版本行否则 ccopen 返回 None；仅当段切片不含版本行时才拼，避免拼接样本双 banner）；逐段解析数据守恒、段级 `state`（`parsed|degraded`，§3.5）独立；日志含非 UTF-8 二进制字节 | 结果解析切段实现口径；读写一律 `errors="replace"` |
| S5 | 停滞阈值默认 10 分钟（`config.py:43`）；真实日志存在最长 22.9 分钟无进度信号窗口（既有风险，非多步新增） | 段开始锚点触发时同步 `note_progress` 复位停滞计时 |
| S6 | 执行模型：多步文件 = 一次 `g16 input.gjf` 进程 = HQ 一个 job = 一条执行记录 | dispatcher 调度循环、队列、席位、对账流程**零改动**；仅资源记账（`resolve_link0` 返回值）与产物选择（`resolve_chk`/formchk）按段扩展（B4 前置，B12 复核）；其余改动集中在 parse/monitor/results/契约/前端 |

金标准样本（`~/g16/tests/`，既有目录约定）：
- `q5_water_spfreq.gjf/.out`——正确用法金标准对（段 2 同名重声明 `%chk` +
  AllCheck/TCheck + freq，2 次 Normal termination，频率
  1684.5331/3840.9525/3970.1611）；
- `q5_water_nochk_crash.gjf/.out`——段 2 缺 `%chk` 声明崩溃反例对；
- `q5_water_oldchk_only.gjf/.out`——`%oldchk` 单独声明正例对（段 2 仅
  `%oldchk`，相对路径；2 次 Normal termination，频率与金标准一致）。

## 2. 明确不做（边界，防蔓延）

本计划为多步支持的**完整实现**（导入→分段编辑→提交→分阶段监控→分段结果→
产物→收尾一次闭环，B1–B13），无后续分期；下列为永久边界或视真实需求另议项，
不预留后续计划：

- **拆段任务链方案**：不另建拆分器（用户手动拆任务入队即等价）；
- 多步文件内含 `%chk=@task:`/`@exec:` 符号引用：**一律拒绝**（严于单任务席位
  口径——`validate_single_seat_input` 现状拒 @task:、@exec: 经三点校验放行，
  多步段级 chk 归属使符号引用语义不可控，多步对 @exec: 一并收紧；
  dependencies.py:129-147）；
- 组合流精修与多步互斥：候选入选拒绝多步候选（后端 = `POST
  /workflows/conformer-refinement` 前置检查 422，前端按候选列表 `multistep`
  标记禁选，§3.4），精修生成器不生成多步文件；
- 队列成员行实时多段读数（维持现状）；
- 段级 cube 派生物：`input.fchk` 只对应末个声明 `%chk` 的段；非 fchk 归属段
  （含末段未声明时回落到前一个声明段之后的段）轨道页只读、不生成 cube；
  cube 的 MO 上界按该 fchk 所属段的 orbitals 校验，不按聚合值；
- 工作区 `.out` 分析（`POST /analysis/workspace-out`）维持聚合，不提供段
  切换；段级分析只覆盖历史执行的分析域端点；
- 段级终态落库：进度维持引擎内存态 + 快照透出（段级历史回看依赖真实需求，
  届时另议，本计划不预留）；
- `kind=crest` 任务不适用多步（crest 输入为 xyz，无段概念）。

## 3. 契约与数据设计（定稿接口，B1 落文档）

### 3.1 解析输出结构（`parse_input` 返回，preview/提交响应同构）

- **单步文件（段数 1）**：既有结构不变——`{"blocks": {...}, "parse_errors": [],
  "warnings": []}`，另加 `"stages": null`、`"stage_violations": []`。
- **多步文件（段数 ≥2）**：`{"blocks": null, "stages": [...], "parse_errors": [],
  "warnings": [], "stage_violations": [...]}`；`stages[]` 元素：
  `{"stage_index": 1起, "line_span": [start, end), "blocks": {...},
  "parse_errors": [...], "warnings": [...]}`，行号一律**全文件绝对行号**
  （警告按行号即可映射段，前端无需额外字段即可路由）。`line_span` 为
  左闭右开，`end` 不含 `--Link1--` 行；分隔行不归属任何段，落在分隔行的
  警告（如 `stage_separator_blank`）由前端显示在相邻段交界。多步时顶层
  `warnings` 为各段 warnings 的扁平并集（同一行号口径），`stages[].warnings`
  保留分段视图；顶层 `parse_errors` 只承载全文件级解析错误（退化形态空段
  结构错误等；段数超限走 `stage_violations`），段级
  错误一律在 `stages[].parse_errors`，导入/提交/预览消费点必须逐段遍历，
  不得只看顶层；段数超限不走 `parse_errors`（走 `stage_violations`，见下）。
- **`stage_violations[]`（段级阻断违规载体，B2/B3 产出、导入/提交核验消费）**：
  两形态顶层均带，单步恒为空数组（单步维持现状不阻断）。元素为
  `{"code", "stage", "line", "message"}`——`stage` 1 起、`line` 全文件绝对
  行号；文件级违规（段数超限）两者为 null，且解析短路：`blocks=null`、
  `stages=null`，不产分段视图。该载体仅导入/提交核验消费（按 `code` 映射
  §3.2 的 reason/422），不透出 `InputPreview` 契约——阻断违规文件不会成为
  候选；`parse_errors` 的三键结构（`section`/`line`/`message`）保持不变
  （金标准套件契约断言 `test_golden_suite_no_crash_and_contract_shape`
  依赖；该测试的 `blocks` 键集断言由 B2 同批适配出单步/多步/超限短路
  三分支）。
- **契约同构约束**：`InputPreview.blocks` 改为可选/可空（单步必带、多步为
  null），新增可选 `stages[]`（单步为 null）；`required` 仅保留
  `candidate_id`/`filename`。B1 以 `oneOf` 或 optional+nullable 精确表达，
  并新增运行时契约用例拒绝「两者皆空/皆满」（OpenAPI 3.0.3 下 `$ref` 与
  `nullable` 不得同级，按既有契约约束内联）。
- `multistep` 过渡口径：B2 起保留为派生键（= `stages is not None`），导入/提交
  两处既有判定（candidates.py:108、verify.py:46）不动、维持 §7.1 渐进放行，
  随 B4 解卡与两处产生点一并移除。

### 3.2 错误码 / reason 词表

| 词 | 层 | 语义 |
|---|---|---|
| `INPUT_MULTISTEP_UNSUPPORTED` | 导入 reason + 提交核验 422 | **退役**：两处产生点（导入 reason、提交核验兜底）随 B4 解卡移除；deprecated 标注落 openapi.yaml 文件头错误码清单与导入 reason 词表（见下），保留一个版本后移除；前端为 message 透显、无错误码映射，无需前端联动 |
| `INPUT_STAGE_LIMIT_EXCEEDED` | 解析层载体 `stage_violations`（§3.1 超限短路）→ 导入 reason + 提交 422 | 段数 > 10（上限值设定口径见 §1 S1 标注） |
| `INPUT_STAGE_CHK_REQUIRED` | 解析层载体 `stage_violations`（含 stage/line，§3.1）→ 导入 reason + 提交 422 | 多步文件任一段（含段 1）路由含读 chk 类关键字而该段**无可读 chk 源**（未声明 `%chk` 且未声明 `%oldchk`；`%chk`/`%oldchk` 任一单独声明即为可读源；S3 崩溃形态，词表 = B1 封闭词表，details 携带 stage/line，映射口径见下条）；单步文件维持现状不阻断 |
| 警告 kind 新词 | 非阻断 | `stage_link0_default`（段 k≥2 未声明 `%nprocshared`/`%mem`：G16 原生将回落 1 核/800MB，执行时按首段有效值补齐；警告行号 = 该段段首行 `line_span[0]`，纳入 §3.1 全文件绝对行号口径；段 1 缺席由该段 `blocks.link0.missing`（即 `stages[0].blocks.link0.missing`）与缺省注入通道承载）、`stage_chk_absent`（段未声明 `%chk`：本段不落盘 chk；仅多步生效、任意段注记——单步维持现状，受「单步回归零变化」约束）、`stage_separator_blank`（`--Link1--` 前不是恰好一个空行：0 空行或 ≥2 空行；仅多步生效，提交通道由规范化补足/收拢，导入通道不阻断） |

- 两枚新码均为双载体，解析层统一由 §3.1 `stage_violations` 承载（`parse_errors`
  三键结构不变）：提交路径为顶层 `code`（422，`details` 可选携带 `stage`/`line`），
  导入路径只进 `details.errors[].reason`（422 外壳仍为 `VALIDATION_FAILED`，
  同既有导入词表）。导入 `details.errors[]` 条目新增**可选** `stage`（1 起，
  段级违规为该段序号）与 `line`（全文件绝对行号；文件级违规如段数超限两者
  缺省），既有 `filename`/`reason`/`message`/`parse_errors` 字段不变——产生点
  `candidates.py` `_validate_one` 由 `stage_violations` 映射（candidates.py:108
  既有 multistep 判定随 B4 反转时一并接此映射），B1 契约同步补该条目可选
  字段与用例。
- 登记同步点：`docs/api/openapi.yaml` 两处「35 码」注释（:16 文件头错误码
  全集、:222 `ErrorBody.code` 描述）同步为 37 码；
  `web/tests/test_error_codes.py` 的 `CONTRACT_CODES`、:22「35 码」注释与
  :4 docstring「29 码」残留必须同步增补，否则 B4 新增 `err()` 调用会被
  `test_impl_codes_subset_of_contract` 判越界。
- `INPUT_MULTISTEP_UNSUPPORTED` 的 deprecated 标注同时落文件头错误码清单
  （:39-40）与导入 reason 词表（:83 一带）；保留一个版本后连同
  `CONTRACT_CODES` 条目一并移除。

### 3.3 运行时契约（SSE/REST）

- `execution.progress` 载荷新增**可选** `stage: {"index": 1起, "count": N}`；
  `opt_step`/`scf_cycle`/`scf_round`/`converged`/`last_line` 保持「当前段内读数」
  语义（`scf_round` 跟随段重置）；段切换归位口径：`opt_step=null`（不预置
  伪造读数，待该段首条 `Step number` 行出现后置 1）、`scf_cycle=null`、
  `scf_round=null`（该段首条 `Cycle 1` 行出现后自 1 起算）、`converged=null`；
  随 B7 同步 sse.md 事件枚举表
  `execution.progress` 行载荷字段列；`system.snapshot` 附带的 progress 同构。
- 多步执行的每条 `execution.progress` 均携带 `stage`（不只段切换那一条），
  因为前端 `events.ts` 以整对象替换 `progress`——缺省字段会被清空，只有
  每条事件都带 `stage` 才能保证段号不丢。
- **不新增 SSE 事件类型**：段迁移由 `stage.index` 变化自然表达，前端据 diff
  驱动步进器过渡。
- REST：`GET /executions/{id}` 的 `progress` schema 同步加 `stage`（可选）。

### 3.4 编辑契约

- `GET /candidates/{id}/preview`：单步返回既有 `blocks`；多步返回 `stages[]`（3.1）。
- `PUT /candidates/{id}/blocks/{section}` 新增 `stage` query 参数（默认 1；
  `stage` 超出段数范围或单步文件携带 `stage≠1` 一律 422，防静默写错段）——
  后端 `save_block` 按段定位 span 重组，**向后兼容**。
- 候选列表项新增可选 `multistep: bool`（组合流禁选与列表提示的数据源；
  B1 契约 / B4 后端 / B5 前端）。

### 3.5 `analysis.json`（单文件分段数组，result_ref 不变）

顶层新增 `stages[]`（每段：`stage_index`/route 摘录/`state=parsed|degraded`/
`degraded_reason`，以及与顶层同构的五键 `result`/`convergence`/
`frequencies`/`orbitals`/`thermochemistry`，逐段由独立 `ccopen` 产出）；
单步文件写 `"stages": null`，前端按无分段处理。顶层另增 `"fchk_stage":
1起 | null`——`input.fchk` 所属段（末个声明 `%chk` 的段；全部未声明时
为 null），供 B11 只在该段开放 cube。既有嵌套结构（五键及其下 `summary`、
`energy_series` 等子键）逐字段保留向后兼容，分析面板渐进迁移；字段形状
以 B10 实施时 `results.py` 现产 dict 为准逐字段搬迁，不另立 schema。

**分段读数出口**：analysis 域四端点（`GET /history/{id}/analysis`、
`/history/{id}/analysis/convergence`、`/history/{id}/analysis/frequencies`、
`/history/{id}/analysis/orbitals`）新增
可选查询参数 `stage`（1 起；缺省 = 既有聚合形，向后兼容）。`stage` 合法且
该段存在时返回该段对应键；越界/单步文件携带 `stage≠1` 一律 422
`VALIDATION_FAILED`；该段块不可用时维持既有 `ANALYSIS_PARSE_FAILED` 语义。
这样 B11 的段切换复用既有端点与 schema，不新增路径/事件。多步执行的分析页
默认打开**末段**（前端显式传末段序号 = `stages.length`），避免把不同几何/
方法的 SCF 序列画成一条曲线；缺省参数仍返回聚合形，供旧客户端兼容——聚合形
由整文件单解析单元产出（Q1：跨段静默聚合），**不保证跨段语义**（两段均含
频率时频率序列翻倍等），前端与文档不得将其宣传为跨段总量口径。

## 4. 批次与工作项（提交粒度 = 一个可审查提交）

### L0 契约文档（1–1.5 人日）

| # | 工作项 | 涉及文件 | 规模 | 验收判据 |
|---|---|---|---|---|
| B1 | 契约 diff：`InputPreview` +`stages[]`/`blocks` 语义（§3.1 契约同构约束）、`Execution.progress` +`stage`、候选列表项 +`multistep` 标记（§3.4）、错误码三词表（§3.2；含 35→37 码与 `test_error_codes` 同步）、`Warning.kind` 词表说明扩容（12→15，§3.2 三新 kind；description 级词表非 enum，生成物零影响）、读 chk 类关键字封闭词表定稿（逐词附官方手册页出处；对照清单覆盖隐含读 chk 族：`Opt=Restart`、`IRC=Restart/Read`、`Freq=ReadFC/ReadFCHT`、`Polar=Check`、`Guess=Check` 等。S3/B3 校验依据）、`PUT blocks` +`stage` 参数（越界 422）、analysis 域四端点 +`stage` 查询参数（§3.5，越界 422）、`analysis.json` 分段数组 + `fchk_stage` 注记（落 walkthrough.md，内部形态不写入 OpenAPI schema）；sse.md 事件枚举表 `execution.progress` 行载荷字段列同步；契约生成物随本批入库（`web/scripts/gen_models.py` 与 `npm run gen:types` 重跑） | `docs/api/openapi.yaml`、`docs/api/sse.md`、`docs/api/walkthrough.md`（M0 拒绝决议行改判）、`web/src/models/models.py`（重生成）、`web/frontend/src/api/contract.ts`（重生成）、`web/tests/test_error_codes.py`、`web/tests/test_contract_rest.py` | M | `test_openapi_ssot`/`test_contract_sse`/`test_contract_rest`/`test_error_codes` 全绿，`Warning.kind` 词表与 §3.2 一致；`web/scripts/gen_models.py` 与 `npm run gen:types` 重跑零 diff；`INPUT_MULTISTEP_UNSUPPORTED` 带 deprecated 标注；封闭词表成文（逐词附出处）；候选列表 `multistep` 标记、PUT `stage` 与 analysis `stage` 越界 422 成文；`InputPreview` 单步/多步两形态契约用例通过（拒绝两者皆空/皆满）；导入 `details.errors[]` 条目可选 `stage`/`line` 字段成文并有契约用例（§3.2 映射口径） |

### L1 输入侧放行（19–28 人日）

| # | 工作项 | 涉及文件 | 规模 | 验收判据 |
|---|---|---|---|---|
| B2 | `parse_input` 分段循环（按 `--Link1--` 切段，识别沿用现状 `strip().casefold()` 口径，每段跑既有五节状态机）；`scan_spans`/`reassemble`/`verify_and_normalize` 段参数化；`multistep` 保留为 `stages` 派生键（§3.1 过渡口径）；段间空行规约一次成文（`--Link1--` 前规约恰好一空行——0 空行补足、≥2 空行收拢，经 `verify_and_normalize` 写回、结构掩码自证守卫；解析通道对非恰好一空行只记 `stage_separator_blank` 非阻断警告，导入不拒；QST2 双空行例外仅段内有效、段交界一律按段间规约，组合表随本项定稿）；段上限 10 校验（超限短路：`blocks=null`/`stages=null`，顶层 `stage_violations` 携带 `INPUT_STAGE_LIMIT_EXCEEDED`，通道拒绝随 B4 贯通）；退化形态（文件以 `--Link1--` 开头、连续分隔行、尾部分隔行后无内容）为空段结构错误，记顶层 `parse_errors`（通道拒绝：提交 422、导入 `INPUT_PARSE_FAILED` reason，随 B4 贯通）；单步文件 round-trip 字节零变化（解析输出仅按 §3.1 增删键） | `web/src/parse/blocks.py`、`web/tests/test_parse_blocks.py`（金标准套件同批适配） | L | 金标准单步样本（`~/g16/tests/com/*.com`）round-trip 零变化（结构掩码自证）；`q5_water_spfreq.gjf` 解析为 2 段、全部行号为全文件绝对行号；0 空行/≥2 空行多步样本解析产 `stage_separator_blank` 非阻断警告、`verify_and_normalize` 规范化写回（本项验收止于解析/规范化单测——导入与提交放行随 B4 验收，§7.1 渐进放行）；超 10 段样本解析短路（`stage_violations` 携带 `INPUT_STAGE_LIMIT_EXCEEDED`，通道拒绝随 B4 验收）；退化形态样本顶层 `parse_errors` 判空段结构错误（通道拒绝行为随 B4 验收）；`test_parse_blocks` 全绿——金标准套件同批适配（单步分支维持 `blocks` 键集断言、多步分支断言 `stages` 结构与全文件绝对行号、超限短路分支断言 `stage_violations`，`parse_errors` 三键断言不变）+ 新增段级用例 |
| B3 | 逐段校验编排：keywords/link0_rules/section_ordering 按 `line_offset` 逐段调用；跨段规则（§3.2）：读 chk 关键字且无可读 chk 源（无 `%chk` 且无 `%oldchk`）阻断（`INPUT_STAGE_CHK_REQUIRED`，按 B1 封闭词表；多步文件段 1 同样适用）、`stage_link0_default`/`stage_chk_absent` 注记、段内 `%chk` 重复沿用既有 kind；三新 kind 中文 message 模板随本批产实现（message 不含 kind 字样） | `web/src/parse/keywords.py`、`link0_rules.py`、新增 `stage_rules.py`（或并入 blocks.py）、`web/src/parse/blocks.py`（`parse_input` 段级校验编排接入点与 `stage_violations` 产出）、`web/tests/test_warning_messages.py`（`KIND_VOCABULARY` 与 `CASES` 同步扩容） | M | 崩溃反例 `q5_water_nochk_crash.gjf` 解析即产 `stage_violations` 阻断条目（`INPUT_STAGE_CHK_REQUIRED`，含 stage/line）；`%oldchk` 单独声明不被误拒；金标准对零阻断错误、零意外告警——段 2 仅产 `stage_link0_default`（其仅声明 `%chk`，未声明 `%nprocshared`/`%mem`，属 §3.2 预期告警）；封闭词表逐项有解析用例；`test_warning_messages` 全绿（三新 kind 登记且模板齐备、覆盖断言过）；拼写/重复/子选项三类警告逐段行号为全文件绝对行号 |
| B4 | 解卡 + 派发前置：导入 reason 反转（多步合法；仅段数超限、读 chk 缺声明、逐段解析错误拒）；`resolve_link0` 先改为逐段扫描 + 未声明段按首段有效值补齐（段 1 亦未声明则取配置默认；段无 Link0 块时注入行置于段首，`--Link1--` 分隔空行后、route 行前）+ 跨段取最大值（dispatcher 容量检查/核账口径），`resolve_chk` 先改为末个声明 `%chk` 的段（B12 只做复核与真实 G16 验收）——这两项必须先于多步提交放行落地；`verify_and_store` 移除 multistep 422 与 `multistep` 派生键（§3.1）→ stages 校验贯通 + 规范化写回；`validate_queue_members`/`validate_single_seat_input` 对多步内 `@task:`/`@exec:` 引用拒绝（`parse_link0_refs` 由仅扫段 1 Link0 区扩为逐段 Link0 区扫描——每段前导 `%` 区，跨段引用一并拒；非全文扫描：route 后误置的 `%` 行已由解析判为解析错误，不得在此命中造成误拒）；`save_block` +`stage` 参数（越界 422，§3.4）；preview 返回 `stages[]`；候选列表项 +`multistep` 标记（§3.4）；`blocks=null` 消费点段感知/null 安全（`pending._parse_extra`、candidates `resolve_title`/`warning_count`（多步汇总 `stages[].warnings`）/导入响应警告（多步扁平化逐段）、`routers/candidates.py` preview 路由、`verify.py` 规范化自证与 warnings、`save_block` round-trip——多步 title 取段 1、警告逐段绝对行号、自证按目标段 blocks 比较且其余段字节不变）；组合流候选入选守卫（`POST /workflows/conformer-refinement` 前置检查——现有「分子说明节无坐标」422 不兜住：`_extract_molecule_block` 对多步仍取到段 1 坐标，`parse_input(...)["blocks"]["molecule"]["formula"]`（workflows.py:161）在 B2 使 blocks 为 null 后将 500；本项在取坐标前显式拒绝多步候选 422 `WORKFLOW_STATE_INVALID` 并补用例，§2 边界）；重新排队多步 = 整文件原样重跑；断点续跑多步 = 不适用（B2 后多步 `blocks=null`，`_route_kind`（resume.py:71）经空 route 兜底返回 None → preview/confirm 按 `unknown_kind` ineligible，引导走重新排队），不做段级 `Opt=Restart` 注入、也不注入 `%oldchk` | `web/src/services/candidates.py`、`pending.py`、`workflows.py`、`verify.py`、`dependencies.py`、`routers/candidates.py`、`web/src/engine/workspace.py`（resolve_link0、resolve_chk——resolve_chk 由 chk-materialize-fix-plan T4 从 `finalize.py` 迁入本文件，本项改造基于迁移后形态，依赖见版本与依赖口径） | L | `test_candidates_import`/`test_submit_verify` 反转用例全绿；段 2 结构损坏时导入 `INPUT_PARSE_FAILED`、提交 422；三路径（行内/队列/重新排队）多步提交贯通；候选列表/席位成员视图多步 title 与警告正常（不 500）；多步候选组合流入选 422；多步重新排队整文件重跑贯通、多步断点续跑判定 ineligible（零注入）；调度记账 = max(各段有效值)、`input.fchk` 取末个声明段（前置验证）；金标准 round-trip 自证不变 |
| B5 | BlockEditor 开放分段编辑：段选择器 + 每段一套块卡 + 段级 PUT + `KIND_SECTION` 警告按段路由（含 `stage_link0_default`/`stage_chk_absent`/`stage_separator_blank` 三个新 kind，段间空行警告归段交界）；组合流多步候选禁选（按候选列表 `multistep` 标记）与提交确认 preview 消费点 `blocks=null` null 安全（`CandidatesView`/`QueueEditorModal`/`BlockEditor` 的 `blocks.link0` 直取等）；多步确认框聚合各段 `blocks.link0.missing` 与 `stage_link0_default` 警告，任一段缺失即黄警并给出该段有效补齐值，禁止「Link0 声明齐全」与警告并存；多步成员的接续勾选显示「多步任务不支持接续」；单步文件 UI 与现状一致 | `web/frontend/src/components/BlockEditor.vue`、`views/CandidatesView.vue`、`components/ComboFlowDialog.vue`、`components/QueueEditorModal.vue`（`api/contract.ts` 由 B1 重生成，本项只消费） | L | 金标准对多段编辑（逐段保存）后重解析结构不变；单步文件回归零变化；`npm run build`（vue-tsc）零错误；422 保存错误段定位正确；多步候选组合流禁选生效、提交确认弹窗黄警覆盖各段且无矛盾文案 |
| B6 | fake_g16 多段化 + 测试反转收口：`stages=N` 参数、双形态段边界行可切换、指定段失败；金标准对/反例对入测试基线 | `web/tests/fake_g16.py`、`test_parse_blocks.py`、`test_candidates_import.py`、`test_submit_verify.py`、`test_block_save.py`、`test_e2e_fake_g16.py`（§5 端到端多段链路扩在此文件） | M | 多段端到端（fake）导入→提交→执行贯通；调度记账 = 各段有效值最大值；两形态锚点用例齐备；全量 pytest 绿 |

### L2 监控阶段化（7–11 人日）

| # | 工作项 | 涉及文件 | 规模 | 验收判据 |
|---|---|---|---|---|
| B7 | progress 段边界检测（S2 双形态锚点正则；形态二为兼容冗余——单进程多步生产样本均形态一，见 §8 Q2）；状态结构 +`stage_index/stage_count`（`stage_count` 由输入解析按 execution 注入——`ProgressTracker` 为 dispatcher 单例，入 per-execution 状态；契约只暴露 `stage.index`/`stage.count`，段标签仅用于内部日志）；段切换按 §3.3 归位值表归位（守卫倒退）；段开始锚点触发 `note_progress` 复位停滞——段切换瞬间 `_facts` 至少返回 `stage`（即使其余读数均为 null），保证 dispatcher `_progress_step` 既有 `facts is not None → note_progress` 链路在段切换即触发，`engine/monitor.py` 接口零改动 | `web/src/engine/progress.py`、`dispatcher.py`（注入 stage_count） | M | `q5_water_spfreq.out` 基线（形态二锚点）：2 段计数正确、段 2 切换瞬间 `opt_step=null`、首条 `Step number` 行后为 1；`h2o_optfreq_popreg.out` 基线（形态一锚点）：段 1 `opt_step` 1→3、段 2 切换瞬间 null、首条 `Step number` 行后 1（3→null→1 跨段归位守卫不误报倒退）；`test_progress_parse` 全绿 + 段迁移/截断重扫跨段用例 + 仅 stage 事件（其余读数 null）亦复位停滞用例 |
| B8 | 事件与快照扩段字段（§3.3）：progress 载荷构造单源 `ProgressTracker._facts`，`execution.progress` +`stage`（多步每条事件均携带，非仅切换条）在 SSE 事件与 `system.snapshot` 附带进度两通道同时生效；crest 豁免路径不受影响 | `web/src/engine/progress.py`（`_facts`/状态结构） | S | `test_sse_events`/`test_snapshot_progress` 扩展用例全绿；多步连续多条 progress 的 `stage` 不丢；快照与事件 `stage` 一致；Last-Event-ID 重放帧带 `stage`；契约与 B1 文档一致 |
| B9 | 执行卡阶段步进器：新组件（段 n/N + 每段 StateChip 复用）；`events.ts` `execution.progress` 分支扩段字段；crest「无增量解析」占位模式沿用；文案分隔符沿用既有规范（长句 `—`、紧凑 `/`，禁圆点） | `web/frontend/src/components/StageStepper.vue`（新）、`views/ExecutionsView.vue`、`stores/events.ts` | M | fake 多段执行下步进器 1→2 自然过渡（无读数倒退闪烁）；单步执行 UI 回归不变；`audit_frontend_offline.sh` 过 |

### L3 结果与产物（8–13 人日）

| # | 工作项 | 涉及文件 | 规模 | 验收判据 |
|---|---|---|---|---|
| B10 | 结果分段解析（S4 口径）：`Normal termination` 切边界 + 原始头 banner 前缀逐段 `ccopen`（仅当段切片不含 `Gaussian 16:` 版本行时拼原始头，避免拼接样本双 banner）；`analysis.json` 分段数组 + `fchk_stage`（§3.5）；`errors="replace"`；多步切段解析共享总预算（默认 60s，耗尽后剩余段标 degraded，`degraded_reason` 记「解析预算耗尽」；单步维持既有 60s）；succeeded 执行内的段切片解析失败 → 该段 degraded（已得段保留；整体执行 failed 不进入 write_analysis）；analysis 域四端点接 `stage` 查询参数（§3.5；缺省聚合、越界 422）；workspace-out 维持聚合（忽略 `stages[]`，§2 边界） | `web/src/parse/results.py`、`finalize.py`（write_analysis）、`web/src/services/analysis.py`、`routers/analysis.py` | M | 切段对账逐位一致（Q1 基线）：`CVL_open.out` scf 27+1=28、freq 174；`h2o_optfreq_popreg.out` 段 1 opt scf 3 + 段 2 freq scf 1 = 4、freq 3；金标准 `q5_water_spfreq.out` 段 1 sp / 段 2 freq 归属正确（scf 1+1=2、freq 3）；`test_analysis_parse` 全绿 + 分段用例；`test_analysis_api` 覆盖 `stage=1/2` 返回对应段块、越界 422、缺省聚合不变；预算耗尽用例（剩余段 degraded、不阻塞派发 tick） |
| B11 | 分析面板分段适配：`AnalysisPanel` 段选择器按 `stage` 查询参数逐段拉取（§3.5），收敛曲线按所选段单段渲染（切换段即重取并清空旧图，不做跨段叠加）；degraded 段呈现；非 `fchk_stage` 段 cube 入口置灰（`analysis.json` 的 `fchk_stage`，§2/§3.5） | `web/frontend/src/components/analysis/*.vue` | M | 金标准数据下两段收敛曲线正确渲染；多步默认打开末段；段切换无串数据（逐段请求 `stage=N`）；degraded 段有明确标注；仅 `fchk_stage` 段 cube 可用，其余段置灰；离线闸门过 |
| B12 | 产物与资源复核：`resolve_chk` 的末个声明段选择与 `resolve_link0` 的逐段补齐/最大值已在 B4 前置落地（两函数均在 `engine/workspace.py`，迁移后形态，依赖见版本与依赖口径），本项复核 formchk 目标（末段未声明时回落前一个声明段，全部未声明回落 `input.chk` 既有语义；中间段 chk 原样保留）；`defaulted` 聚合口径 = 任一段注入缺省行即 true；`protect_transient`/`reap_scratch` 段失败口径复核（现状已保全全部顶层 .chk、只收 Gau-*/.rwf，段 k 失败时 k-1 已成功段 chk 已一并保全——本项补用例固化，不改行为）；cube `_nmo_upper` 按 `fchk_stage` 的 orbitals 校验（cube 请求本身不携带段，非归属段由前端置灰，§2 边界） | `web/src/engine/finalize.py`、`workspace.py`、`dispatcher.py`（记账）、`web/src/services/cube.py` | M | 金标准对执行后 `input.fchk` 含段 2 频率数据（1684.5331/3840.9525/3970.1611 可辨）——主判据，证明 fchk 取自末个声明 `%chk` 段的 chk；Total Energy = 末段 SCF Done 仅作一致性附验（两段 SCF Done 同值 -76.4088086134，能量等值无区分力）；仅真 G16 环境可验，归属 §6 真机冒烟；末段无 `%chk` 时回落前一个声明段、全无声明回落 `input.chk` 均有单测；每段均含注入后 Link0；记账值 = max(各段有效值)；默认值聚合口径有断言；段失败保全用例通过；cube 上界取 `fchk_stage` 所属段，非归属段按钮置灰；`test_finalize_*` 全绿 |
| B13 | 收尾：硬边界文档修订（`docs/project-intro.md:48`「功能硬边界」条，该文件须先随文档批次入库；`docs/specs/roadmap.md:314` 导入决策、`docs/specs/roadmap.md:297` 空行规约补注「0/≥2 空行导入告警、提交规范化」；`docs/api/walkthrough.md:88` M0 决议改判已于 B1 完成，本项复核；`docs/api/mapping.md:16`「确认框 Link0 黄色警告」行按 preview `stages[]` 形态改述）+ 走查/验收 + progress/CHANGELOG 同步 + 本计划状态行回填终态 | 文档 + `progress.json`、`CHANGELOG.jsonl` | M | 闸门全过（§6）；§6 总验收走查链（导入→分段预览→编辑→三路径提交→分段进度→分段分析→formchk 末段）全勾；发布流程可走通 |

## 5. 测试计划

- **反转用例**：`test_parse_blocks.py:80`（多段解析通过 + 段结构断言，
  `multistep` 派生键断言随派生保留）、
  `test_candidates_import.py:95`（导入放行 + 超限/缺声明拒）、
  `test_submit_verify.py:247`（提交贯通 + 词表新码）；三处原断言均为
  「拒绝」，反转时须重写断言体（段结构/行号/码位），不得只改期望值。
- **新增用例族**：段间空行规约（正反例 + QST2 × 段交界组合 + 0 空行导入
  只警告不拒）、段上限、封闭词表逐项（B1 词表 × 解析断言）、跨段阻断/注记词表（含 `%oldchk` 单独声明不被误拒）、多步解析总预算耗尽、确认框各段黄警聚合、
  progress 双形态锚点（形态二素材 = q5 金标准对；形态一素材 = CVL/h2o 日志）
  + 段迁移守卫（`h2o_optfreq_popreg.out` 段 1 `opt_step` 1→3、段 2 切换
  瞬间归位 null、首条 `Step number` 行后 1）＋每条多步 progress 均带
  `stage`＋仅 stage 事件（其余读数 null）亦复位停滞＋截断重扫跨段、崩溃形态（`q5_water_nochk_crash.out`：段 2
  `Error termination` 后 `stage` 停留 2、无段 2 完成锚点、执行 failed）、
  候选列表/席位成员视图多步 title 与警告（`blocks=null`
  消费点不 500）、退化形态（`--Link1--` 后无内容、连续 `--Link1--`、文件以 `--Link1--` 开头——均按空段结构错误拒：导入 `INPUT_PARSE_FAILED`、提交 422）、跨段同名 `%chk` 不误报 `link0_directive_duplicate`、
  多步内 `@task:`/`@exec:` 符号引用拒绝（含段 1 `%chk=@exec:` 收紧用例；`parse_link0_refs` 扩为逐段 Link0 区扫描后跨段引用命中；route 后误置 `%` 行不由该函数命中）、组合流多步候选拒绝、多步 requeue 整文件重跑、多步断点续跑判定
  ineligible（零注入）、PUT `stage` 与 analysis `stage` 越界 422、
  cclib 切段对账、resolve_chk 末段（含末段无声明回落）、每段注入、`fchk_stage`/非归属段 cube 置灰、`defaulted` 任一段注入即 true、
  契约三件套（openapi/sse/rest）+ `test_error_codes` 37 码 +
  `web/scripts/gen_models.py`/`npm run gen:types` 重跑零 diff。
- **端到端**：`test_e2e_fake_g16` 扩多段链路（fake `stages=2`，含段失败形态：
  段 2 失败 → 段 1 保全 + 执行 failed）。
- **金标准**：`q5_water_spfreq`（正确链路全绿；progress 形态二锚点素材——
  段边界 = 第 2 次 `Entering Link 1`，无 `Proceeding` 行）、`q5_water_nochk_crash`
  （导入即拒）、既有 CVL/h2o 多步日志（`CVL_open.out`/`h2o_optfreq_popreg.out`：
  解析与切段对账基线，兼 progress 形态一锚点素材——`Proceeding` 行 +
  段 1 单次 `Entering Link 1`）。

## 6. 闸门与总验收

- 每批次：`uv run pytest` + `uv run python scripts/validate_progress.py`；
  契约批次另跑 `web/scripts/gen_models.py` 与 `npm run gen:types` 重跑零 diff、
  `test_error_codes`；前端批次先跑 `npm run build`（vue-tsc 零错误），再跑
  `scripts/audit_frontend_offline.sh`（依赖 `dist`）、`check_tokens.py`、
  `check_contrast.py`；派发链路改动确认 `target/release/hq` 存在
  （AGENTS.md §6.1 第 4 条）。
- 总验收（B13）：导入 + 三路径提交（行内/队列/重新排队）多步贯通 + 金标准
  全链（导入→分段预览→编辑→提交→执行→分段进度→分段分析→formchk 末段）
  在 fake 环境 + 真实 G16 冒烟各走一遍；金标准类用例依赖仓库外样本
  （`~/g16/tests/`），既有门控分两类：环境变量 `G16WEB_G16_SAMPLES`
  （控制 test_analysis_parse/test_cube_api/test_analysis_api；其中
  test_cube_api 另硬依赖真机文件 `~/g16/cubegen` 可执行与
  `h2o_optfreq_popreg.fchk`——变量在位仍可因真机文件缺失 skip，留痕须
  注明具体缺项）与硬编码路径 skipif（test_parse_blocks/test_submit_verify/
  test_block_save/test_progress_parse），skip 须计数并留痕原因、不计入
  通过数；
  test_finalize_result.py 的样本依赖用例无门控，随 B10/B12 纳入门控；
  总验收前确认样本在位；发布前 `scripts/check_plan_status.py`
  全量扫描（本计划状态行已回填终态）。

## 7. 实施注意事项（已知坑，来自实测）

1. **渐进放行**：B2/B4 未全部落地前，多步文件维持提交拒绝——分段化半成品
   一旦进入编辑/规范化会按单 job 结构误重组（旧 `scan_spans` 地基）；
   B2 起 `multistep` 保留为 `stages` 派生键，导入/提交既有判定跨批可用（§3.1）。
   B4 解锁提交前，`resolve_link0`/`resolve_chk` 的段化必须先落地（§4 B4），
   否则多步执行按首段资源记账、formchk 取首段 chk；B4 与 B5 连续提交，
   两提交之间不得部署发布，中间态不得让用户打开多步候选预览。
2. **二进制字节**：样本日志含非 UTF-8 字节（CVL 0xbe 等），所有日志读写
   `errors="replace"`（progress.py 既有口径）。
3. **结构掩码自证**：段间规约改变会触发规范化自证（变化→500 拒落盘），
   规约表须在 B2 一次成文后再接自证，避免反复改口径；多步自证按
   `[stages[].blocks]` 逐段比较并忽略 `line_span`（分隔行/空行规约会移动
   行号），段数变化单独校验。
4. **行号口径**：全部校验产物保持全文件绝对行号——前端按行号映射段的
   设计依赖这一点，禁止换成段内相对行号。
5. **版本窗口**：`INPUT_MULTISTEP_UNSUPPORTED` deprecated 一个版本后再移除，
   期间导入 reason 与提交 422 文案不变（前端透显 message，无前端联动）。
6. **契约再生**：改 `openapi.yaml` 后必须重跑 `web/scripts/gen_models.py` 与
   `npm run gen:types` 并把产物随 B1 入库；否则 `test_openapi_ssot` 的
   模型零 diff 断言与前端类型不同步。`test_error_codes` 的
   `CONTRACT_CODES`、:22「35 码」注释与 :4「29 码」docstring 残留同批更新为 37 码。
7. **progress 整对象替换**：前端 `events.ts` 对 `execution.progress` 是整对象
   替换（`stores/events.ts` 现有分支），多步事件必须每条都带 `stage`；
   否则段切换那条之后的普通进度事件会把段号清空。
8. **q5 样本是拼接样本**：`q5_water_*` 的 .out 为逐段受控运行拼接（两份
   `Gaussian 16:` 头、PID 各异、无 `Proceeding`），只作形态二锚点与切段
   对账基线，不得当作单进程多步输出推广到其他日志形态。

## 8. 附录：实测证据（Q1–Q5 定谳摘要）

- **Q1**：整文件 cclib 单解析单元静默跨段聚合（不可作段级归属）；切段 +
  banner 前缀逐段解析全部成功且数据守恒（CVL scf 27+1=28、freq 174=174；
  h2o 3+1=4、3=3）；段切片缺 `Gaussian 16:` 版本行 → ccopen 返回 None。
- **Q2**：段边界信号 Windows/Linux 一致；`Entering Link 1 = …l1.exe PID=` 行
  7 种路径形态、尾部统一；出现频次与环境相关（双形态，S2）。形态分布：
  单进程多步生产样本（CVL/h2o）均呈形态一；q5 两对样本呈两次独立 g16 运行
  的拼接特征（`Gaussian 16:` 头 2 个、PID 各异、无 `Proceeding` 行），
  形态二锚点属兼容冗余，取先规则下不干扰形态一判定。
- **Q3**：停滞默认阈值 10 分钟；CVL 实测最长 22.9 分钟无进度信号窗口
  （既有风险）；缓解 = 段开始锚点触发 `note_progress` 复位。
- **Q4**：官方 link0 页：%-行是「控制多步文件特定 step 的唯一方式」；
  「未声明即继承」无官方措辞 → 由 Q5 实测定谳。
- **Q5**：四变体受控实验（本机 ES64L-G16RevC.01）：段 2 零 Link0 声明 →
  AllCheck 崩（相对/绝对路径均复现）；显式同名 `%chk`、`%oldchk`+`%chk`、
  `%oldchk` 单独声明三者均成功；`%oldchk` 单独声明（相对/绝对路径各一组）
  Link 0 日志为 `Copying data from "<oldchk>" to current chk file`，未声明
  `%chk` 时当前 chk 即 GAUSS_SCRDIR 下 scratch `Gau-<pid>.chk`（正常退出即
  清理）；段 2 频率 1684.5331/3840.9525/3970.1611 与金标准逐位一致，作业
  声明的 chk 不被改写（大小停留段 1 的 651264 字节，频率成功段为 663552；
  formchk 无频率数据、Total Energy 仍为段 1 单点能 -76.4088086）；故
  `%oldchk` 单独声明即为可读源，阻断条件维持「无 `%chk` 且无 `%oldchk`」，
  B3 不得误拒；段 2 未声明 `%mem` → 19 条 `Leave Link` 全部回落默认 800MB
  （日志 `MaxMem` 单位为 8 字节 words：金标准段 1 `MaxMem=134217728`
  = 1 GiB 与声明 `%mem=1gb` 一致、段 2 `MaxMem=104857600` = 800 MiB
  即回落值）；「金标准段 2 成功源于环境级默认 chk（`GAUSS_YDEF`/CWD
  `Default.Route`）」仅指受控原始样本；`q5_water_spfreq.gjf` 的段 2 显式
  声明 `%chk`，两者不要混读；formchk 产物 Total Energy 与末个声明 `%chk`
  的段的 SCF Done 位位一致。
  q5 样本 .out 均为逐段受控运行拼接产制（特征见 Q2）。探针脚本
  `/tmp/link1-probe/`、`/tmp/q5-g16-smoke/`（一次性，不入仓库），
  样本特征本身即测试基线。