# M1 C/D 阶段二审修复清单

> 状态：已执行完毕（2026-09-25，K1–K7 均取建议值；各条状态列回填提交摘要）。由 C/D 阶段二次审查（2026-09-25）产出；审查依据
> [m1-plan.md](m1-plan.md) §4.4/§4.5/§7、[m0-frontend-design.md](m0-frontend-design.md)
> （被审成员，同为本清单修复对象）、[m1-acceptance.md](m1-acceptance.md)。
> 审查范围：C 阶段起点 `5d6d4b3b9` → HEAD；一审修复批次 `59109e46c..HEAD`
> 单独复核。
>
> **执行纪律**：批次 0（前端设计文档）先行修复并冻结，批次 1 起各项修复均以
> 修订后的设计规范为验收依据；每项独立提交（单类变更、中文动词开头 summary），
> 状态列由执行者更新，"完成"项回填提交摘要。

## 0. 审查概况与独立复现

- 方法：三路并行审查（规范轴 / 规格轴 / 一审修复复核）+ 主审独立复现；
  diff 材料留存于 `.codebuddy/tmp/d-*.diff`（gitignored，复核后可删）。
- 独立复现（2026-09-25，未采信实施者自述）：
  - `uv run pytest -q` → **225 passed**；
  - `npm run build`（vue-tsc + vite）→ **通过**；
  - `uv run python scripts/validate_progress.py` → **OK**；
  - 对比度按 WCAG 相对亮度公式独立复算（与设计 §2.1 表逐项对照）；
  - 全仓扫描：字号/字距/缓动/媒体查询/契约字段/裸请求。
- 无法独立复核：D1/D2 历史走查与演练的实测过程（截图不入库，仅核对
  验收记录与代码的一致性）。

## 1. 一审修复复核结论（9 笔）

| 提交 | 结论 | 依据 / 残留 |
|---|---|---|
| `ff9260b57` 决策点 3 关闭 | 部分得当 | 关闭结论与 `webkitdirectory` 实现一致；引据不实：称"已经 GUI 走查验证（m1-acceptance §1.1）"，§1.1 二十六项无文件夹导入条目 |
| `e61282ffd` skip_failed e2e | 得当 | 真 hq + CliGateway + 引擎全链路，断言成员 1 failed / 成员 2 succeeded / 队列 `finished_with_failures` + 回退 |
| `1ad7ecfad` 验收回填 | 得当 | 与测试断言逐项吻合 |
| `13254aed1` 补 `--text-2xs` | 得当 | 文档/样板/tokens 值一致；残留：`tokens.css:21`"12.5px 起"与文档"12px"口径不一（F-06 归口） |
| `d5309ad3a` v2 留痕 | 部分得当 | 所引 §1/§3 存在；"令牌对齐已复核"宽于留痕（无令牌专项核对记录，D-07 补做） |
| `200e02a66` 字号收编 | 同类未全量 | 硬编码字号全局清零、4 处 10px 中文升档；`ExecutionsView.vue:277` 中文「CPU 占用/内存 RSS」误收 `--text-2xs`；11px 中文整批未识别（F-06 整改） |
| `9522d7077` getText | 得当 | `parseAs` 仅剩 `client.ts:17` 一处 |
| `6dbd60629` stalled 捆扎 | 得当 | 单 Map、成对置位/解除、无序列化副作用 |
| `e5ba896dc` 空 favicon | 得当 | `index.html:8` 空 data URI；残留：`m1-acceptance.md:65` 未同步（F-13） |

总判：方向正确，6.5/9 到位；两项系统性不足——**同类问题未全量扫描**（字号）、
**跨端修复未同步**（拖拽重排，F-01）。

## 2. 批次 0：前端设计文档修复（优先，冻结点）

| # | 位置 | 问题 | 修复动作 | 验收 | 状态 |
|---|---|---|---|---|---|
| D-01 | design §2.3/§2.1 | tokens.css 独有 5 变量未登记：`--side-width`(216px)、`--topbar-height`(56px)、`--channel-card-width`(340px)、`--backdrop-dim`、`--backdrop-modal`（两主题值） | 补进 §2 令牌清单（含两主题值与用途）；样板 `:root` 同步补齐 | `check_tokens.py`（D-06）逐变量 diff 为空 | 完成（docs(design): 登记样本外 5 枚令牌并对齐样板变量块） |
| D-02 | design §2.2【裁决 K2】 | 要求"woff2 落 `public/fonts/` 入库 + font-display block/swap + preload"，实现为 @fontsource 构建期打包（`main.ts:8-14`），无 public 目录 | 建议：改文档——分发改述"@fontsource 构建期打包（npm 锁定 + unicode-range 子集）"，保留"禁 CDN、离线可用"硬要求；font-display 统一 swap、删 preload 硬要求（哈希化产物无法静态 preload） | 文档与 `package.json`/`main.ts` 一致，无悬空要求 | 完成（docs(design): 字体分发改述为 @fontsource 构建期打包方案） |
| D-03 | design §2.2【裁决 K1】 | "中文 ≥12px"与实现成批 11px 中文冲突；`--text-xs` 档"含中文一律 12px"与 tokens 注释"12.5px 起"口径不一 | 建议：维持 12px 硬规则（可读性硬线，不推荐放宽），口径统一为"含中文一律 `--text-sm`(12.5px)"；新增细则"同一样式类同时承载中文与拉丁时以中文档位为准" | 文档自洽；F-06 按其验收 | 完成（docs(design): 统一中文微标签口径为 --text-sm 并新增混排细则） |
| D-04 | design §2.1/§7/§8【裁决 K4】 | 对比度表未实测回填；独立复算亮色 failed 徽标 = **4.454 < 4.5** | 新增 `scripts/check_contrast.py`（组合清单 + WCAG 公式，输出回填值，纳入闸门）；亮色 `--state-failed`/`--danger` 由 `#c23a31` 调至 **`#bd352b`**（徽标 4.73，同色相最小偏移）或 `#b93329`（4.91 留余量）；文档表改"实测值"口径 | 脚本全组合 ≥4.5；tokens/样板/文档三处同步 | 完成（docs 亮色 failed 调至 #bd352b 并回填实测值 + fix(web) tokens 同步 + chore(scripts) 新增对比度闸门） |
| D-05 | design §2.4/§6【裁决 K3】 | §2.4"仅两条缓动" vs §6 呼吸用 `ease-in-out`；实现另有未登记动效（`stallbreathe` 1.6s、`pulse` 1.2s、`cardpulse` 2.4s） | 建议：§2.4 增列"呼吸曲线 `ease-in-out`（仅呼吸类动效）"；§6 补录 3 项已实现动效 | 文档与实现无未登记动效；F-10 按其执行 | 完成（docs(design): 补录呼吸曲线与已实现动效并将两项 M1 承诺移入 M2） |
| D-06 | design §8 | 样板与 tokens.css 逐变量非空（`--font-ui/--font-body` vs `--font-mono/--font-sans`、缺 5 变量）；无机械检查 | 修样板变量块（变量名/栈与 tokens 对齐、补 5 变量）；新增 `scripts/check_tokens.py` 逐变量 diff 并纳入闸门 | `python scripts/check_tokens.py` 输出 diff 为空 | 完成（docs 样板变量块对齐 + chore(scripts): 新增设计令牌逐变量一致性闸门脚本） |
| D-07 | design 头部 / §8 | "令牌对齐已复核（记录见 m1-acceptance §1/§3）"宽于留痕；并排走查、接管清单、reduced-motion 无专项记录 | 补做并留痕至 `m1-acceptance.md` 新增小节：令牌 diff 脚本输出、接管清单 6 项逐条、reduced-motion 实测、并排走查结论；修正 design 头部引用 | 留痕含可复现命令与实测输出 | 完成（docs(design): 补记设计规范落地复核留痕并修正走查表述，m1-acceptance §1.5） |
| D-08 | design §9/§3/§5【裁决 K5】 | §9 承诺 M1 接入 HQ 连接状态行与 select/checkbox/toggle 规格，实际留 M2 且未走 diff | 建议：走文档 diff 将两项移入 M2 行（与 `m1-acceptance.md:66-68` 存案一致） | 文档与验收记录一致 | 完成（同 D-05 提交：HQ 连接状态行与 select/checkbox/toggle 规格移 M2） |

## 3. 批次 1：P1 功能修复（依赖批次 0）

| # | 位置 | 问题 | 修复动作 | 验收 | 状态 |
|---|---|---|---|---|---|
| F-01 | `PendingView.vue:58/165` + `m1-acceptance §1.1` | 存在锁定席位即禁用全部拖拽，与后端"锁定原位即放行"（`c6a0906e3`）矛盾；§1.1 走查条目"锁定席位保持原位时放行｜通过"不可复现 | 门控改为：锁定席位不可作拖源/落点，等待区（锁定席位之后）可拖；提交 order 保证锁定席位下标不变，越界拒绝并提示；补走查（含锁定席位场景）后修正 §1.1 表述 | 窗口非空时等待区可重排；走查通过并留痕 | 完成（fix(web): 待执行页拖拽门控对齐锁定原位放行语义 + 走查留痕见 m1-acceptance §1.5/§1.2#13） |
| F-02 | `web/src/engine/monitor.py:209` + `ExecutionsView.vue:49-56` | `elapsed_s` 硬编码 `0.0` → "已运行"恒 0s，`started_at` 兜底永不生效 | 后端填真实值（now − `started_at`，None 防护）；前端保持；补 `test_monitor_stall` 断言 elapsed > 0 | 通道卡"已运行"随 1Hz 跳动；测试断言通过 | 完成（fix(core): 执行监控 elapsed_s 填真实运行时长） |
| F-03 | `CandidatesView.vue:244-251` + `onImportChange` | folder 模式整目录直传，含杂文件即整批 422；B3 要求"前端传该文件夹内全部受支持文件" | 前端过滤：扩展名 `.gjf/.com`（大小写不敏感）+ 跳过隐藏目录；过滤后为空则提示且不发请求；后端校验与整批原子不变 | 含杂文件文件夹仅提交受支持项；全杂文件前端提示；测试/走查通过 | 完成（fix(web): 文件夹导入前端过滤受支持输入文件） |

## 4. 批次 2：P2 契约与规范整改

| # | 位置 | 问题 | 修复动作 | 验收 | 状态 |
|---|---|---|---|---|---|
| F-04 | `docs/api/openapi.yaml` + `services/candidates.py:87` + `CandidatesView.vue:107-108` | `duplicate` 契约外字段（后端注释自认；前端强转读取），违 m1-plan §0"不漂移契约" | 走契约 diff：响应 files 条目补 `duplicate: boolean` → 重跑两侧生成物（`uv run python web/scripts/gen_models.py`、`npm run gen:types`）→ 去强转 | `test_openapi_ssot.py` 通过；无强转；双闸门 | 完成（docs(api): 契约补登 duplicate 并同步生成物 + refactor(web): 去强转改走契约类型） |
| F-05 | `stores/events.ts:78-87` | 裸 `fetch("/api/v1/queues")` + 手写类型，违 §4.4"全部走契约 TS client" | 改 `client.GET("/queues")`；SSE 的 fetch 保留并注明例外 | grep 无裸 fetch（SSE 除外） | 完成（refactor(web): 队列名缓存请求收口契约 client） |
| F-06 | 4+ 视图（Candidates/Queues/Executions/Settings/History/Pending） | 中文 <12px 与中文字距成批：已确证 `CandidatesView:494/523/575/628`、`QueuesView:116`、`ExecutionsView:257/277`、`SettingsView:226`、`CandidatesView:577` 等（全量以扫描为准） | 按 D-03 口径全量整改：承载中文类升 `--text-sm`、去 `letter-spacing`；`.ro .l` 拆中文/拉丁两档；`tokens.css:21` 注释口径同步 | 逐处改前/改后清单核对；`npm run build`；手动冒烟 | 完成（fix(web): 中文微标签字号与字距越限全量整改） |
| F-07 | `HistoryView.vue:180` / `CandidatesView.vue:211` | `causeLabel` 逐字重复 | 抽到共享模块（如 `utils/labels.ts`） | grep 单一定义 | 完成（refactor(web): 失败归因措辞抽取共享模块） |

## 5. 批次 3：P3 样式/体验/夹具收尾

| # | 位置 | 问题 | 修复动作 | 验收 | 状态 |
|---|---|---|---|---|---|
| F-08 | `SettingsView.vue:336`、`QueuesView.vue:212` | 响应式残留（§2.3 禁） | 删除两处 `@media`（窄屏靠横向滚动） | grep 仅剩 reduced-motion | 完成（fix(web): 移除设置页与队列页响应式残留） |
| F-09 | `QueuesView.vue:192/125`、`HistoryView.vue:478/458` | `opacity:.4` 非 §4.3 两态；行高 44px 偏离 40px | 改骨架行/底部扫描线两态；行高对齐 40px | 与候选页（`base.css:158-162`）对照走查 | 完成（fix(web): 列表刷新改扫描线两态并对齐行高 40px） |
| F-10 | `QueuesView.vue:200`、`HistoryView.vue:490` | 扫描线三份重复、缓动不一（`scan/scanx` vs `base.css:296` `scanline`） | 删本地 keyframes，统一引用 base.css `.scanline`（`--ease-std`） | grep keyframes 仅剩共用实现 | 完成（refactor(web): 扫描线动效统一引用 base.css 共用实现） |
| F-11 | `web/tests/fake_g16.py` `_conf` | 环境变量分支 `kv` 未 strip（内嵌分支已修） | 对齐为 `kv.strip().split("=", 1)` | 夹具自检/相关单测通过 | 完成（test(web): 夹具 G16_FAKE 环境变量分支键值对补 strip） |
| F-12 | `test_e2e_fake_g16.py`（2 处 skip） | 缺 `target/release/hq` 时关键 e2e 静默跳过，闸门弹性过大 | 提交前检查清单补"hq 产物存在"项 + 文件头注记（不改 skip 语义） | AGENTS/闸门说明更新 | 完成（docs(test): 提交前检查清单补 hq 产物存在项并注记 e2e 跳过前提） |

## 6. 批次 4：记录与进度同步

| # | 位置 | 问题 | 修复动作 | 状态 |
|---|---|---|---|---|
| F-13 | `m1-plan.md:772`、`m1-acceptance.md:65/122`、m1-plan §9 风险 10【裁决 K7】 | 422 笔误未修；favicon 条目过时；"224 passed"与现值 225 不符；风险 10"保留 store 单测"对象不存在 | 分别改 409、移入已修复清单、更新数字；风险 10 预案改为"手动冒烟 + M2 视需要补单测"；复核 §6 表与 §5.3 说明的对应 | 完成（docs(plans): 修正验收记录过时项并登记已知限制） |
| F-14 | `m1-acceptance` §1.3 或 progress `known_issues`【裁决 K6】 | 自然序仅页内（`CandidatesView.vue:33-36`，`page_size=50`）跨页乱序；前后端双实现无对照测试 | 建议登记为已知限制（M2 处理），M1 不扩契约 | 完成（docs(plans): 同上提交，§1.3 登记自然序仅页内有序已知限制） |
| F-15 | `CHANGELOG.jsonl` / `progress.json` | 收尾 | 逐笔同步 + 双闸门；新脚本（D-04/D-06）纳入闸门说明 | 完成（docs(agents) 闸门清单更新 + chore(progress) 未发布变更逐笔同步，本行为收尾回填） |

## 7. 待裁决项（K1–K7）

| # | 事项 | 建议默认值 | 影响项 |
|---|---|---|---|
| K1 | 中文 12px 硬规则 | 维持硬规则、改实现；口径统一为 `--text-sm`(12.5px) | D-03、F-06 |
| K2 | 字体分发 | 改文档为 @fontsource 方案（保留禁 CDN）；font-display 统一 swap、删 preload | D-02 |
| K3 | 缓动 | §2.4 增列呼吸曲线 `ease-in-out`（仅呼吸类）；§6 补录已实现动效 | D-05、F-10 |
| K4 | 对比度 | 建 `check_contrast.py` 闸门 + 亮色 failed 调 `#bd352b`（4.73） | D-04 |
| K5 | §9 M1 承诺 | HQ 连接状态行与 select/toggle 规格移 M2（走文档 diff） | D-08 |
| K6 | 自然序跨页 | 登记已知限制，M2 处理 | F-14 |
| K7 | 风险 10 预案 | 修订表述（"保留 store 单测"改为"手动冒烟 + M2 视需要"） | F-13 |

## 8. 验收闸门与提交组织

- 每项提交前：`uv run pytest -q`、`npm run build`、`uv run python scripts/validate_progress.py`；
- 批次 0 完成后新增并纳入闸门：`python scripts/check_tokens.py`（D-06）、
  `python scripts/check_contrast.py`（D-04）；
- 提交：按 [conventional_commits.md](../references/conventional_commits.md)
  逐项拆分（单次一类变更、中文动词开头 summary），文档与代码分提交；
- 历史提交不回改（`f485323dc` 混合类型、C1–C7 摘要名词起首属既成事实，
  仅在后续提交中纠正习惯）；
- 执行完成后的验证留痕回填 [m1-acceptance.md](m1-acceptance.md)（与 D-07 合并记录）。
