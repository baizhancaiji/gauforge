# 代码审查报告：input-verify-gap-remediation-plan 批次 B7（正确性补修 G11）

## 一、审查依据与范围
- **依据**：`docs/plans/input-verify-gap-remediation-plan.md` §2.14 G11 方案（:968-1003）、
  §3 批次表 B7 行（:1017）、§3.1 B7 节点（:1035-1037）、§5 测试方案总纲（:1101-1129）；
  实施者留痕 §8.9（:1503-1542）仅作对照，不作为结论依据。
- **对象**：git 区间 `7b5c06aa..HEAD`（B6 收口后全部 5 提交）：2ed38a76（先行红测试）、
  444ba1ec（progress 开工）、29c71d88（实现）、a4f68b71（进度/CHANGELOG 收口）、
  890bb553（计划留痕与状态回填）。
- **范围证实**：`git status` 工作树 clean；`git diff 7b5c06aa..HEAD --stat` 实测改动全集
  6 文件——`web/src/parse/blocks.py`（+20/-2）、`web/tests/test_parse_blocks.py`（+41）、
  `CHANGELOG.jsonl`（+1/-1）、`CHANGELOG.md`（+1）、`progress.json`（+8/-3）、计划文档
  （+43/-1）。`docs/api/openapi.yaml` 与 `web/src/parse/warnings.py` 在该区间**零改动**
  （git diff 为空，实测），「无 schema 与 kind 词表变更」声明成立。依赖约束核实：
  B4 的 `parse_charge_tokens` 单点已在（B7 前即存在），B7 改动与 B6 文件集无交集。
- **报告落盘**：`docs/plans/input-verify-gap-remediation-plan-B7-review.md`（调用方指定）。

## 二、功能完整性对照
| 编号 | 计划条目（批次表 :1017 / §2.14） | 实现位置 | 结论 |
|---|---|---|---|
| R1 | `parse_charge_tokens` 在归一化前剥离**引号外**首个 `!` 及其后内容 | `web/src/parse/blocks.py:155-168`（引号感知扫描截断，en-dash/逗号/斜杠归一在剥离之后） | 已落地 |
| R2 | `0 1 ! …` 预览/导入/提交零错误、编辑保存放行 | 四通道独立冒烟全过（见第五节①–④） | 已落地 |
| R3 | `0,1 0,1 0,1 ! …` 同上（多组对） | 同上（counterpoise=2 输入，四通道零错误） | 已落地 |
| R4 | `charge_mult` 规范化输出不含注释文本 | `blocks.py:378`（parse_input）与 `candidates.py:412-419`（_expected_blocks）均以整数重建输出；实测响应为 `'0 1'` / `'0 1 0 1 0 1'` | 已落地 |
| R5 | 剥离后 token 不足/非整数仍照常记 parse_errors | `test_parse_blocks.py:245-256` 三形态（不足/非整数/独立注释行）转绿；剥离逻辑不改既有判定 | 已落地 |
| R6 | 既有电荷行用例（斜杠/en-dash/多组对）不回归 | `test_parse_blocks.py:711/737` 等既有用例全量套件内通过 | 已落地 |
| R7 | 全量测试不回归 | `uv run pytest`：**847 passed, 0 skipped**（本次独立实测）；`target/release/hq` 存在（10-15 构建），无 e2e 静默跳过 | 已落地 |
| R8 | G16 Rev. C.01 冒烟一例实测背书，分歧按 §2.12 登记 | 本审查独立复现两例（单组对/多组对）均 Normal termination，log 确认 `Gaussian 16, Revision C.01`；实测与手册一致，无分歧登记需求（见第五节⑤） | 已落地 |
| R9 | 无 schema 与 kind 词表变更 | openapi.yaml / warnings.py 零改动（git diff 实测） | 已落地 |
| R10 | CHANGELOG 登记接受集扩大 | `CHANGELOG.jsonl` unreleased 追加 `fixed/parse` 条目（G11、接受集扩大、G16 冒烟背书），`gen_changelog_md.py --check` 通过 | 已落地 |
| R11 | §2.14 涉及文件：`test_block_save.py` 补「编辑保存通道放行」用例 | B7 区间 `test_block_save.py` **零改动**；全库检索确认无 save_block+电荷+注释组合用例；仅以不入库的临时脚本实测背书（留痕 §8.9，偏离未说明） | **未落地 → 问题 P1** |

单点拉齐核实：`parse_input`（`blocks.py:368`）、`_validate_section`（`candidates.py:333`）、
`_expected_blocks`（`candidates.py:412`）三通道确实共用 `parse_charge_tokens` 单点，
与「经同一单点自动拉齐」的方案一致。

## 三、问题清单
| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| P1-1 | P1 | 测试有效性 | `web/tests/test_block_save.py`（缺失用例）；对照计划 :995-998 | §2.14 明确要求在 `test_block_save.py` 补「编辑保存通道放行」用例，实际未补且留痕未登记该偏离——编辑保存通道（G11 三大误拒症状之一，原 422 主战场）的 G11 行为无持久化回归保护，仅由不入库临时脚本背书（留痕 §8.9）；后续 `candidates.py:333` 调用点若被改坏，全量测试无法拦截 | 补 `save_block(tid, "charge_mult", ["0 1 ! …"])` 放行 + 规范化输出断言用例（可并入既有 :220/:495 用例族），提交时在留痕补记偏离原因 |
| P3-1 | P3 | 约定违例 | `progress.json` `"updated"`（a4f68b71 引入） | 由历史一贯的带时区偏移格式 `2026-10-21T00:22+0800` 退化为无偏移的 `2026-10-21T00:33`（近 8 次历史提交实测均带 `+0800`）；`validate_progress.py` 仅校验字段存在不拦格式 | 回填为带 `+0800` 偏移的 ISO 8601 格式，与历史惯例拉齐 |
| P3-2 | P3 | 可维护性 | `web/src/parse/blocks.py:151`；对照 `keywords.py:58-60` | docstring「与 route 通道 C3 管道同规」概括不精确：C3 管道引号内 `!` 保留为 token 整体不切分，电荷行将引号内 `!` 替换为空格作分隔符（`blocks.py:167`）——「引号外首个 `!` 截断」同规，引号内 `!` 的后续处理两处不同；docstring 虽已注明「留作分隔符处理不入 token」且有测试断言（`test_parse_blocks.py:232-243`），但「同规」易误导后续维护者 | 将「同规」表述限定为「注释截断规则同规」，或注明引号内 `!` 处理差异及缘由 |

实现层未发现逻辑缺陷：未闭合引号时扫描自然落到行尾（无引号外 `!`，整行走既有归一化）；
`line[:cut]` 内残留 `!` 只可能来自引号内，替换为分隔符与测试断言一致；单行 O(n) 扫描
无性能与注入面。

## 四、测试与闸门实测
| 闸门 | 命令 | 实测结果 |
|---|---|---|
| 全量测试 | `uv run pytest` | **847 passed, 0 skipped**（120.44s，本次独立执行）；`ls -la target/release/hq` 确认产物存在（-rwxr-xr-x，10-15 22:52），无 e2e 静默跳过 |
| 进度校验 | `uv run python scripts/validate_progress.py` | OK（exit 0） |
| CHANGELOG 一致性 | `uv run python scripts/gen_changelog_md.py --check` | OK——CHANGELOG.md 与 CHANGELOG.jsonl 一致 |
| 计划状态 | `uv run python scripts/check_plan_status.py` | OK——10 份计划文档状态均已回填为终态 |
| 前端闸门 | `audit_frontend_offline.sh` / `check_tokens.py` / `check_contrast.py` | **不适用**——B7 零前端文件改动（diff stat 证实），非前端/展示批次 |
| 语料基线 | 临时脚本 `uv run python /tmp/b7_review/corpus_baseline.py`（新旧实现逐文件对比，`~/g16/tests/com` 1156 文件，utf-8/replace 解码、不拒文件口径） | 新旧均：charge_mult 解析失败命中 6 文件（test0892/0894/0896/0897/1100/1102），**差集为空**；warnings 总数 **25→25**（link0_directive_unknown 2、molecule_multiple_charge_pairs 5、title_forbidden_char 18，逐 kind 零变化）；解析异常 0——与留痕 §8.9 数字逐位一致（独立复现） |
| 先行红复核 | `git worktree add /tmp/b7_review/wt-red 2ed38a76` 后跑 `-k g11` | **2 failed**（test_g11_charge_line_inline_comment、test_g11_comment_cut_quote_aware）**1 passed**（test_g11_comment_stripped_still_validates 回归守卫）——先行红两例 + 守卫绿的设计与自述一致（独立实测，worktree 已清理） |

## 五、端到端与视觉审查记录
**① 四通道实测**（development.md §6.2 隔离实例：`G16WEB_HOME=/tmp/b7_review/g16web-home`、
`G16WEB_HQ_BIN=$PWD/target/release/hq`、uvicorn `127.0.0.1:8398`，实测后已 kill 停止）：

| 通道 | 请求 | 实测 |
|---|---|---|
| 导入 | `POST /api/v1/candidates`（两 gjf multipart） | 201，两文件 `error=None`（id=1 仅自带 `%pchk` 触发 `link0_directive_unknown` 警告，属 B4 检测项正常工作，与 G11 无涉） |
| 预览 | `GET /api/v1/candidates/{1,2}/preview` | `parse_errors=[]`；`charge_mult='0 1'` / `'0 1 0 1 0 1'`（不含注释）；多组对带 counterpoise=2 佐证无 molecule_multiple_charge_pairs 警告 |
| 编辑保存 | `PUT /api/v1/candidates/{1,2}/blocks/charge_mult`（body 传注释原文） | **HTTP 200 放行**（非 422），响应 `blocks.charge_mult` 规范化无注释 |
| 提交 | `POST /api/v1/candidates/{1,2}/submit` | HTTP 200，零 parse 错误，warnings 仅 `%pchk` 一项 |

提交后 G16 执行段两任务 `failed`，逐日志归因均**非 G11 形态**：① 冒烟输入用整数坐标
（t_cp 日志三组 `Charge = 0 Multiplicity = 1` 已全部正常读取后，`Wanted a floating point
number` 于坐标行——与留痕 §8.9 顺带观察的该机 G16 限制一致，属 §2.12 不校验面）；
② t_comment 自带 `%pchk` 非官方 Link 0（l1.exe percent card 拒绝，审查者构造输入失误）。

**② G16 Rev. C.01 直跑复现**（`source ~/g16/bsd/g16.profile`，`/tmp/b7_review/g16run`，
log 首部确认 `Gaussian 16, Revision C.01`）：
- t_comment（`0 1 ! neutral singlet`，浮点坐标）：`Charge = 0 Multiplicity = 1` 正常读取，
  **Normal termination**，exit=0；
- t_cp（`0,1 0,1 0,1 ! cp pairs`，counterpoise=2，Fragment 标注 + 片段电子数合法化后）：
  三组电荷/多重度全部正常读取，**Normal termination**，exit=0。

实测与手册一致（G16 忽略行内注释），无 §2.12 分歧登记需求——与留痕结论一致（独立
复现；审查者输入与实施者哈希不同系坐标写法/Fragment 标注差异，不影响行为判定）。

**③ 视觉 UI/UX**：不适用——B7 无前端文件改动（diff stat 证实），无视觉验收面。

## 六、总体结论
**有条件通过。**

B7（G11）核心交付全部成立且经独立实测背书：单点实现正确、三通道拉齐、四通道冒烟
零错误、G16 Rev. C.01 直跑两例 Normal termination 与手册一致、语料基线零扰动、全量
847 passed 0 skipped、四项校验闸门全绿、无 schema 与 kind 词表变更、CHANGELOG 登记
到位、先行红设计经独立复核证实。

通过条件（整改后复审，不需重跑全部闸门）：
1. **P1-1**：补 `test_block_save.py` 编辑保存通道 G11 放行用例（§2.14 明确要求），并在
   计划留痕补记该偏离原因；
2. **P3-1 / P3-2** 顺带整改（progress.json updated 格式回填；blocks.py docstring「同规」
   表述限定）。
