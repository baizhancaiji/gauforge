# 代码审查报告：输入文件勘误校验缺口补齐计划 B5–B7 批次（G7/G8 + G10-a/G10-b + G11）

> 审查人：code-reviewer 子代理（AGENTS.md §6.2 第二层独立复核，只审不改）。
> 审查日期：2026-10-21。全部结论来自本审查独立执行的命令与实测输出，
> 不采信实施者自述与 §8 留痕数字；除本报告外未创建/修改任何仓库文件，
> 临时实例与 G16 冒烟均在 /tmp 下进行且已清理。

## 一、审查依据与范围

- **依据**：`docs/plans/input-verify-gap-remediation-plan.md` 全文——§2.8（G7）、
  §2.9（G8）、§2.13（G10-a/G10-b，决策点 11/12/13）、§2.14（G11）、
  §2.11 矩阵相关行、§3 批次表 B5/B6/B7 验收标准、§3.1 批次节点与 G16 冒烟
  清单、§4 契约影响、§5 测试总纲、§2.12 已知限制（区分「已登记限制」与
  「未登记缺陷」，前者核其登记准确性）。文中行号与「现状」以 2026-10-18
  HEAD 为基线、经多轮原位勘误，本审查一律以当前文本方案语义对照实际代码。
- **对象**：git 区间 `f5387615..04db8a4b`（HEAD），共 **48 提交**。批次切分
  与 §8.6–§8.11 对照：B5 = bbbdc390（开工）至 374247a2 共 7 提交；B6 =
  24967697（计划再修立项）经 31a2cb60（审计工具）、79b2f2ab（词典
  1166→1345）、1f248515（审计留痕）至 **f6129cef（G10-a enforce 屏蔽，批次
  最后提交，序列勘误以 prose-audit §9.2 R3 为准）**；B6 审查整改 =
  55dcfd69/bc0a47a9/96bc31df（R1 过滤层脚本化先行红→实现→留痕勘误）；
  B7 = 2ed38a76（先行红）、444ba1ec（开工）、29c71d88（实现）、a4f68b71
  （收口）；B7 审查整改 = 06a82794、1a954f72、6a1d4f06；终审再修收口 =
  71d2a022…04db8a4b。历史审查报告五份（b5/b6-code/prose-audit/B7/
  final-review-r1）作为整改复核对象逐条验证，不作为结论依据。
- **范围证实**：`git status` 工作树 clean；`git rev-list --count
  f5387615..HEAD` = 48；`git diff --stat f5387615..HEAD` 实测 51 文件
  （+52035/−221），全部落在计划点名文件与留痕/进度/生成物内；
  `crates/` 零改动（内核未触碰）；审查全程重跑生成物（gen_models/gen:types）
  与前端重构建后 `git status` 仍 clean，零残留。
- **报告落盘**：`docs/plans/input-verify-gap-remediation-plan-B57-review.md`
  （调用方指定；落盘前确认该路径不存在，未覆盖任何既有报告）。

## 二、逐批次验收标准对照（验收点 / 实测命令 / 结果）

### B5（§2.8 G7 + §2.9 G8）

| 编号 | 验收点 | 实测命令（摘要） | 结果 |
|---|---|---|---|
| V1 | 字典重生成幂等闸门（B5 时点 1166；现含 B6 为 1345） | `git show 57b34225:web/src/parse/keywords.txt \| wc -l` = 1166；现库 `wc -l` = 1345；`extract_keywords.py --out /tmp` 连跑两次 + 与在库 `cmp` | **已落地**。真实 KB 在机（`~/gaussian-kb/data/page_manifest.json`）、无 skip，两次重生成逐字节一致且与在库逐字节一致 |
| V2 | 词条规模断言三处同步（§8.6 口径修正 3：先行提交漏第三处、实现提交补齐） | `git show af0cf810:web/tests/test_combo_templates.py \| grep -c 1164` = 2（漏改实证）；`git show 57b34225:… \| grep -c 1166` = 2（补齐）；当前 `grep -n 1345` 于 test_extract_keywords.py:137/212 + test_combo_templates.py:445 | **已落地**。三处现均为 1345；先行红漏改与 §8.6 留痕吻合 |
| V3 | KB 缺失时 skip 须记录、不得当通过 | 全量 `uv run pytest`（本机 KB 在，真实执行） | **已落地**。848 passed **0 skipped**，无 skip 冒充 |
| V4 | `#t`/`#n` 模板保存通过 | 隔离实例 `PUT /api/v1/combo-templates/2` route=`#t b3lyp/6-31g(d) opt` | **已落地**。HTTP 200，notice 零警告（n/t/p 在典 `grep -cx` 各 1） |
| V5 | `scf=conven`/`scf=conv` 组合词经键名命中放行；`fre`/`geo` 词典层面不识别（enforce 拒绝口径已随 B6 决策点 12 屏蔽为警告） | 探针 `token_in_dict`：scf=conven/conv=True、fre/geo=False；`check_route_spelling("#p fre geo")` → keyword_spell + suggestion=freq/geom；隔离实例 PUT route=`#p fre geo` → 200 + `spelling_warnings=["fre","geo"]` | **已落地**。缩写不识别限于词典层面成立；warn 近邻提示正确；矩阵「route 拼写」模板列=警告口径符合 |
| V6 | G8 十条用例（在典零警告/未知选项/嵌套取值/跨关键字 readfcht/readfc 零警告/部分命中仅报未命中/calfcf 附 suggestion=calcfc/IOp/ONIOM/External 零警告） | 临时探针 `check_route_options` 逐例（/tmp/b57_review/probe.py，36/37 过，唯一失选项见问题 F-1 归因）；测试用例 `test_g8_option_unknown_matrix` 等全绿 | **已落地**。12 项 G8 判定链探针全过（含 `opt=(calcfc,xyzzy)` 仅报 xyzzy、`readfcht` suggestion=readfc、三值形零警告、`opt==calcfc` 静默合 §2.12 登记） |
| V7 | warnings kind 词表增 `route_option_unknown` | `grep -n route_option_unknown docs/api/openapi.yaml`（:1477 词表、:1061 notice 载体）；生成物再生日 diff=0 | **已落地**。openapi ↔ models.py ↔ contract.ts 三份一致 |
| V8 | 唯一前缀判活（§8.6 口径修正 1） | 探针：`density=curr`/`freq=numer` 零警告；`scf=conv`、`freq=readanh` 歧义仍警告（readanharm/readanharmonic；suggestion=readanharm） | **已落地**（`scrf=conven` 示例笔误见问题 F-1，判为文档问题非实现缺陷） |

### B6（§2.13 G10-a + G10-b）

| 编号 | 验收点 | 实测命令（摘要） | 结果 |
|---|---|---|---|
| W1 | 模板保存拼写错误仅警告、零 422（enforce 屏蔽，决策点 12） | 隔离实例（127.0.0.1:8421，health=`v3.3.0-86-g04db8a4b` 即审查 HEAD）PUT route=`#p zzzzzq` → **200** + `notice.spelling_warnings=["zzzzzq"]`；route=`nofatsharp`+nproc=0+mem=0+cpu=abc → 422 且 reasons=[route_must_start_with_hash, nproc_not_positive_int, mem_value_invalid, cpu_list_invalid]，**keyword_not_in_dict 不在其中** | **已落地**。`combo_templates.py:40 SPELLING_MODE="warn"` 单点、模块 docstring 切换纪律已改写 |
| W2 | `ignore_spelling=true` 与不传行为一致 | 同 route 两 PUT（false/true）→ 响应 notice **逐键相等**；`test_oov_tokens_pass_with_warnings_after_enforce_off`（test_combo_templates.py:209）在 848 全量内 | **已落地**。字段保留不删、屏蔽期不生效 |
| W3 | 前端豁免按钮隐藏以浏览器实测验收（AGENTS §6.2） | 本轮：`ComboTemplatesModal.vue` grep（按钮代码已删、ignore_spelling 恒 false）；`npm run build` 后 dist grep——「忽略拼写警告」/saveWithExemption/exemptTokens/hasKeywordErrors 零残留、`ignore_spelling:!1` 恒 false 实证；audit_frontend_offline/check_tokens/check_contrast 三闸门绿 | **静态证据全过；本轮浏览器视觉实测未覆盖**（子代理无 playwright 工具）——历史留痕 prose-audit §9.3 L1 已有 playwright 三场景实测（按钮移除/琥珀警告/硬错误阻断）在案，**本轮未独立复测，是否补测待调用方裁量** |
| W4 | 面⑤三路互补差集近似全量审计清单落盘 + 逐条人工复核留痕 | `docs/plans/audit/` 12 文件在库（path1/2/3、merged、warn、review、excluded、review_flat 511 行、review_detail 475 行、review_decisions.txt 475 行、make_decisions.py、corpus_baseline_b6.json）；B5 时点 worktree（31a2cb60）+ 现行 `audit_prose_options.py` 重跑 → 79/1306/96/1435/1262/475/787，**七份 JSON 与入库逐字节一致**（R1 整改闭环独立证实）；裁决分布 `cut -f3 review_decisions.txt \| sort \| uniq -c` = admit_impl 4/admit_manual 65/admit_rule 89/reject_a 37/reject_noise 280（=475） | **已落地**。漏斗全程可复现；`B6_MANUAL_OPTIONS` 实测 76 条（23 键组），与留痕 §3 R2 补记一致 |
| W5 | 复核通过缺口全部入典（幂等闸门 + 规模断言同步） | 词典 1166→**1345**；`grep -cx opt=addredundant / freq=nnroa` 各 1；幂等与断言见 V1/V2 | **已落地** |
| W6 | `opt=addredundant`/`freq=nnroa` 零警告复测 | 探针两例零警告；隔离实例 PUT `#p opt=addredundant` → 200 且三类 notice 全空；G16 直跑 `#p hf/sto-3g opt=addredundant`（gjf sha256 前缀 3a2af98c）→ **Normal termination** | **已落地**（零误报 + G16 背书双证） |
| W7 | `td=window`/`units=bohr`/`geom=modela` 等 A 类维持预期警告 | 探针三例均 route_option_unknown 恰 1 条；语料基线 modela 265/bohr 14/ultrafine 14 计数逐位复算（见 W9） | **已落地**。`_PAREN_TAIL` 注释与 `workspace.py` 模块头单位口径（KB/MB/GB/TB/KW/MW/GW/TW）已按 A 类/官方口径修正（代码实读确认） |
| W8 | G16 冒烟按 §3.1 B6 清单（B 类复测、prop=wrf 一例、缩写判活正反例） | 本轮独立直跑（G16 Rev. C.01，`~/g16/g16`，日志确认版本）：opt=addredundant=Normal、freq=numer=Normal（判活正例）、scf=conv=Normal（歧义警告系保守残余，G16 接受——与 D-1 勘误口径一致）、freq=readanh=**Error termination**（DiNa 非标准输入拒绝，歧义警告正确）、prop=wrf 语料基线 wrf 形态 route_option_unknown 警告在案（B6 审查 t3 QPErr 拒绝留痕） | **已落地**。`COMPAT_EXTRA_KEYWORDS` 已删（section_ordering.py 仅存注释引用），prop=wrf 出典（grep -cx = 0）与 G16 拒绝的裁决自洽 |
| W9 | 语料基线回归对照复跑、逐条归因、无歧义翻转型新增误报 | 自写 harness（/tmp/b57_review/corpus.py）全量 1156 文件复算：6 kind 条数/命中文件数/55 形态/每形态计数与 `corpus_baseline_b6.json` **逐位一致**（394 文件/469 条 route_option_unknown）；`readanh` 新增歧义警告经本轮 G16 直跑拒绝证实为正确警告 | **已落地**。零偏差 |
| W10 | 契约：模板端点 description（enforce→仅警告、ignore_spelling 不生效）+ 生成物零 diff；warnings 词表不变 | `docs/api/openapi.yaml`:88-92/1013-1061/3183-3184 实读；gen_models + gen:types 再生后 `git diff` 均 0 行；kind 词表较 B5 无增删 | **已落地** |

### B7（§2.14 G11）

| 编号 | 验收点 | 实测命令（摘要） | 结果 |
|---|---|---|---|
| X1 | `parse_charge_tokens` 归一化前剥离引号外首个 `!` 及后内容（引号感知） | 代码实读 `blocks.py:144-172`；探针：`0 1 ! neutral singlet`→`["0","1"]`、`0,1 0,1 0,1 ! cp pairs`→6 token、`0 1 "a!b"`→引号内 `!` 替换为分隔符不截断（`["0","1",'"a','b"']`，docstring P3-2 整改后的两通道差异口径相符） | **已落地** |
| X2 | 四通道放行（预览/导入/提交零错误、编辑保存 200） | 隔离实例端到端：POST 导入两 gjf（sha256 前缀 41d3ce49/726b4955）→ 201 error=None；preview → parse_errors=[]、charge_mult=`'0 1'`/`'0 1 0 1 0 1'`（不含注释）；PUT blocks/charge_mult 传注释原文 → **200** 放行；POST submit → 200（normalized=False 系「文本已规范无需处理」语义，契约 :1740 核实） | **已落地** |
| X3 | `charge_mult` 规范化输出不含注释文本 | 同 X2 实测值 | **已落地** |
| X4 | 剥离后 token 不足/非整数仍报错 | `test_block_save.py::test_charge_mult_inline_comment_allowed`（:234，B7 审查 P1-1 整改用例）内 `pytest.raises(ApiError)` 于 `["0 ! only charge"]`；`test_parse_blocks.py:245` 守卫例；848 全量内通过 | **已落地**。编辑保存通道（原 422 主战场）已有持久化回归保护 |
| X5 | 既有电荷行用例（斜杠/en-dash/多组对）不回归 | 848 passed 全量（含 :225-231 斜杠/en-dash 用例）；探针 `0/3`→`["0","3"]`、`–1 2`→`["-1","2"]` | **已落地** |
| X6 | G16 冒烟一例（电荷行行内注释） | `#p hf/sto-3g` + `0 1 ! neutral singlet`（sha256 前缀 381879cd）直跑 → **Normal termination**，log `Charge = 0 Multiplicity = 1` 正常读取 | **已落地**。实测与手册一致，无 §2.12 分歧登记需求 |
| X7 | 无 schema 与 kind 词表变更；CHANGELOG 登记接受集扩大 | B7 区间 openapi/warnings 词表零改动（B7 审查证实 + 本区间 diff 复核）；CHANGELOG unreleased 含 G11 fixed/parse 条目（含「与 route 通道 C3 管道同规…」口径），`gen_changelog_md.py --check` 绿 | **已落地** |

## 三、四查结论（AGENTS §6.2）

1. **校验可复现**：全量 `uv run pytest` **848 passed, 0 skipped**（2 warnings
   为 fastapi/starlette deprecation 既有环境噪声），`target/release/hq`
   在位（10-15 构建）无 e2e 静默跳过；`validate_progress.py`、
   `gen_changelog_md.py --check`、`check_plan_status.py`（10 份计划终态）、
   `audit_frontend_offline.sh`（重构建 dist 后复跑仍绿）、`check_tokens.py`、
   `check_contrast.py` 全部 rc=0。契约生成物独立再生（gen_models +
   gen:types）零 diff。全部独立执行，非引用实施者输出。
2. **指标可复现**：①词典幂等——真实 KB 两次重生成逐字节一致且与在库一致
   （1345）；②B6 审计漏斗——B5 时点 worktree 重跑现行审计工具，七份产物与
   入库**逐字节一致**（79/1306/96→1435→1262→475+787），裁决分布 4/65/89/
   37/280 逐位吻合，`B6_MANUAL_OPTIONS` 76 条；③语料基线——自写 harness
   全量 1156 文件复算，6 kind 双维度与 55 形态逐位一致（394/469）；
   ④G8/G10/G11 判定链探针 37 项（36 过，1 失项经三重证据归因为计划文档
   笔误，见 F-1）；⑤G16 Rev. C.01 直跑 5 例行为与系统判定对照全部自洽。
3. **范围可证实**：48 提交、51 文件 diff 实测；crates/ 零改动；声称未触碰
   的文件（link0_rules.py、其余前端组件）不在 diff 清单；B7 与 B6 文件集
   无交集、B5 时点词典 1166 与先行红漏改第三处断言均以 `git show` 实证。
   重跑生成物与前端构建后工作区仍 clean。
4. **端到端可用**：隔离实例（`G16WEB_HOME=/tmp/b57_review/g16web-home`、
   G16WEB_HQ_BIN 指向在库 hq、127.0.0.1:8421，health 版本即审查 HEAD）——
   G10-a 六项接口实测 + G11 四通道实测全过（见第二节表），实测后实例已停
   止、临时工作区待清理；G16 直跑在 /tmp 隔离目录完成（Fort 文件等残留随
   临时目录清理）。历史整改复核：B5 R1（死代码删除，AST 扫描 return 后
   不可达零残留）/R2–R4（留痕勘误在文）/R5–R8（备案与改写在文）、B6 R1
   （过滤层脚本化逐字节复现）/R2–R9、B7 P1-1（test_block_save 用例在）、
   P3-1（progress.json updated=`2026-10-21T09:03+0800` 带偏移）、P3-2
   （docstring 限定表述）、final-review D-1…I-2（主文档原位勘误逐处核对）
   ——全部在当前代码与文档中成立，未发现整改回退。

## 四、问题清单

| 编号 | 级别 | 分类 | 位置 | 描述与实测依据 | 整改建议 |
|---|---|---|---|---|---|
| F-1 | P3 | 文档一致性（计划正文示例笔误） | `docs/plans/input-verify-gap-remediation-plan.md` §2.9（「如 `density=curr`、`freq=numer`、`scrf=conven`」）与 §8.6 口径修正 1（「`scrf=conven` 官方正面例合法」） | 唯一前缀判活正面例键名笔误：应为 `scf=conven` 而非 `scrf=conven`。实测三重证据：①`grep -x "scrf=con[a-z]*" web/src/parse/keywords.txt` 空（scrf 无 con* 词条）；②gaussian-kb 官方 `scrf.md` 的 #### 选项条目清单无 Conventional（`scf.md:123` 有 `#### Conventional`）；③探针 `check_route_options("#p scrf=conven")` 产 route_option_unknown 恰 1 条（判定链正确行为），而 `#p scf=conven` 零警告（conventional 唯一前缀判活）。实现无缺陷，B5 审查/B6 留痕实测对象亦为 scf=conven | 下轮文档维护时将两处 `scrf=conven` 改为 `scf=conven`；无需动代码与测试 |
| F-2 | P3 | 可维护性（docstring 口径滞后） | `scripts/extract_keywords.py:49`（「B6 三路差集全量审计逐条裁决」）、`scripts/audit_prose_options.py:2`（「三路差集全量审计」） | final-review D-3 将主文档五处「全量审计」收敛为「三路互补差集近似全量审计」，但两处活代码 docstring 未同步；CHANGELOG unreleased 的 G10-b 条目同字样属 append-only 历史条目不在此列 | 随下个代码批次顺带将两处 docstring 措辞对齐「三路互补差集近似全量审计」；不影响功能 |

无 P0/P1/P2 级发现。已登记的 §2.12 已知限制核验：`scf=conv` 歧义保守残余
（G16 接受而警告照发，本轮直跑复现 t5 同结论）、`freq=readanh` 歧义警告与
G16 拒绝一致（本轮直跑复现）、`opt==calcfc` 静默（探针证实）、缩写词级精确
匹配（fre/geo 探针证实）、prop=wrf 兼容项关闭——登记内容与实现行为逐条相符，
登记准确性成立。

**视觉 UI/UX 维度**：B6 前端改动（豁免按钮移除）本轮以源码 grep + 重构建
dist grep（豁免文案与三个函数标识符零残留、`ignore_spelling:!1` 恒 false）
+ 三道前端闸门绿作静态证据；**内置浏览器视觉实测本轮未覆盖**（子代理无
playwright 工具），历史留痕 prose-audit §9.3 L1 有 playwright 三场景实测
在案。该维度本轮不给出独立「视觉通过」结论，是否补测待调用方裁量。

## 五、总体结论

**通过。**

B5/B6/B7 三批验收标准逐条独立复现成立（第二节 22 项对照全部落地）：全量
848 passed 0 skipped、七项闸门与生成物零 diff 全绿、词典幂等 1345、审计
漏斗七产物逐字节可复现、语料基线逐位吻合、G10-a 六项接口与 G11 四通道
端到端实测通过、G16 Rev. C.01 直跑 5 例（B 类零误报、判活正例、两歧义
警告方向均正确、电荷行注释正常读取）行为自洽；五份历史审查报告的全部
整改声称在当前代码与文档中验证成立，无回归。

条件（登记即可，均不阻断）：
1. F-1：计划文档两处 `scrf=conven` 示例笔误随下轮文档维护改为 `scf=conven`；
2. F-2：两处脚本 docstring「全量审计」措辞随下个代码批次对齐 D-3 口径；
3. 浏览器视觉实测本轮未覆盖（静态证据 + L1 历史留痕在案），如需本轮独立
   视觉证据，按 development.md §6 拉起实例对组合流模板弹窗补测三场景
   （豁免按钮不存在、词典外 token 保存 200 且琥珀警告展示、%mem=0 红描
   边 422）。
