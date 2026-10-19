# 代码审查报告：输入文件勘误校验缺口补齐计划 B1 批次（G0+C1+C2+C3）

## 一、审查依据与范围

- 依据：`docs/plans/input-verify-gap-remediation-plan.md` §2.0.1（G0 统一 warnings 通道）、
  §2.1（C1 Geom=Checkpoint 豁免收窄）、§2.2（C2 括号形态识别）、§2.3（C3 拼写 token 化）、
  §3 实施批次表 B1 行与 §3.1 批次纪律、§4 契约影响、§7 风险登记表。
- 对象：git 区间 `3ca70180..42ca49fe` 共 5 个提交（f2590e07 进度开工、b19cf79b 契约文档先行、
  2df7df1d 测试先行、bf807e0a 实现、42ca49fe 进度收口），17 个文件、+490/-89 行。
- 范围证实：`git diff --stat 3ca70180..42ca49fe` 逐文件核对通过；声称未改动的
  `web/src/services/verify.py`、`_scan_spans`/`verify_and_normalize` 的 geom 语义、
  G1/G2/G4/G9 等后续批次范围均零改动（diff 文件清单不含、`grep -n -i geom web/src`
  仅命中 `blocks.py` 的 `_geom_exemption_tier` 及词典/无关字段）。
- 报告落盘：`docs/plans/input-verify-gap-b1-review.md`（调用方指定）。
- 审查执行日：2026-10-19；审查方式：AGENTS §6.2 独立复核四查，全部结论来自独立实测。

## 二、总体结论

**有条件通过。**

B1 批次的主体目标全部达成且质量良好：G0 通道、C1 豁免收窄、C2 括号识别、C3 token 化
管道均已按计划落地，契约先行/生成物闸门/端到端行为/前端视觉实测全部通过；但存在
**1 项 P1**（`@filename/N` 后缀未豁免，官方合法形态在模板 enforce 通道被误拒，与计划
§2.3 明文不符）与 **1 项 P2**（温度联动 `has_freq` 对 `freq(...)` 括号形漏判），
须整改并复审后方可合入后续批次（B2 依赖 B1 的 token 管道，建议先修 R1）。

## 三、功能完整性对照

| 编号 | 计划条目 | 实现位置 | 结论 |
|---|---|---|---|
| G0-1 | `parse_input` 返回值增 `warnings: list[dict]`，默认空 | `web/src/parse/blocks.py:264-265` | 已落地（实测 `set(r) == {"blocks","parse_errors","multistep","warnings"}` 且恒 `[]`） |
| G0-2 | 条目形态 `{line, keyword, kind, message, suggestion?, task_id?}`，`message` 必填 | `web/src/parse/keywords.py:158-162` | 已落地（实测含 `message`；`task_id` 属 B3 队列聚合，未到批次） |
| G0-3 | `line` 全文件 1 起；`check_route_spelling` 增 `line_offset`，`save_block` 传 route 起始行 | `keywords.py:143`、`web/src/services/candidates.py:407-410` | 已落地（`_scan_spans` 0 起 span 作偏移，换算正确；CRLF/LF/多行 route 实测均正确） |
| G0-4 | `parse_errors` 语义不变（阻断） | `blocks.py` 阻断路径零改动 | 已落地（端到端实测 422 仍触发） |
| G0-5 | 命名统一 `warnings`；`notice.spelling_warnings` 不改名 | `combo_templates.py:181` | 已落地 |
| G0-6 | 预览端点契约增可选 `warnings` | `openapi.yaml` InputPreview、`routers/candidates.py:159-163` | 已落地（端到端实测响应含 `warnings` 键） |
| C1-1 | 豁免拆两档，判定收敛 `parse_input` 单一私有函数 | `blocks.py:92-121` `_geom_exemption_tier` | 已落地 |
| C1-2 | checkpoint 档取消 title/电荷豁免，文案改「仅 AllCheck 可省略」 | `blocks.py:203-205、220-222` | 已落地（实测 checkpoint/check 缺节双报；文案精确） |
| C1-3 | 不改动 `_scan_spans`/`verify_and_normalize` | 全区间 diff | 已落地（零改动，docstring 注明勿同步，§7 风险 2 缓解到位） |
| C2-1 | token 化按「头部=取值集合」判定 geom 括号形 | `blocks.py:104-120` | 已落地（括号/空格/`check` 同义/逗号后空格/大小写/前缀误命中（`allcheck1`/`checkpointx`→None）实测全对；allcheck 并出优先） |
| C3-1 | 括号感知切分（`6-31g(d,p)`、`IOp(6/50=1)` 整词） | `keywords.py:56-91 _tokenize_line` | 已落地（实测整词保留） |
| C3-2 | 引号感知（`External="RunTink Amber"`） | 同上 | 已落地（实测不闭引号亦不炸） |
| C3-3 | 切分前截断首个**引号外** `!` | `keywords.py:63-66` | 部分落地（引号外且**括号深度 0** 才截断，见 R3） |
| C3-4 | `@` 开头 token 豁免（**含 `/N` 后缀**） | `keywords.py:130-131`（`token_in_dict` 豁免） | 部分落地：`@file` 裸形豁免生效；**`@file/N` 被深度 0 的 `/` 拆散，`N` 成孤立 token，enforce 误拒**（R1，P1） |
| C3-5 | 裸 `=` 丢弃并粘合 `key=value`；`key (…)` 合并 | `keywords.py:94-121 _merge_pairs` | 已落地（连续 `=`、跨行 `=` 粘合、`=` 行首、非 bare 词不误合并均实测通过） |
| C3-6 | `_token_in_dict` 迁入 `keywords.py` 并扩展括号形键名命中 | `keywords.py:124-140`；`combo_templates.py:52-60` 已删本地版 | 已落地（`iop(6/50=1)` 按 `(` 前头部取键实测命中） |
| C3-7 | `check_route_spelling` 先精确命中再近邻 | `keywords.py:147-162` | 已落地 |
| C3-8 | combo 模板与拼写检查共用同一管道 | `combo_templates.py:89、93` | 已落地（`_TOKEN_SPLIT` 全库清零；但 `has_freq` 旁路旧口径漂移，见 R2） |
| B1-验收 | 既有测试不回归、记录 passed/skipped；五类误拒+空格形+引号值+括号 Geom+`Geom=Check` 用例转绿；Checkpoint 缺节被拒、AllCheck 不变 | 四个测试文件 | 达成（`750 passed, 0 skipped` 独立复现，hq 产物在位、e2e 真实执行；上述用例实测通过） |
| 契约 | 共享 `Warning` schema（message 必填、suggestion/task_id 可选）；`InputPreview.warnings`；saveBlock 响应去外层包装；roadmap §2.7 两处括注；生成物再生零 diff | `openapi.yaml:1440-1466、1526-1533、2177-2190`；`roadmap.md:290-291` | 达成（`gen_models.py`+`npm run gen:types` 后 `git status` 零残留，实测） |
| §3.1 | 提交序列 文档→测试→实现→进度；当批登记 CHANGELOG/progress | 5 个提交 | 基本达成（序列正确；实现提交内含两处测试口径对齐，见 R4；CHANGELOG unreleased 四条含「接受集收窄」与 migration 登记完整） |

## 四、问题清单

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| R1 | **P1** | 功能完整性 | `web/src/parse/keywords.py:56-91`（`_tokenize_line` 的 `_SEP_CHARS="/#"` 含 `/`） | 计划 §2.3 明文「`@` 开头 token 直接豁免（含 `/N` 后缀）」未完整实现：`@mols.dat/3` 被深度 0 的 `/` 切成 `@mols.dat` + `3`，孤立数字 token 词典外——**组合流模板 enforce 通道误拒官方合法形态**（`validate_and_normalize(1, {"route": "#p opt freq @mols.dat/3"})` → 422 字段级校验失败）。这正是 C3 要消灭的「官方合法形态误拒」的残余。分块保存 warn 通道因 `3` 无近邻不警告，不表现 | `_tokenize_line` 切分时对 `@` 开头的当前 token 吸收紧随的 `/数字` 段（或 `token_in_dict` 之外在 tokenize 层做 `@` 整词豁免，含 `/N`）；补 enforce 用例 `#p @mols.dat/3` 放行断言（现 `test_enforce_official_forms_pass` 只有 `#p @mols.dat` 裸形） |
| R2 | **P2** | 逻辑与边界 | `web/src/services/combo_templates.py:99` | 温度联动 `has_freq = any(t == "freq" or t.startswith("freq="))` 未覆盖 C3 本批刚放行的官方括号形：`freq(readanharmonic)`、`freq (readanharmonic)`、`FREQ(ReadFC)` 时 `has_freq=False`，**不自动补 `temperature=298.15` 且 `notice.temp_applied` 恒 False**，与模块 docstring「route 含 freq 而未配置温度 → 自动补」承诺不符（实测 `freq`、`freq=readanharmonic`、`freq,readanharmonic` 均正确补温，唯括号形漏）。数值后果恰被 G16 默认温度 298.15K 掩盖，但行为口径不一致，且无任何测试覆盖该组合形态 | `has_freq` 判定改用 token 头部（`t == "freq"` 或 `t.split("(")[0].rstrip("=") == "freq"`），或直接复用 tokenize 后的头部解析；补 `freq(readanharmonic)` → `temp_applied=True` 用例 |
| R3 | P3 | 技术方案符合性 | `web/src/parse/keywords.py:63-66` | `!` 截断条件为 `depth == 0 and ch == "!"`，括号内 `!` 不截断（`opt(ca!lcfc)` 保留整词）；计划字面为「首个**引号外** `!`」未豁免括号内。行为后果等价（两种口径下 `opt` 键名均命中放行），形态罕见 | 在 docstring 注明「括号内 `!` 视为选项字符不截断」的实现口径，或对齐计划改为仅引号内豁免；二选一即可 |
| R4 | P3 | 约定违例 | 提交 bf807e0a（`web/tests/test_block_save.py:304`、`web/tests/test_combo_templates.py:264-271`） | 实现提交内修改两处测试断言（`w["line"] == 1` → `== 5`；`temperature=300,310` 期望 reason 迁移），与「测试先行（预红）→ 实现（转绿）」的理想序列不符：先行测试按相对行号预写，实现后口径演化。两处改动本身均有注释与 migration 登记、语义合法（绝对行号是 G0 验收项；逗号切分符合官方语法），非弱断言 | 后续批次把可预判的口径变化（如行号基准）在测试先行提交写对；此类实现期测试修订单独说明（commit message 已说明，可接受） |
| R5 | P3 | 可维护性 | `web/src/services/candidates.py:31-32` | services 层跨模块导入 `parse.blocks` 的私有名 `_scan_spans`/`_split_lines`（下划线前缀），封装边界穿透。计划未指定取行号手段，此实现是最短路径，功能正确 | 中期可将 `_scan_spans` 中「节起始行」能力提为 `parse.blocks` 公共 API（或提供 `route_start_line(text)` 薄封装）；不阻断本批 |

补充实测记录（不构成问题）：`#p = calcfc` 会粘合为 `p=calcfc` 且因 `p` 在典（`_SINGLE_OK` 遗产）键名命中放行——`=` 紧跟表单字母的病态输入，无实际误报面；`#t`/`#n` 单字母仍词典外属 G7（B5）已知限制，与旧行为一致。

## 五、测试与闸门实测（全部独立复跑）

| 闸门 | 命令 | 实测结果 |
|---|---|---|
| 全量测试 | `uv run pytest -q` | **750 passed, 0 skipped**, 2 warnings（仅三方库弃用告警），111.77s |
| hq 产物 | `ls target/release/hq` | 存在（17,957,408 字节，2025-10-15 构建）；`test_e2e_fake_g16.py` 的 skipif 分支真实执行、无静默跳过 |
| 单文件收集既有问题 | `uv run python -m pytest web/tests/test_block_save.py --collect-only` | 复现循环导入（`default_inputs_dir` partially initialized）；经 `git worktree` 在基线 3ca70180 同样复现，**证实为既有问题，与 B1 改动无关**（本批未改 services 层依赖图：candidates 对 parse.blocks 仅增量导名，keywords 无项目内依赖） |
| 进度校验 | `uv run python scripts/validate_progress.py` | OK |
| CHANGELOG 一致性 | `uv run python scripts/gen_changelog_md.py --check` | OK（逐字一致） |
| 生成物闸门 | `uv run python web/scripts/gen_models.py` + `cd web/frontend && npm run gen:types` 后 `git status --porcelain` | **零残留**（models.py / contract.ts 再生后与提交版逐字节一致） |
| 前端离线 | `bash scripts/audit_frontend_offline.sh` | 通过（dist 零外链，豁免 5 组白名单） |
| 设计令牌 | `uv run python scripts/check_tokens.py` | OK（暗 92/亮 31 变量逐项一致） |
| 对比度 | `uv run python scripts/check_contrast.py` | OK（全组合 ≥ 4.5:1） |

登记口径核对：CHANGELOG unreleased 四条（C1/C2/C3/G0）与 `progress.json` 一致，含「接受集
收窄」标注与 `temperature=300,310` 口径迁移的 migration 说明——计划 §2.1「行为变更登记」
要求满足。

## 六、端到端与视觉审查记录

环境：按 `docs/references/development.md` §6.1 起隔离实例
（`G16WEB_HOME=/tmp/g16web-b1review G16WEB_ENGINE=0`，端口 8399，用毕已停并清理）。

| 场景 | 操作 | 实测结果 |
|---|---|---|
| C1 拒收 | POST `/api/v1/candidates` 导入 `#p b3lyp/6-31g(d) geom=checkpoint\n\n`（缺 title/电荷） | 整批 422 `VALIDATION_FAILED`，`files[].reason=INPUT_PARSE_FAILED`，parse_errors 含 title+charge_mult 双报（文案「仅 Geom=AllCheck 可省略」）——与计划 §2.1 预期逐字吻合 |
| C2 放行 | 导入 `#p b3lyp/6-31g(d) geom=(allcheck,modredundant)\n\n` | 201，`parse_errors=[]`，`title=null`——AllCheck 括号形不再误报 |
| G0 预览 | GET `/api/v1/candidates/{id}/preview` | 200，响应键 `blocks/parse_errors/warnings/candidate_id/filename`，`warnings=[]` |
| 绝对行号 | PUT `/api/v1/candidates/{id}/blocks/route`，文件 route 位于第 5 行（3 行 link0+空行） | `warnings=[{line:5, keyword:"oppt", kind:"keyword_spell", message:"「oppt」疑似拼写错误，是否意为「opt」", suggestion:"opt"}]`——全文件绝对行号正确、message 必填、suggestion 在位（`scf=tigh` 键名命中不报警，值校验属 G8/B5，符合本批口径） |
| 前端视觉 | playwright（chromium headless，dist 构建产物，hash 路由 `/#/candidates`）：选中候选 → 「编辑」→ route 填入含 `oppt` 文本 → blur 自动保存 | 截图与元素级实测：`.be-warn` 渲染 1 条 `⚠ 第 5 行 「oppt」疑似拼写错误，是否意为「opt」」，等宽字体、琥珀文字色 `rgb(125,92,25)`、布局无破版；`.be-info`「已自动保存」同屏确认非阻断。message 优先渲染生效（回落分支未触发，由类型可选性保证）。截图：`/tmp/pw-b1review/0*.png`（审查过程件，已清理；结论以文字记录为准） |

前端视觉维度凭实际打开页面 + 截图 + computed style 实测下结论：**通过**（代码层
check_tokens/check_contrast 仅作佐证）。

## 七、结论与条件

**有条件通过。** 条件：

1. **（P1，R1）** 修复 `@filename/N` 后缀豁免并在 `test_enforce_official_forms_pass`
   补该形态用例——B2 的 G4 触发词匹配将复用同一 tokenize 管道，此缺陷不修会向下扩散；
2. **（P2，R2）** 修复 `has_freq` 对括号形的漏判并补 `temp_applied` 断言；
3. （P3，R3–R5）随批处置或在后续批次登记：`!` 括号内口径注明、测试修订纪律、
   `_scan_spans` 私有名封装。

修复后仅需针对 R1/R2 复审（复跑全量 pytest + 新增用例 + enforce 实测），无需重做全量审查。

## 八、整改复审（R1/R2 针对性复审，2026-10-19）

复审范围：git 区间 `42ca49fe..a3f28538`（b9c244f7 测试先行红、cd7947c5 计划留痕 §8.1、
93cbac04 实现、a20348d6 进度登记、a3f28538 本报告入库）。仅针对第七节条件 1)/2)，
按第七节约定不重做全量审查；全部结论来自独立实测，不采信实施自述。

### 8.1 R1（P1：`@file/N` 后缀豁免）——已修复，验证通过

- **原失败形态复测**：`validate_and_normalize(1, {"route": "#p opt freq @mols.dat/3"})`
  → 200 放行（修复前 422 字段级校验失败，本次实测通过）；warn 通道
  `check_route_spelling("#p opt freq @mols.dat/3")` → `[]` 零误报。
- **实现审查**（`web/src/parse/keywords.py:53-54、95-98`）：深度 0 遇 `/` 且当前
  token 以 `@` 开头、`/` 后匹配 `_AT_SUFFIX_N`（`\d+(?=$|[\s,/#])`，数字后为行尾
  或分隔符）时并入 token。`re.match(head, j+1)` 的 `$` 锚定全串末尾，不会在行中
  误命中；`cur[0] == "@"` 保证非 `@` token 不受影响。
- **边界矩阵实测（16 例）**：
  - 目标形态 `@mols.dat/3` 整词豁免；`@a/3/b` 吸附 `@a/3`、`b` 独立（与处置说明一致）；
  - 不误吸附：`@x/`（尾随孤立 `/`）、`@a/3.5`（小数非 N）、`@a/33abc`、
    `@file/3freq`（数字后跟字母）、`@a /3`、`@a/,3`（空格/逗号隔断后 `/3` 非后缀）；
  - 零回归：`b3lyp/6-31g(d,p)`、`IOp(6/50=1)`、`External="a/b/2"`（引号内斜杠）、
    geom 档位判定（allcheck/checkpoint）均不受影响；
  - warn 通道 `@a/3/b` 的 `b` 无近邻不警告。
- **测试**：`test_enforce_official_forms_pass` 追加 `"#p opt freq @mols.dat/3"`、
  `test_spell_official_forms_not_flagged` 同步追加，两者独立单跑 PASSED。
- **观察项（不阻断）**：① `@file/2/3` 多级 `/N` 宽容整词豁免（非官方形态向放行
  方向倾斜，与 R1「不误拒」目标同向，无副作用）；② `@dir/sub/file.dat/7` 含路径
  斜杠的 @file 仍拆散（`sub`/`file.dat` 词典外）——官方 @filename 语法未明确支持
  路径形式，计划 §2.3 仅要求 `/N` 后缀，属计划外形态；如后续语料出现再议。

### 8.2 R2（P2：`has_freq` 括号形漏判）——已修复，验证通过

- **原失败形态复测**（`web/src/services/combo_templates.py:98-100`，改按 token 头部
  `t.partition("=")[0].split("(", 1)[0] == "freq"` 判定）：
  `freq(readanharmonic)`、`freq (readanharmonic)`、`FREQ(ReadFC)` 三态均
  `temp_applied=True` 且 route 末尾补 `temperature=298.15`。
- **不回归**：`freq`、`freq=readanharmonic`、`freq,readanharmonic`（warn 模式对照
  B1 基线）仍正确补温；`frequency`、`freqx`、`opt=(freq)`、`IOp(6/50=1)` 均不误判
  （temp_applied=False）；已配置 `temperature=310`/`temp=300` 时不重复补。
- **温度校验回归**：`freq(readanharmonic)` 组合下 `temperature=abc/-1/0` 三态仍 422
  拒绝（`temp_value_invalid` 路径完好）。
- **测试**：`test_temp_auto_apply_bracket_form_freq` 独立单跑 PASSED。

### 8.3 R3–R5 处置核查

- R3：`keywords.py` 模块与 `_tokenize_line` docstring 已注明「括号/引号内 `!` 属值的
  一部分不截断」口径并指向审查报告 R3；计划 §8.1 同步登记——处置符合第七节条件 3)。
- R4/R5：登记于计划 §8.1（R4 教训「可预判口径变化在测试先行提交写对」；R5 约定
  B2 触及同区域时提公共 API）——按第七节「登记」口径接受。

### 8.4 闸门复跑（独立执行）

| 闸门 | 实测结果 |
|---|---|
| `uv run pytest -q` | **751 passed, 0 skipped**（107.60s；= 750 + 新增 `test_temp_auto_apply_bracket_form_freq`，hq 产物在位） |
| `uv run python scripts/validate_progress.py` | OK |
| `uv run python scripts/gen_changelog_md.py --check` | OK（C3 条目补登 R1/R2 后两文件一致） |
| 工作树 | clean（区间改动全部入库，无未跟踪残留） |

### 8.5 复审结论

**闭环。** 第七节条件 1)（R1）与 2)（R2）均已修复并经独立实测验证，条件 3)（R3–R5）
按约定处置/登记完毕；全量闸门复跑通过，无残留阻断项。两条观察项（`@file/2/3`
宽容整词、`@` 路径形态不豁免）均为计划外边界的方向性备注，不构成问题，随 §8.1
留痕即可，B2 起若相关语料出现再议。
