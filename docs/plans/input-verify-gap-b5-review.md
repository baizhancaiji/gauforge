# 代码审查报告：输入文件勘误校验缺口补齐计划 B5 批次（G7 字典扩面 + G8 子选项归属校验）

## 一、审查依据与范围

- **依据**：`docs/plans/input-verify-gap-remediation-plan.md` §2.8（G7）、§2.9（G8）、§3 B5 验收标准、§3.1 批次流程、§8.6（B5 留痕，实施者自述，本审查逐项独立核实）；AGENTS.md §6.2 独立复核四查；契约 `docs/api/openapi.yaml`（Warning.kind 词表、`notice.route_option_warnings`）。
- **对象**：git 区间 `bbbdc390^..374247a2`，共 7 提交（bbbdc390 开工、0ec1e484 契约先行、af0cf810 测试先行红、57b34225 实现、5473f537 进度收口、1d4d837f 留痕、374247a2 断言修正）。
- **范围证实**：`git diff --stat bbbdc390^..374247a2` 实测 18 文件（+535/−26），全部与 B5 相关——计划点名的 6 个核心文件 + 契约生成物（`web/src/models/models.py`、`web/frontend/src/api/contract.ts`）+ 进度两件（CHANGELOG.jsonl/md、progress.json）+ 测试 fixture（`web/tests/fixtures/kb_route.md`）；无越界改动。审查期间工作树干净（HEAD = 374247a2）。
- **报告落盘**：`docs/plans/input-verify-gap-b5-review.md`（调用方指定，沿用 `input-verify-gap-b234-review.md` 结构惯例；该路径此前不存在，未覆盖任何既有报告）。

## 二、总体结论

**通过**（附 4 项登记性发现，均不阻断）。四查全部独立执行：835 passed 0 skipped 实测复现、语料基线 13 项指标中 12 项逐位吻合、端到端三通道（导入/分块保存/模板 enforce）实测通过且 line 语义正确、契约生成物再生零 diff。无 P0/P1 级发现。

## 三、功能完整性对照（计划 §3 B5 验收标准逐条）

| 编号 | 验收条目 | 实现位置 | 结论 |
|---|---|---|---|
| V1 | 字典重生成幂等闸门通过（1166 词条） | `web/src/parse/keywords.txt`（实测 1166 行）；`scripts/extract_keywords.py:315-329`（面⑥ `_route_alt_words`） | **已落地**。真实 KB 在机（`~/gaussian-kb/data/page_manifest.json`），独立重跑 `uv run python scripts/extract_keywords.py` 后 `diff` 零差异；`n`/`t` 两词入典实测（`git show` 前后 `keywords.txt` 仅增 `n`、`t` 两行） |
| V2 | 1164 断言同步（计划写「两处」） | `test_extract_keywords.py:134`、`test_extract_keywords.py`（loader 测试）、`test_combo_templates.py:435` | **已落地（实为三处）**。实测三处均为 1166；af0cf810 先行提交确实漏第三处（`git show af0cf810:web/tests/test_combo_templates.py` 第 435 行仍为 1164），57b34225 补齐——§8.6 口径修正 3 与 git 实况相符 |
| V3 | KB 缺失时 skip 须记录 | `test_extract_keywords.py:118-127`（`pytest.skip("gaussian-kb 结构化数据目录不存在")`） | **已落地**。本机 KB 在，全量 `uv run pytest` 实测 **835 passed, 0 skipped**——真实 KB 闸门真实执行，无「skip 冒充通过」 |
| V4 | `#t`/`#n` 模板 enforce 通过 | `test_combo_templates.py` `test_enforce_route_alternate_forms_pass` | **已落地**。端到端实测 `PUT /api/v1/combo-templates/1` route=`#t/#n/#p b3lyp/6-31g(d) opt` 均 200（见 §六） |
| V5 | `scf=conven`/`scf=conv`/`fre`/`geo` 精确匹配拒绝（缩写不识别） | `test_g7_abbreviation_exact_match_scope`、`test_enforce_bare_abbreviation_rejected` | **已落地（有据偏离，留痕一致）**。词典层面四 token 均不在典（实测）；`fre`/`geo` 裸词 enforce 拒绝（422，reason 两条 `keyword_not_in_dict`）实测通过；`scf=conven`/`scf=conv` 因 = 形 token 键名命中（B1 既有行为）enforce 放行——与 §3 验收字面「拒绝」不符，§8.6 口径修正 2 已登记裁决（以决策点 5「保持整词与键名精确命中」原文为准），判据自洽、测试按修正后口径固化 |
| V6 | G8 十条用例（在典零警告/未知选项/嵌套取值/跨关键字/`opt=(readfc)` 零警告/部分命中仅报未命中/近邻建议/IOp/ONIOM/External 零警告） | `test_parse_blocks.py` `test_g8_option_unknown_matrix`、`test_g8_unique_prefix_and_non_option_heads` | **已落地**。十条用例全部存在且非恒真（逐一含具体断言，见 §五「防凑绿核查」）；独立函数级探针逐例复现通过 |
| V7 | warnings kind 词表增 `route_option_unknown` | `docs/api/openapi.yaml`（Warning.kind description）；生成物 `models.py`、`contract.ts` 同步 | **已落地**。`test_contract_rest.py` 新增契约断言；`gen_models.py` + `npm run gen:types` 再生后 `git diff` 实测零残留 |

计划 §2.9 补充要求核对：
- **触发通道**：五通道全覆盖——预览（`routers/candidates.py:164`）与导入/提交（`services/verify.py:64`）同走 `file_warnings`，分块保存（`services/candidates.py:51-62` `_route_warnings` 第三路）、模板保存（`services/combo_templates.py:103-106`），与 §2.11 矩阵「route 子选项归属（G8）= 预览/导入/提交/分块保存/模板全部警告」一致。
- **分级（决策点 6 仅 warn）**：模板通道 `check_route_options(route_cf)` 无条件附加于 notice、不参与 422 判定（实测 `opt=(readfcht)` 200）；其余通道仅入 warnings 数组。符合。
- **选项级近邻建议**：实测 `opt=(calfcf)` → `suggestion=calcfc`；`opt=(readfcht)` → `suggestion=readfc`。符合。
- **「G4 触发词选项集匹配复用同一拆解辅助」**：未落实——`section_ordering.py`（B2 落地）未复用 `_split_key_options`（全仓 grep 仅 keywords.py 内部引用）。见发现 R6。

## 四、问题清单

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| R1 | P2 | 可维护性 | `web/src/parse/keywords.py:385-398` | `check_route_options` 在 `return out`（:384）之后残留 14 行不可达死代码（旧 token 判定逻辑：`t = tok.strip()` … `return bool(sep) and ...`），系编辑残留；行为无影响但明显降低可读性 | 删除 :385-398；可加 ruff 死代码类检查防再犯 |
| R2 | P2 | 文档与事实（留痕取数口径未注明） | `docs/plans/input-verify-gap-remediation-plan.md:1210-1211`（§8.6 口径修正 1） | 留痕称原口径（无唯一前缀判活）「官方语料实测 45.7% 文件误报」；本审查以相同判定链独立复刻（仅去掉 `o.startswith(base)` 判活分支）实测 **509/1156 = 44.03%**。数量级与结论（原口径大量误报）一致，但逐位不可复现且复刻细节（是否保留单字母/isdigit 豁免等）未注明，违反 AGENTS §6.2「取数口径注明」 | 补注 45.7% 的取数口径（复刻脚本/豁免集），或改按本审查 44.03% 口径修正留痕 |
| R3 | P2 | 功能完整性（词典覆盖缺口样例遗漏） | `web/src/parse/keywords.py:272-273`（`_PAREN_TAIL` 注释）；语料实测 | `td=window(13,-12)` 是官方 TD=Window 选项（带参数），词典无 `td=window` 条目（`grep -cx td=window` = 0），语料 **7 文件**命中 `route_option_unknown`（「window 疑似非 TD 的官方选项」）。该形态被列为 `_PAREN_TAIL` 的设计示例注释，暗示已被设计覆盖，实际仍报警告；§8.6 B 类样例清单（opt=addredundant、freq=nnroa、units=bohr）未含 td=window。warn 级不阻断，属 B 类（面⑤覆盖缺口）同性质 | 将 `td=window` 并入另批词典扩面清单；修正常量注释避免「已覆盖」误导 |
| R4 | P3 | 文档一致性 | `docs/plans/input-verify-gap-remediation-plan.md:1199-1200`（§8.6 提交列表） | 留痕称 B5「共 6 提交」并逐一列名，但区间实为 7 提交——374247a2（断言修正）在留痕提交 1d4d837f 之后追加，提交列表未更新（374247a2 自述「本条漏并 57b34225,补登」指变更说明口径，非列表修订） | §8.6 提交列表补 374247a2 一条 |
| R5 | P3 | 技术方案符合性 | `web/src/parse/keywords.py:337-340` | 计划 §2.9「G4 的触发词『选项集』匹配复用同一拆解辅助，不另写括号解析」未落实：`section_ordering.py` 未引用 `_split_key_options`。实际危害为零（G4 触发词为头部精确等值/选项集精确包含，语义不同源），属计划文字失效 | 下轮计划修订时删除或改写该句 |
| R6 | P3 | 逻辑与边界 | `web/src/parse/keywords.py:270`（`_VALUE_FORM_HEADS`） | `iop` 白名单成员实际不生效：`IOp(6/50=1)` 经 `_split_key_options` 拆出 key=`iop(6/50`（:291 `eq > 0` 分支按第一个 `=` 切分），零警告的真实原因是「key 不在典」而非白名单；oniom/external 两成员真正生效。结果正确、注释口径与机制不符 | 注释据实修正（iop 靠键名不在典兜底），或拆解时对括号内含 `/` 的头部回退白名单匹配 |
| R7 | P3 | 逻辑与边界 | `web/src/parse/keywords.py:422-427`（拼写 continue） | 键在典且选项型的 token 不再做整词近邻：畸形 `opt==calcfc`（双等号，base 为空串直通）由改动前「可能得 keyword_spell 近邻建议」变为零警告。极边缘畸形输入，warn 级宁漏勿误口径内 | 备案即可，不要求整改 |
| R8 | P3 | 约定一致性 | `web/src/services/combo_templates.py:103` | 模板通道传入 casefold 后 route 文本，`keyword` 字段为小写化原文；导入/保存通道保留用户原大小写。与既有 `route_duplicates`/`spelling_warnings` 同源惯例一致，契约未约束大小写 | 备案；如需统一留待既有惯例一并处理 |

## 五、测试与闸门实测（全部独立复跑，不引用实施者输出）

| 闸门 | 命令 | 实测结果 |
|---|---|---|
| 全量测试 | `uv run pytest` | **835 passed, 0 skipped**（115.64s；与实施者声称一致）。`target/release/hq` 在位（`ls -la` 确认，e2e 无静默跳过条件） |
| 进度校验 | `uv run python scripts/validate_progress.py` | OK，退出码 0 |
| CHANGELOG 一致 | `uv run python scripts/gen_changelog_md.py --check` | OK——CHANGELOG.md 与 jsonl 一致 |
| 设计令牌 | `uv run python scripts/check_tokens.py` | OK——明亮/暗色各 31 变量逐变量 diff 为空 |
| 对比度 | `uv run python scripts/check_contrast.py` | OK——全部组合 ≥ 4.5:1（最差 text-faint/bg-inset 4.90:1） |
| 前端离线 | `bash scripts/audit_frontend_offline.sh` | OK——dist 零外链资源引用（豁免 5 组白名单前缀） |
| 契约再生 | `uv run python web/scripts/gen_models.py` && `npm run gen:types` | `git diff` 两生成物均 **0 行**残留 |
| 字典幂等 | `cp keywords.txt /tmp` → `uv run python scripts/extract_keywords.py` → `diff` | **零 diff**（真实 KB 在机），1166 行 |

**防「断言放松凑绿」核查**：
- af0cf810 先行红属实：`git show af0cf810:web/src/parse/keywords.py | grep -c check_route_options` = **0**，同提交测试文件引用 **24** 处——收集期导入失败即红。
- G8 用例逐条含具体值断言（kind/keyword/suggestion/line/message 关键字），无恒真断言；`test_g8_line_offset_absolute` 的 5→6 修正是断言纠正（geom= 位于 route 第 2 行 + 偏移 4），本审查独立验证 6 为正确值（374247a2 修正方向正确，非放松——正确断言更严）。
- 1166 断言三处同步实测；`test_real_kb_inrepo_dictionary_matches_regeneration` 含逐字节对比 + skip 显式声明，本机无 skip。

## 六、端到端与视觉审查记录

- **视觉 UI/UX：不适用**——本批次无前端界面改动（`contract.ts` 仅为类型生成物；前端三闸门已作为代码层佐证通过）。
- **端到端实测（隔离环境：`/tmp/b5_e2e` 临时 SQLite + 临时 inputs 目录，跑完已清理；不触真实工作区）**：
  1. **导入通道**：`import_files` 含 `geom=(allcheck,xyzzy)`（route 位于全文件第 5 行）→ 成功条目 warnings 返回 `[(route_option_unknown, xyzzy, line=5)]`，**line 为全文件绝对行号** ✓。
  2. **分块保存通道**：`save_block(tid, "route", ...)`——单行 `geom=(allcheck,xyzzy)` → line=5；两行 route（geom= 在 route 第 2 行）→ **line=6**（1 起 route 内行号 + scan_spans 0 起偏移，`blocks.py:513-543` 语义核实一致）；`#p opt=(calcfc,ts) freq density=curr` → 零警告 ✓。
  3. **模板 enforce 通道**（HTTP TestClient `PUT /api/v1/combo-templates/1`）：`#p opt=(readfcht) freq` → **200**（不阻断）+ `notice.route_option_warnings=[{line:1, keyword:"readfcht", suggestion:"readfc"}]`（line 为模板 route 文本行号，与契约 description 一致）；`#p scf=conven opt` → 200 零警告（唯一前缀判活）；`#p scf=conv opt` → 200 + 警告 keyword=`conv`（歧义前缀不判活）✓。
- **G16 真机冒烟**：不适用——§3.1 冒烟节点仅设 B1/B2/B4，B5 无节点，§8.6 如实登记「未执行」。

**语料基线独立重算**（`~/g16/tests/com` 全量 .com，scan_spans 提取 route + `check_route_options`，与实施者口径同源）：

| 指标 | 实施者声称（§8.6） | 独立重算 | 判定 |
|---|---|---|---|
| 语料文件数 | 1156 | 1156（目录另有非 .com 杂项 5 个，不在口径） | ✓ |
| 命中文件数 | 420（36.33%） | 420（36.33%） | ✓ 逐位一致 |
| 警告条数 | 507 | 507 | ✓ |
| 去重形态数 | 69 | 69（keyword 原文 casefold 口径；key=base 归一则 66，口径未注明但 69 可复现） | ✓ |
| 超 3 条文件 | 6 个，最大 5 条 test0386 | 6 个：test0386=5、test0385/0431/0442/0985/1187 各 4 | ✓ |
| geom=modela | 265 条 | 265 | ✓ |
| scf=novaracc | 43 | 43 | ✓ |
| scf=noincore | 20 | 20 | ✓ |
| units=bohr | 14 | 14 | ✓ |
| cphf=ultrafine | 14 | 14 | ✓ |
| opt=addredundant（B 类） | 登记存在 | 6 条 | ✓ 存在 |
| 原口径（无唯一前缀判活）误报文件 | 45.7% | **44.03%（509 文件）** | ✗ 见 R2 |

- **A 类归因抽验**：`geom=modela` 不在典（`grep -ix modela keywords.txt` 空）——G03 旧形态按词典口径报 unknown，与 G8「对照官方手册」立题一致，非误报逻辑缺陷。
- **样本抽验**：`test0386.com` route `#p ram1 opt=(gdiis,big) test geom=(nodist,noangle,nodihed) nosymm` → 恰 5 条警告（OPT 2 条 + GEOM 3 条），message 均同时给出选项与左侧关键字，与 §2.9 条目形态要求一致。

## 七、验收标准判定与结论

**B5 验收标准（计划 §3）逐条判定**：V1–V7 全部通过（V5 为已登记的有据偏离，偏离裁决 §8.6 口径修正 2 经核实与实现、测试三方一致）。§8.6 留痕与实测事实核对：测试数字（835/0）、词典（1166 = 1164 + n + t、幂等无 skip）、三处口径修正、语料基线主体数字（12/13 项逐位吻合）均属实；仅 45.7% 一项不可逐位复现（R2）与提交列表缺 374247a2（R4）。

**总体结论：通过。**

条件（登记即可，均不阻断合入）：
1. R1 死代码删除（建议随下一代码批次顺带处理）；
2. R2 留痕 45.7% 补注取数口径或修正数字；
3. R3 `td=window` 并入另批词典扩面清单；
4. R4 §8.6 提交列表补 374247a2。
