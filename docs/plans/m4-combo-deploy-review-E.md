# 代码审查报告：m4 插波批次 E（验收与发布）就绪度复核

> 审查人：实现代码审查专员（独立复核，不采信实施者自述；只审不改）
> 审查日期：2026-10-14 · 分支 g16-webui · HEAD = bffba5a2 · 工作区干净
> 边界声明：本次审查**未执行**冻结五步、未打 tag、未做任何发布动作——仅复核 E 的执行条件并输出差距清单。

## 一、审查依据与范围

- **依据**：`docs/plans/m4-combo-template-deploy-plan.md`——§2 WBS 批次 E 行（验收标准）、§5 提交序列（#14/#15）、§6 闸门清单、附录 B（预期条目域与「无空白条目」要求）、附录 C 评审清单 C1–C11、§7 R-4 放行判据、§8.1 降级口径与进度跟踪锚、§8 开放事项 4；`docs/references/changelog-spec.md`（§1.4 豁免口径、§1.6 发布流程、§1.7 semver 判定、§2.3 更新时机）；AGENTS.md §5.2/§6。
- **对象**：工作区当前状态全量——计划文档附录 B、`CHANGELOG.jsonl`、`progress.json`、四份审查报告（`m4-combo-deploy-review-A-B.md`/`-C.md`/`-D.md`/`-F1F2.md`）、插波全量提交（`b8ba4287..bffba5a2`，46 个提交）。
- **范围证实**：`git status` 起止均为 clean（porcelain 空输出，实测）；`git log --oneline b8ba4287..HEAD` 实测 46 提交，与批次 A/B/C/D/F1/F2 及三轮审查整改的提交清单逐一对应；审查终了复验 `git status --porcelain` 为空（再生与构建产物零残留）。
- **报告落盘**：`docs/plans/m4-combo-deploy-review-E.md`（调用方指定路径；落盘前 `ls docs/plans/` 确认无同名既有报告，未覆盖任何文件）。

## 二、总评（E 就绪度结论）

**结论：有条件就绪。**

技术面全部就绪：§6 闸门终跑全绿（全量 739 passed 零跳过、e2e 3 例真实运行、契约再生字节幂等零 diff、前端四闸门过、治理两脚本过、hq 产物在位）；四份审查报告的 P0/P1/P2 **全部闭环**（R-4 放行判据的缺陷轴满足）；`CHANGELOG.jsonl` unreleased 与 `progress.json` 镜像 17 条逐条完全一致；三轮审查整改的 fixed 条目齐全；版本判定预核成立（含 added 无 breaking → minor → **3.2.0**）；B3 不登记与 enforce 直上口径自洽；next_steps 与本波无冲突。

剩余差距均为**执行层与裁决层**事项，无技术阻断：① docs(plans) 类提交（计划定稿/走查回填/审查报告落盘）未记 unreleased，按 changelog-spec §1.4 豁免口径条件 2 与 v3.1.0 先例应记，须实施者在冻结第 1 步（E1 的「无遗漏」确认）裁决——补记或明示豁免（E-1）；② 审查整改尚无附录 B 条目，建议补录 RG1–RG6（E-2）；③ 批次 C 审查报告第六节浏览器抽检清单无处置留痕（E-3）。上述收口且用户当次明确授权后，E1–E5 可执行。

## 三、附录 B 条目完整性对照表

预期条目域（附录 B ：505/:517-529）：A1–A24（A7 拆 A7a/A7b）、AG1、FG1/FG2、B1/B2/B3、D1–D5、E1–E5。实测 `grep -n "^- 批次 / 条目："` 逐条核对：

| 预期条目 | 附录 B 现状 | 结论 |
|---|---|---|
| AG1（A 批次词表三对照） | 已回填（:533），含 F-3 补注（:547，md5 口径 + `--disable-timestamp` 整改指向） | 已有实测结论 |
| B1（四项核验复核） | 已回填（:553），2026-10-14 开工复核通过 | 已有实测结论 |
| B2（词典扩充再生） | 已回填（:572），97→387、判据①②③、逐字节一致 | 已有实测结论 |
| B3（enforce 切换复核） | **无条目**——`SPELLING_MODE = "enforce"`（`web/src/services/combo_templates.py:34` 实测）、全库无「切换 enforce」提交（`git log --grep` 空输出）→ §5 #6 未执行 | **口径正确**：B3 仅 #6 执行时登记（附录 B :525），与 C11 后半「若执行 #6 须四项」一致——本波 enforce 直上、#6 不适用，B3 无条目系条件提交语义的如实体现，非空白违规 |
| A1–A24（C 批次浏览器走查） | 已回填（:594，逐条实测），A7b 标注「不适用（enforce 已上线，无降级）」、A24 随 FG2 补录、A13 含 C-4 补注（:626） | 已有实测结论；「不适用」标注符合「无空白条目」要求 |
| D1–D5（D 批次真机走查） | 已回填（:663/:690/:709/:723/:746），D2 记录 2 项缺陷随 #12 落库修复 | 已有实测结论 |
| FG1/FG2（F1/F2 git diff 核对） | 已回填（:758/:794），含 F1F2-1/F1F2-2 口径补注（:775/:781） | 已有实测结论 |
| E1–E5（冻结五步留痕） | **无条目** | **预期空白**：批次 E 未执行（冻结属用户授权动作，§8 开放事项 4），E 执行时逐条对应 AGENTS.md §5.2 回填 |
| §1.1 F-4 行号口径补注 | 在位（:111「以形态内容为准（独立审查 F-4 实测…）」） | 已补 |

**无空白条目要求判定**：对已执行批次（A/B/C/D/F1/F2）而言逐条有实测结论或标注「不适用」，无空白——满足批次 E 验收标准的该子句；E1–E5 属待执行批次的载体位，不构成空白违规。

**应补录条目建议（RG 系，审查整改尚无附录 B 条目）**：四轮审查的发现与修复以审查报告、CHANGELOG 条目 13–17 与计划文档补注为载体，但附录 B 无对应走查条目。建议实施者随 E 阶段 docs(plans) 提交补录（明细见第八节 E-2）：RG1（F-1 is_default 修复复验）、RG2（F-2 再生幂等复验）、RG3（C-1/C-2/C-3 豁免两段式与错误态修复 + A7a/A18 断言回归）、RG4（D-1/D-2 离线布局修正与真资产布局对照）、RG5（D-3/D-4/D-5 参数防线沙箱用例）、RG6（F1F2-1/F1F2-2 留痕口径补注，纯文档可并入）。

## 四、unreleased 完整性与镜像一致性核对

### 4.1 镜像一致性（程序化逐条 diff）

`python3` 解析两文件逐字段（type/scope/summary/breaking/migration）比对：**CHANGELOG.jsonl unreleased 17 条 = progress.json unreleased 17 条，逐条完全一致**（实测输出「逐条 diff 结果: 完全一致」）。复现：

```bash
python3 - <<'EOF'
import json
cl=[json.loads(l) for l in open('CHANGELOG.jsonl',encoding='utf-8') if l.strip()][11]['changes']
pj=json.load(open('progress.json',encoding='utf-8'))['unreleased']
print(len(cl),len(pj),all(a==b for a,b in zip(cl,pj)))
EOF
```

### 4.2 对照 git log 的完整性

插波区间 `b8ba4287..bffba5a2`（46 提交）与 unreleased 17 条映射核对：

| unreleased 条目 | 对应提交 | 核对 |
|---|---|---|
| 1–2（development.md §6 拆分、种子脚本） | cb0901c5 / 4b859196（波前） | 在册 |
| 3–7（#2–#5：契约/存储/词典/契约补录/校验服务） | 1f09471b / f6165113 / 07da49c0 / cd529130 / e8b5d4ca | 在册 |
| 8–10（#8/#9/#12：弹窗/下拉/部署脚本） | 136b7663 / f81477a6 / 2129e931 | 在册 |
| 11–12（#7/#10：F1/F2） | b953de99 / d5c6ef2a | 在册 |
| 13–17（**三轮审查整改 fixed**） | 619842d3（F-1）／22d437c0（F-2）／4a72f5b6（C-1/C-2/C-3）／47bd0793（D-1/D-2）／7a15d6df（D-3/D-4/D-5） | **齐全**；F1F2 轮零修复（仅 P3 注记，随 bffba5a2 落） |
| chore/test 类（#11、进度登记、报告落盘等） | 按豁免口径不记/待裁决（见 E-1） | — |

**整改 fixed 条目结论：三轮（A-B/C/D）全部在册、无遗漏；F1F2 轮无修复项，口径成立。**

**发现（E-1，P3）**：docs(plans) 类实质提交未记 unreleased——插波计划定稿（5306891b）、五批走查留痕回填（0e963732/22fbd736/e6884c24/d9504f8f/1f2f74bc，含 R-3 具名清单定案回填）、四份审查报告落盘与留痕注记（5f408326/846a6a9a/2a2a01ec/bffba5a2）。按 changelog-spec §1.4 豁免口径条件 2（「计划定稿与裁决回填、审核结论留痕」**照记**）与 v3.1.0 先例（「A5 断点续跑与组合流设计定稿」「落档 M4 D3 验收走查记录」均照记），该批提交应记；属冻结第 1 步「确认 changes 已完整（无遗漏）」的裁量输入，须实施者裁决：补记（建议合并为 2–3 条 docs 摘要）或在 E 验收记录中明示豁免理由（注：v3.0.2 批次 m4-plan 修订即未逐条记录，存在先例分叉，故定 P3 裁决项而非确定性遗漏）。

### 4.3 治理闸门

`uv run python scripts/validate_progress.py` → `OK`（exit 0）；`uv run python scripts/gen_changelog_md.py --check` → `check_changelog_md: OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致`（exit 0）。

## 五、§6 闸门终跑实测记录（全部独立重跑，2026-10-14，HEAD bffba5a2）

| # | 闸门 | 命令 | 实测输出（摘要） | 判定 |
|---|---|---|---|---|
| 1 | 全量测试 | `uv run pytest -q` | **739 passed, 2 warnings in 105.61s**——0 failed、0 skipped（warnings 为 starlette/anyio DeprecationWarning，环境噪声） | 过 |
| 2 | e2e 真实运行 | `uv run pytest web/tests/test_e2e_fake_g16.py -q` | **3 passed in 5.25s**——hq 在位，非静默跳过，通过数无虚高 | 过 |
| 3 | hq 产物 | `ls -l target/release/hq` | `-rwxr-xr-x 17957408 Oct 12 11:23`（md5 `14afadd556c5d54b4c13f0535e37648b`） | 在位 |
| 4 | 进度校验 | `uv run python scripts/validate_progress.py` | `OK`，exit 0 | 过 |
| 5 | CHANGELOG 一致性 | `uv run python scripts/gen_changelog_md.py --check` | `OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致`，exit 0 | 过 |
| 6 | 契约三闸门 | `uv run pytest web/tests/test_openapi_ssot.py web/tests/test_error_codes.py web/tests/test_extract_keywords.py -q` | **23 passed**（含词典全小写/去重/排序与判据①②③断言） | 过 |
| 7 | 契约再生零 diff | `uv run python web/scripts/gen_models.py` + `cd web/frontend && npm run gen:types` | 生成命令带 `--disable-timestamp`（F-2 整改在位）；再生后 `git status --porcelain` **空输出**——字节幂等零 diff 字面成立 | 过 |
| 8 | 前端构建 | `cd web/frontend && npm run build` | vue-tsc 零错误，`✓ built in 5.00s`（chunk >500kB 为既有 3dmol/echarts 打包提示，非闸门项） | 过 |
| 9 | 前端零外链 | `bash scripts/audit_frontend_offline.sh` | `零外链资源引用（豁免 5 组白名单前缀）`，exit 0 | 过 |
| 10 | 设计令牌 | `uv run python scripts/check_tokens.py` | 暗色 92/92、明亮 31/31，逐变量 diff 为空，`OK` | 过 |
| 11 | WCAG 对比度 | `uv run python scripts/check_contrast.py` | 全组合 ≥ 4.5:1（最低 failed 徽标 4.71:1），`OK` | 过 |
| 12 | 工作区还原 | 再生+构建后 `git status --porcelain` | 空输出——**工作区还原干净** | 过 |

整改落库证据抽验（独立核验，非采信自述）：F-1 断言在位（`web/tests/test_combo_templates.py:101` `test_is_default_false_preserves_row_state`、`:172` `test_is_default_omitted_or_false_preserves_default_owner`）；C-1 两段式逻辑在位（`ComboTemplatesModal.vue:172-190`，「两段式按 token 粒度豁免」+ `every(t => exemptTokens.has(t))` 重试门控）；D-3/D-4/D-5 在位（`setup_deps.sh:58` `sed -n '2,25p'`、`:46-48` `--dest` 缺值用法提示 exit 2、`:121` `chmod +x "$crest_bin"` 收窄）；D-1/D-2 修正文本在位（`deployment.md:128-137`，crest/ 嵌套上移与 xtb-dist/ 改名两段与审查 D 建议措辞及 D2 实测布局一致）。

## 六、附录 C 逐条复核结论（C1–C11，非降级交付口径）

| # | 维度 | 结论 | 证据 |
|---|---|---|---|
| C1 | 依赖齐备无环 | 可勾选 | §2 依赖关系（A→B→C，F1 并行，F2 依赖 F1+C+B，D 独立，A–D/F1/F2→E）与批次子步骤齐备；实际执行序（git log）与依赖边一致，无环 |
| C2 | 闸门判定可复核 | 可勾选 | 本报告第五节逐项实测即复核留痕；各批次另有四份审查报告闸门记录 |
| C3 | 风险登记覆盖四类 | 可勾选 | §7 R-1–R-13 覆盖技术/资源/时间/外部依赖，逐条含触发条件与应对预案（R-11 为已接受取舍、已标注） |
| C4 | R-1/R-2/R-3 与 §8 口径一致 | 可勾选 | R-1/R-2 降级语义指向 §8.1 且本波未触发（词典 387 词达标、enforce 直上）；R-3 的 2026-10-13 核验执行结论已回填 §8.2/§3.2/附录 A |
| C5 | 交付物明确含词表三 | 可勾选 | §2 各批次产出物含路径与内容范围；词表三 11 项 reason 与 §3.2 清单一一对应（AG1 已复核，本报告未重跑 grep、采信 A-B 审查四-7 逐位一致结论 + 契约 23 passed） |
| C6 | 留痕载体与格式已定 | 可勾选 | 附录 B 条目格式块（:504-512）与环境检查前置、预期条目域齐备 |
| C7 | 验收标准可量化 | 可勾选 | WBS 验收列均为可验证判据（零 diff、逐条断言、HTTP 200+workflow_id、11 项 reason 等），无模糊表述 |
| C8 | 附录 A 与 §3.2/§3.4 一一对应 | 可勾选 | 附录 A 25 条与 §3.2 矩阵/§3.4 规格对应（审查 C 第三节 F1–F16 逐条核对通过；A7a/A7b 按 mode 分执行已留痕） |
| C9 | 交叉引用无断链 | 可勾选（以已核查范围为限） | 本审查核查的交叉引用（B3↔#6、E1–E5↔AGENTS §5.2、§8.1↔C11、R-13↔E 依赖、§1.1↔FG1/FG2）均可达；§1.1 存量清单经 F1/F2 审查逐条与代码核对清零 |
| C10 | 全小写口径贯穿 | 可勾选 | §3.2 归一化行（casefold 入库）、§4（词典全小写断言，闸门 #6 过）、§5（#4 再生/#7 F1/#10 F2）三线一致；FG1/FG2 复扫零大写残留（F1F2 审查复核） |
| C11 | 降级口径 | **前半不适用，后半不适用** | 本波**非降级交付**：B2 判据①②③全过留痕（387 词达标）、`SPELLING_MODE="enforce"` 默认上线（实测）、§5 #6 未执行（无切换提交）——故「降级交付时」分支（B1/B2 待补标注、A7a 不适用、遗留项登记 next_steps）整体不适用；「若执行 #6」分支因 #6 未执行亦不适用。非降级交付要求 C1–C10 全过——本节逐条成立 |

**§8.1 进度跟踪锚核对**：本波非降级交付 → 无需将「词典扩充 + enforce 切换」登记 `next_steps`；progress.json `next_steps` 现有 3 条（v3.0.2 附件上传、S3 判据盲区观察、N5 备查）**与本波无冲突**，核实成立。

## 七、版本判定预核与 R-4 放行判据

### 7.1 版本判定预核（changelog-spec §1.7）

- unreleased 17 条构成：**added 8**（条目 2/3/4/5/7/8/9/10）+ **changed 4**（条目 1/6/11/12）+ **fixed 5**（条目 13–17），`breaking` 全为 false。
- §1.7：无 breaking 且含 added → **minor → 3.2.0**。判定成立。
- 现状核对：`CHANGELOG.jsonl` 第 12 行 `version=null, status="unreleased"`，semver/date 缺省——**未冻结态正确**；README 当前版本表述为 v3.1.0（README.md:4）——冻结第 5 步待刷新态正确。

### 7.2 R-4 放行判据（阻断性缺陷清零）

四份审查报告 P0/P1/P2 闭环核对（逐条独立验证修复落库，见第五节抽验）：

| 报告 | 编号 | 级别 | 闭环证据 | 状态 |
|---|---|---|---|---|
| A-B | F-1 is_default 语义 | P0 | 619842d3 修复 + repo/API 级断言在位 + 审查 C 四保存路径复验 | **已闭环** |
| A-B | F-2 再生时间戳头 | P2 | 22d437c0 修复（`--disable-timestamp`）+ 本报告第五节 #7 再生零 diff 独立复现 | **已闭环** |
| C | C-1 豁免粒度 | P2 | 4a72f5b6 两段式修复 + 代码在位（ComboTemplatesModal.vue:172-190） | **已闭环** |
| D | D-1/D-2 离线布局 | P1 | 47bd0793 修正 + deployment.md:128-137 与真资产布局一致 | **已闭环** |
| F1F2 | —（无 P0/P1/P2） | — | 仅 P3 留痕措辞 | — |

P3 层：F-3/F-4/C-4/F1F2-1/F1F2-2 补注在位；C-2/C-3/D-3/D-4/D-5 已随整改提交修复；C-5 无需整改；F-5/D-6 备案（D-6 可选项未做，见 E-4，不阻断）。**阻断性缺陷清零 → R-4 放行判据在缺陷轴满足**；R-4 触发条件（同一断言回归失败 ≥2 次或缺陷累计 ≥5 条）未触发——走查缺陷（C 批 2 项 + D 批 2 项）均当场修复且未再现。

## 八、E 执行差距清单（距离可执行冻结五步还差的项）

| # | 事项 | 责任方 | 前置 | 级别 |
|---|---|---|---|---|
| 1 | **E-1 docs 类条目裁决**：插波计划定稿、五批走查回填、四份审查报告落盘共 10 个 docs(plans) 提交未记 unreleased（§4.2）——冻结第 1 步「无遗漏」确认的裁量输入：补记（建议合并 2–3 条 docs 摘要）或明示豁免理由 | 实施者 | 冻结（E1）前 | P3 |
| 2 | **E-2 RG1–RG6 补录附录 B**：四轮审查整改无附录 B 条目，建议随 docs(plans) 提交补录复验留痕（RG1 is_default 复验／RG2 再生幂等复验／RG3 两段式豁免 + A7a/A18 回归／RG4 离线布局对照／RG5 参数防线沙箱／RG6 注记归组）。注：A1–A24 条目的 A7a 步骤描述仍系修复前批次级豁免行为，宜借 RG3 顺带补注两段式现行为 | 实施者 | 冻结（E1）前 | P3 |
| 3 | **E-3 C 审查报告浏览器抽检清单处置**：审查 C 第六节「主代理浏览器复测清单」的完成/豁免无留痕，其结论注明「复核后方可与附录 B 留痕合并作为批次 E 验收输入」——补做抽检或在 E 验收记录中明示以附录 B 实施者 playwright 留痕 + 审查 C API 级复验为准 | 主代理/用户 | E 验收记录落盘前 | P3 |
| 4 | **E-4 D-6 备案项**：`setup_deps.sh --dest /` 退化值防护未做（审查 D 明示「可选」）——保持备案或下次脚本触批顺手收口，不阻断 E | 实施者 | 无（可延后） | P3 备注 |
| 5 | **E1–E5 执行本身**：冻结五步按 AGENTS.md §5.2（SSOT 为 changelog-spec §1.6）执行并逐条回填附录 B。**执行注意**：AGENTS.md §5.2 五条目未显式含 README 步，实际须按 §1.6 六步走——含第 5 步 README.md 版本表述刷新（v3.1.0→v3.2.0）与 §2.3 发布时复核（next_steps/known_issues/context 刷新，latest_released_version 出现于 context） | 实施者（用户授权后） | 用户当次明确授权 | 执行项 |
| 6 | **next_steps 冻结复核**：§2.3 要求发布时复核与现状一致——现 next_steps 仅登记 v3.0.2 附件上传，而 context 载明 v3.1.0 附件亦待上传；冻结第 4 步复核时顺带对齐（补登 v3.1.0 上传或确认已完成） | 实施者 | 冻结第 4 步 | P3 备注 |
| 7 | **发布授权**：3.2.0 冻结、tag 与任何推送须用户当次明确授权（§8 开放事项 4、AGENTS.md §5.4）——一次授权不推定延伸 | 用户 | 全部冻结动作之前 | 授权项 |

## 九、问题清单汇总

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| E-1 | P3 | 约定违例（待裁决） | CHANGELOG.jsonl unreleased；提交 5306891b/0e963732/22fbd736/e6884c24/d9504f8f/1f2f74bc/5f408326/846a6a9a/2a2a01ec/bffba5a2 | docs(plans) 类实质提交（计划定稿/裁决回填/审核结论留痕）未记 unreleased，与 §1.4 豁免口径条件 2 及 v3.1.0 先例（A5 定稿、D3 走查记录照记）不一致；v3.0.2 批次亦有不记先例，口径分叉 | 实施者在冻结第 1 步裁决：补记合并条目或明示豁免理由并留痕 |
| E-2 | P3 | 可维护性（留痕） | m4-combo-template-deploy-plan.md 附录 B | 四轮审查整改（619842d3/22d437c0/4a72f5b6/47bd0793/7a15d6df 及各补注）无附录 B 条目；A7a 走查描述未反映两段式修复后行为 | 补录 RG1–RG6（见第八节 #2） |
| E-3 | P3 | 测试有效性（流程） | m4-combo-deploy-review-C.md 第六节 | 浏览器抽检清单无处置留痕，C 报告结论与附录 B 合并的条件未闭合 | 补做抽检或明示以既有留痕为准并落 E 验收记录 |
| E-4 | P3 | 备注（安全/健壮性） | scripts/deploy/setup_deps.sh | D-6 `--dest /` 退化值防护未做（审查 D 定性可选备案） | 保持备案，下次触批顺手收口 |
| E-5 | P3 | 备注（执行注意） | 附录 B「E1–E5 逐条对应 AGENTS.md §5.2 冻结五步」 | AGENTS.md §5.2 五条目不含 README 刷新，SSOT §1.6 为六步 | E 执行时按 §1.6 六步走并在 E1–E5 回填中覆盖 README 步 |

无 P0/P1/P2 问题。本审查未发现任何技术阻断项。

## 十、端到端与视觉审查记录

- 本批次为验收与发布收口，无新增 UI/链路改动；端到端面以闸门实测覆盖：hq 产物在位（17,957,408 字节）→ e2e 3 例真实运行非静默跳过（第五节 #2/#3），全量 739 passed 含派发/续跑/物化链回归。
- 视觉面：本审查环境无浏览器工具，未做视觉实测，**不在视觉维度给出通过结论**；批次 C 的浏览器视觉走查以附录 B 实施者 playwright 留痕（A1–A24 逐条 + 截图路径）为载体，审查 C 已做 API 级独立复验，其浏览器抽检清单的处置为差距项 E-3。

## 十一、总体结论

**有条件就绪。**

- **已就绪面**：§6 闸门全部独立复跑全绿且工作区还原干净；四份审查报告 P0/P1/P2 全部闭环（R-4 缺陷轴满足）；unreleased 镜像逐条一致、整改 fixed 条目齐全；版本判定 minor→3.2.0 成立且冻结前字段状态正确；B3 不登记、C11 前半不适用、next_steps 无冲突三项口径核实成立。
- **放行条件**（逐条完成后方可执行冻结）：
  1. E-1：实施者对 docs(plans) 类提交的 unreleased 记录口径作出裁决（补记或明示豁免）——冻结第 1 步输入；
  2. E-2：实施者补录 RG1–RG6 附录 B 条目（可与 E-1 同一 docs(plans) 提交）；
  3. E-3：C 审查浏览器抽检清单完成或明示豁免；
  4. 用户对 3.2.0 冻结与发布的当次明确授权（§8 开放事项 4）——此前不得执行任何冻结/tag/推送动作。
- 条件 1–3 收口后，E1–E5 按 changelog-spec §1.6 六步执行（含 README 刷新与 §2.3 复核）并逐条回填附录 B，本波即可发布收口。
