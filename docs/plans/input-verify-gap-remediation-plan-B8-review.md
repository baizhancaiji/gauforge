# 代码审查报告：输入文件勘误校验缺口补齐计划 B8 批次（G12 + 全面复审 R2–R5/F-2 随批整改）

> 审查人：code-reviewer 子代理（AGENTS.md §6.2 第二层独立复核，只审不改）。
> 审查日期：2026-10-21。全部结论来自本审查独立执行的命令与实测输出，
> 不采信实施者自述与 §8.12 留痕数字；除本报告外未创建/修改任何仓库文件，
> 隔离冒烟实例与临时工作树均在 /tmp 下且已清理。

## 一、审查依据与范围

- **依据**：`docs/plans/input-verify-gap-remediation-plan.md`——§2.15（G12/B8
  方案四要点、涉及文件、验收标准、「再次保存即清空」B8 落地口径）、§3 批次表
  B8 行（四场景浏览器实测 + B6 补测三场景、全量测试不回归、前端三闸门全绿、
  无契约变更）、§3.1 B8 节点（依赖 B3 已收口、出口含 B6 视觉补测三场景、
  R2–R5/F-2 同轮随批处置留痕 §8.12）、§8.12（实施者交付声明，逐条作为待证
  声明核验）。计划文案口径一律以 B8 提交形态（`git show 6b992ff9:<path>`）
  为准。
- **对象**：git 区间 `04db8a4b..6b992ff9`，共 **10 提交**。批次切分经
  `git log --oneline` 与 §8.12 实施序列逐条对照：21d1c9b4（整改开工）→
  e0a97e4a（F-1 勘误）→ 8c1832cb（立项 §2.15）→ 7fea1b1f（测试先行）→
  c3d50560（R3 实现）→ 6c10c765（R4）→ b6a1c250（R5/F-2）→ ea7ea5c2
  （R1 前端渲染）→ a1bcce0a（两报告落盘 + §8.12 留痕 + §2.15 状态回填）→
  6b992ff9（CHANGELOG/progress 收口）——与 §8.12「文档→测试→实现→进度
  同步」序列吻合，提交类型与顺序经 git log 核对。
- **范围证实**：`git diff --stat 04db8a4b..6b992ff9` 实测 **16 文件
  +561/−16**，全部落在 §8.12 声称范围（R1 两 Vue、R3 link0_rules.py、
  R4 candidates.py、R5/F-2 三脚本/注释、3 测试文件、两份复审报告、计划、
  CHANGELOG、progress）；`git diff 04db8a4b..6b992ff9 -- docs/api/` 为
  **0 行**（契约零变更，B8 行「无契约变更」成立）；`crates/` 零改动；
  HistoryView/ResumeDialog 零改动（后续按需项口径成立）。当前工作区存在
  4 文件未提交改动（两 Vue「·」→「—」、计划与 B14 报告），系 B8 之后另行
  修正，不计入本报告结论；B8 结论全部以 6b992ff9 提交形态核定。
- **报告落盘**：`docs/plans/input-verify-gap-remediation-plan-B8-review.md`
  （约定命名，落盘前确认该路径不存在，未覆盖任何既有报告）。

## 二、实现完整性对照（§2.15 方案逐项 + 随批整改）

| 编号 | 计划条目（提交态口径） | 实现位置（6b992ff9） | 结论 |
|---|---|---|---|
| C1 | 导入成功响应按文件聚合非空 warnings，零警告文件不入列 | CandidatesView.vue:207-210（`data.files.filter((f) => f.warnings?.length).map(...)`） | **符合**（隔离实例实测：spell.gjf 有警告入列、同批 nproc_empty.gjf 各自聚合） |
| C2 | 琥珀清单区，与既有 422 逐文件失败清单同构、warn 色档 | CandidatesView.vue:524-533 与 :515-522（import-errors）结构同构（head+行 文件/消息两列）；.import-warnings 边框 `color-mix(var(--warn) 40%)`、iw-head `var(--warn)`（:807-832） | **符合**（视觉观感见第五节局限声明） |
| C3 | 导入条目「文件名 · 第 N 行 message」 | CandidatesView.vue:529-530 实渲染 `文件名 ⚠ 第 N 行 message` | **偏差**（⚠ 代「·」，P3-1 登记） |
| C4 | 再次发起导入即清空 | CandidatesView.vue:143/151/174（pickFiles/pickFolder/onImportChange 三入口均清 importWarnings） | **符合** |
| C5 | 单任务提交：工具条琥珀注记、与 submitNote 同级邻位 | CandidatesView.vue:508-513（工具条 div 之后紧邻，submitNote 注记于 :484 工具条内） | **符合**（条目形态见 C6） |
| C6 | 提交条目「⚠ 第 N 行 message」 | CandidatesView.vue:511 实渲染 `⚠ 提交警告 · 第 {{w.line}} 行 {{w.message}}` | **偏差**（多「提交警告」前缀，P3-1 登记） |
| C7 | 重新打开提交确认框即清空 | CandidatesView.vue:240（openSubmit 清 submitWarnings） | **符合** |
| C8 | 队列直接提交：done 注记下方「⚠ 任务 #task_id · 第 N 行 message」 | QueueEditorModal.vue:475-478（note `<p>` 之后 v-for，逐字与提交态 §2.15 一致） | **符合**（构建产物 grep 证实 ` ⚠ 任务 #"+task_id+" · 第 "+line+" 行 "`） |
| C9 | 弹窗重开/再次保存即清空 | QueueEditorModal.vue:276（watch(() => props.open) 重开清 submitWarnings）；保存成功路径不清空——done 锁定后保存/提交按钮均禁用（:569/:578），再次保存必经重开，行为等效满足 | **符合**（但 §8.12 所称「登记为必做实现动作见 §2.15」在提交态落空，P3-3 登记） |
| C10 | HistoryView/ResumeDialog 渲染不在本项，登记后续按需项 | 两文件零改动 | **符合** |
| C11 | R3：`check_link0_lines` 对 %nproc 系空值（含截断形 %nprocshare）与 `%cpu=` 空值记 link0_value_invalid | c3d50560（link0_rules.py:110-129）：nproc 系 `ok=False` 默认 + `if not ok` 统一告警；cpu 改 `if not val or cpu_list_count(val) is None`；裸形 `%nproc`（无等号，directive_head 取首词、val 空）同告警 | **符合**（先行红：7fea1b1f 状态单独运行 test_g5_link0_empty_value_warns 实测 **1 failed**；实现后转绿；隔离实例导入 `%nproc=` 文件实测产 `link0_value_invalid` 第 1 行） |
| C12 | R2：矩阵「不适用」格防回归断言（分块保存列 G9/G4/C1/C2、模板列触发词 route 放行代表断言） | test_block_save.py::test_matrix_not_applicable_block_save（:521-540）、test_combo_templates.py::test_matrix_not_applicable_template_save（:543-552） | **符合**（三新用例在 04db8a4b 基线 grep 均 0，851=848+3 成立） |
| C13 | R4：`_validate_one` 死键 bom_stripped 删除 | 6c10c765；全仓 grep `bom_stripped` 零残留 | **符合** |
| C14 | R5：pred_read_window docstring 落空引用改自足表述 | b6a1c250（section_ordering.py:153-156）；提交态计划全文唯一「RW」出现在 §8.12 自述行（:1682），§2.12 确无 RW 条目——落空引用理由证实 | **符合** |
| C15 | F-2：extract_keywords/audit_prose_options 三处措辞对齐「三路互补差集近似全量审计」 | b6a1c250（audit_prose_options.py:2、extract_keywords.py:49 与 :351 注释） | **符合**（恰三处） |
| C16 | F-1：`scrf=conven`→`scf=conven` 原位勘误 | e0a97e4a（§2.9 与 §8.6 口径修正 1 两处） | **符合** |
| C17 | 提交纪律：单次提交只做一类变更 | 10 提交类型分别为 chore/docs/docs/test/fix/refactor/docs/feat/docs/chore | **符合** |
| C18 | B6 视觉补测三场景（豁免按钮不存在、词典外词 200 琥珀、%mem=0 红描边 422） | 留痕 §8.12 场景④⑤⑥；B8 区间未触碰 ComboTemplatesModal/BlockEditor（B57 W3 静态证据维持） | **存疑**（本轮浏览器实测未独立复现，见第五节） |

## 三、问题清单

| 编号 | 级别 | 分类 | 位置（6b992ff9 提交形态） | 描述与实测依据 | 整改建议 |
|---|---|---|---|---|---|
| P3-1 | P3 | 技术方案符合性（条目文案与计划口径逐字偏差） | web/frontend/src/views/CandidatesView.vue:511（提交条目）、:529-530（导入条目） | 提交态 §2.15 规定导入条目「文件名 · 第 N 行 message」、提交条目「⚠ 第 N 行 message」；实现实渲染「文件名 ⚠ 第 N 行 message」（⚠ 代「·」）与「⚠ 提交警告 · 第 N 行 message」（多「提交警告」前缀）。§8.12 场景②留痕（「⚠ 提交警告 · 第 4 行 …」）与构建产物 grep 均证实实际形态如实入痕，但未声明与计划文案的偏离。队列条目（QueueEditorModal.vue:477）与计划逐字一致，无偏差。显示文案单字符/前缀级偏差，不改变功能与数据流 | 已提交形态与计划文案二选一对齐：或按计划文案改两处条目，或以勘误方式在 §2.15 原位改写为实际交付口径（与后续工作区未提交的文案重写方向合并处理）；随下轮文档/前端维护顺带闭环 |
| P3-2 | P3 | 文档一致性（提交数与事实不符） | docs/plans/input-verify-gap-remediation-plan.md §8.12（:1745「区间 v3.3.0..f5387615，31 提交」）与 input-verify-gap-remediation-plan-B14-review.md（对象节与四查节两处「31 提交」），均 a1bcce0a 提交 | 实测 `git rev-list --count v3.3.0..f5387615` = **38**；同一提交内三处写 31，与 B14 报告自身的批次切分叙述矛盾 | 随下轮文档维护将三处「31 提交」改为「38 提交」（工作区已有同向未提交修正，提交即闭环） |
| P3-3 | P3 | 文档一致性（跨引用落空：B9 承接登记缺位） | docs/plans/input-verify-gap-remediation-plan.md §8.12（:1681-1682）对照 §2.15（:1018-1043） | §8.12 声称「『再次保存即清空』登记为必做实现动作（均见 §2.15）」，但提交态 §2.15 仅有队列条目「弹窗重开/再次保存即清空」字样，无「B8 落地为弹窗重开清空（watch(open) 重置）、保存成功路径清空随下个前端批次承接」的登记文本——该 bullet 系工作区未提交改动方才补入。实现侧行为（C9）本身等效满足且不违计划，仅登记缺位使 B9 承接口径在提交态无文档锚点 | 随下轮文档维护补入 §2.15 的 B9 承接登记（或随工作区未提交改动一并提交），使 §8.12 的「见 §2.15」可回指 |

无 P0/P1/P2 级发现。三条 P3 均为文档/文案层，功能与数据流经实测无缺陷。

> 处置留痕（2026-10-21）：三条 P3 已随工作区整改闭环——P3-1 经 §2.15
> 条目文案原位勘误与前端分隔符修订对齐交付口径、P3-2 三处「31 提交」改
> 「38 提交」、P3-3 §2.15 补 B9 承接登记；登记见计划 §8.12「B8 批次
> 独立审查与 P3 处置」，随下轮文档提交入库。

## 四、测试与闸门实测（全部独立重跑）

| 闸门 | 实测输出 |
|---|---|
| `uv run pytest -q` | **851 passed, 0 skipped**，2 warnings（starlette/anyio deprecation 既有环境噪声），116.81s。851=848+3：三个新增用例（test_g5_link0_empty_value_warns、test_matrix_not_applicable_block_save、test_matrix_not_applicable_template_save）在 04db8a4b 基线 `git show | grep -c` 均 0；§8.12「848 + B8 新增 3」逐位吻合 |
| `target/release/hq` | 在位（17,957,408 字节）——e2e 无静默跳过，851 passed 无虚高 |
| 先行红复现 | `git worktree add /tmp/b8-red-wt 7fea1b1f` 后运行 `test_parse_blocks.py::test_g5_link0_empty_value_warns` → **1 failed**（AssertionError，any(...)=False）；与 §8.12「实测 1 failed」一致，测试先行序列证实 |
| `uv run python scripts/validate_progress.py` | OK，rc=0 |
| `uv run python scripts/gen_changelog_md.py --check` | OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致，rc=0；unreleased 行含 B8 两条目（added/web G12、fixed/parse R3+R4+R5/F-2），progress.json unreleased 同步、in_progress 清空（6b992ff9 实读） |
| `uv run python scripts/check_plan_status.py` | **主仓 rc=1**：唯一 FAIL 项为计划状态行「部分实施（…B9…待执行）」——归因于工作区未提交的 B8 后改动，非 B8 本体；在 6b992ff9 临时工作树（`git worktree add /tmp/b8-review-wt 6b992ff9`）复跑 → rc=0「10 份计划文档状态均已回填为终态」，B8 提交形态闸门成立 |
| 前端构建（B8 提交形态） | 临时工作树 `npm run build`（vue-tsc -b && vite build）通过，5.08s |
| `bash scripts/audit_frontend_offline.sh /tmp/b8-review-wt/web/frontend/dist` | 「零外链资源引用（豁免 5 组白名单前缀）」，rc=0 |
| `check_tokens.py`（工作树脚本，主仓 venv） | 「暗色 92 变量/样板 92 变量、明亮 31/31 — 逐变量 diff 为空」，rc=0 |
| `check_contrast.py`（同上） | 「全部组合 ≥ 4.5:1」，rc=0 |
| 契约生成物 | `git diff 04db8a4b..6b992ff9 -- docs/api/` = 0 行；openapi.yaml 未触碰，B3 定型的 warnings 契约形态零变更，「无契约变更（纯前端消费）」成立 |

## 五、端到端与视觉审查记录

**API 冒烟（development.md §6.1 隔离实例，与 §8.12 同口径）**：
`G16WEB_HOME=/tmp/g16web-b8-review G16WEB_ENGINE=0`、127.0.0.1:8412、
`/system/health` 版本 **3.3.0-96-g6b992ff9（即审查 HEAD）**。实测：

1. 导入 `#p optt`（keyword 拼写错）→ **201**，`files[0].warnings =
   [{line:1, keyword:"optt", kind:"keyword_spell", message:"「optt」疑似拼写错误，是否意为「opt」", suggestion:"opt"}]`——message/line/kind 形态齐全；
2. 导入 `%nproc=` 空值文件 → **201**，warnings=[{line:1, kind:
   "link0_value_invalid", message:"%nproc 系值须为正整数"}]——R3 修复端到端生效（含 line 绝对行号）；
3. 导入 route 未终止文件 → **422 VALIDATION_FAILED**，`details.errors[0]`
   键为 filename/reason/message/parse_errors，**无 warnings 键**——导入
   warnings 与 422 details 分离性成立（B3 口径未被 B8 破坏）；
4. `POST /candidates/3/submit` → **200**，顶层键 normalized/seat_id/
   task_id/warnings，warnings=[keyword_spell 第 1 行]——单任务提交通道与
   前端 C5/C6 消费形态一致；
5. 建队（2 成员）+ `POST /queues/{id}/submit` → **200**，warnings 两条各带
   `task_id:1`/`task_id:2` 与成员一一对应——队列 task_id 归属成立，前端
   C8「⚠ 任务 #task_id …」渲染输入形态实证。

实例已 kill，/tmp 工作区与日志已清理；`git status` 复核仅剩调用方声明的
4 个未提交文件，审查过程零残留。

**视觉 UI/UX 维度（审查局限声明）**：本子代理无 playwright 浏览器工具，
§8.12 六场景浏览器实测（导入琥珀清单、提交工具条注记、队列 task_id 警告 +
B6 补测三场景）**未独立复现**，该维度不给出独立「视觉通过」结论。已做的
静态一致性核验：B8 提交形态重构建产物 grep 证实「⚠ 提交警告 · 第」「⚠ 任务
#…· 第 …行」文案与 §8.12 留痕逐字相符、两 Vue 警告区均 `role="status"`、
清空时机（C4/C7/C9）与色档类（--warn、q-warn、import-warnings）与代码一一
对应。六场景是否补测留待主会话裁量（AGENTS §6.2 浏览器实测以留痕为准的
话，§8.12 留痕与提交形态静态一致、无矛盾发现）。

## 六、总体结论

**有条件通过。**

B8 验收标准逐条独立复现：全量 851 passed 0 skipped（848+3 逐位核实、hq
在位无静默跳过）、治理与前端闸门全绿（check_plan_status 主仓失败已逐条
归因为工作区未提交改动、提交形态复跑 rc=0）、契约与 crates 零 diff、R1
四要点与 R2–R5/F-2/F-1 整改在提交形态全部落地、先行红真实复现、隔离实例
五项 API 冒烟（含 R3 空值端到端与 422 分离性）通过。§8.12 自述与实测不
符之处仅限三条 P3 文档层偏差（条目文案两处与计划口径逐字不一致、B14 区间
提交数 31 应为 38、「再次保存即清空」的 §2.15 登记在提交态缺位），无功能
性问题。

条件（登记即可，均不阻断）：
1. P3-1：CandidatesView 两处条目文案与 §2.15 口径二选一对齐（改码或原位
   勘误），可并入工作区已进行的文案修正一并提交；
2. P3-2/P3-3：三处「31 提交」改 38、§2.15 补 B9 承接登记（工作区未提交
   改动已含同向修正，提交即闭环）；
3. 视觉维度：六场景浏览器实测本轮未独立复现（静态一致性无矛盾），如需
   独立视觉证据，按 development.md §6.1 拉起隔离实例由主会话补测。

## 七、Playwright 视觉复测留痕（主会话补测，2026-10-21，闭环第五节局限与第六节条件 3）

> 复测人：主会话（playwright MCP 内置浏览器）。实例同 §6.1 口径：
> `G16WEB_HOME=/tmp/g16web-b8-visual G16WEB_ENGINE=0`、127.0.0.1:8413，
> `/system/health` 版本 **v3.3.0-96-g6b992ff9**；前端 dist 由工作区构建——
> 含工作区未提交的「·」→「—」分隔符修正，故条目文案呈「—」形（即 P3-1
> 整改方向已在工作区落地的形态），其余与 6b992ff9 提交态一致。六张截图存
> `.playwright-mcp/b8-s{1..6}-*.png`（本地留证，不入库）；实例已 kill，
> /tmp 工作区与测试文件已清理，仓库工作区零残留（仅余本报告与调用方既有
> 4 个未提交文件）。

| # | 场景（§8.12 口径） | 实测结果 | 判定 |
|---|---|---|---|
| ① | 导入拼错关键字文件见琥珀清单 | UI 上传 spell.gjf（route「optt」在第 4 物理行）+ clean.gjf → 琥珀清单「导入警告 1 条 — 非阻断，已入库」，按文件聚合仅 spell.gjf：「⚠ 第 4 行 「optt」疑似拼写错误，是否意为「opt」」——行号与物理行一致；clean.gjf 零警告未入列；再次导入即清空旧清单、新清单「导入警告 2 条」按文件聚合（nproc.gjf「⚠ 第 3 行 %nproc 系值须为正整数」） | **通过** |
| ② | 单任务提交后见工具条琥珀注记 | spell.gjf 提交确认框（foot 仅「取消/提交」）确认后，工具条下方琥珀 status：「⚠ 提交警告 — 第 4 行 「optt」疑似拼写错误，是否意为「opt」」；**重新打开提交确认框即清空**（重开后页面 grep「提交警告」零命中） | **通过** |
| ③ | 队列直接提交见 task_id 归属警告 | 队列 [004 nproc, 003 spell] 直接提交 → done 注记「已保存并提交」下方两条琥珀：「⚠ 任务 #4 — 第 3 行 %nproc…」「⚠ 任务 #3 — 第 4 行 「optt」…」；与 `/api/v1/pending` ground truth（seat 2 成员 task 4=nproc、task 3=spell）**逐一对应，归属正确**；无警告成员（clean.gjf，task #2）零条目；**弹窗重开即清空**（同会话关闭后再开新队列弹窗，「任务 #」「已保存并提交」零命中）。注：任务号非按成员序分配（首成员得 #4）系后端分配行为，UI 忠实透传，非 B8 前端问题 | **通过** |
| ④ | 组合流模板弹窗无豁免按钮 | 设置页「组合流模板」开 ComboTemplatesModal，foot 仅「关闭/保存」，无「忽略拼写警告并保存」——G10-a 移除口径在当前构建成立 | **通过** |
| ⑤ | 词典外 token route 保存 200 放行 + 琥珀警告 | route 改「#p b3lyp/6-31g(d) opt freq zzzzzq」保存 → 200 非阻断，琥珀注记两条：「已补齐温度 temperature=298.15」（freq 联动照常）+「词典外关键词（已放行）：zzzzzq」；route 回显归一化文本 | **通过** |
| ⑥ | %mem=0 保存 422 + 红描边 + 错误清单 | %mem 填 0 保存 → 422，顶部 alert「%mem 须为正数（GB 数值）」；%mem 输入框挂 `.ct-invalid`，computed borderColor **rgb(189, 53, 43) = #bd352b**，与 tokens.css `--danger` 令牌声明逐字一致（令牌驱动，非硬编码色） | **通过** |

**复测结论：六场景全过，C18 由「存疑」改判「符合」，第五节视觉局限闭环，
第六节条件 3 满足——本报告结论由「有条件通过」收敛为「通过」
（余 P3-1/P3-2/P3-3 三条文档层登记项不阻断，整改路径见第三节）。**
