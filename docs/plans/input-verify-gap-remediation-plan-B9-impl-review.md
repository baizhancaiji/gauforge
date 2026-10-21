# B9 批次实现审查报告（G13 · 提交前核验预显、警告文案、堆叠限高与持久化复验）

> 审查对象：`git diff 78bef9fa..HEAD`（分支 g16-webui，HEAD `334ea301`，共 13 个提交）。
> 审查依据：[input-verify-gap-remediation-plan.md](input-verify-gap-remediation-plan.md)
> §2.16（方案与六条用户裁决①–⑥）、§3 批次表 B9 行、§3.1 B9 节点、§8.13（实施留痕）、
> §8.14（Link0 缺省补全收窄裁决留痕）；[openapi.yaml](../api/openapi.yaml)
> Candidate.warning_count 契约；前置审查报告
> [input-verify-gap-remediation-plan-B9-review.md](input-verify-gap-remediation-plan-B9-review.md)
> R1–R8 处置核对；AGENTS.md §6.1/§6.2/§6.3。
> 审查日期：2026-10-21。审查方法：AGENTS §6.2 四查独立复核——全部闸门由审查人
> 独立复跑并记录实测输出，留痕数字逐位重算（含 /tmp worktree 对 161ed8ab 先行红
> 与 78bef9fa 基线数的归一复现），接口级冒烟在隔离实例实测，前端视觉项经
> playwright（chromium headless，1480×940，暗色主题）真实浏览器实测并逐项断言。
> 审查人：ZCode（GLM）。只审不改：除本报告外仓库零改动（工作树全程保持 clean）。

## 一、结论

**通过。** B9/G13 六条用户裁决①–⑥全部落地且有可复现实测背书；§8.14 Link0 收窄
实现与测试断言口径一致、duplicate 补全伪影确证消除；前置审查 R1–R8 逐条处置落实；
全部闸门独立复跑全绿，§8.13/§8.14 留痕数字逐位复现（872 passed 0 skipped、
先行红 4 failed/867 passed、基线 851、tokens 93/93+31/31）；契约先行与生成物
再生零 diff 实测证实。无 P0/P1/P2 问题；登记 4 项 P3（徽标列宽「固定 56px」在
auto 表格布局下实为下限、计划状态行留痕区间漏 §8.14、生成物 description 折行
空格伪影、submitted 态成员占位信息量）与 2 项本次审查未覆盖说明（队列直接提交
回执链路需引擎、G16 真机不在本批）。

| 级别 | 编号 | 摘要 | 位置 |
|---|---|---|---|
| P3 | I-1 | 徽标占位列「列宽固定」声明在表格 auto 布局下仅为下限：带「⚠ 13」徽标实测 67px、「⚠ 1」60px、全空态回落 56–60px；行级显隐无列移（隔离实验全列零差），但整表最后一个徽标消失时徽标列 −4～−11px 且后续列一次再分布 | `CandidatesView.vue:1009-1012`（`.warn-col{width:56px;min-width:56px}` 无 max-width、表格未用 `table-layout:fixed`） |
| P3 | I-2 | 计划头部状态行「验收留痕 §8.1–§8.13」未含 §8.14（Link0 收窄裁决及其实现 67a9f883/cf59112f 属本批收口内容），区间表述不精确（§8.14 自身有出口记录，check_plan_status 通过） | `input-verify-gap-remediation-plan.md:3` |
| P3 | I-3 | openapi `warning_count` description 用 `>-` 折叠标量，生成物出现词间空格伪影（「响应中 现算」「逐条现算 （file_warnings」）；再生零 diff 闸门下不可手改生成物，需从 YAML 源消除（改单行或 `|`） | `openapi.yaml:277-285` → `models.py:131-133`、`contract.ts:1035-1036` |
| P3 | I-4 | submitted（memberOnly）队列弹窗成员区逐个显示「成员输入预览不可用 — 无法核验」占位：preview 对 submitted 成员恒 404（端点守卫），该态下核验预显本质不可得，占位重复呈现信息量有限（§8.13 ⑨ 已登记为符合端点守卫语义的预期行为，中性文案不误导；观察项备案） | `QueueEditorModal.vue:149-153,563-567` |

## 二、审查依据与范围

- **依据**：上文所列四项（计划文档 §2.16/§3/§3.1/§8.13/§8.14、openapi 契约、
  B9-review 报告 R1–R8、AGENTS.md 审查条款）。
- **对象**：`git diff 78bef9fa..HEAD`，23 文件 +718/−119。
- **范围证实**：`git status` 工作树 clean；`git diff --stat` 改动面与 13 个提交
  声称一致；**crates/ 零改动**（`git diff --stat 78bef9fa..HEAD -- crates/` 输出
  为空）；前置审查报告 B9-review 文件本体不在改动集内（未被实施过程改写）。
- **报告落盘**：`docs/plans/input-verify-gap-remediation-plan-B9-impl-review.md`
  （调用方指定路径；原名 `-B9-review.md` 已被计划文档前置审查占用，本报告另名
  `-B9-impl-review.md`，未覆盖任何既有报告）。

## 三、功能完整性对照（§2.16 交付点逐项）

| 编号 | 计划条目（§2.16） | 实现位置 | 结论 |
|---|---|---|---|
| F1 | 裁决⑤·单任务确认框提交前预显：消费 openSubmit 已取回的 preview warnings、零警告零渲染 | `CandidatesView.vue:234,243,254`（submitPreviewWarnings 取自 preview 响应）、`:686-690`（预显区） | 已落地（浏览器实测：多警告候选动作前呈现 13 条，零警告候选零渲染 +「Link0 声明齐全」） |
| F2 | 裁决⑤·队列弹窗成员级预显：复用 loadLinkStates 既有并行取数路径扩展消费 warnings，不新增请求路径；创建态与编辑态；成员 preview 失败仅该成员占位 | `QueueEditorModal.vue:146-193`（同一 preview 响应并取 lines+warnings）、守卫放宽 `readonly||done`（`:149-153`）、占位 `:563-567` | 已落地（实测每成员恰一次 preview 请求 delta=3/3；创建态与编辑态双态实测各成员归属正确；404 成员仅该成员占位、其余不阻断） |
| F3 | 裁决①②·文案修订：导入条目自含形「⚠文件名: L行号 message」、汇总行「导入警告 N 条」、提交回执「⚠ L行号 message」、队列回执「⚠ 任务 #task_id: L行号 message」、行号一律 L 形、禁「—」统一分隔 | `CandidatesView.vue:515,531-534,687-688`、`QueueEditorModal.vue:497-502,569-571` | 已落地（浏览器实测 14 条全部命中 `^⚠[^:]+: L\d+ ` 正则；message 逐 kind 中文模板见 F4） |
| F4 | 裁决②·message 逐 kind 中文警告语模板清单 + 测试固化（kind 字样不得入 message） | `web/tests/test_warning_messages.py`（14 样例 / 12 kind 全集；`test_template_list_covers_kind_vocabulary` 强制词表同步）；标点随批修正 `keywords.py:236-239`（8fbd8491 空格）、`link0_rules.py:135`（e0dd03d5 全角括号） | 已落地（词表与 openapi Warning.kind 12 kind 逐一对上；断言含 CJK、无 kind 字样、模板短语） |
| F5 | 裁决④·全部警告展示区限高滚动，新令牌 + 样板同步 | `tokens.css:67`（--warn-list-max-height: 200px）+ `m0-ui-preview.html:40` 同步；`.import-warnings/.submit-warns/.q-warns/.q-mem-warns/.be-warns` 均限高+overflow | 已落地（实测 14 条 scrollHeight 505 / clientHeight 198，滚动可达末条无吞没；check_tokens 93/93+31/31） |
| F6 | 裁决③⑥·warning_count 现算不落库：列表切片后现算（R4 约束）、单条 GET、退回候选同口径；不可读回落 0 | `services/candidates.py:71-84`（现算单点）、`routers/candidates.py:97-103`（切片后循环）、`:152-156`（单条 GET）、`services/history.py:236-237`（退回候选） | 已落地（API 实测三路径数值一致；删输入副本后回落 0 不 500；契约必填经 schema 校验转红→转绿） |
| F7 | 裁决③·徽标占位列（文件名与标题之间、无表头授权偏离、N=0 空置、aria/title 语义） | `CandidatesView.vue:566`（空 th）、`:595-604`（N>0 徽标 + title/aria） | 已落地（浏览器实测 multi2 ⚠13 / spell ⚠1 / clean·q3 空置；aria-label 含文件名与条数；行级显隐无列移见问题 I-1） |
| F8 | 裁决⑥·分块编辑保存即复验：BlockEditor 逐块 warnings 详情（kind→块映射）+ saved 事件刷新徽标与详情 | `BlockEditor.vue:32`（defineEmits saved）、`:42-58`（KIND_SECTION 12 kind 映射）、`:225`（emit）、`:289,316,341,366,402`（五区渲染）；宿主 `CandidatesView.vue:649` `@saved="load"` | 已落地（实测 route 修复保存后徽标即时消退、详情即时消退、重开提交框零渲染） |
| F9 | 裁决⑥·「再次保存即清空」+ done 后成员预显清空（防规范化改写后滞后） | `QueueEditorModal.vue:425-427`（save 清空 submitWarnings）、`:456-459`（submitNow 后重拉 loadLinkStates，done 态清空成员区） | 已落地（代码核对；弹窗重开回执清空经浏览器实测；done 链路需引擎，见「未覆盖项」） |
| F10 | 裁决⑥·缺省补全前后 file_warnings 内容集等价断言（多重集 + 行号平移口径，R1 修正后口径） | `web/tests/test_parse_blocks.py:869-951`（三例：双注入平移 +2 / 齐全全等 / 值域外边界例） | 已落地（随全量测试独立复跑通过） |
| F11 | 契约动作：Candidate 增 warning_count 必填、现算不落库 description、openapi 先行 + 生成物零 diff；kind 词表不变 | `openapi.yaml:255,277-285`、`models.py:131-134`、`contract.ts:1035-1036` | 已落地（审查人独立重跑 gen_models.py + gen:types 后 `git status/diff` 均空——再生零 diff 实测证实；词表 12 kind 未变） |
| F12 | §8.14 收窄：resolve_link0 仅指令行缺失时注入；值非法不注入、记账回落缺省、defaulted 语义改写 | `engine/workspace.py:75-76,85-118`（按行存在性判定）+ docstring 改写（`:52-64`） | 已落地（五态测试 `test_dispatch_engine.py:539-561`：%mem=2W/abc/空值、%nprocshared=zz、%cpu=x-y 均无注入且记账安全回落；duplicate 伪影消除经 `test_parse_blocks.py:927-951` 断言 + 本审查 API 实测双重证实） |
| F13 | §8.14 测试先行红 → 转绿（cf59112f → 67a9f883） | `test_dispatch_engine.py:142-147`（%CPU=x 行存在即不注入，defaulted=False 改写） | 已落地（提交序列与 diff 证实） |
| F14 | CHANGELOG migration 登记（值域外声明行为变更） | `CHANGELOG.jsonl` unreleased「收窄 Link0 缺省补全…」条目 migration 字段（对照 §8.14 文字逐句一致） | 已落地（gen_changelog_md --check 通过） |

**前置审查 R1–R8 处置核对（逐条）**：

- **R1**：§2.16 等价性断言已改写为「(kind, keyword, message, suggestion) 多重集
  逐条一致 + 注入 N 行时块后行号整体 +N」（plan:1114-1121）；§8.14 收窄后值域外
  破例自构造消除、§2.12 对应条目改写为「已消除」（plan §2.12 表末行）。最终口径
  与实现、测试三方一致。**已落实。**
- **R2**：「新增成员时预显/新增成员即预显」表述已全文删除（grep 零命中），改为
  「编辑弹窗（创建态与编辑态）打开时」。**已落实。**
- **R3**：现状段改写 + 方案显式指认复用 loadLinkStates（plan:1100-1103）；实现
  确为同一响应扩展消费，实测每成员恰一次请求。**已落实。**
- **R4**：方案 4 补「分页切片后的当前页条目现算」约束（plan:1151-1152）；实现
  `routers/candidates.py:97-103` 循环在切片后。**已落实。**
- **R5**：裁决③与规范化复验的边界说明已补（plan:1145-1148「属复验机制的自然
  结果、不属用户主动消除路径」）。**已落实。**
- **R6**：Candidate schema description 补现算口径 + required 定名（openapi.yaml:255,
  277-285）。**已落实。**
- **R7**：验收标准补「成员 preview 取回失败仅该成员占位提示」实测项（plan:1184）。
  **已落实（本审查浏览器实测通过）。**
- **R8**：方案 4 补 BlockEditor 保存完成事件通路声明（plan:1160-1161）；实现
  `BlockEditor.vue:32,225` + 宿主 `CandidatesView.vue:649`。**已落实。**

## 四、问题清单

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| I-1 | P3 | 视觉 UI/UX | `CandidatesView.vue:1009-1012` | 「列宽固定 56px」在 `table-layout:auto` 下仅为下限：实测带「⚠ 13」徽标列宽 67px、「⚠ 1」60px、全空态回落 56–60px。行级显隐无列移（隔离实验：修复一行徽标前后 8 列 x+width 全差为零）；整表最后一个徽标消失时徽标列 −4px（⚠13 场景 −11px）、后续列一次再分布 ≤3.1px。验收主场景（导入出现徽标/修复消退）不受影响 | 如需严格定值：表格启用 `table-layout:fixed` 或 `.warn-col` 补 `max-width:56px`（配合徽标不换行已有）；或计划/留痕口径将「列宽固定」改述为「列宽有界（56px 下限）、行级显隐无列移」 |
| I-2 | P3 | 可维护性（文档） | `input-verify-gap-remediation-plan.md:3` | 状态行「验收留痕 §8.1–§8.13」漏 §8.14——Link0 收窄裁决、实现（67a9f883）与测试（cf59112f）属本批收口内容，留痕却在 §8.14 | 状态行区间改「§8.1–§8.14」（随下轮文档提交顺带修正） |
| I-3 | P3 | 可维护性 | `openapi.yaml:277-285` | `warning_count` description 采用 `>-` 折叠标量，YAML 折行转空格使生成物出现「响应中 现算」「逐条现算 （file_warnings」等词间空格伪影（`models.py:131-133`、`contract.ts:1035-1036`）；生成物受再生零 diff 闸门约束不可手改 | 将该 description 改为单行长句或 `|` 字面块，再生成一次生成物（顺带可修） |
| I-4 | P3 | 视觉 UI/UX（备案观察） | `QueueEditorModal.vue:149-153,563-567` | submitted（memberOnly）队列弹窗每成员恒显「成员输入预览不可用 — 无法核验」占位（preview 对 submitted 成员端点守卫 404），该态核验预显本质不可得，逐成员重复占位信息量有限。§8.13 ⑨ 已登记为符合端点守卫语义的预期行为，中性文案不误导，不算缺陷 | 可选优化：memberOnly 态下以一句汇总说明替代逐成员占位，或将占位文案区分「已提交不可核验」与「解析失败」两种成因 |

**显式核对未构成问题的疑点**：

- 占位文案「成员输入预览不可用 — 无法核验」使用「—」分隔：裁决①范围系警告条目
  文案（警告族内分隔一律冒号或括注），该文案为中性占位提示、非警告条目，且与
  既有 `linkTitle` 文案（`QueueEditorModal.vue:134`「…形态锁定）— 接续勾选不可用」）
  同形，判不属裁决①违反面。
- `BlockEditor.KIND_SECTION` 新 kind 缺席即不渲染：已有「词表扩容须同步本表」注释
  与 `test_template_list_covers_kind_vocabulary` 强制断言双保险，扩容时测试先红，
  属已声明的提醒点而非静默缺陷。
- `warning_count` 读 `default_inputs_dir() / str(candidate_id)`：candidate_id 由
  FastAPI `int` 路径参数约束，无路径穿越面；`read_bytes().decode("utf-8")` 符合
  AGENTS §10 显式编码约定；前端全部 `{{ }}` 插值渲染、无 `v-html`，无注入面。
- `resolve_link0` 收窄后消费方数值安全：行存在但值全部不可解析时 `nproc_value/
  mem_value` 回落 `int(nproc_default)/float(mem_gb_default)`（`workspace.py:98-118`），
  dispatcher 直接 `int(value)` 不会遇 None/非数。

## 五、测试与闸门实测（全部由审查人独立执行）

| 闸门 | 命令 | 实测输出 | 判定 |
|---|---|---|---|
| 全量测试 | `uv run pytest -q` | **872 passed, 0 skipped**（2 warnings 为 starlette/anyio 弃用告警，与本批无关），118.58s | 与 §8.14 留痕「872 passed 0 skipped」逐位一致 |
| e2e 静默跳过排查 | `ls target/release/hq` + `uv run pytest web/tests/test_e2e_fake_g16.py -v` | hq 存在（17,957,480 B ELF，10-15 22:52）；3 用例 PASSED（pipeline/http_gateway/skip_failed_continues） | hq 在位，无静默跳过，通过数无虚高 |
| 进度校验 | `uv run python scripts/validate_progress.py` | `OK`，exit 0 | 通过 |
| 设计令牌 | `uv run python scripts/check_tokens.py` | 暗色 93/93、明亮 31/31，逐变量 diff 为空 | 与 §8.13 记载一致 |
| 对比度 | `uv run python scripts/check_contrast.py` | 全组合 ≥ 4.5:1（最低 failed 徽标 4.71:1） | 通过 |
| CHANGELOG 一致性 | `uv run python scripts/gen_changelog_md.py --check` | `OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致` | 通过 |
| 计划状态 | `uv run python scripts/check_plan_status.py` | `OK — 10 份计划文档状态均已回填为终态` | 通过 |
| 前端离线构建 | `bash scripts/audit_frontend_offline.sh` | `dist 零外链资源引用（豁免 5 组白名单前缀）`，exit 0 | 通过 |
| 生成物零 diff | 重跑 `gen_models.py` + `gen:types` 后 `git status --porcelain` / `git diff --stat` | 两者输出均为空 | F11「openapi 先行 + 再生零 diff」实证 |

**留痕数字归一复现（不采信自述、worktree 独立重演）**：

- 先行红（§8.13 记「4 failed / 867 passed」）：`git worktree add /tmp/b9-red-wt
  161ed8ab` 后全量 pytest → **4 failed**（test_candidate_warning_count_chain、
  test_candidate_carries_warning_count、test_candidate_detail_against_schema、
  test_return_candidate_from_failed——与 §8.13 记载的 4 例及「return-candidate 201
  同形态被必填转红波及」完全一致）+ 865 passed + 2 skipped；skip 原因为「仓库构建
  hq 缺失」（worktree 无 `target/`，系环境差异非代码状态），挂 `target` 符号链接后
  定向复跑 e2e 3 passed → 归一口径 **865+2=867 passed**，与留痕逐位一致。
- 入口基线（§8.13 记「基线 851 + 新增 20」）：worktree @78bef9fa
  `pytest --collect-only -q` → **851 collected**；HEAD 872 = 851 + B9 测试 20 +
  收窄断言 1（test_link0_invalid_value_not_injected），数字自洽。

## 六、端到端与视觉审查记录

**API 冒烟**（隔离实例 `G16WEB_HOME=/tmp/g16web-b9rev`、`G16WEB_ENGINE=0`、
127.0.0.1:8300，dev§2.2 方式起停，用毕清理）：

- 导入 13 警告文件（3×link0_value_invalid、2×link0_directive_unknown、
  link0_line_too_long、link0_directive_duplicate、title_forbidden_char、
  molecule_multiple_charge_pairs、atom_label_unknown、molecule_unterminated、
  keyword_spell、route_duplicate）→ 列表 `warning_count=13`、单条 GET `13`、
  preview warnings 13 条全文件绝对行号；零警告文件两路径均 `0`。
- 分块修复链：route→title→charge_mult→link0 四次保存，保存响应 warnings 逐级
  7→5→4→3→1（复验即时）；molecule 节恒只读系既有 M2 语义（`INVALID_REQUEST`
  「molecule 节不可编辑」），atom_label_warning 不可经 UI 消除——非本批引入。
- 输入副本不可读：删 `inputs/<id>` 后单条 GET 200 且 `warning_count=0`（回落不 500）。
- 删除：DELETE 204，列表随行消失。
- 退回候选（第三路径）：向隔离实例注入 failed 终态执行后
  `POST /history/{id}/return-candidate` → **201 响应含 `warning_count=1`**（与
  新候选实际警告数一致）。
- 提交规范化复验：含 EOF 警告候选提交 → `normalized=true`，回执 warnings
  **13→12**（molecule_unterminated 随补空行自然消退，§2.16④ 边界说明的活例）。
- 既有阻断语义不回归：% 行置于 route 后 → 422「Link 0 命令必须位于 route 节之前」。

**浏览器实测**（playwright chromium headless 1480×940、暗色主题、HEAD 构建产物
v3.3.0-112-g334ea3，13 项断言脚本 + 目检截图，产物已清理）：

1. 导入四文件：汇总行「导入警告 14 条」逐字命中；14 条自含条目全部匹配
   `^⚠[^:]+: L\d+ `；清单限高 200px + overflow auto（505/198），滚动可达末条
   无吞没/裁切。
2. 徽标占位列：multi2「⚠ 13」、spell「⚠ 1」、clean/q3 空置；aria-label/title
   语义齐全；空 th 占位列在位（无表头授权偏离可见）；隔离实验证实行级徽标消退
   全列 x+width 零位移（问题 I-1 限于全空态回落）。
3. 单任务确认框预显（裁决⑤）：多警告候选打开即见 13 条「⚠ L行号 …」（动作发生
   前）、条目格式全对、预显区限高 200px；零警告候选零渲染 +「Link0 声明齐全」；
   修复后重开预显零渲染 + 徽标空置。
4. 队列弹窗创建态 + 编辑态（裁决⑤）：创建态 3 成员各自归属（13/1/占位）、404
   成员仅该成员占位「成员输入预览不可用 — 无法核验」、console 仅预期 404、每成员
   恰一次 preview 请求（delta=3）；编辑态（队列页双击 b9edit）成员级 1/4 条归属
   正确，截图目检布局无溢出/遮挡。
5. 分块修复复验（裁决⑥）：route 修复保存后徽标即时消退、详情即时消退、重开
   提交框零渲染。
6. 删除带徽标候选随行消失；重复导入同文件两次各自「⚠ 1」互不覆盖。
7. 弹窗重开无上一动作回执（回执清空）。
8. 截图目检：琥珀色一致、mono 行形、无令牌外硬编码色值（check_tokens 佐证）。

**本次审查未覆盖项**（如实登记，不以单测/脚本替代后声称通过）：

- 队列「直接提交」动作触发的回执呈现与 done 后成员区清空：需引擎链路
  （ENGINE=0 下未走通该动作），仅代码核对（`QueueEditorModal.vue:456-459,497-502`）
  与重开清空实测；§8.13 ⑤ 的实施者 playwright 留痕不作为本审查结论采信。
- G16 真机（Rev. C.01）端到端：不在 B9 验收范围，本审查未执行。

## 七、总体结论

**通过**——无保留条件。四项 P3 均为文案/样式精度与文档表述层面的改进项，
不阻断 3.4.0 发布流程；建议随下轮文档或样式提交顺带处置（I-2/I-3 成本极低，
I-1 可二选一：加约束或改口径留痕）。B1–B9 全部收口的状态与 progress.json
「进入 3.4.0 发布流程」登记相符，发布冻结按 §5.2 由用户启动。
