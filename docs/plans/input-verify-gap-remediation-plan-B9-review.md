# B9/G13 计划文档审查报告

> 审查对象：[input-verify-gap-remediation-plan.md](input-verify-gap-remediation-plan.md)
> §2.16（G13）及其关联的 §2.15、§3 批次表 B9 行、§3.1 B9 节点、§4 契约动作。
> 审查日期：2026-10-21。审查基线：HEAD `6b992ff9` + 工作区未提交的 B8 审查
> P3-1 整改（两 Vue 文件「·」→「—」各 2 行，§8.12 已留痕）。
> 审查方法：按 AGENTS §6.2 精神对计划文档做合规性与合理性审查——文档中每条
> 涉及代码现状的表述均经 codegraph 定位并回读源码逐条核实（本文引用均带
> `file:line`），方案逐项评估技术可行性与风险点覆盖，未运行测试（文档审查，
> 无实现可测）。审查人：ZCode（GLM）。

## 一、结论

**有条件通过：方案主体成立、六条用户裁决①–⑥均有落点、现状描述绝大部分与代码一致；发现 2 项 P2（方案断言与实现矛盾、验收项指认了不存在的交互）与 6 项 P3，修正后方可进入实施。**

| 级别 | 编号 | 摘要 |
|---|---|---|
| P2 | R1 | 「缺省补全前后 `file_warnings` 逐条一致」等价性断言与 `resolve_link0` 行注入实现矛盾 |
| P2 | R2 | 「新增成员时预显/新增成员即预显」指认了当前 UI 不存在的交互，验收项不可测 |
| P3 | R3 | 现状「队列弹窗对成员不做任何预检」与代码不符；方案未指认复用既有取数路径，存在双请求风险 |
| P3 | R4 | 列表现算「页大小内解析成本」依赖「切片后计算」实现约束，方案未点名 |
| P3 | R5 | 裁决③「仅两条路径可消除」与「提交规范化改写后同径复验」字面矛盾，缺边界说明 |
| P3 | R6 | Candidate schema description 与现算 `warning_count` 的口径未登记 |
| P3 | R7 | 验收标准缺「成员 preview 取回失败占位提示」实测项 |
| P3 | R8 | 「保存后刷新列表徽标」依赖的前端事件通路不存在，方案未声明 |

## 二、事实核对

### 2.1 核对一致项（抽样全对，列举关键项）

| 文档表述（§2.16） | 核实结果 |
|---|---|
| 导入琥珀清单按文件聚合、条目「文件名 ⚠ 第 N 行 message」、汇总行「导入警告 N 条 — 非阻断，已入库」 | 一致（`CandidatesView.vue:525-534`；「—」形依赖工作区未提交的 P3-1 整改，HEAD 实装为「·」形，§8.12 已留痕，随下轮文档提交入库即可对齐） |
| 单任务提交注记「⚠ 提交警告 — 第 N 行 message」、重新打开提交确认框即清空 | 一致（`CandidatesView.vue:511`、`:240`） |
| 队列直接提交「⚠ 任务 #task_id — 第 N 行 message」、弹窗重开清空 | 一致（`QueueEditorModal.vue:477`、`:269-277`） |
| 「再次保存即清空」尚待实现 | 一致（`save()` 于 `QueueEditorModal.vue:404-409` 不清空 `submitWarnings`，仅 `submitNow()` `:438` 赋值） |
| 单任务确认框打开时已取回 `/candidates/{id}/preview` 但未消费 warnings | 一致（`openSubmit` `CandidatesView.vue:242-250` 仅取 `blocks.link0.missing`） |
| 预览与导入/提交/分块保存同走 `file_warnings` 全集单点、全文件绝对行号 | 一致（`routers/candidates.py:157-168`、`services/candidates.py:63-68`） |
| 提交核验在规范化后文本上计算 warnings 并写回存储 | 一致（`services/verify.py:44-65`） |
| 分块保存响应即新 InputPreview + warnings | 一致（`services/candidates.py:480-491`） |
| 候选列表行无警告状态 | 一致（`_candidate_view` `routers/candidates.py:54-58` 无 warnings 字段） |
| Link0 缺省经 `resolve_link0` 补全，`completed_text` 为 G16 实际执行文本 | 一致（`engine/workspace.py:49-100`，`materialize` `:105-114` 写 `run/<id>/input.gjf`） |
| 当前缺省值经设置校验恒为合法值 | 一致（`config.py:96-101`：`link0_default_nproc` min 1、`link0_default_mem_gb` min 1，注入行不产警告） |
| 缺失指令本身不产 warnings，仅中性「未声明 · 执行时将按默认值补齐」注记 | 一致（注记现存于 `CandidatesView.vue:269`、`BlockEditor.vue:268`；系既有豁免文案，不在 B9 文案修订面） |
| 重复导入同一文件新建条目、不覆盖既有条目 | 一致（`import_files` 对 duplicate 仍 `create_candidate` 并落盘，`services/candidates.py:160-166`） |
| `message` 产出点已以中文为主、无逐 kind 模板清单与断言 | 一致（`link0_rules.py:85-134`、`keywords.py:236/366/431`、`blocks.py:345-510` 抽样全中文；无文案断言测试） |
| Candidate 契约、gen_models + gen:types 再生闸门可行 | 一致（`openapi.yaml:252-276` 已有 `title`「响应中实时解析注入」先例可循；`web/scripts/gen_models.py` 与 `package.json` `gen:types` 均在） |
| 成员 preview 取回失败不阻断其余成员（有既有先例） | 一致（`loadLinkStates` 逐成员 `.catch(() => null)` → `available=false` 占位提示，`QueueEditorModal.vue:152-179`） |

### 2.2 事实偏差项

**R3（P3）现状「队列弹窗对成员不做任何预检」不实。**
`loadLinkStates`（`QueueEditorModal.vue:144-179`）在弹窗打开时（`:301` 调用）
已对每个成员并行 `GET /candidates/{id}/preview`，只是只消费
`blocks.link0.lines`（接续 chk 勾选初始化），不消费 `warnings`。§2.16 现状
应改为「队列弹窗打开时已并行拉取成员 preview 但仅消费 Link0 行，warnings
未消费」；方案 1「打开及新增成员时对每个成员并行取 preview」应显式指认与
`loadLinkStates` 的既有取数合并复用（如扩展其返回数据或并列消费同一响应），
否则按字面新写一条取数路径会造成同一弹窗每次打开每成员两次 preview 请求。

**R2（P2）「新增成员」交互不存在。**
队列弹窗模板（`QueueEditorModal.vue:480-539`）成员行仅有拖拽排序、接续勾选、
移除三类操作，无新增入口；`canSave` 注释明示「编辑态只减不增」（`:325-328`），
创建态成员来自打开前的候选选中集。§2.16 方案 1「打开及新增成员时对每个成员
并行取 preview」与验收标准「新增成员即预显」均指认了不存在的交互，后者按
字面不可测。需改写为与实际交互面一致（如「打开弹窗即预显（创建态与编辑态）」）；
若确需弹窗内加成员能力，须先立项该交互本身，不属于 G13 范围。

**R1（P2）等价性断言与 `resolve_link0` 实现矛盾。**
§2.16 方案 1：「存储文本核验与补全后核验的 warnings 结果集恒等——B9 以测试
断言固化该等价性（缺省补全前后 `file_warnings` 逐条一致）」。
`resolve_link0` 的补全是**行注入**：`completed = lines[:end] + inject +
lines[end:]`（`engine/workspace.py:87-97`），缺 %nprocshared/%mem 时注入
1–2 行，Link0 块之后的全部内容行号整体 +N。凡缺省注入且 Link0 块后存在警告
的文件（如 route 拼写警告），`file_warnings(completed_text)` 与
`file_warnings(stored_text)` 的 `line` 字段必然不同——「逐条一致」按全字段
比较必假；按内容比较则不称「逐条」。警告**内容集**恒等成立（注入行取值合法
不产警告，已由 §2.1 设置值域核实），但方案必须改写断言口径，否则实施时要么
产出必假测试、要么静默偏离方案。建议改为：

> 缺省补全前后 `file_warnings` 的 `(kind, keyword, message, suggestion)`
> 多重集逐条一致；补全注入 N 行时 Link0 块之后警告行号整体 +N，行号口径
> 维持存储文本绝对行号（与预览/编辑所见一致）。

## 三、技术合理性与风险点覆盖评估

**裁决①–⑥覆盖核对（全覆盖）**：①文案修订→方案 2；②中文 message 硬口径
→方案 2；③持久化与两条消除路径→方案 4；④条目堆叠限高→方案 3；
⑤提交前核验预显（任务级粒度）→方案 1；⑥新鲜度与补全后核验→方案 1/4。

**方案主体判断**：

- 预显复用既有 `GET /candidates/{id}/preview`（零后端与契约变更）成立——
  preview 与提交核验确为同一解析管道（`parse_input` + `file_warnings` 单点），
  行号全文件绝对；单用户 WSL2 场景成本可控（队列成员 ≤10，页大小受设置约束）。
- 「现算不落库」机制合理，与 Candidate.title「响应中实时解析、不落库」契约
  先例同构（`openapi.yaml:273-276`），无快照滞后风险，复验语义自洽。
- 预显（存储文本）与提交回执（规范化后文本）允许差异的口径已声明
  （「提交期注入/改写……不在预显口径」），与 B8 实测「提交通道规范化后行号」
  一致，无矛盾。
- 文案口径（「⚠ L行号 message」、冒号相接、禁「—」作统一分隔）与用户裁决①
  一致；新增文案未引入「·」分隔符（既有「未声明 · …」注记系存量豁免，不在
  修订面，处置正确）。
- message 中文硬口径 + 测试断言可行：警告 message 产出点集中在
  `parse/blocks.py`、`parse/keywords.py`、`parse/link0_rules.py` 三文件
  （§2.16 涉及文件列名准确），现状抽样已全中文，固化为模板清单 + 断言的
  成本低。
- 契约动作（Candidate 增 `warning_count: int`，openapi 先行 + 生成物零 diff）
  可行且有 `title` 先例；kind 词表不变、预显零契约变更的表述与 §4 一致。

## 四、缺漏清单

**R4（P3）列表现算的成本口径缺实现约束。**
§2.16 方案 4 承诺 warning_count「页大小内解析成本与预览通道同量级」，但现
`list_candidates` 在分页切片**前**对全量候选构建视图（含逐条 `resolve_title`，
`routers/candidates.py:81-98`）。若实施时顺势把 `warning_count` 加进
`_candidate_view`，成本将随全量候选数而非页大小增长，承诺落空。方案应点名
「warning_count 仅对切片后当前页条目现算」的实现约束（或同步重构切片顺序并
留痕）。

**R5（P3）裁决③与复验机制的字面矛盾。**
裁决③「仅『分块编辑修复』与『删除候选』两条路径可消除」与方案 4「提交规范化
改写文本后经列表刷新同径复验」并存：`verify_and_normalize` 的补空行会消除
`molecule_unterminated`/`variables_unterminated` 等 EOF 型警告（计划 §2.10
自述「纯 EOF 会被追加空行兜住」），即提交成功本身即可使部分警告消退，非用户
主动修复。建议在 §2.16 补一句边界：「裁决③的『消除』指用户主动修复路径；
提交规范化使警告消退属复验机制的自然结果，两者不矛盾」，避免验收歧义。

**R6（P3）Candidate schema 口径未登记。**
Candidate 现描述「创建即完整，此后不变」（`openapi.yaml:254`），与现算
`warning_count`（随文件编辑/提交规范化变化）字面冲突。契约动作应补充：
沿 `title` 先例注明 `warning_count` 为「响应中现算、不落库」，并同步更新
schema description；required 与否一并定名。

**R7（P3）验收标准缺一项。**
方案 1 有「成员 preview 取回失败该成员占位提示、不阻断其余成员」，§2.16 验收
标准与 §3 B9 批次行均未列对应实测项，建议补入浏览器实测清单。

**R8（P3）「保存后刷新列表徽标」的前端通路不存在。**
`BlockEditor.vue` 现无任何 `defineEmits`/`emit`（全文零对外事件），
「分块保存成功后详情即复验结果并刷新列表徽标」需要新建 BlockEditor →
CandidatesView 的事件通路（或等价机制）。方案机制本身可行，但涉及文件清单
未声明该新增通路，建议补一句实现口径，避免实施时遗漏徽标刷新。

**时间节点依赖**：无缺漏——B9 依赖 B8（已收口，§8.12）、并入 3.4.0、入口/
出口闸门齐备（§3.1 B9 节点），与决策点 10「不设日历承诺」一致。

**测试用例要求**：主体齐备（逐 kind 中文断言、warning_count 链路三态、堆叠
限高、等价性闸门）；缺 R7 一项，另建议 `warning_count` 契约用例落点点名
`test_contract_rest.py`（§5 已有通用要求，B9 测试清单可显式回指）。

## 五、修正建议汇总

1. **R1（必改）**：按 §2.2 R1 建议原文改写等价性断言口径（内容集一致 +
   行号 +N 平移显式化）。
2. **R2（必改）**：删除或改写「新增成员时预显/新增成员即预显」为与现交互面
   一致的表述（「打开弹窗即预显，创建态与编辑态」）；如需弹窗内加成员能力，
   另行立项。
3. **R3**：现状段改写为「队列弹窗打开时已并行拉取成员 preview（消费 Link0
   行），warnings 未消费」；方案 1 指认复用 `loadLinkStates` 既有取数路径，
   杜绝每成员双请求。
4. **R4**：方案 4 补「warning_count 仅对当前页切片后条目现算」约束。
5. **R5**：补裁决③与规范化复验的边界说明一句。
6. **R6**：契约动作补 Candidate description 与 required 口径。
7. **R7**：验收标准补「成员 preview 取回失败占位提示」实测项。
8. **R8**：涉及文件/方案 4 补 BlockEditor → 列表刷新事件通路的实现口径。

以上 R1/R2 为实施前置（不改则验收项不可测或测试必假），R3–R8 为文档同批
修订项。修正后本计划 B9/G13 可进入实施。
