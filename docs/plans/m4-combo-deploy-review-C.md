# 代码审查报告：m4 插波批次 C（前端：组合流模板配置弹窗 + 设置页入口 + ComboFlowDialog 方案选择器）

- 审查人：独立实现代码审查（与实施分离，只审不改）
- 日期：2026-10-14
- 分支：g16-webui（工作区干净，HEAD = a5a19b8c）

## 一、审查依据与范围

- 依据：`docs/plans/m4-combo-template-deploy-plan.md` §3.4 前端交互规格、§2 WBS 批次 C 行、附录 A 断言清单 A1–A24（当前 mode=enforce，A7a 执行、A7b 不适用）、§6 闸门清单（前端四闸门）、§7 R-9；附录 B 的 A1–A24 走查留痕（不采信自述，能复现的独立复跑）。
- 对象（提交）：136b7663（ComboTemplatesModal + 设置页入口）、f81477a6（ComboFlowDialog 方案选择）、4eb68e9c（.gitignore 走查截图目录）、53f294c7 / 299b2ec1 / f23aa417 / e6884c24（进度登记与走查回填）；联动核对 619842d3（A+B 审查整改：is_default 保存语义）。
- 对象（文件）：`web/frontend/src/components/ComboTemplatesModal.vue`、`web/frontend/src/views/SettingsView.vue`（入口）、`web/frontend/src/components/ComboFlowDialog.vue`、`web/frontend/src/api/contract.ts`（消费面）、`.gitignore`。
- 范围证实（实测）：`git show --stat` 逐提交核对——136b7663 仅 2 个前端文件（+490）、f81477a6 仅 ComboFlowDialog.vue（+55/-5）、4eb68e9c 仅 .gitignore（+2）、4 个进度/回填提交仅触 progress.json / CHANGELOG.jsonl+md / 计划文档，**零业务代码混入**；批次 C 提交未触及后端，与「服务端组合流提交链零改动」（§1）声明一致。`git status` 干净。
- 报告落盘：`docs/plans/m4-combo-deploy-review-C.md`（调用方指定路径）。

## 二、总评与结论

**结论：通过（附 1 项 P2 建议整改与 3 项 P3 备注，均不阻断合入）。**

批次 C 交付物与 §3.4 交互规格逐条对照全部落地；附录 A 中可脱离浏览器判定的断言（A5/A6/A8/A9/A10/A13-route 半支/A15/A16/A17/A22/A23 及序列化往返）经临时隔离实例 API 直调逐条复现通过；is_default 修复（619842d3）后前端保存载荷与「radio 不可取消」语义兼容性经四种保存路径实测确认；前端四闸门与全量测试独立重跑全绿（738 passed 零跳过，hq 产物在位，e2e 真实运行非静默跳过）。发现 1 项豁免粒度偏粗的语义边界（P2）与 3 项轻微备注（P3），不影响功能可用性与既有断言结论。

## 三、§3.4 交互规格逐条对照（功能完整性）

| 编号 | 计划条目（§3.4） | 实现位置 | 结论 |
|---|---|---|---|
| F1 | 入口：SettingsView 运行级参数区「组合流模板」按钮，弹 ConfirmModal 外壳（默认插槽 + #foot） | SettingsView.vue:272–278（按钮位于「运行级参数」section 内，:245 起该 section）、:318（`<ComboTemplatesModal :open="comboOpen">`）；ComboTemplatesModal.vue:183–189（ConfirmModal 外壳，默认插槽 + `#foot` :290–313） | 已落地 |
| F2 | 顶部一排 5 个矩形框（`.preset/.preset--on` 选中范式），显式数字 1–5 + 配置名 + 默认徽标，点击选中（accent 描边）展开编辑区 | ComboTemplatesModal.vue:192–207（`v-for` 5 框，`ct-preset--on` 选中类，数字 `ct-num` + 徽标 `ct-badge` + 配置名 `ct-name` 两行结构）、:349–355（`border-color: var(--accent)` 选中描边） | 已落地（选中范式 accent 描边等价复刻；类名为组件 scoped 新造 `ct-preset/--on`，非字面复用 OrbitalsPanel 的 `.preset/--on`——scoped 样式无法跨组件共享，范式一致，P3 备注见 C-5） |
| F3 | 打开配置页自动选中方案 1 | ComboTemplatesModal.vue:103 `selectScheme(templates.value[0]?.template_id ?? 1)` | 已落地 |
| F4 | 编辑区字段齐备：配置名 / route 单行 textarea @input 剥离换行 / link0 三框 | ComboTemplatesModal.vue:228–231（配置名）、:242–248（route textarea + `@input="stripNewlines"`，:107–112 剥离实现）、:251–285（link0 三框） | 已落地 |
| F5 | %nprocshared inputmode=numeric；%mem inputmode=decimal；%cpu 默认置灰、勾选「指定CPU核心」启用 | :254–260（numeric）、:266–274（decimal）、:277–284（`:disabled="!useCpu"`）、:261–264（「指定CPU核心」复选框位于 %nprocshared 输入框下方） | 已落地 |
| F6 | 「设为默认」radio 语义：默认不可取消、仅可改选 | :114–119（`toggleDefault` 显式回写 `checked = true` 防原生 DOM 取反脱节——走查缺陷修复①落点）、:233（`:checked="isDefault"` 受控） | 已落地 |
| F7 | 422 errors 全量一次展示（字段级红描边 + 顶部错误清单双范式） | :146–151（errors 全量赋值）、:209–214（顶部错误清单 `role="alert"`，reason 显式）、:55–56 + :246/:259/:272/:282（fieldErrors → route/nproc/mem_gb/cpu\|link0 红描边，与后端 `_verr` field 值域一一对应，combo_templates.py:84–175 实测核对） | 已落地 |
| F8 | 豁免按钮出现条件 = keyword_not_in_dict | :57–59（`hasKeywordErrors`）、:294–303（按钮 `v-if="hasKeywordErrors"`） | 已落地 |
| F9 | 豁免记忆作用域 = 弹窗打开期间 × 全局 token 集：跨方案共享、关闭清空、失败不清、成功保持、重开重校验 | :50（组件级 `exemptTokens`）、:97（重开清空）、:80–87（切方案不清——跨方案共享）、:146–151（失败路径不清）、:167–170（保存时集合非空即携带 ignore——成功后保持）；「关闭清空」实现为「重开时清空」（弹窗关闭期集合不可被消费，行为等价） | 已落地（粒度偏差见 P2/C-1） |
| F10 | temp_applied「已补齐」/ normalized「已归一化」提示；spelling_warnings 展示 | :216–223（`已补齐温度 temperature=298.15` / `已归一化（全小写入库）` / `词典外关键词（已放行）：…`） | 已落地 |
| F11 | 未点保存本地改动丢弃：切方案/关闭均回已保存值 | :79–87（`selectScheme` 重拉 `fillForm`）、:89–105（重开 watch 重新 GET 并选中方案 1） | 已落地 |
| F12 | ComboFlowDialog 打开时并行拉 GET /settings + GET /combo-templates | ComboFlowDialog.vue:80–83（`Promise.all`） | 已落地 |
| F13 | 方案下拉 5 条配置名、默认选中 is_default 条 | :182–191（option 文本 `{{ t.template_id }} · {{ t.name }}{{ t.is_default ? "（默认）" : "" }}`）、:90–91（`templates.find(t => t.is_default)` 默认选中） | 已落地 |
| F14 | 回填序列化 `%nprocshared=…`/`%mem=…GB`/`%cpu=…` 全小写、仅非空项 | :47–54（`serializeLink0` 三行条件拼接；`GB` 无空格） | 已落地 |
| F15 | 保留手改能力；提交载荷契约不变（template.route/link0 数组） | :57–67（仅显式选择触发回填）、:115–127（`route: route.value.trim()` + link0 行数组按行拆分，非空才携带——与 M4 既有契约一致，A21 留痕载荷形态核对相符） | 已落地 |
| F16 | FALLBACK_ROUTE 与后端 `config.COMBO_TEMPLATE_INITIAL_ROUTE` 字面一致（F2 #6 单值来源） | ComboFlowDialog.vue:26 `"#p b3lyp/6-31g(d) opt freq"` ≡ config.py:153（逐字符一致）；拉取失败回落链 :45/:61/:89 | 已落地 |

## 四、发现清单

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| C-1 | P2 | 逻辑与边界 | web/frontend/src/components/ComboTemplatesModal.vue:167–170 | **豁免粒度偏粗：会话内已豁免任一 token 后，新词典外 token 不再被拦截。** `saveNormal()` 以「会话豁免集非空」为 `ignore_spelling` 开关，而后端语义为批次级全量放行（combo_templates.py:101–103：ignore_spelling=true 时**该批全部** OOV token 放行）。实测（临时实例 API 探针）：先豁免 `mycustomkeyword` 后，同会话另一方案提交含**新** token `anothercustomword` 的 route 且 ignore=true → 200 放行落库（仅 notice 警示）。与 §3.3「豁免集＝该批该 reason 的 token 集」按 token 粒度的读法存在偏差；A7a 断言仅覆盖同 token 场景、走查未触及该边界。影响有限（新 token 仍展示于「已放行」警示、不静默无痕），且 §3.4「全局 token 集」表述亦可解释现行为 | 二选一：(a) 前端改两段式——`saveNormal` 不带 ignore，仅当 422 错误中 OOV token 全部已∈豁免集时自动以 ignore 重试一次（新 token 仍会 422 并再次出示豁免按钮）；(b) 维持现状，但在计划 §3.3/§3.4 明示「会话豁免＝该弹窗会话内全量放行」口径并补录附录 B A7a 注记（文档先行，消除歧义） |
| C-2 | P3 | 逻辑与边界 | web/frontend/src/components/ComboTemplatesModal.vue:98–105 | 打开时 `GET /combo-templates` 失败（`data` 为空）直接 `return`：无错误提示、无重试入口；若此前打开过，`templates` 残留上次数据而编辑区不刷新（`selectScheme` 未执行），呈现陈旧值。本机回环低概率，仅体验问题 | 失败分支补错误态文案 + 重试按钮，或清空 `templates` 强制空态 |
| C-3 | P3 | 逻辑与边界 | web/frontend/src/components/ComboFlowDialog.vue:69–93 | 重开对话框至两个并行 GET 返回之间存在竞态窗口：`route`/`link0` ref 保留上次会话值（refs 跨开关持久），窗口内用户可见并理论上可点「一键提交」送出陈旧 route（`busy` 已复位 false、无 loading 屏蔽）。本机时延毫秒级、实际风险很低 | open 分支先行重置 `route`/`link0`（或置 loading 态屏蔽提交）待回填 |
| C-4 | P3 | 测试有效性 | web/src/services/combo_templates.py:175（后端域）；附录 A A13 | A13 断言「route/link0 含 @task:/@exec: → 422 link0_symbol_ref_forbidden」的 **link0 半支经 API 不可达**：cpu 值含 `@exec:` 时先被 proc-list 文法拦截（实测 `cpu="0,1,@exec:9"` → 422 `cpu_list_invalid`，见 §五复现），`field="link0"` 分支为防御性死代码。拒绝语义成立、reason 与断言字面不符；附录 B A13 留痕仅实测 route 半支、未注明 link0 半支行为 | 附录 B A13 条目补注「link0 半支由 cpu_list_invalid 前置拦截、reason 漂移属预期」，或后端在 cpu 文法判定前先行符号引用子串检测；属 A+B 域问题，随下一轮后端整改带走 |
| C-5 | P3 | 可维护性 | web/frontend/src/components/ComboTemplatesModal.vue:328–355 | §3.4「沿用既有选中态样式（`.preset/.preset--on`）」以组件内新造类名 `ct-preset/--on` 实现，视觉范式等价（accent 描边 + 选中底色 + 数字 accent 着色），未字面复用 OrbitalsPanel.vue:334 的 `.preset--on`（scoped 样式跨组件不可共享，抽全局样式属过度设计）。备注性登记，不需整改 | 无需整改；如后续出现第三处 preset 范式再考虑抽公共样式 |

## 五、测试与闸门实测（独立复跑，2026-10-14）

| 闸门 | 命令 | 实测输出（摘要） | 结论 |
|---|---|---|---|
| 前端构建（vue-tsc 零错误） | `cd web/frontend && npm run build` | `vue-tsc -b && vite build` 通过，`✓ built in 6.27s`，零类型错误（HistoryView 大 chunk 警告为既有 3dmol/echarts 打包形态，非本次引入） | 通过 |
| 前端零外链审计 | `bash scripts/audit_frontend_offline.sh` | `零外链资源引用（豁免 5 组白名单前缀）`，退出码 0（对刚构建的 dist 执行） | 通过 |
| 设计令牌一致性 | `uv run python scripts/check_tokens.py` | `暗色 92 变量 / 明亮 31 变量，逐变量 diff 为空，check_tokens: OK` | 通过 |
| WCAG 对比度 | `uv run python scripts/check_contrast.py` | `全组合 ≥ 4.5:1（最低 text-faint/bg-inset 4.90:1），check_contrast: OK` | 通过 |
| 全量测试 | `uv run pytest -q` | **738 passed, 2 warnings, 0 skipped**（114s）；`target/release/hq` 在位（17,957,408 字节，10-12 构建）——e2e 真实运行，无静默跳过 | 通过 |
| 进度两文件校验 | `uv run python scripts/validate_progress.py` | `OK` | 通过 |
| CHANGELOG 一致性 | `uv run python scripts/gen_changelog_md.py --check` | `check_changelog_md: OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致` | 通过 |

**API 直调复核**（临时隔离实例：`G16WEB_HOME=/tmp/g16web-review-c G16WEB_ENGINE=0 uv run python -m web.src.main`，127.0.0.1:8300，种子全新未污染真实工作区 `~/g16web`；走查后实例已停、/tmp 工作区已删；真实工作区仅只读查询核验）：

| 断言 | 复现（curl PUT/GET /api/v1/combo-templates…） | 实测输出 | 结论 |
|---|---|---|---|
| A5 route/name 清空恢复 | 方案 5 PUT `{"route":""}`；PUT `{"name":""}` 后 GET | route 恢复 `#p b3lyp/6-31g(d) opt freq temperature=298.15`（temp_applied=true，与留痕「叠加补齐形态」一致）；name 恢复 `配置5` | 通过 |
| A6 非 # 开头 | PUT route=`p b3lyp/6-31g(d) opt freq` | 422 `route_must_start_with_hash` 一条全报；多行分支 API 直调 → `multi_line_route`（叠加 OOV 报告，与测试口径一致） | 通过 |
| A8 temp 补齐/不重复补 | 混合大小写 freq 无温度 PUT；已含 `temperature=310` PUT | 前者 200、route 含 `temperature=298.15`、notice `temp_applied=true`；后者 `temp_applied=false`、不重复补 | 通过 |
| A9 温度非法三变体 | `temperature=abc` / `-1` / `300,310` | 三者均 422 `temp_value_invalid` | 通过 |
| A10 mem 下限与 nproc×cpu | mem=0.5/nproc=1；nproc=8/cpu=1-4；nproc=4/cpu=1-5 | 422 `mem_below_per_core_floor`；422 `nproc_cpu_mismatch`；200 放行（多于默许） | 通过 |
| A13 符号引用 | route 含 `@task:`；cpu 含 `@exec:9` | 前者 422 `link0_symbol_ref_forbidden`；后者 422 `cpu_list_invalid`（reason 漂移，见 C-4） | route 半支通过，link0 半支偏差已登记 |
| A15/A16/A17 三错误一次全报 | 同一 PUT nproc="0"/mem_gb="abc"/cpu="a-b" | 422 单响应含 `nproc_not_positive_int`（field=nproc）+ `mem_value_invalid`（field=mem_gb）+ `cpu_list_invalid`（field=cpu）三条——field 值与前端红描边映射一一对应；`-1`/`2.5` 变体均 422 | 通过 |
| A22 归一化回显 | PUT route=`#P B3LYP/6-31G(D) OPT FREQ` | 200，GET 回显 `#p b3lyp/6-31g(d) opt freq temperature=298.15`，notice `normalized=true` | 通过 |
| A23 link0 清空 → NULL | 方案 3 PUT 三字段空串 | GET 返回 nproc/mem_gb/cpu 全 null；前端 `serializeLink0` 对 null 三字段返回空串、提交时 link0 字段整体省略（ComboFlowDialog.vue:125 条件展开，代码级核验） | 通过 |
| 序列化往返（A11 数据面） | 方案 2 存 nproc=4/mem=8/cpu=1-4 后 GET + 前端序列化逻辑重放 | GET `4`/`8`/`1-4` → `%nprocshared=4`/`%mem=8GB`/`%cpu=1-4`，全小写、仅非空项、GB 无空格 | 通过 |
| is_default 四路径（619842d3 兼容） | 默认行 false / 非默认行 true / 默认行 true / 字段缺省 | 默认归属依次：保持方案 1；迁移方案 4 且全表唯一；保持；保持——「恒有且仅有一条默认」不变式成立。前端 `fillForm` 回显 is_default → 默认行保存恒携 true、非默认行携 false（保持语义安全）、改选携 true（迁移），与修复后契约完全兼容 | 通过 |
| A7a/A18 豁免链（API 面） | OOV token 无豁免 PUT；ignore=true PUT；新 token + ignore=true PUT | 422 `keyword_not_in_dict`（message 含 token 原文）；200 + `notice.spelling_warnings=["mycustomkeyword"]`；新 token 亦放行（批次级，见 C-1）。代码级：失败不清（:146–151）、成功保持（:167–170）、重开清空（:97）、跨方案共享（:50 组件级 + :80–87 不清）均核实 | 通过（粒度偏差 C-1 另计） |

**走查缺陷修复落点核实**（审查项 7）：① A4 `toggleDefault` 显式回写 `checked = true` —— ComboTemplatesModal.vue:114–119 在位；② 布局修复 —— 方案框两行结构 `ct-preset-top`（:200–204、:343–348）、「指定CPU核心」复选框移至 %nprocshared 输入框下方 `ct-check--inline`（:261–264、:443–447）、标签 `flex-wrap` 防溢出（:433）均在位。`.gitignore` 规则覆盖核验：`git check-ignore -v docs/plans/assets/m4-combo-deploy/A1-test.png` → 命中 `.gitignore:35:docs/plans/assets/m4-combo-deploy/`。

**真实工作区只读核验**（走查留痕声明抽查）：`~/g16web/g16web.db`（sqlite只读 URI 连接）——`crest_root="~/opt/crest-3.0.2"`（A21「走查后已恢复」属实）；`combo_templates` 默认归属在方案 1（A3「已改回方案 1」属实）。

## 六、需主代理浏览器复测清单

本审查无浏览器工具，以下纯 UI/视觉/交互断言依赖主代理以内置浏览器（playwright）在 127.0.0.1:8300（`npm run build` 产物经 FastAPI 托管，构建需先执行）复核。附录 B 已有实施者 playwright 走查留痕，本清单为独立抽检口径：

| 断言 | 操作序列 | 预期 |
|---|---|---|
| A1 | 设置页 → 「组合流模板」打开配置弹窗 | 自动选中方案 1（accent 描边），编辑区显示「配置1」与小写初始 route |
| A2 | 观察顶部 | 5 个矩形框均匀排布、显式数字 1–5、初始命名「配置n」 |
| A3 | 改选方案 5 → 保存 → 观察徽标；再改回方案 1 保存 | 默认徽标全页恒唯一、随保存迁移 |
| A4 | 在默认行点击「设为默认」复选框 | 勾选不被取消（radio 语义），仅可通过改选他行迁移 |
| A8 提示面 | route 含 freq 无温度 → 保存 | 回显归一化 route 并出现「已补齐温度 temperature=298.15」绿色提示 |
| A11/A20/A21 | 候选页 → 「组合流」打开 ComboFlowDialog | 方案下拉含 5 条「id · 配置名（默认）」、默认选中 is_default 条；选择方案 2（若已配 link0）回填 `%nprocshared=…`/`%mem=…GB`/`%cpu=…` 三行与 GET 值一致；手改 route 后提交，载荷 route 为手改值 |
| A12 | 编辑区改 route 不保存 → 切方案 → 切回；关闭重开 | 均回已保存值（本地改动丢弃） |
| A14 | 观察 %cpu 编辑框 → 勾/取消「指定CPU核心」 | 默认置灰（disabled 半透明），勾选后可填 |
| A15–A17 视觉面 | nproc=0、mem=abc、cpu=a-b 一并保存 | 顶部错误清单 3 条 reason 全展示，三编辑框红描边 |
| A19 | 设置页观察入口位置 | 「组合流模板」按钮位于运行级参数区、点击弹出配置弹窗 |
| A22 提示面 | route 输入混合大小写 → 保存 | 回显小写值并出现「已归一化（全小写入库）」提示 |
| A23 UI 面 | 方案 3 link0 清空保存后，ComboFlowDialog 选方案 3 | Link0 textarea 为空（无 link0 行） |
| A24 | 候选页缺 link0 声明的候选行提交确认框 | 黄警文案 `%nprocshared=…`/`%mem=…GB` 小写无空格（F2 #8 收口，代码落点 CandidatesView.vue:246–252 已核实） |
| 豁免按钮 UI（A7a/A18） | route 加词典外 token → 保存 | 出现「忽略拼写警告并保存」按钮；点击后落库并展示放行清单；重开弹窗同 token 重新拦截 |

## 七、与附录 B A1–A24 留痕的偏差对照

| 断言 | 留痕结论 | 独立复核结果 | 偏差 |
|---|---|---|---|
| A1–A4 | 通过（浏览器实测） | 代码级全部落地（F2/F3/F6 项）；默认归属唯一性、radio 不可取消语义经 API 佐证 | 无偏差；视觉面待浏览器抽检 |
| A5 | 通过 | API 复现一致（恢复初始 route 叠加温度补齐、name 恢复「配置n」） | 无 |
| A6 | 通过（UI 非 # 分支 + API 多行/空行） | API 复现一致 | 无 |
| A7a/A18 | 通过 | API + 代码级复现一致（拦截/豁免放行/重开重拦/跨方案共享/失败不清/成功保持） | **新增边界**：豁免粒度偏粗（C-1），留痕未覆盖「已豁免后新 token」场景，非留痕错误、属断言盲区 |
| A8/A9/A10 | 通过 | API 逐条复现一致 | 无 |
| A11 | 通过 | 数据面（GET 值 → 序列化形态）复现一致；浏览器回填面待抽检 | 无 |
| A12/A14 | 通过 | 代码级落地（selectScheme/回已保存值、:disabled 绑定）；视觉面待抽检 | 无 |
| A13 | 通过（route 半支） | route 半支 API 复现一致；**link0 半支 reason 漂移**（cpu_list_invalid 前置拦截） | 偏差已登记（C-4，后端域） |
| A15/A16/A17 | 通过 | 三错误一次全报 + field 映射复现一致 | 无 |
| A19/A20/A21 | 通过 | 入口/下拉/载荷契约代码级落地；载荷形态与留痕抓包一致（route + link0 数组、非空才携带） | 无；浏览器面待抽检 |
| A22/A23 | 通过 | API 复现一致（normalized=true 回显小写；NULL 往返 + 前端序列化空串/字段省略） | 无 |
| A24 | 通过（F2 补录） | 代码落点核实（CandidatesView.vue:246–252 小写无空格）；浏览器面待抽检 | 无 |
| 留痕环境声明 | — | 「crest_root 已恢复」「默认已改回方案 1」两项经真实工作区只读查询证实 | 无 |

## 八、总体结论

**通过。** 批次 C 按计划 §3.4 完整落地，四闸门与全量测试独立重跑全绿，API 可判定断言逐条复现通过，is_default 修复后前端行为兼容。附条件：

1. C-1（P2）：豁免粒度偏粗——建议按「前端两段式重试」或「计划文档明示会话级全量放行口径」二者择一收口（若选后者须文档先行并补录附录 B 注记）。
2. C-4（P3）：A13 link0 半支 reason 漂移留痕补注（后端域，可与 A+B 整改线合并处理）。
3. 第六节浏览器抽检清单由主代理复核后，本报告结论方可与附录 B 留痕合并作为批次 E 验收输入。
