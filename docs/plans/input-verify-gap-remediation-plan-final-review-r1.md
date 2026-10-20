# 代码审查报告：输入文件勘误校验缺口补齐计划·终审（第 1 轮）

> 审查人：终审子代理（AGENTS.md §6.2 第二层独立复核）。全程只审不改：
> 全部结论来自本审查独立执行的命令与实测输出，未采信实施者自述数字与各批
> 审查留痕结论（留痕仅作索引进场，涉及处均重新实测）。

## 一、审查依据与范围

- **依据**：`docs/plans/input-verify-gap-remediation-plan.md` 全部需求、实施
  批次（§3 B1–B7）与验收标准，含 §1 规则 SSOT、§2 缺口方案（G0–G11、
  C1–C3）、§2.11 通道矩阵、§4 契约影响、§5 测试方案、§6 决策记录。
- **对象**：实施计划落盘后至 HEAD 的完整实现，git 区间
  `3ca70180^..HEAD`（自 `f2590e07` B1 开工至 `84fb8667` B7 审查报告落盘，
  共 76 提交）。
- **范围证实**：`git status --porcelain` 实测工作区 clean；
  `git diff --stat 3ca70180^..HEAD` 实测 **67 文件 +56038/−408**，改动全集
  为 `web/src`（parse/services/routers/engine/models）、`web/tests`、
  `web/frontend`（3 组件 + 契约类型）、`scripts`（extract_keywords /
  audit_prose_options / check_plan_status）、`docs/api/openapi.yaml`、
  `docs/specs/roadmap.md`、计划与留痕文档、CHANGELOG/progress——与计划
  §2/§4 声明的涉及文件面一致；`crates/` 零改动（Rust 内核无越权修改）。
  六份逐批审查留痕（b1 / b234 / b5 / b6-code / b6-prose-audit / B7）均在库。
- **报告落盘**：`docs/plans/input-verify-gap-remediation-plan-final-review-r1.md`
  （调用方指定；落盘前确认同名文件不存在，零覆盖）。

## 二、功能完整性对照

缺口总表（§2.0）13 项逐条判定，实现位置均经本轮代码实读 + 独立行为冒烟
（临时脚本直接调用解析层，86 个断言点，85 通过，唯一未过项经查证为 §8.3
已留痕实现口径，见第五节）核实：

| 编号 | 计划条目 | 实现位置 | 结论 |
|---|---|---|---|
| C1 | Geom 豁免拆三档，Checkpoint 仅豁免坐标，title/电荷缺失照拒 | `web/src/parse/blocks.py:194-223`（`_geom_exemption_tier`） | 已落地（冒烟：checkpoint 缺电荷/缺 title 被拒、有电荷零错、`check` 同义、`= ` 两侧空格识别均过） |
| C2 | geom 括号形/空格形识别 | 同上（经 `tokenize_route` 括号感知） | 已落地（`geom=(allcheck,modredundant)`、`geom = checkpoint`、`geom=(checkpoint,…)` 冒烟全过） |
| C3 | enforce/warn 五类官方合法形态不误拒 | `web/src/parse/keywords.py:57-156`（括号/引号感知 + `@file/N` 吸附 + 裸 `=` 粘合 + `key (…)` 合并 + 引号外 `!` 截断） | 已落地（逗号分隔、行内注释、`@mols.dat/3`、引号值、`opt = (calcfc, ts)`、`opt (calcfc, ts)` 冒烟全过） |
| G0 | 非阻断 warnings 统一通道 | `blocks.py:236,526`（返回值含 `warnings`，默认空列表，`message` 必备） | 已落地（导入/预览/编辑保存/提交四通道实测均携带） |
| G1 | 拼写检查接入导入与提交 | `services/candidates.py`（导入）、`services/verify.py` + 6 调用点 | 已落地（导入实测 `oppt`→`keyword_spell`+`suggestion=opt`、line=2 全文件绝对；`candidates.py:192`、`queues.py:137`、`history.py:202`、`resume.py:256`、`workflows.py:254/276` 逐一核实取 `res["normalized"]`，queues 逐成员填 `task_id`） |
| G2 | route 重复关键字检测 | `keywords.py:193-240`（判定表 + 容器头白名单 16 项 + iop 豁免） | 已落地（`opt opt` 警告、`freq freq=readfcht`/`iop(5/17=1) iop(6/50=1)` 豁免、双选项集/`scf=tight scf=xqc` 警告、正常 route 无警告，冒烟全过） |
| G3 | Link 0 错位两情形检测 | `blocks.py:301-306`（route 内 % 行）、`blocks.py:332-338`（title 内 % 行） | 已落地（两情形阻断冒烟过；文件开头前导 % 行归 Link0 收集为 §8.3 已登记口径，两种情况均阻断无放行） |
| G4 | Section Ordering 官方表固化 | `web/src/parse/section_ordering.py:187-343` | 已落地（独立计数 59 行 = 4 core + 54 additional + 1 automatic；no 例外 7 行与 §1.2 加粗行一一对应；`any_trigger` 只消费 additional，普通 route 为 False，`gen` 触发为 True；附加节 EOF 阻断/有空行零错冒烟过） |
| G5 | 值域拉齐（%mem/%nproc/%cpu/行长/指令文法/title 禁字/BOM） | `web/src/parse/link0_rules.py` + `blocks.py:288-290,341-348` | 已落地（`%mem=2W`/`%mem=0` 警告、`%cpu=0-5/2` 放行、501 字符 % 行警告、`%save`/`%kjob l502 2` 无等号放行、重复/未知指令警告、title 禁字警告、BOM 入口剥离零错，冒烟全过） |
| G6 | 原子行文法与多组电荷对 | `blocks.py:425-472`（`_tokenize_atom_line`/`_classify_atom`） | 已落地（`-1 2` 放行、`0 0` 拒、多组对无佐证警告 + 规范化保留全组 `0 1 0 1 0 1`、counterpoise/Fragment 佐证零警告、`O-Bq` 占行不计式（atom_count=3/formula=H2）、`X` 哑原子、`Foo` 不告警、`Zz` 告警、`C,0,0,0`/`C/0/0/0`/`C(Iso=13,Fragment=2)`/`C-CT--0.06` 冒烟全过） |
| G7 | 词典面⑥ `n`/`t` + 精确匹配口径 | `scripts/extract_keywords.py` + `web/src/parse/keywords.txt` | 已落地（`n`/`t` 在典；B5 时 1166 词条，B6 G10-b 扩面后 1345 词条实测；决策点 5 词级精确匹配维持） |
| G8 | 括号内子选项归属校验 | `keywords.py:265-394`（`_VALUE_FORM_HEADS` 白名单 + 键内唯一前缀判活 + 近邻建议） | 已落地（`opt=(calcfc,ts)`/`opt=(readfc)`/`scrf=(solvent=water,read)`/`IOp(6/50=1)`/`ONIOM(…)`/`External="…"` 零警告，`opt=(readfcht)` 跨关键字警告、`geom=(allcheck,xyzzy)`/`opt=(calcfc,xyzzy)` 仅报未命中项、`opt=(calfcf)` 附 `suggestion=calcfc`、`freq=numer` 判活零警告、`scf=conv` 歧义警告，冒烟全过） |
| G9 | 核心节必需空行显式检测 | `blocks.py:309-312,353-355,414-420,464-472,507-512` | 已落地（route/title EOF 阻断 + 缺 title 归因提示、空分子说明阻断、分子说明/Variables EOF 警告、`--Link1--` 前缺空行附注、AllCheck 不豁免 route 终止空行、AllCheck 豁免集不报 title/电荷/分子说明，冒烟全过） |
| G10-a | 模板保存 enforce 屏蔽（决策点 12） | `web/src/services/combo_templates.py:40`（`SPELLING_MODE = "warn"` 单点） | 已落地（实测 `frqu` → 200 + `notice.spelling_warnings=["frqu"]` 零 422；`ignore_spelling=true` 与不传行为一致；`mode="enforce"` 分支保留待恢复） |
| G10-b | B 类词典扩面与三路审计 | `scripts/audit_prose_options.py` + `extract_keywords.py` 面⑦/手工补录 + `docs/plans/audit/`（12 份产物在库） | 已落地（词典 1166→1345；`opt=addredundant`/`freq=nnroa` 零警告、`geom=modela`/`td=(window(…))` A 类维持预期警告，冒烟过；warn→review 过渡层已经 B6 整改脚本化入库 bc0a47a9） |
| G11 | 电荷行行内 `!` 注释剥离 | `blocks.py:144-172`（`parse_charge_tokens` 引号感知截断单点） | 已落地（`0 1 ! …` 与 `0,1 0,1 0,1 ! cp pairs` 四通道零错误、`charge_mult` 规范化无注释、剥后 token 不足仍报错、编辑保存 HTTP 200 放行，实测过） |

批次验收标准（§3 表）逐批核对：B1（五类误拒转绿 + Checkpoint 收严 + 契约
Warning schema）✓；B2（59 行表 + G9 用例 + roadmap §2.7 回补——本轮实读
`docs/specs/roadmap.md:290-292` 证实例外全集 7 项、Title 行 AllCheck 括注、
Checkpoint title 补全三处齐备）✓；B3（三响应 warnings + `task_id` 队列聚合
+ 422 响应不带 warnings）✓；B4（矩阵逐格 + 词典 kind 词表七项）✓；
B5（1166 幂等 + G8 十用例）✓；B6（enforce 屏蔽 + 审计清单落盘 + 词典
1345 + G16 冒烟 8 例表）✓；B7（四通道 + G16 冒烟 2 例 + CHANGELOG 登记
接受集扩大）✓。CHANGELOG.jsonl unreleased 行含 G0–G11 全部批次条目
（本轮实读核对）。

## 三、问题清单（实现层，当前存在）

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| I-1 | P3 | 逻辑与边界 | `web/src/parse/blocks.py:341-343` | title 禁字警告为行级粒度且每行只报**首个**禁字字符（`next()` 取首个）：实测 `t_itle #x` 仅报 `_` 不报同行 `#`。B2–B4 审查 R6 已裁决行级粒度，本条为其自然延伸（warn 级，不影响阻断语义），但同行其余禁字对用户不可见 | 随批改为 message 列出该行全部禁字字符；或维持现状并在 §2.12 登记粒度口径 |
| I-2 | P3 | 约定违例（留痕维度） | `docs/plans/input-verify-gap-b6-prose-audit.md` §7 | B6 语料基线仅登记文件数（417→394）/总条数（498→469）/形态数（66→55），未按 B2–B4 审查 R6 整改要求登记「同文件同 kind ≤3」逐文件维度（B5 §8.6 有登记）。扩面方向只消除警告、语料命中文件集为 B5 子集，风险有界 | 发布前在 §7 补一行超阈核查结论（可引用 B5 裁决：命中集为 B5 的子集，沿用行级粒度裁决） |

无 P0/P1/P2 级发现。B6 审查登记的批次纪律 P3 项（提交序列 R3、提交拆分
R4、summary 动词开头 R5）已经 prose-audit §9.2 处置闭环，且 B7 批次已恢复
合规（先行红独立提交 2ed38a76、实现提交 summary 动词开头），不再列为待整改。

## 四、计划文档本身的问题（docProblems）

不以计划为权威，通读全文并与留痕/实测交叉核对，发现 4 处「留痕已勘误、
主文档正文未回改」型问题（均无实现危害，属文档滞后）：

| # | section | what | affected |
|---|---|---|---|
| D-1 | §2.9 末段（:733-737）与 §3.1 B6 节点（:1032-1034） | 两处仍断言「`scf=conv` 歧义前缀 G16 拒绝」，与 B6 出口冒烟 t5 实测（**Normal termination 接受**，prose-audit §8）直接矛盾；prose-audit §8 t5 声称「随批修正 §2.9」未落实到主文档正文，现与 `keywords.py:343-345` docstring（「scf=conv 歧义却被 G16 接受，B5『拒绝』系推断错误」）互相矛盾 | G8 缩写判活口径的权威记载；后续读者按计划正文会复述已被实测推翻的断言 |
| D-2 | §2.6 G3 方案（:543-545） | 「route 节缺失时 % 行出现在 title 位置同样按情形 2 记 parse_errors」未限定形态，与实现及 §8.3 留痕口径（**文件开头前导 % 行归 Link0 收集规则，不在 G3 检测面**）不一致（本轮实测：`%chk` 为文件首行且 route 缺失时仅报「缺少 route 节」；% 行在标题行之后则报 G3 title 错误——两种情况均阻断，无放行差异） | B3 G3 检测面理解的准确性（仅错误归因记载差异，非行为缺陷） |
| D-3 | §2.0 缺口总表 G10 行 + §2.13 方案 2 | 「三路差集**全量**审计」表述与 prose-audit §9.2 R8 已收敛的「三路互补**近似**全量」不一致（路②限于 keyword 页 Options 章节条目正文，覆盖边界已在留痕登记），主文档正文未同步 | B6 审计覆盖边界的认知；Options 章节外散文裸词提及不在任何一路覆盖面内（已确认两 B 类形态均落在章节内，影响未显现） |
| D-4 | §2.13 方案 1 + §8.8 末段 | 「G10-a enforce 屏蔽（先行独立提交）」与实际提交序列不符（G10-a `f6129cef` 为 B6 最后一个提交、晚于收口登记 `173872b7`），prose-audit §9.2 R3 已勘误「以留痕为准」但正文未改 | B6 批次纪律记载与 git 史的一致性 |

## 五、测试与闸门实测（全部独立复跑，不引用他人输出）

| 闸门 | 命令 | 实测结果 |
|---|---|---|
| 全量测试 | `uv run pytest` | **848 passed, 0 skipped**（112.62s，exit 0，2 条三方库 deprecation 警告与本项目无关） |
| hq 产物 | `ls -la target/release/hq` | 存在（-rwxr-xr-x，17.9MB，2026-10-15 22:52 构建）——e2e 无静默跳过，通过数无虚高 |
| 进度校验 | `uv run python scripts/validate_progress.py` | OK（exit 0） |
| CHANGELOG 一致性 | `uv run python scripts/gen_changelog_md.py --check` | OK——CHANGELOG.md 与 CHANGELOG.jsonl 一致 |
| 计划状态（发布前闸门） | `uv run python scripts/check_plan_status.py` | OK——10 份计划文档状态均已回填为终态 |
| 前端零外链 | `bash scripts/audit_frontend_offline.sh` | OK——dist 零外链资源引用（豁免 5 组白名单前缀） |
| 设计令牌 | `uv run python scripts/check_tokens.py` | OK——暗色 92/92、明亮 31/31，逐变量 diff 为空 |
| 对比度 | `uv run python scripts/check_contrast.py` | OK——全组合 ≥ 4.5:1（最低 4.90:1） |
| 契约再生 | `uv run python web/scripts/gen_models.py` + `npm run gen:types` | 两步再生后 `git status --porcelain` 对 `openapi.yaml`/`models.py`/`contract.ts` **零残留**——生成物与契约 SSOT 逐字节一致 |

**独立行为冒烟**：临时脚本（`/tmp/final_review_r1/smoke_core.py` +
`smoke_fix.py`，直接 import 解析层）共 86 断言点，85 通过；唯一未过项
（route 缺失 + 文件开头 % 行未报 G3 title 错误）经查证为计划 §8.3 已登记
实现口径（文件开头前导 % 行归 Link0 收集），补充实测确认 % 行在标题行之后
时报 G3 错误、% 行在分子说明之后不报（§2.6 明文不扫描后续节）——**非缺陷**。
临时脚本与工作区用后已清理。

## 六、端到端与视觉审查记录

**① 隔离实例端到端**（development.md §6.2：`G16WEB_HOME=/tmp/final_review_r1/g16web-home`、
`G16WEB_HQ_BIN=$PWD/target/release/hq`、uvicorn `127.0.0.1:8399`；实测后
uvicorn 与 hq server/worker 已全部 kill，临时工作区已删除）：

| 通道 | 请求 | 实测 |
|---|---|---|
| 导入 | `POST /api/v1/candidates`（t_comment 单组对注释 / t_cp 多组对注释两 gjf） | 201，两文件通过（无 error），warnings=[] |
| 预览 | `GET /api/v1/candidates/{1,2}/preview` | `parse_errors=[]`；`charge_mult='0 1'` / `'0 1 0 1 0 1'`（**不含注释文本**，G11） |
| 编辑保存 | `PUT /api/v1/candidates/1/blocks/charge_mult`（body 传注释原文） | **HTTP 200 放行**（非 422），响应 `blocks.charge_mult='0 1'` |
| 提交 | `POST /api/v1/candidates/{1,2}/submit` | HTTP 200，`SubmitResponse` 含 `normalized` + `warnings` 字段 |
| 模板保存（G10-a） | `PUT /api/v1/combo-templates/1`，route=`#p frqu opt` | HTTP **200** + `notice.spelling_warnings=["frqu"]`（零 422）；`ignore_spelling=true` 与不传行为一致（均 200 + 同样警告） |
| 模板保存（G10-b/G8） | route=`#p opt=addredundant freq=nnroa` / `#p opt=(readfcht)` | 前者 200 零拼写警告；后者 200 + `route_option_warnings`（`suggestion=readfc`） |
| 对照 | 422 场景核实 | 模板保存的 422 全部来自**既有**资源下限校验（`mem_below_per_core_floor`/`nproc_cpu_mismatch`），非拼写 enforce——G10-a 屏蔽语义确认 |

**② 前端视觉实测**（playwright chromium，前端 dist 为最新构建（10-20 23:30
晚于全部前端源码，`exemptTokens`/`saveWithExemption` 产物零残留））：

- 组合流模板弹窗（`/#/settings`）：仅「关闭」「保存」两键，**「忽略拼写警告
  并保存」豁免按钮已隐藏**（G10-a 前端改动）；route 填 `#p frqu opt` 保存
  后弹窗保持打开、顶部琥珀提示「**词典外关键词（已放行）：frqu**」，布局无
  破版（截图 `final-r1-combo-warn.png`，过程件存 /tmp 未入库）。
- 候选编辑（`/#/candidates`，t_spell.gjf）：route 块编辑 blur 自动保存后渲染
  「**⚠ 第 2 行 「oppt」疑似拼写错误，是否意为「opt」**」琥珀警告条 +
  「已自动保存」——非阻断、message 优先渲染（G0 前端消费）生效（截图
  `final-r1-bewarn-spell.png`）。
- 导入响应 warnings 渲染链路：导入 t_spell 后 `files[]` 条目即携带
  `keyword_spell` 警告（line=2 全文件绝对行号），API 层先行验证。

**③ G16 直跑**：本计划逐批冒烟（B1×2、B2×6、B3×2、B4×3、B6×8、B7×2）已
由各批审查独立复现（B6 审查复跑 5 例 + 补测 2 例、B7 审查直跑 2 例 Normal
termination）；终审不再重复真实 G16 计算冒烟——本轮以解析层 86 断言点 +
四通道 API 实测覆盖同 fare 行为面，真实 G16 执行链路的 hq 派发经隔离实例
提交动作验证（提交 200、席位创建、hq server/worker 正常拉起）。

## 七、总体结论

**通过。**

- 计划 13 项缺口（C1/C2/C3 + G0–G11）与 B1–B7 全部批次验收标准逐条落地，
  经本轮独立代码实读、86 点行为冒烟、四通道 API 实测与前端视觉实测证实；
  9 项闸门全绿（含 hq 产物在位、契约生成物零 diff）；各批独立审查发现的
  P1/P2 问题（B1 R1/R2、B234 R1–R6、B5 R1/R3、B6 R1、B7 P1-1）全部整改
  闭环并经当轮复审留痕。
- 遗留事项均不阻断：2 条 P3 观察项（I-1 title 禁字同行只报首个、I-2 B6
  留痕条数维度缺登）与 4 条文档勘误建议（D-1…D-4，均为「留痕已勘误、
  计划正文未回改」型），建议随 3.4.0 发布流程或下轮文档维护顺带处置；
  其中 D-1（scf=conv 断言与实测矛盾）建议优先勘误，避免权威口径分叉。
- 发布提示：计划状态行「随 3.4.0 发布」——CHANGELOG unreleased 行条目已
  齐备、`check_plan_status.py` 已绿，3.4.0 冻结发布动作（§5.2 流程）待
  用户执行。
