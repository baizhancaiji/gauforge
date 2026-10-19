# 代码审查报告：输入文件勘误校验缺口补齐计划 B2–B4 批次（G4/G9 + G1/G2/G3 + G5/G6）

## 一、审查依据与范围

- 依据：`docs/plans/input-verify-gap-remediation-plan.md` §2.4（G4 Section Ordering 固化）、
  §2.5（G1 拼写接入导入/提交）、§2.6（G2 重复关键字判定表 + G3 Link0 错位）、
  §2.7（G5 值域拉齐 + G6 原子行文法）、§2.10（G9 核心节空行检测）、
  §2.11 五通道矩阵、§3 B2/B3/B4 验收标准、§4 契约影响、§5 测试方案总纲、
  §8.2–§8.4 实施留痕；语料噪声双阈值（新增警告文件 ≤5%、同文件同 kind ≤3）。
- 对象：git 区间 `c6b0d6ef..HEAD`（HEAD = 0c60733a），**实测 16 个提交**（任务描述
  写 19 个，`git log --oneline c6b0d6ef..HEAD | wc -l` = 16：b42961ab 开工 →
  22d9a543/48a4eac2/bb0af603/ab596fc8/8895192b B2 → 9462637f/6b8941eb/cc0b6559/
  c477e672/701f17ef B3 → 6885ba57/57362a48/bfe567d3/4227a859 B4 → 0c60733a 留痕），
  32 文件 +2256/−191。
- 范围证实：`git diff c6b0d6ef..HEAD --stat` 逐文件核对；**B1 修复零回退**——
  `git diff a3f28538..HEAD -- web/src/parse/blocks.py` 中 `_geom_exemption_tier`
  仅 docstring 私有名随 R5 整改更名（scan_spans/split_lines 公共化），档位判定逻辑
  未动且新增三处正确消费（G9 项 2/4/5）；`_AT_SUFFIX_N`（@file/N 豁免）与
  combo `has_freq` token 头部判定（R2 整改）区间内零 diff；行为抽查
  `geom=(allcheck,modredundant)`→allcheck、`geom=checkpoint`→checkpoint、
  `@mols.dat/3` 拼写零警告均复现。工作区有一枚未跟踪残留 `fort.7`（B4 G16 冒烟
  在仓库根运行的积分文件，2026-10-19 12:13，文件头与 §8.4 g6ff 场景吻合），见 R9。
- 报告落盘：`docs/plans/input-verify-gap-b234-review.md`（调用方指定）。
- 审查执行日：2026-10-19；方式：AGENTS §6.2 独立复核四查，全部结论来自独立实测，
  不采信实施者自述（含 §8 留痕数字，逐项重跑重算）。

## 二、总体结论

**有条件通过。**

B2–B4 三批的验收标准（§3 对应行）逐条达成：G4 官方 59 行表固化且表驱动测试逐行
断言、G9 七项检测全部落地、G1 三响应 warnings 与 6 处调用点改造、G2 判定表与
豁免公式、G3 两情形分级、G5 值域/指令文法/行长/BOM//n、G6 鬼/哑原子与多组对——
独立实测与闸门复跑全部吻合；先行红（B2 收集失败、B4 12 failed）经 git worktree
实跑证实；B1 修复无回退；hq 产物在位、e2e 无静默跳过。存在 **6 项 P2**（Link0
警告行号口径偏离 G0、BOM 读取路径未按方案统一 utf-8-sig、电荷行斜杠分隔的
编辑保存通道误拒、模板 notice.route_duplicates 契约缺口、预览通道缺 route
拼写/重复警告、语料条数阈值超标未复审登记），无 P1；另有 5 项 P3 随批处置即可。

## 三、功能完整性对照

| 编号 | 计划条目 | 实现位置 | 结论 |
|---|---|---|---|
| G4-1 | §1.2 全表 59 行落码（4 core + 54 additional + 1 automatic），散文行 11 具名单列 | `web/src/parse/section_ordering.py:190-346` | 已落地（逐行清点 59=4+54+1；`test_section_ordering.py` EXPECTED 59 元组逐行断言，no 例外全集 7 行断言；external_readinput 以 `_and(_key,_opt_any)` 组合表达、功能等价） |
| G4-2 | `_EXTRA_KEYWORDS` 替换为 official 表驱动 + `COMPAT_EXTRA_KEYWORDS=("prop=wrf",)`；wants_extra 查 `any_trigger`；core 行 all 不入 any_trigger | `section_ordering.py:358-366`、`blocks.py:445,554` | 已落地（实测普通 route `any_trigger=False`；`#p prop=wrf` True；裸子串禁令遵守——谓词全为头部等值/选项集包含） |
| G4-3 | 附加节 terminator：仅末节 EOF 检测；空集合不报；全 yes 报 parse_errors；混合保守不报；automatic 不参与 | `blocks.py:482-492`、`section_ordering.terminator_missing:369-373` | 已落地（Gen 单触发 EOF 阻断、带空行不报、Gen+Pop=NBORead 混合不报三态实测通过） |
| G9-1 | route EOF 阻断 + title 落空根因提示 | `blocks.py:274-277,321-326` | 已落地（实测「route 节未以空行终止」+「（route 未以空行终止时其后内容会并入 route）」两段文案） |
| G9-2 | title EOF 阻断（AllCheck 豁免集不报；route 终止不豁免） | `blocks.py:318-320` | 已落地（`test_g9_title_eof_allcheck_exempt_route_still_required` 在位；allcheck 档 title EOF 实测零错误） |
| G9-3 | charge_mult 失败文案附「误并内容」根因 | `blocks.py:383-389` | 已落地（吞并形态实测命中） |
| G9-4 | 空分子说明缺节固定 parse_errors（checkpoint/allcheck 档不报） | `blocks.py:433-436` | 已落地（普通档报、checkpoint/allcheck 两档不报三态实测） |
| G9-5/6 | 分子说明/Variables EOF 非阻断警告 | `blocks.py:437-441,475-480` | 已落地（kind=molecule_unterminated/variables_unterminated 实测；Variables: 无空行直接跟原子行以区头为边界的语料校准同步在位） |
| G9-7 | --Link1-- 前缺空行附注 | `blocks.py:212-213` | 已落地（实测 message 含「--Link1-- 前缺少空行，官方要求」） |
| G1 | 导入 `_validate_one` 返回 {error, warnings}；`verify_and_store` 返回 {normalized, warnings}；6 处调用点；三响应返回点取 `res["normalized"]`；resume 透传；队列 task_id；422 不携带 warnings；不引入 enforce | `candidates.py:53-104,128-171`、`verify.py:27-63`、`routers/candidates.py:187-194`、`routers/queues.py:126-175`、`history.py:201-207`、`resume.py:256-266`、`workflows.py:254,276` | 已落地（6 处调用点逐一核对；queues `if res["normalized"]` 真值正确；`test_requeue_normalized_flag_from_dict_result` 真值回归在位；实测导入成功条目携带 warnings、422 details.errors[] 无 warnings 字段） |
| G2 | token 头部聚合 + §2.6 判定表；容器头白名单 16 项；豁免公式 `head=="iop" or (head in _CONTAINER_HEADS and bare>=1 and valued>=1)` | `keywords.py:188-235` | 已落地（判定表 7 行全数实测：mp2 mp2 警告 / freq freq=readfcht 豁免 / opt opt=(calcfc,ts) 豁免 / 双选项集警告 / scf=tight scf=xqc 警告 / iop 并写豁免 / #p opt freq 无；组合场景口径见 R7） |
| G3 | 情形 1（% 入 route 文本）/情形 2（% 成 title 行）均 parse_errors；分块保存 reason=route_line_link0_forbidden/link0_misplaced；检测范围限 route 起→title 止 | `blocks.py:266-271,296-303`、`candidates.py:_validate_section route/title 分支` | 已落地（两情形 + 缺 route 时 title 后错置可达场景 + 分子说明 % 行不扫描，四态实测通过；文件头前导 % 行归 Link0 收集不检测——§8.3 已登记口径） |
| G5-1 | 电荷行多组对：偶数整数、首组 mult≥1 阻断、后续组 mult≠0、负值宽容+佐证警告、charge_mult 全组规范化 | `blocks.py:334-389`、`candidates.py:_validate_section charge_mult` | 已落地（`-1 2`/`0 0`/`0 1 0 -1`/Guess=Fragment/Fragment 参数佐证/counterpoise 全形态实测；首组负值阻断与 §2.11 矩阵「首组多重度 >0」一致） |
| G5-2 | 值域统一：W/B 删除、%mem>0、`_MEM_VALUE_RE` 下沉 `link0_rules.py`、parse 侧 warnings；`_mem_to_gb` 删 QW 补 GW/TW | `link0_rules.py:23-35,93-102`、`workspace.py` 薄封装 | 已落地（实测 2GW=16.0GB、1KW=8KB、2MW=16MB、2W/2QW 拒绝、%mem=0 警告；旧表 mw 差 1024 倍与 kw KeyError 修正经 `test_dispatch_engine` 双断言） |
| G5-3 | Link0 单行 ≤500：编辑保存阻断 / 导入提交警告 | `link0_rules.py:76-82`、`candidates.py:_validate_section link0` | 已落地（501 字符实测警告；`test_save_link0_rejects_overlong_line` 阻断） |
| G5-4 | 指令文法：无等号指令集、24+ 已知指令、未知/重复仅警告、多 = 取值不二次切分 | `link0_rules.py:38-65,84-124` | 已落地（%save/%kjob l502 2/%subst l913 零警告、%xyz=1 unknown、%mem 重复 duplicate 实测；%gpucpu=0-3=0-1 按首个 = 切分） |
| G5-5 | title 禁用字符：parse_input 记 warnings | `blocks.py:304-313` | 已落地（@ 字符实测警告、行号正确；编辑保存保持阻断既有） |
| G5-6 | BOM：导入 utf-8-sig 解码 + 落盘剥离字节（哈希/落盘以剥离后为准）；parse_input 入口防御剥离 | `candidates.py:84-90,142-160`、`blocks.py:200-201` | 部分落地（导入通道逐字节测试与实测通过；**verify_and_store/save_block 读取路径仍 decode("utf-8")，与方案「所有读取路径统一 utf-8-sig」不符**——R2） |
| G5-7 | %cpu /n 后缀全通道放行、非法形态警告/阻断 | `link0_rules.py:128-151` | 已落地（0-5/2→3 核、0-5/0 拒绝实测；`test_save_link0_accepts_slash_n_cpu`） |
| G6 | 鬼原子判定先于元素识别（O-Bq 计行不计式）、哑原子 X、最长元素符号前缀（Foo→F 不告警、Zz 警告）、首 `-` 前片段（C-CT--0.06）、括号参数表、自由格式分隔、原子序数 1..118、未知标签仅 warnings | `blocks.py:79-129,414-430` | 已落地（全部形态实测通过；XX/`-`/小写 x 的宽容口径系语料校准且 §8.4 留痕，宽于计划字面向不误报方向） |
| B2 契约 | kind 词表增 molecule_unterminated/variables_unterminated；parse_errors description 更新；roadmap §2.7 例外全集回补 | `openapi.yaml:1458-1470,1539-1556`、`roadmap.md:292` | 已落地（例外 7 项含 CASSCF=SpinOrbit、Pop=NBO6Read；Title 行 AllCheck 括注与 Checkpoint 补全 B1 已落，本批补齐例外全集） |
| B3 契约 | CandidateCreate.files/SubmitResponse/ResumeConfirmResponse 增可选 warnings（文档先行 9462637f） | `openapi.yaml:782-787,1698-1706,1733-1742` | 已落地（生成物零 diff 实测） |
| B4 契约 | kind 词表增 7 项；charge_mult 多组对 description；BOM 口径入导入 description | `openapi.yaml:1461-1467,1518-1524,2084-2086` | 已落地（词表 11 项=1 既有+2 B2+1 B3+7 B4 与计划 §4 完全一致） |
| §3.1 纪律 | 文档→测试→实现→进度提交序列；当批 CHANGELOG/progress 登记 | 16 提交、CHANGELOG unreleased 9 条（B1 4 + B2 2 + B3 2 + B4 1） | 达成（先行红经 worktree 实跑证实：48a4eac2 点 test_section_ordering 收集失败、57362a48 点 12 failed；progress in_progress 归位） |
| §5 阈值 | 语料噪声：新增警告文件 ≤5% 且同文件同 kind ≤3，超阈复审 | `~/g16/tests/com` 1158 输入文件复算 | 部分达成（17 文件/1.47% 达标；**test0380.com title_forbidden_char 4 条超条数阈值，§8.4 留痕仅登记文件维度**——R6） |

## 四、问题清单

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| R1 | **P2** | 逻辑与边界 | `web/src/parse/link0_rules.py:76,121`（`enumerate(lines, 1)` 与 duplicate 固定 `"line": 1`） | Link0 非阻断警告的 `line` 是 **link0 块内序号**而非 G0 规定的全文件绝对行号：实测 `parse_input("\n\n%mem=2W\n#p …")`（% 行在全文件第 3 行）警告 `line=1`；`link0_directive_duplicate` 的 line 恒为 1（重复位置信息丢失）。`check_link0_lines(lines)` 接口不含块起始行号，parse_input 收集时丢弃了原行号。与计划 §2.0.1「line：全文件 1 起，与 parse_errors 相同」直接冲突，导入/提交/预览/分块保存四通道的 Link0 值域/指令警告行号定位均失准 | `check_link0_lines` 增加 `line_offset` 参数（blocks.py 收集时记录首 % 行的全文件行号传入），duplicate 条目取该 kind 首次出现的块内行号 + offset；补前导空行/注释场景的行号断言用例 |
| R2 | **P2** | 技术方案符合性 | `web/src/services/verify.py:39`、`web/src/services/candidates.py:445` | 计划 §2.7 项 6 明文「`verify_and_store`、`save_block`、`resolve_title` 等所有读取路径统一 `utf-8-sig`」，实现仅在导入解码（`candidates.py:84`）与 parse_input 入口防御剥离落地；提交/保存读取路径仍 `decode("utf-8")`。实测：inputs 目录手工放置带 BOM 副本时 `verify_and_store` 正常解析（parse_input 兜底）但 **BOM 字节随规范化写回保留落盘**（与「剥离后的字节用于哈希与落盘」不符）；`save_block` 场景下 `scan_spans` 对首行 `\ufeff#p` 的 `startswith("#")` 判定失效（route span 丢失）。实际风险受限：导入通道已剥离、历史带 BOM 文件在旧版导入时即被拒，库内不存在该类文件——但方案字面未满足 | 三处读取路径（verify.py:39、candidates.py:445、resolve_title 的读取处）改 `decode("utf-8-sig")`，或登记「以 parse_input 入口防御剥离替代」的口径偏离并同步计划 §2.7；补一条带 BOM 磁盘副本的提交/保存用例 |
| R3 | **P2** | 逻辑与边界 | `web/src/services/candidates.py` `_validate_section` charge_mult 分支（仅 `replace(",", " ")`）与 `_expected_blocks` 同处 | 电荷行**斜杠分隔**（官方自由格式分隔符，`C/0/0/0` 同族）通道不一致：`parse_input("0/1")` 放行且规范化 `charge_mult="0 1"`，编辑保存 `_validate_section("charge_mult", ["0/1"])` 实测 422 must_be_integer_pairs 拒绝——§2.11 矩阵「分子说明自由格式分隔符 | 各通道均为无法解析时才阻断」被违反；en-dash `–`（parse_input 宽容换负号）同理。多组对 `0,1 0,1 0,1` 编辑保存放行正常（实测），缺口仅斜杠/en-dash 两形。测试无斜杠分隔电荷行用例 | `_validate_section`/`_expected_blocks` 的电荷行分词对齐 parse_input 口径（`replace("–","-").replace(","," ").replace("/"," ").split()`，建议抽 `blocks.parse_charge_tokens` 单点）；补 `["0/3"]`、`["0,1/0,1"]` 编辑保存放行用例 |
| R4 | **P2** | 技术方案符合性 | `web/src/services/combo_templates.py:190-191`（`notice["route_duplicates"]`） | 模板保存响应新增 `notice.route_duplicates` 字段（Warning 对象数组），**openapi.yaml 的 notice properties、models.py、contract.ts 三处生成物均无该字段**——违反 roadmap §1「契约先行」与 §4「生成物零 diff」纪律（响应形态超出契约）。`test_combo_templates.py:450-466` 已断言该字段，功能本身符合 §2.6「触发：…组合流模板保存」 | openapi.yaml `ComboTemplateMutationResult.notice` 增可选 `route_duplicates`（items 引用 Warning schema），重跑 gen_models + gen:types 零 diff；同批顺带把 B3/B4 分块保存新增 reason（route_line_link0_forbidden/link0_misplaced/link0_line_too_long/must_be_integer_pairs）按 §4「按分块保存端点自行登记」补入 saveBlock 422 description（前端无硬编码，文档性缺口） |
| R5 | **P2** | 功能完整性 | `web/src/routers/candidates.py:159-163`（preview 只回传 `r["warnings"]`） | §2.11 矩阵「route 拼写 / route 重复关键字 | 预览=警告」未满足：预览响应只含 parse_input 产物，`keyword_spell`/`route_duplicate` 不在（导入/提交/分块保存/模板四通道均符合）。openapi InputPreview.warnings 的新 description 把 keyword_spell 归属写为「分块保存 route 拼写近邻」，与矩阵的预览列矛盾且未见 §8 留痕登记该取舍（§2.5 方案正文只列了导入/提交两通道，矩阵与方案文本存在张力，实施取了窄侧未留痕） | 二选一：preview 端点改用 `_file_warnings(r, r["blocks"]["route"], split_lines(text))` 对齐矩阵；或按现状修订计划 §2.11 预览列并在 §8 留痕 + 同步 openapi description——两侧必须一致 |
| R6 | **P2** | 约定违例 | `docs/plans/input-verify-gap-remediation-plan.md` §8.4 留痕 | 语料噪声**双阈值**中条数维度失登：独立复算 1158 个输入文件（.com 1156 + .gjf 2），新增警告 17 文件/1.47%（≤5% 达标，文件数与留痕一致），但 **test0380.com 的 title_forbidden_char 4 条 >「同文件同 kind ≤3」阈值**（title 3 行含 `_`、1 行含 `#`，行级检测每行一条，非误报但确超阈）。§5 要求「超过阈值需复审」，§8.4 只登记了文件维度与 atom_label_unknown 校准，未登记条数维度超标及复审结论 | 在 §8.4 补登记 test0380 超阈事实与复审结论（属官方语料 title 误并 route 续行的真实禁字，行级粒度所致，接受或改为每文件每 kind 聚合一条）；后续批次按双阈值分别留痕 |
| R7 | P3 | 技术方案符合性 | `web/src/parse/keywords.py:219-225` | §2.6 判定表的组合场景口径：「1 裸 + 2 非空选项形」（如 `freq freq=readfcht freq=readanharmonic`）按实现整体豁免（bare≥1∧valued≥1），按判定表字面其中「两个非空选项集」应警告。判定表未定义该组合，实现口径自洽且 G16 冒烟只验证了两 token 形 | 在 §8.3 或 keywords.py docstring 注明组合场景口径；若后续语料出现，补 `freq freq=a freq=b` 用例固化 |
| R8 | P3 | 约定违例 | 提交 cc0b6559（`opf`→`optt` 等 5 个测试文件）、bfe567d3（`2GW` 期望 2048→16.0 等 4 个测试文件） | 实现提交内含测试修订 9 处：`opf` 与 `opt` 的 difflib 比值 0.667 < 0.80 无近邻（先行用例断言本身不成立）、G3「文件头 % 行」场景被 Link0 收集吞掉不可达（先行用例构造错误）、2GW 期望值按旧错误换算预写、`len(warnings)==1` 未预判 B4 警告集扩容。均无断言弱化、commit message 有部分说明——B1 R4 教训「可预判的口径变化在测试先行提交写对」部分重演 | 后续批次先行测试提交前先对不可达场景/近邻比值做离线预验（difflib 一行脚本即可）；实现期测试修订在 commit message 逐条列明 |
| R9 | P3 | 约定违例 | 仓库根 `fort.7`（未跟踪） | B4 G16 冒烟（§8.4 g6ff 场景）在仓库根运行遗留的 Gaussian 积分文件（2026-10-19 12:13，383 字节），未清理即收口 | 删除该残留文件；G16 冒烟统一在临时工作目录运行（与 AGENTS §6.1 冒烟纪律一致） |
| R10 | P3 | 可维护性 | `docs/api/openapi.yaml:1546-1551` | `InputPreview.warnings` 的 description 只列 keyword_spell/molecule_unterminated/variables_unterminated 三 kind，未随 B3/B4 更新——分块保存/预览响应实际可出现全部 11 种 kind（权威词表在 Warning.kind 完整，通道描述滞后） | description 改为引用 Warning.kind 词表 + 列通道差异（如 task_id 仅队列聚合），避免逐批维护第二份词表 |
| R11 | P3 | 可维护性 | `web/src/parse/blocks.py:361-371`、`keywords.py:234` | ① 多组对佐证判定用裸子串（`"counterpoise"/"oniom"/"guess=fragment" in route_l`，注释词也会误豁免——宽松方向无阻断风险，且属佐证判定非触发词，不违反 §7 字面但建议注明）；② `neg_or_frag` 在 parse_ok=True 时恒可由 `len(nums)>2` 推出（首组负值已被拒、后续组存在即 len>2），条件冗余；③ duplicate message「请确认是否 intended」中英混杂 | ① docstring 注明佐证判定口径；② 删除冗余条件；③ 措辞改「请确认是否有意为之」 |

## 五、测试与闸门实测（全部独立复跑）

| 闸门 | 命令 | 实测结果 |
|---|---|---|
| 全量测试 | `uv run pytest -q` | **815 passed, 0 skipped**，2 warnings（三方库弃用告警），118.02s——与 §8.4 留痕一致 |
| hq 产物 | `ls -la target/release/hq` | 存在（17,957,408 字节）；e2e skipif 分支未触发，无静默跳过 |
| 先行红 | `git worktree add /tmp/wt-b2red 48a4eac2` 后跑 test_section_ordering.py | **收集失败**（section_ordering.py 不存在）——B2 先行红证实 |
| 先行红 | `git worktree add /tmp/wt-b4red 57362a48` 后跑 test_parse_blocks.py | **12 failed, 39 passed**（G5/G6 用例先红）——B4 先行红证实（worktree 用毕即清） |
| 进度校验 | `uv run python scripts/validate_progress.py` | OK |
| CHANGELOG 一致性 | `uv run python scripts/gen_changelog_md.py --check` | OK（逐字一致） |
| 设计令牌 | `uv run python scripts/check_tokens.py` | OK（暗 92/亮 31 逐变量一致） |
| 对比度 | `uv run python scripts/check_contrast.py` | OK（全组合 ≥ 4.5:1，最低 4.90:1） |
| 前端离线 | `bash scripts/audit_frontend_offline.sh` | 通过（dist 零外链，豁免 5 组白名单） |
| 生成物闸门 | `uv run python web/scripts/gen_models.py` + `npm run gen:types` 后 `git status` | **零残留**（仅既有未跟踪 fort.7） |
| 语料噪声 | 临时脚本遍历 `~/g16/tests/com`（1158 输入文件） | 新增警告 17 文件/1.47%（阈值 57 文件达标）；kind 分布：title_forbidden_char 18、molecule_multiple_charge_pairs 5、link0_directive_unknown 2；**test0380.com 单文件同 kind 4 条超阈**（R6）；atom_label_unknown/route_duplicate/link0_value_invalid 等 7 种 kind 语料内零命中 |
| 留痕数字核对 | progress.json / CHANGELOG unreleased | in_progress 已归位（null）；unreleased 9 条与三批一一对应；B2=772/B3=793/B4=815 的增量口径（+21/+21/+22）与区间测试改动量吻合 |

## 六、端到端审查记录

本次未起完整服务（调用方指定「不必起完整服务」），按四查第 4 条以 uv 环境
直接调用 Python API 实测关键路径（临时脚本置于 /tmp/b234review，用毕清理）：

| 场景 | 实测结果 |
|---|---|
| G9 七项 | route EOF 双文案、title EOF（allcheck 豁免不报）、charge_mult 误并根因、空分子说明三档（普通报/checkpoint 不报/allcheck 不报）、molecule_unterminated、variables_unterminated、--Link1-- 附注——全部符合 §2.10 |
| G4 | Gen 附加节 EOF 阻断 / 带终止空行不报 / Gen+Pop=NBORead 混合保守不报 / prop=wrf 兼容触发 / 普通 route any_trigger=False——全部符合；terminator_missing 混合 False |
| G2 判定表 | 7 行判定 + line_offset + 白名单外选项形重复（`mp2=ful mp2` 警告）+ 容器头双裸形警告——全部符合 §2.6 |
| G3 | 情形 1（% 吞入 route）/ 情形 2（% 落 title）/ 文件头前导 % 归 Link0 / 缺 route 时 title 后错置可达命中 / 分子说明 % 行不扫描——与 §8.3 登记口径一致 |
| G5 | 2GW=16.0GB、1KW=8KB、2MW=16MB（差 1024 倍已修）、2W/2QW 拒绝、%mem=0 警告、501 字符警告、%save/%kjob l502 2 零警告、%xyz=1 unknown、%cpu=0-5/2→3 核、0-5/0 拒绝、%nprocshare=4 截断形放行——全部符合 |
| G6 | O-Bq 计 4 原子 formula=H2O1、X/XX 哑原子不计式、Foo→F 不告警、Zz 警告、C-CT--0.06 取 C、C(Iso=13,Fragment=2) 整词、`C,0,0,0`/`H/0/0/1.1` 自由分隔、原子序数 8→1、Fragment 参数佐证零警告、无佐证多组对警告且 charge_mult 全组保留——全部符合 §2.7 |
| 多组对值域 | `-1 2` 零错误、`0 0` 阻断、`0 1 0 -1` 宽容+Guess=Fragment 文案警告、首组 mult<1 阻断（§2.11 矩阵口径）——符合 |
| 通道一致性 | **发现 R3**：`0/1` parse_input 放行（charge_mult="0 1"）vs 编辑保存 422 拒绝；**发现 R1**：前导空行场景 Link0 警告 line=1（应 3）；duplicate 警告 line 恒 1 |
| BOM 链路 | **发现 R2**：带 BOM 磁盘副本 verify_and_store 解析正常但 BOM 字节随写回保留落盘（normalized=False） |
| G16 冒烟佐证 | 未复现真实 G16 冒烟（外部程序，运行产物 fort.7 残留与 §8.4 g6ff 场景文件头 H2O2/sto-3g 吻合，间接佐证冒烟真实发生；G2 豁免的 testrt 冒烟与 B2 Gen/Pseudo 冒烟按留痕采信但已在验收表中以离线等价用例独立覆盖判定逻辑） |
| 前端视觉 | 不适用——本批区间无 .vue 改动（仅 contract.ts 类型再生），无视觉 UI/UX 变化可实测；后端新增 warnings 的前端渲染缺口已并入 R5 说明（CandidatesView/提交确认框未渲染导入/提交 warnings，计划 §2.5「涉及文件」所列前端项未落地且未留痕，其用户可见性依赖 R5 的通道对齐决策） |

## 七、结论与条件

**有条件通过。** B2–B4 验收标准主体达成、闸门全绿、无 P1；合入后续批次（B5）
前须完成以下整改：

1. **（P2，R1）** Link0 警告行号对齐 G0 全文件绝对口径（`line_offset` 参数 +
   duplicate 行号修正 + 行号断言用例）；
2. **（P2，R2）** 三处读取路径统一 utf-8-sig，或登记口径偏离并补带 BOM 副本用例；
3. **（P2，R3）** 电荷行分词口径单点化（斜杠/en-dash 编辑保存对齐 parse_input）并补用例；
4. **（P2，R4）** notice.route_duplicates 契约登记 + 生成物再生零 diff（顺带补分块
   保存新 reason 的端点级登记）；
5. **（P2，R5）** 预览通道 route 拼写/重复警告与 §2.11 矩阵对齐（或修订矩阵并留痕）；
6. **（P2，R6）** §8.4 补登记语料条数阈值超标（test0380）及复审结论。

P3（R7–R11）随批处置即可，不阻断。整改后仅需针对 R1–R6 复审（复跑全量 pytest +
新增用例 + 生成物闸门），无需重做全量审查。
