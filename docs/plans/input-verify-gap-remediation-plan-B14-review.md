# 代码审查报告：输入文件勘误校验缺口补齐计划 B1–B4 批次（G0/C1/C2/C3 + G4/G9 + G1/G2/G3 + G5/G6）

## 一、审查依据与范围

- 依据：`docs/plans/input-verify-gap-remediation-plan.md` 全文逐节对照——§2.0.1（G0）、
  §2.1–§2.3（C1/C2/C3）、§2.4（G4）、§2.5（G1）、§2.6（G2/G3）、§2.7（G5/G6）、
  §2.10（G9）、§2.11（规则×通道矩阵）、§3 批次表 B1–B4 验收标准列、§4 契约影响、
  §5 测试总纲、§6 决策点 1–9、§2.12 已知限制。
- 对象：git 区间 **`v3.3.0..f5387615`（38 提交，2026-10-19）**。批次切分经
  `git log --oneline v3.3.0..f5387615` 与计划 §8.1–§8.5 留痕逐条对照确定：
  B1=3ca70180 开工 → c6b0d6ef 复审闭环（含整改 93cbac04 与独立审查 a3f28538）；
  B2=b42961ab → 8895192b；B3=9462637f → 701f17ef；B4=6885ba57 → 0c60733a；
  §8.5 审查整改=f1188024 → f5387615。B5 及之后（af0cf810 起，至 HEAD 04db8a4b）
  不在本批范围；其触及本批文件者（blocks.py/keywords.py/section_ordering.py/
  candidates.py/workspace.py 共 5 文件 +194/−28）按交叉影响观察，不改变本批结论。
- 范围证实：`git diff --stat v3.3.0..f5387615`（37 文件 +4335/−292）逐文件核对；
  工作树 clean（`git status` 无输出）、B2–B4 审查遗留的仓库根 `fort.7` 已确认删除
  （`ls fort.7` → No such file）。契约生成物可再生零残留（见第四节）。
- 报告落盘：`docs/plans/input-verify-gap-remediation-plan-B14-review.md`（调用方指定，
  落盘前确认无同名报告，未覆盖任何既有文件）。
- 审查执行日：2026-10-21；方式：AGENTS §6.2 独立复核四查，全部结论来自本审查
  独立执行的命令与实测输出，不采信实施者自述与 §8 留痕数字。

## 二、逐批次验收标准对照（§3 批次表逐条实测）

### B1（G0+C1+C2+C3）

| 验收点 | 实测命令/方式 | 结果 |
|---|---|---|
| `warnings` 通道就位、默认空列表、含 `message` | `parse_input(WATER)` 断言 `set(r)=={blocks,parse_errors,multistep,warnings}`、`warnings==[]`（test_parse_blocks.py:131 独立复跑）+ 全矩阵实测 | 达成 |
| 五类误拒形态+无等号空格形+引号值+括号 Geom+`Geom=Check` 转绿 | 隔离实例逐形态跑 `check_route_spelling`：逗号分隔/`!` 注释/`kw(option)` 无等号/`@file` 含 `/N`/`= `两侧空格/`opt (calcfc, ts)`/`External="RunTink Amber"`/`6-31g(d,p)`/`IOp(6/50=1)` 全部零警告 | 达成 |
| Checkpoint 缺电荷/缺 title 被拒、AllCheck 不变 | `parse_input("#p b3lyp/6-31g(d) geom=checkpoint\n\n")` → title+charge_mult 双报；括号形/逗号后空格/`geom = allcheck`/`geom (allcheck)`/`geom=check` 五态实测一致；**G16 Rev. C.01 直跑复核**：Checkpoint 缺电荷 l101 报 `Charge and Multiplicity card seems defective`（与 §8.1 留痕一致） | 达成 |
| 既有全量测试不回归、记录 passed/skipped | 本次独立复跑 848 passed / 0 skipped（含 B5–B7 后续批次用例；B1 收口时点为 751，经 git 区间测试文件 diff 佐证增量口径） | 达成 |
| 契约：共享 Warning schema（message 必填、suggestion/task_id 可选）；InputPreview 增可选 warnings；生成物零 diff | openapi.yaml Warning schema（required=[line,keyword,kind,message]）+ InputPreview.warnings + `gen_models.py`/`npm run gen:types` 再生后 `git status --porcelain` 零输出（本次独立复跑） | 达成 |

### B2（G4+G9）

| 验收点 | 实测命令/方式 | 结果 |
|---|---|---|
| `section_ordering.py` 表与 §1.2 逐行一致（59=4+54+1） | 隔离脚本打印全表：59 行、core=4/additional=54/automatic=1、terminator no 共 7 行（core link0 + additional 6）、section_id 唯一、official 字段与 §1.2 59 行逐行顺序一致 | 达成 |
| `any_trigger` 只消费 additional 且普通 route 为 False | `any_trigger("#p b3lyp/6-31g(d) opt freq")==False`、`("# hf/sto-3g")==False`；`#p gen`→True、`#p guess=lowsymm`→True；表驱动测试 test_section_ordering.py 断言在位 | 达成 |
| G9 route/title EOF 阻断、两种吞并归因、空分子说明缺节、分子说明/Variables EOF 警告 | 隔离实例实测：route EOF→「route 节未以空行终止」+title 缺失文案含根因提示「（route 未以空行终止时其后内容会并入 route）」；title 直连电荷行→「title 节未以空行终止」；空分子说明→`缺少分子说明节（原子定义行）`（checkpoint/allcheck 档不报三态实测）；`molecule_unterminated`/`variables_unterminated` 警告在位；allcheck 纯 EOF 仍报 route 未终止（route 不豁免） | 达成 |
| roadmap §2.7 回补（2 例外 + Title 行括注 + Checkpoint title 补全） | roadmap.md:290–292 逐字核对：例外全集 7 项含 CASSCF=SpinOrbit、Pop=NBO6Read；Title 行「仅 Geom=AllCheck 可省略」；分子说明行「Checkpoint 时仅原子坐标可省，title 与电荷/多重度行仍必须存在」 | 达成 |
| 契约：kind 词表增 `molecule_unterminated`/`variables_unterminated`；附加节 terminator 记 parse_errors；parse_errors description 更新 | openapi.yaml Warning.kind 词表 12 项逐字核对（1 既有 + 11 新增与 §4 清单完全一致）；parse_errors description 含 G9/G4 口径与「提交通道先行规范化，纯 EOF 消除、吞并仍拒」两通道差异 | 达成 |

### B3（G1+G2+G3）

| 验收点 | 实测命令/方式 | 结果 |
|---|---|---|
| 导入/提交响应携带 warnings；导入 422 `details.errors[]` 不携带 | 隔离临时实例：导入拼错关键字（optt）→ 201 且 `files[].warnings` 含 keyword_spell；导入 Checkpoint 缺节 → 422 VALIDATION_FAILED、错误条目无 warnings 键；`grep verify_and_store` 全部 6 处调用点（routers/candidates.py:192、routers/queues.py:137、history.py:202、resume.py:256、workflows.py:254/276）逐一核对 | 达成 |
| 三个响应返回点全部取 `res["normalized"]` | candidates 路由 `res["normalized"]`、queues 路由 `if res["normalized"]`（dict 恒真风险消除）、history `res["normalized"]` 逐一读码核对；`test_requeue_normalized_flag_from_dict_result` 回归在位 | 达成 |
| resume 响应透传 warnings | resume.py:256–264 读码 + openapi ResumeConfirmResponse.warnings（789 行）契约在位 | 达成 |
| 队列提交 warnings 带 task_id | queues.py `collected.append({**w, "task_id": m["id"]})`；单任务提交（candidates 路由）不填；test_queue_submit_collects_member_warnings_with_task_id 在位 | 达成 |
| 重复/错位用例按 §2.6 判定表与 §2.11 矩阵各通道一致 | G2 判定表 7 行 + R7 组合场景 + 白名单外重复，11 例隔离实测全部吻合（mp2 mp2 警告/freq freq=readfcht 豁免/opt opt=(calcfc,ts) 豁免/双选项集警告/scf=tight scf=xqc 警告/iop 并写豁免/#p opt freq 无）；G3 两情形（% 入 route=parse_errors、% 落 title=parse_errors）+ route 缺失时 title 节内任意位置同判 + 文件头前导 % 不在检测面 + 分子说明 % 行不扫描，四态实测吻合 | 达成 |
| 契约：kind 增 route_duplicate；CandidateCreate.files/SubmitResponse/ResumeConfirmResponse 增可选 warnings（openapi 先行） | openapi 三响应字段核对；提交序列 9462637f（契约）→ 6b8941eb（测试）→ cc0b6559（实现）→ c477e672（进度）符合文档先行纪律 | 达成 |

### B4（G5+G6）

| 验收点 | 实测命令/方式 | 结果 |
|---|---|---|
| §2.7 用例全绿；§2.11 矩阵逐格符合 | 隔离实例 38 个形态逐格实测（详见第三节矩阵记录）：`-1 2`/`0 0`/首组负值阻断、多组对全组规范化 `0 1 0 1 0 1`、无佐证警告/counterpoise 佐证零警告、`%mem=2W`/`%mem=0`/`%mem=2GW`、`%nprocshared=0`、`%cpu=0-5/2` 放行与 `0-5/x` 警告、501 字符警告、`%save`/`%kjob l502 2` 零警告、`%foo=1` unknown、`%mem` 重复 duplicate、O-Bq/X/Foo/Zz/C-CT--0.06/C(Iso=13,Fragment=2)/`C,0,0,0`/`C/0/0/0`、BOM 剥离——全部符合 | 达成 |
| `%mem=2W` 编辑保存阻断、导入/提交警告；`%mem=0` 同口径；`%cpu=0-5/2` 通过 | 隔离临时实例：save_block link0 `["%mem=2W"]` → 422 `mem_value_invalid`；导入通道同值 → 非阻断 `link0_value_invalid` 警告；模板 `mem_gb="0"` → 422（决策点 8）；`cpu_list_count("0-5/2")==3` | 达成 |
| 多组电荷对/负多重度佐证/自由格式分隔符/Foo 不告警/Zz 告警/X 哑原子/BOM 落盘剥离 | 全部实测通过；BOM 导入后落盘字节 `not raw.startswith(b"\xef\xbb\xbf")` 实测为 True，且三读取路径（verify.py:41、candidates.py:456、resolve_title:225）统一 utf-8-sig | 达成 |
| kind 词表增 7 项 | openapi Warning.kind 词表含 link0_value_invalid/link0_line_too_long/link0_directive_unknown/link0_directive_duplicate/title_forbidden_char/atom_label_unknown/molecule_multiple_charge_pairs | 达成 |
| link0_rules.py 下沉 + workspace 复用（历史缺陷 mw 差 1024 倍等修正） | workspace.py:30–46 薄封装读码确认；`mem_to_gb` 单位集 KB/MB/GB/TB/KW/MW/GW/TW 与值域同源、QW 删除、GW/TW 补齐；`%mem=2GW` 导入零警告（旧缺陷回落缺省注入路径消除） | 达成 |

## 三、四查结论（AGENTS §6.2）

### 1. 校验可复现（全部独立重跑）

| 闸门 | 实测输出 |
|---|---|
| `uv run pytest -q` | **848 passed, 0 skipped**，2 warnings（三方库弃用告警），122.14s；`target/release/hq` 存在（17,957,408 字节），e2e 无静默跳过 |
| `uv run python scripts/validate_progress.py` | OK |
| `uv run python scripts/gen_changelog_md.py --check` | OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致 |
| `uv run python scripts/check_plan_status.py` | OK — 10 份计划文档状态均已回填为终态 |
| `bash scripts/audit_frontend_offline.sh` | dist 零外链资源引用（豁免 5 组白名单） |
| `uv run python scripts/check_tokens.py` | OK — 逐变量 diff 为空 |
| `uv run python scripts/check_contrast.py` | OK — 全部组合 ≥ 4.5:1 |
| 生成物闸门 | `web/scripts/gen_models.py` + `npm run gen:types` 后 `git status --porcelain` **零输出**（models.py/contract.ts 再生与提交版逐字节一致） |

### 2. 指标可复现

- 词条 1166（B5 后 1345）：本批区间内 1166 断言三处（§8.6 口径修正 3）经
  test_extract_keywords/test_combo_templates 全量跑通过，区间口径与留痕一致。
- section_ordering 59=4+54+1：独立脚本复算逐行吻合（见第二节 B2 行）。
- `any_trigger` 普通 route 为 False：复算为 False。
- §2.11 矩阵 22 行规则：parse_input 层 38 形态逐格实测与矩阵登记一致；发现两处
  轻微缺口见问题清单 P3-2/P3-3。

### 3. 范围可证实

- B1–B4 区间 38 提交与 §8.1–§8.5 留痕逐条对应；每批均为
  「契约文档 → 测试先行 → 实现 → 进度同步」序列（提交类型与顺序经 git log 核对）。
- 声称未改动部分零改动：`_scan_spans`/`verify_and_normalize` 无 geom 语义
  （grep 证实仅 parse_input 消费 `_geom_exemption_tier`）；B234 审查整改
  （d44df202/9a3cbd9f）仅触及声称文件。
- 契约生成物零 diff：重跑双生成命令后 `git status --porcelain` 零输出。

### 4. 端到端可用（隔离临时实例，/tmp 工作区、用毕清理）

| 场景 | 实测结果 |
|---|---|
| 导入正常文件 | 201，warnings=[] |
| 导入拼写错误（optt，近邻 opt） | 201 非阻断，warnings 含 keyword_spell + suggestion |
| 导入 Checkpoint 缺 title/电荷 | 422 VALIDATION_FAILED，reason=INPUT_PARSE_FAILED，错误条目无 warnings 字段 |
| 导入重复关键字（mp2 mp2） | 201 非阻断，warnings 含 route_duplicate |
| BOM 文件导入 | 落盘副本无 BOM 字节（剥离后哈希/落盘） |
| 提交核验 verify_and_store | 返回 {"normalized","warnings"} 两键 |
| 分块保存 route 行内 `!` 注释 | 放行 |
| 分块保存 title 含 `%chk=` | 422 link0_misplaced |
| 分块保存 %mem=2W | 422 mem_value_invalid |
| 分块保存电荷行行内注释 | 放行 |
| 多步 --Link1-- 导入 | 422 INPUT_MULTISTEP_UNSUPPORTED |
| 模板通道（G2/温度/enforce 屏蔽/mem/cpu） | route_duplicates 随 notice 携带；`freq(readanharmonic)` 补温；词典外 token warn 放行；mem_gb=0/cpu 非法阻断 |
| G16 Rev. C.01 直跑冒烟（本机 ~/g16 可用） | ①Checkpoint 缺电荷：l101 `Charge and Multiplicity card seems defective`——C1 收严与官方一致；②正常作业生成 chk 后 AllCheck 全省略：Normal termination——AllCheck 豁免档正确（冒烟在 /tmp 运行，零仓库残留；整数坐标被该机 G16 拒绝属 §8.9 已登记实测口径，改浮点坐标通过） |

## 四、问题清单

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| R1 | **P2** | 功能完整性 | `web/frontend/src/views/CandidatesView.vue`（B1–B4 区间与至今 HEAD 零改动） | 计划 §2.0.1/§2.5「涉及文件」与 §5 总纲明列「CandidatesView.vue 渲染导入/提交 warnings」，至今未落地且 §8 留痕未见登记该取舍：导入响应 `files[].warnings`、提交/队列/历史/续跑四响应的 warnings 在前端无任何渲染点（全前端仅 BlockEditor.vue 渲染分块保存 warnings、ComboTemplatesModal.vue 渲染模板 notice）。B2–B4 审查（input-verify-gap-b234-review.md §六）曾将此缺口并入 R5 说明，但 §8.5 整改处置仅落实了预览通道数据面对齐（后端 file_warnings 单点），前端渲染未处置——API 层警告通道已齐备，用户在导入与提交确认界面看不到警告 | 落地 CandidatesView 导入条目与提交确认框的 warnings 渲染（复用 Warning schema 类型，视觉实测验收）；或按计划修订流程在 §8 登记口径偏离（前端渲染另批立项）并同步 §2.5/§5，两侧必须一致 |
| R2 | P3 | 测试有效性 | `web/tests/`（全量） | 计划 §5 明文「模板『不适用』必须有对应断言，不能只写注释」未落实：§2.11 矩阵中模板列的不适用格（title≤5 行/title 禁字/电荷格式/分子说明非空/多组对佐证/原子行/G3/附加节终止等规则在模板通道；Geom 豁免边界在分块保存通道）均无行为断言——模板校验函数对这些字段不产生校验属「字段不存在」的结构事实，未见任何测试固化 | 为矩阵「不适用」格补最小断言（如模板载荷含未知字段不产生 422、save_block 不做 geom 豁免校验），或在 §8 登记该验收项的口径修订 |
| R3 | P3 | 逻辑与边界 | `web/src/parse/link0_rules.py:108–117` | `%nproc=`（等号后空值）在导入/提交/预览通道**零警告**（`if val:` 短路跳过校验），而同形的 `%mem=`（空值）会触发 link0_value_invalid；编辑保存通道对空值有 empty_value 阻断。§2.11 矩阵「%nproc 正整数：预览/导入/提交=警告」在空值形态不成立 | `check_link0_lines` 对 `%nproc` 系空值补一条 link0_value_invalid 警告（与 `%mem` 空值口径拉齐） |
| R4 | P3 | 可维护性 | `web/src/services/candidates.py:106` | `_validate_one` 返回的 `"bom_stripped"` 键无任何消费方（import_files 仅取 error/data/warnings），属死代码 | 删除该键或注明调试用途 |
| R5 | P3 | 约定违例（文档一致性） | `web/src/parse/section_ordering.py:156`（pred_read_window docstring） | 「缩写 RW 词面过短不纳入（§2.12 已知限制）」引用落空——计划 §2.12 已知限制表中无 ReadWindow 缩写（RW）专项条目，引用指向不存在的登记 | 补 §2.12 条目或改写引用为「人工转换取舍」（并随批留痕） |

**存疑项**：无——本批全部结论均有可复现实测支撑。

**已登记已知限制核对**（§2.12，区分「已登记」与「新缺陷」）：Guess=Cards EOF 分歧、
`#p restart` 豁免档、`opt==calcfc` 静默、title 禁字行级粒度（实测 bad_title! 仅报
首个 `_`）、键内歧义前缀保守残余、`@file/2/3` 多级后缀宽容、`Geom=Modify` 不覆盖、
`%rwf` 不校验——均按登记口径复测成立，登记准确，不计为新问题。
`COMPAT_EXTRA_KEYWORDS=("prop=wrf",)` 于 B4 收口时点在位（git show f5387615 证实），
B6 按 §2.12/决策点 9 经 G16 实测拒绝后删除（HEAD 的
`test_g4_compat_prop_wrf_removed_after_g16_smoke` 断言在位）——合法演进，非本批偏差。

**B5–B7 交叉影响观察**（不在本批范围，未据以下调整结论）：keywords.py +152 行
（G8 选项化/唯一前缀判活/G10-b 词典扩面）、blocks.py +32 行（G11 电荷行注释剥离）、
section_ordering.py 删 COMPAT 项、combo enforce 屏蔽（决策点 12）——抽查行为
（G8 十条用例、G11 注释剥离、prop=wrf 删除）均与后续批次留痕一致。

## 五、端到端与视觉审查记录

- 端到端：隔离临时实例（/tmp/gf-review-b14，隔离 SQLite + 独立 HOME，用毕已清理，
  零仓库残留——R9 教训执行）实测 12 场景四通道行为（见第三节第 4 条表），全部符合。
  G16 Rev. C.01 直跑冒烟 2 例（Checkpoint 拒/AllCheck 放行）在 /tmp 运行复核通过。
- 视觉 UI/UX：本批区间前端改动仅 BlockEditor.vue +13 行（保存响应 warnings 渲染）
  与 contract.ts 类型再生；该渲染已在 B1 独立审查中按 playwright 快照/截图/计算
  样式实测通过（b1-review §六，本审查核对其截图结论与当前代码一致——
  `.be-warn` 渲染路径与 SaveWarning 类型消费未变）。本批其余无视觉 UI/UX 变化；
  导入/提交 warnings 的前端渲染缺失已作为 R1（P2）登记，其视觉验收随整改执行。

## 六、总体结论

**通过（附一项随批条件）。**

B1–B4 四批的验收标准逐条独立复算达成：G0 通道、C1/C2/C3 正确性修复（G16 直跑
背书）、G4 官方 59 行表固化、G9 七项检测、G1 六调用点改造、G2 判定表、G3 两情形
分级、G5 七项值域与 G6 原子行文法全部按方案落地；两轮历史审查（B1 R1–R5、
B2–B4 R1–R11）的整改在当前代码逐条验证成立且未引入回归；八项闸门全绿
（848 passed / 0 skipped、hq 产物在位、生成物零 diff）；端到端四通道与 G16 冒烟
两例独立复核通过。未发现 P0/P1 问题。

条件（随批处置，不构成合入阻断）：

1. **（P2，R1）** CandidatesView/提交确认框的 warnings 前端渲染缺口须二选一收口：
   落地渲染（含视觉实测），或按计划修订流程在 §8 登记口径偏离——该缺口已跨两轮
   审查遗留，不得再无留痕顺延；
2. （P3，R2–R5）随批处置：矩阵「不适用」格断言、`%nproc=` 空值警告、
   `bom_stripped` 死键、§2.12 引用落空。

> 审查方式声明：本报告全部结论来自独立执行的命令与隔离实例实测（命令随正文记录），
> 未采信实施者自述与 §8 留痕数字；临时实例与冒烟产物均在 /tmp 并已清理。
