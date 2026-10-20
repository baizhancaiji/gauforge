# 代码审查报告：输入勘误缺口补齐计划 B6 批次（G10-a enforce 屏蔽 + G10-b 词典扩面）

> 审查人：code-reviewer 子代理（AGENTS.md §6.2 第二层独立复核）。
> 审查日期：2026-10-20。全程只审不改：全部结论来自本审查独立执行的命令与实测输出，
> 未采信实施者自述数字；除本报告外未创建/修改任何仓库文件。

## 一、审查依据与范围

- **依据**：
  1. `docs/plans/input-verify-gap-remediation-plan.md` §2.13（G10-a/G10-b，决策点
     12/13，含方案与涉及文件）、§3 批次表 B6 行（验收标准与契约动作）、§3.1（批次
     依赖与 G16 冒烟清单）、§5/§7（闸门与长程脚本规范）；
  2. 审计留痕 `docs/plans/input-verify-gap-b6-prose-audit.md`（§1–§8 全部）；
  3. `AGENTS.md` §5（提交规范）、§6（审查机制）、§7（长程脚本规范）、§10（跨平台约定）。
- **对象**：提交区间 `9bc3a456..f6129cef`（HEAD），共 6 提交（自新到旧）：
  `f6129cef` feat(web) G10-a enforce 屏蔽、`173872b7` chore(progress) B6 收口登记、
  `1f248515` docs(plans) 审计留痕、`79b2f2ab` feat(parse) 词典 1166→1345、
  `31a2cb60` feat(scripts) 审计工具、`faf580e8` chore(progress) 开工登记。
  明确排除：工作区未提交改动 `web/tests/test_parse_blocks.py` 的三个 G11/B7 测试
  函数（B7 测试先行，不属 B6）。
- **范围证实**：`git status --porcelain` 实测工作区唯一改动即
  `web/tests/test_parse_blocks.py`（`git diff` 确认仅新增上述三个测试函数，219/232/245
  行附近）；`git diff 9bc3a456..f6129cef --stat` 共 31 文件（+43722/−165），与声称
  改动面一致；`crates/` 零改动（无越权改内核）；声称未触碰的文件
  （如 `web/src/parse/link0_rules.py`、其余前端组件）不在 diff 清单中，零改动证实。
  前端 `dist` 为 gitignore 产物，本审查重构建后确认仍零残留、未污染工作区。
- **报告落盘**：`docs/plans/input-verify-gap-b6-code-review.md`（调用方指定路径，
  落盘前确认无同名文件、零覆盖）。

## 二、功能完整性对照（计划 §3 B6 验收标准逐条）

| 编号 | 验收条目 | 实现位置 | 结论 |
|---|---|---|---|
| V1 | 模板保存拼写错误仅警告、零 422（enforce 屏蔽，决策点 12） | `web/src/services/combo_templates.py`（`SPELLING_MODE="warn"` 单点，`mode="enforce"` 分支保留） | 已落地（接口冒烟四项实测，见 §五） |
| V2 | warn 口径断言含 `ignore_spelling=true` 与不传行为一致 | `web/tests/test_combo_templates.py::test_oov_tokens_pass_with_warnings_after_enforce_off` | 已落地（测试 + curl 双通道证实） |
| V3 | 前端豁免按钮隐藏以浏览器实测验收（AGENTS §6.2） | `web/frontend/src/components/ComboTemplatesModal.vue`（exemptTokens/hasKeywordErrors/oovTokensFromErrors/saveWithExemption 全删，`ignore_spelling` 恒 false） | 部分确认：源码与重构建 dist 零残留（grep 实测）、三道前端闸门绿；浏览器视觉复测超出本审查工具面，登记限制项 L1 |
| V4 | 面⑤散文提及选项审计三路差集清单落盘并逐条人工复核留痕 | `docs/plans/audit/`（path1/2/3、merged、warn、review、decisions）+ `scripts/audit_prose_options.py` + 留痕 §1–§3 | 大体落地；**warn→review 层（1262→475）不可复现**，见 R1 |
| V5 | 复核通过的缺口选项全部入典（幂等闸门 + 规模断言同步） | `scripts/extract_keywords.py`（面⑦ + `B6_MANUAL_OPTIONS`）、`web/src/parse/keywords.txt`（1345）、三处规模断言 1345 | 已落地（词典双跑逐字节幂等且与在库一致；抽查 14 条手工补录原文依据全部核实，见 §四.3） |
| V6 | `opt=addredundant`/`freq=nnroa` 零警告复测通过 | `test_g10b_prose_option_shapes_zero_warnings`；本审查独立判定 `#p opt=addredundant` 零警告 | 已落地（G16 t1 Normal termination 独立复现） |
| V7 | `td=window`/`units=bohr` 等 A 类判归形态维持预期警告不复测 | `test_g10b_a_class_shapes_still_warn`（modela/bohr/window 三形态均报 `route_option_unknown`） | 已落地 |
| V8 | 全量测试不回归 | — | 已落地：已提交 HEAD 基线 838 passed 0 skipped 独立复现（§四.1） |
| V9 | 语料基线仅作回归对照；扩面后复跑逐条归因；不得含唯一前缀歧义翻转型新增误报 | `docs/plans/audit/corpus_baseline_b6.json`；留痕 §7 | 已落地：417→394 文件、498→469 条、66→55 形态逐位独立复现；新增唯一形态 `readanh` 经本审查 G16 实测拒绝（L717 DiNa EOF），警告正确非误报 |
| V10 | A 类判归形态顺带记录 G16 实测对照（不作判据） | 留痕 §8 t3（prop=wrf QPErr） | 部分落地：prop=wrf 有实测；`units=bohr`/`td=window` 无 G16 实测记录（本审查补测 units=bohr = Normal termination），见 R9 |
| V11 | G16 冒烟按 §3.1 B6 清单（B 类复测、prop=wrf 一例、缩写判活正反例各一） | 留痕 §8 六例表 | 已落地（本审查独立复现 t1/t3/t5/t6 四例 + units=bohr 补测；t2/t4 未复跑，留痕在案） |
| V12 | `keywords.py` window 注释按 A 类口径修正；`workspace.py` docstring 旧单位口径顺带修正 | `web/src/parse/keywords.py`（`_PAREN_TAIL` 条）、`web/src/engine/workspace.py` | 已落地（diff 实读确认） |
| V13 | 契约动作：模板保存端点 description 更新（enforce→仅警告、ignore_spelling 不生效）+ 生成物再生零 diff；warnings 词表不变 | `docs/api/openapi.yaml` 五处（词表三头注/ComboTemplateMutationResult/ignore_spelling/spelling_warnings/PUT 端点）↔ `models.py` ↔ `contract.ts` | 已落地（gen_models/gen:types 独立再生零 diff；warnings kind 词表无变更） |
| V14 | `prop=wrf` 兼容分支删除（决策点 9）无残留 | `web/src/parse/section_ordering.py`（`COMPAT_EXTRA_KEYWORDS` 删除、`any_trigger` 纯官方表）、测试改判后断言 | 已落地（grep 零残留；G16 t3 QPErr 拒绝佐证裁决正确） |
| V15 | 无越批实现（B7/G11 不在本批） | 区间内 `blocks.py` 仅注释改动、`parse_charge_tokens` 未动、G11 测试未提交 | 已证实 |

## 三、问题清单

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| R1 | P2 | 测试有效性/审计可复现性 | `docs/plans/audit/warn_candidates.json`→`review_candidates.json` 过渡层；留痕 §1 | **审计漏斗关键层不可独立复现，留痕描述与实测不符**。留痕称「以现行 G8 判定链（check_route_options）重过滤 → 实际产生 route_option_unknown 的复核面 475 形态」；本审查用 B5 时点判定链（`31a2cb60:web/src/parse/keywords.py`）+ B5 词典（1166）对 merged 1435 形态独立重跑 `check_route_options`，得**非空 1262——与入库 warn_candidates.json 全等（交集 1262），而非 475**。warn 层 1262 中被再过滤掉 787 条（恰为全部 path2-only 形态 1188→401；其余来源组合 100% 原样进入 review 面），该层过滤谓词在已提交工具中不存在（`audit_prose_options.py` 只产出到 merged；`make_decisions.py` 从 review 开始消费），即 1262→475 的选择过程无代码、无逐条留痕。被排除的 787 条在隔离判定下**均实际产生 route_option_unknown**，其中若混有官方合法散文提及选项则未被逐条复核。影响有界：面⑦规则提取遍历全部 keyword 页不经复核面、手工补录常量（76）大于复核面裁决数（65）、全部 warn 级不阻断——方向为「漏」，与「全量审计」目标存在差距。复现命令：见 §四.2（3）。 | 将 warn/review 过滤实现为入库脚本（并入 `audit_prose_options.py` 或 `make_decisions.py`），重跑并逐字节比对入库 JSON；或在留痕 §1 补记该层的确切谓词与操作方式，并对 787 条排除项补轻量归因（如按句式锚点/停用词的机械规则）。完成前 B6「全量审计」结论应表述为「三路互补的近似全量」。 |
| R2 | P3 | 留痕取数口径 | `79b2f2ab` 提交信息；留痕 §2 表 | 「B6_MANUAL_OPTIONS 手工补录常量清单（65 条）」与常量实际规模不符：实测常量 **76 条**（复核面内 admit_manual 裁决 65 + 复核面外 11：`bomd=gradonly/local`、`cas=nocpmcscf/nofulldiag`、`freq=readhindered`、`population=savecm5/savenpa`、`sacci=quintet/sextet/septet`；其中 `output=spinrotation` 在 B5 词典已存在，属冗余补录，无害）。留痕 §2 表内「admit_manual 65」作为复核面处置数本身自洽，但常量总规模未在留痕中说明。 | 在留痕 §3 补一句「常量 76 = 复核面裁决 65 + 复核面外 11」，后续提交信息按实际常量规模表述。 |
| R3 | P3 | 技术方案符合性（批次序列） | 区间提交顺序；计划 §2.13 方案 1、§8.8 | 计划与开工登记（`progress.json` 开工 note）均载明「G10-a enforce 屏蔽（先行独立提交）→ G10-b 随后」，实际 **G10-a（f6129cef，22:01）是批次最后一个提交**，且晚于收口登记（173872b7，21:58）——收口登记时 G10-a 代码尚未入库。无功能危害（同批完成、闸门全绿、最终状态正确），但批次序列留痕与 git 史不符。 | 随批在留痕或 progress 中注明实际序列；后续批次按登记序列执行。 |
| R4 | P3 | 约定违例（提交拆分） | `79b2f2ab`、`f6129cef` | 计划 §3 末要求「每批次独立成提交序列（文档 → 测试 → 实现 → 进度同步），单次提交只做一类变更」；B1–B5 均以独立契约先行提交与测试先行提交执行。B6 实际：G10-a 契约（openapi.yaml）+ 生成物（models.py/contract.ts）+ 后端 + 前端 + 测试**单提交**；G10-b 实现 + 测试 + 词典 + 顺带修正**单提交**。无独立契约先行/测试先行提交，「5 用例先行红」「field 白名单 1 例先行红」无法从 git 史独立证实（同提交交付）。 | 后续批次恢复「契约先行 → 测试先行 → 实现」的独立提交粒度；无法补证的先行红主张在留痕标注「过程性陈述，git 不可证」。 |
| R5 | P3 | 约定违例（提交规范） | `79b2f2ab`/`1f248515`/`173872b7`/`f6129cef` 提交 summary | `conventional_commits.md` L19 要求「summary 使用中文、**动词开头**」；4 个提交以名词开头：「面⑦散文句式直述入典…」「B6 G10-b 审计留痕…」「B6 批次收口登记…」「组合流模板保存 enforce 口径暂时屏蔽…」。此前批次（登记/新增/回填）基本合规，本批出现回退。 | 后续提交 summary 改动词开头（如「入典面⑦…」「登记 B6 收口…」「屏蔽组合流模板 enforce 口径…」）。 |
| R6 | P3 | 测试有效性（B7 观察项） | 工作区 `web/tests/test_parse_blocks.py::test_g11_comment_stripped_still_validates` | 调用方预期「3 个 B7 用例故意红」，实测全量 **839 passed + 2 failed**：仅 `test_g11_charge_line_inline_comment`、`test_g11_comment_cut_quote_aware` 红；第三例在 B6（未实现 G11）代码下**本就通过**——其三段断言（剥后 token 不足/非整数/独立注释行）在「不剥注释」现状下同样以非整数 token 记 parse_errors，结局相同，属回归守卫而非先行红。B7 实现后该例应保持绿。 | B7 实施者知悉：先行红实际为 2 例；第三例价值在「实现后仍报错」的回归守卫，验收时不必期待其先红。 |
| R7 | P3 | 留痕取数口径 | 留痕 §6 文件清单表 | 表称 `review_flat.txt`/`review_detail.txt` 为「475 条」；实测 `review_detail.txt` 475 行一致，`review_flat.txt` **511 行、489 个唯一形态** ≠ 475（多出 14 形态，疑含 reject_pos 与复核面外手工项），口径未注明。 | 留痕注明 review_flat 的实际构成与行数口径。 |
| R8 | P3 | 技术方案符合性（覆盖口径） | `scripts/audit_prose_options.py` path2；留痕 §1 路②行 | 路②收窄为「keyword 页 Options 章节 #### 条目正文 + markdown 链接剥离」：有计划内依据（§2.13 路②原文含「与页主题近邻」限定）且已在留痕 §1 与工具 docstring 双处留痕解释（链接文本键归属属链接载体、由路①承接）——**不判偏离**。但由此「全量审计」的精确含义是三路互补的近似全量：Options 章节之外的散文裸词提及（keyword 页概述/Availability/Related 章节、非 keyword 页散文）除字面 `键=选项` 形态外不在任何一路覆盖面内。已确认两 B 类形态（addredundant/nnroa）均落在 Options 条目正文内，实际影响未显现。 | 留痕或 §2.12 把「全量」表述精确为「三路互补近似全量」并登记该覆盖边界；后续如出现 Options 章节外散文提及误报样例再议扩面。 |
| R9 | P3 | 功能完整性（小缺口） | 留痕 §8 | 验收「A 类判归形态顺带记录 G16 实测对照」仅 prop=wrf 落了实测（t3）；`units=bohr`、`td=window` 无 G16 实测记录。本审查补测 `units=bohr`（水分子 STO-3G）= **Normal termination**，佐证该警告为词典口径保守残余（G16 引擎接受，按决策点 11 维持警告的口径自洽）；`td=window` 未测。「不作判据」故不阻塞。 | 留痕 §8 补 units=bohr/td=window 实测行（可引用本报告 §五.1 的补测结果），或注明仅 prop=wrf 一例对照。 |

## 四、测试与闸门实测（全部为本审查独立执行）

### 1. uv run pytest（全量）

- 工作区状态（含 B7 三用例）：`841 collected → 2 failed, 839 passed, 2 warnings in 120.40s`。
  失败恰为 `test_g11_charge_line_inline_comment`、`test_g11_comment_cut_quote_aware`
  （第三例通过，见 R6）；2 warnings 为既有 fastapi/starlette deprecation。
- 已提交 HEAD 基线（deselect 三个 B7 工作区用例）：
  `uv run pytest -q --deselect …×3` → **`838 passed, 3 deselected, 2 warnings`**，
  0 skipped——与收口登记数字一致，零回归成立。
- `target/release/hq` 存在（10-15 构建，区间未动 crates/），e2e 无静默跳过：
  `uv run pytest web/tests/test_e2e_fake_g16.py -q` → `3 passed`。

### 2. 治理与前端闸门

| 闸门 | 命令 | 实测结果 |
|---|---|---|
| 进度校验 | `uv run python scripts/validate_progress.py` | `OK`（rc=0） |
| CHANGELOG 一致 | `uv run python scripts/gen_changelog_md.py --check` | `OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致` |
| 设计令牌 | `uv run python scripts/check_tokens.py` | `OK — 逐变量 diff 为空`（暗 92/亮 31） |
| 对比度 | `uv run python scripts/check_contrast.py` | `OK — 全部组合 ≥ 4.5:1`（最低 4.65:1） |
| 前端离线 | `bash scripts/audit_frontend_offline.sh` | `零外链资源引用（豁免 5 组白名单前缀）`（重构建 dist 后复跑仍绿） |
| 生成物零 diff | `uv run python web/scripts/gen_models.py`；`npm run gen:types`（web/frontend） | 两者独立再生后 `git diff` 均零变化——openapi.yaml ↔ models.py ↔ contract.ts 三份产物一致，契约五处 description 更新完整 |
| 计划状态 | `uv run python scripts/check_plan_status.py` | `[FAIL] input-verify-gap-remediation-plan.md: 状态未回填为终态（当前「待执行」）`，rc=1——**符合预期**（状态行待 B7 完成后统一回填，发布前闸门，不判阻塞） |

### 3. 词典与审计工具幂等/指标复算

1. **词典规模与幂等**：`uv run python scripts/extract_keywords.py --out <tmp>` 连跑两次
   逐字节一致，且与在库 `web/src/parse/keywords.txt` 逐字节一致，**1345 行**（1166→1345
   吻合）。三处规模断言（test_extract_keywords 两处 + test_combo_templates
   `test_spelling_words_loaded_and_gate_ready`，后者同时断言 `SPELLING_MODE == "warn"`）
   均已在全量测试中验证为 1345。
2. **审计漏斗复算**（B5 基线词典 `/tmp` 复原 + 工具重跑）：
   - `audit_prose_options.py --dict <B5 词典>` 重跑 → 路① **79** / 路② **1306** /
     路③ **96** / merged **1435**，与留痕 §1 一致，且 path1/2/3 + merged 四个 JSON 与
     入库产物**逐字节一致**（用 B6 现行词典重跑则得 59/1139/91/1261——差集随词典
     状态移动，属预期）。
   - warn 层：B5 时点判定链重跑 = **1262**，与入库 warn_candidates.json 全等。
   - review 层：**475 不可复现**（R1）；入库 review_candidates.json 实测 475 条。
   - 裁决分布：`cut -f3 review_decisions.txt | sort | uniq -c` → admit_impl **4** /
     admit_manual **65** / admit_rule **89** / reject_a **37** / reject_noise **280**，
     合计 475，与留痕 §2 逐位一致。
   - 手工补录常量：`B6_MANUAL_OPTIONS` 实测 **76 条**（R2）；65 条裁决全部落在常量内。
3. **裁决原文依据抽查（≥10 条要求，实抽 14+5）**：14 条 admit_manual 直接对照
   gaussian-kb markdown 原文全部核实（casscf=slaterdet←opt.md L57 链接字面、
   casscf=spinorbit←cas.md/molspec.md、ccsd=maxcyc←gn.md L22、integral=superfine←
   integral.md L25 等价句、geom=notest←geom.md L307、scf=nodiis、admp=nobandgap←
   「The default is NoBandGap」、stable=noopt←「NoOpt prevents reoptimization and is
   the default」、population=saveesp←Pop=SaveXXX 枚举句、mm=oldqeq、pseudo=coreless、
   gfinput=coulomb、bomd=microcanonical←「one of these keywords: Microcanonical,
   Fixed, and Local」、nmr=cgst←input.md L178 Section Ordering 字面）。另核 5 条甄别
   保留争议例（transformation=abcd、population=no/noa/savento、cas=lanczos）全部在
   B6 词典在典，与留痕 §3 一致；reject_a/reject_noise 抽样 8 条判定理由与形态性质相符。
4. **语料基线 417→394 独立复算**（自写 harness 于 /tmp：`~/g16/tests/com` 1156 文件、
   逐文件 utf-8-sig 解码、`parse_input` 后 `file_warnings` 全集、统计
   route_option_unknown；抽样口径=全量重算）：
   - B6 词典：**394 文件 / 469 条 / 55 形态**（casefold 归一后），与
     corpus_baseline_b6.json 逐位一致（复算原始 keyword 含大小写变体 9 个，
     归并后完全吻合，如 Bohr 4 + bohr 10 = 14）。
   - B5 词典（monkeypatch `kw._cache` 后重跑）：**417 文件 / 498 条 / 66 形态**，
     与留痕 §7 一致。
   - 形态差集：消除 **12**（addredund、addredundant、emass=±1000、gradientonly、
     nnroa、nofulldiag、nostatic、rdopt、savenm、selectnm、vtight）与留痕列表逐位
     一致；新增 **1**（readanh）——B6 验收红线「不得含唯一前缀歧义翻转型新增误报」
     经本审查 G16 实测（t6 拒绝）证实该警告正确。

## 五、端到端与视觉审查记录

### 1. G16 Rev. C.01 冒烟（临时目录 /tmp/g16-smoke-b6-review，用后已清理）

本审查自建 gjf（整数坐标首跑触发 G16「Wanted a floating point number」报错，
改浮点坐标后重跑；gjf 哈希前缀与留痕不同系构造差异，结论一致）：

| 例 | route | 本系统判定（独立复算） | G16 实测 | 与留痕对照 |
|---|---|---|---|---|
| t1 | `#p hf/sto-3g opt=addredundant` | 零警告 | **Normal termination** | ✓ B 类入典零误报 |
| t3 | `#p hf/sto-3g prop=wrf` | `route_option_unknown: wrf` | **QPErr syntax error 拒绝**（route 行回显定位） | ✓ 决策点 9 删除 COMPAT 的实测输入成立 |
| t6 | `#p hf/sto-3g freq=readanh` | `route_option_unknown: readanh`（建议 readanharm） | **`End of line while reading DiNa input.`（l717.exe）拒绝** | ✓ 歧义警告正确、非新增误报 |
| t5（补） | `#p hf/sto-3g scf=conv` | 歧义警告 | **Normal termination（接受）** | ✓ 复现留痕「推翻 B5 拒绝推断」，keywords.py 注释修正有据 |
| tu（补） | `#p hf/sto-3g units=bohr` | A 类预期警告 | **Normal termination（接受）** | 补 R9 证据：警告系词典保守残余，与决策点 11 口径自洽 |

t2（freq=nnroa）/t4（freq=numer）未独立复跑（留痕在案；已复现例数满足 ≥3 例且覆盖
B 类正例、prop=wrf、歧义反例）。

### 2. web 服务 G10-a 接口冒烟（隔离实例，development.md §6.1）

`G16WEB_HOME=/tmp/g16web-b6-review G16WEB_ENGINE=0` 起 127.0.0.1:8401（health 返回
`v3.3.0-65-gf6129cef`，即审查 HEAD；用后已停实例并清理工作区）：

| 项 | 请求 | 实测 |
|---|---|---|
| 词典外 token warn 放行 | PUT /api/v1/combo-templates/1，route 含 `zzzzzq` | **HTTP 200**，`notice.spelling_warnings=["zzzzzq"]` |
| `ignore_spelling=true` 等价 | 同 route + ignore_spelling=true | **HTTP 200**，notice 与上完全一致 |
| 裸词缩写 | route=`#p fre geo` | **HTTP 200**，`spelling_warnings=["fre","geo"]` |
| 非拼写错误仍阻断、词典外不进 errors | route 缺 `#` + nproc=0 + mem=abc + zzzzzq | **HTTP 422**，reasons=[route_must_start_with_hash, nproc_not_positive_int, mem_value_invalid]，`keyword_not_in_dict` **不在** reasons |

四项全部符合 G10-a 预期行为。

### 3. 前端视觉复测（限制项）

- **L1（限制项）**：本审查工具面无内置浏览器（playwright），「豁免按钮消失、
  warn 琥珀提示展示」的视觉实测未能独立执行。已完成的替代证据：源码 grep 零残留、
  `npm run build` 重构建后 dist grep 零残留（`ignore_spelling:!1` 恒 false 编译产物
  亦核实）、audit_frontend_offline/check_tokens/check_contrast 三闸门绿。
  实施者自述 playwright 4 场景通过（不采信为审查结论）。**是否补一轮浏览器视觉
  复测交主代理裁量**；如需，建议按 development.md §6.1 拉起实例打开组合流模板
  弹窗，验证：含词典外 token 保存 → 200 且琥珀警告展示、无「忽略拼写警告并保存」
  按钮、%mem=0 仍红描边阻断。

## 六、总体结论

**有条件通过。**

B6 批次功能验收标准主体达成且经独立复现：G10-a enforce 屏蔽行为在接口级四项
证实、契约三份产物再生产物零 diff、前端豁免路径源码与构建产物零残留；G10-b
词典 1166→1345 幂等闸门与规模断言独立复现、三路差集与裁决分布逐位吻合、14 条
手工补录原文依据全部核实、语料基线 417→394（含消除 12 形态/新增 readanh）
全量复算逐位一致；G16 冒烟 5 例独立复现（含 prop=wrf 拒绝与 readanh 歧义警告
正确性这两条关键裁决背书）；全量测试 838 passed 0 skipped 零回归、hq 在位 e2e
实跑、除 check_plan_status（预期）外全部闸门绿。

**通过条件（整改后闭合）**：

1. **R1（P2）**：审计漏斗 warn→review 层（1262→475）过滤谓词入库脚本化并重跑
   比对，或在留痕补记确切谓词与操作方式、对 787 条排除项补轻量归因——完成前
   「全量审计」表述应收敛为「三路互补近似全量」（可随 B7 批次顺带处理，不阻塞
   B7 开工）。

P3 项（R2–R9）不阻塞合入，建议随批或随 B7 顺带处置：R6 请 B7 实施者知悉先行红
实为 2 例；L1 浏览器视觉复测待主代理裁量。
