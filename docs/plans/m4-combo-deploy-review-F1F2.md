# 代码审查报告：m4 插波批次 F1/F2（Link0/route 全小写收口·后端/前端）

## 一、总评与结论

**结论：通过。**

批次 F1（b953de99 + 8627cfc7 + d9504f8f）与 F2（d5c6ef2a + d457ed55 + 1f2f74bc）对照
m4-combo-template-deploy-plan §0.3/§1.1/§2（WBS F1/F2 行与子步骤）/§4/§5（#7/#10）/§6
逐条独立复核：§1.1 清单 #1–#9 与两条 R-8 表外补录（F1 五处、F2 八处）全部落地且
零遗漏；全库复扫 web/src 与 web/frontend/src 大写 Link0 形态零残留（仅余 strftime
`%Y%m%d` 与文法占位 `%Key=` 两既知非违反项）；语义不变式（仅改写形态、不改 G16
语义）经解析链逐环节核验成立；受影响测试断言刷新后真实锁定小写形态、输入侧大写
夹具保留覆盖大小写不敏感解析；全部闸门独立重跑全绿（全量 739 passed 零跳过、
e2e 3 例真实运行、hq 产物 17,957,408 字节在位、前端四闸门过）；A24 黄警形态经
代码 + API 级实测与后端注入行逐字一致。仅余两条 P3 级留痕措辞精度问题（FG1 记录
「crates/ 零命中」的口径与 test_dispatch_engine 断言计数口径），不影响代码与功能，
不阻断合入。

## 二、审查依据与范围

- **依据**：docs/plans/m4-combo-template-deploy-plan.md——§0.3 需求三（全小写统一
  规则）、§0.4 定案口径 4、§1.1 存量清单（#1–#9 + R-8 三条补录注）、§2 WBS F1/F2
  行与批次内子步骤、§4 测试矩阵「既有回归（F1/F2 批次刷新）」行、§5 提交 #7/#10、
  §6 闸门清单（F1 必检 hq 产物）、附录 B FG1/FG2 留痕（不采信自述、逐条独立复跑）。
- **对象**：F1 = b953de99（feat(web)，14 文件 +60/−59）+ 8627cfc7（chore(progress)）
  + d9504f8f（docs(plans)，38 行插入）；F2 = d5c6ef2a（feat(frontend)，4 文件
  +26/−19）+ d457ed55（chore(progress)）+ 1f2f74bc（docs(plans)，+55/−3）。
- **范围证实**（实测）：`git status` 工作区干净；`git show --stat` 证实
  b953de99 仅触 web/src 七个业务文件 + hq/gateway.py + 三个测试文件（+60/−59），
  d5c6ef2a 仅触四个前端组件（+26/−19），两个回填提交仅触计划文档，两个进度提交
  仅触 CHANGELOG.jsonl/CHANGELOG.md/progress.json——**无越界改动、无夹带**。
  再证范围外零改动：`git diff --stat b953de99^..1f2f74bc -- web/src crates docs/api`
  合计 11 文件 +40/−40，与上述清单逐一对应。
- **报告落盘**：docs/plans/m4-combo-deploy-review-F1F2.md（调用方指定）。

## 三、§1.1 清单逐条核对表

| 条目 | 计划处置 | git diff 证据（复现：`git show <提交> -- <文件>`） | 结论 |
|---|---|---|---|
| #1 workspace.py:111 派发注入 | `%nprocshared=` | b953de99：`-inject.append(f"%NProcShared={declared}")` → `+f"%nprocshared={declared}"` | 已落地 |
| #2 workspace.py:115 派发注入 | `%mem=`（GB 无空格） | 同提交：`-f"%Mem={_fmt_gb(mem_gb)}GB"` → `+f"%mem={_fmt_gb(mem_gb)}GB"` | 已落地 |
| #3 resume.py:146 续跑注入行 | `%oldchk=` | 同提交：`-lines.insert(i, f"%OldChk=@exec:{source_eid}")` → `+%oldchk=@exec:…` | 已落地 |
| #4 resume.py:148 契约响应行 | `%oldchk=` | 同提交：`link0_lines` 值同步 `%oldchk=@exec:` | 已落地 |
| #5 materialize 改写前缀 casefold | `%chk=`/`%oldchk=`，无引用行前缀原样 | 同提交 `_rewrite_line`：`-return head + sep + dep_name` → `+return head.casefold() + sep + dep_name`；改写仅作用于 parse_link0_refs 命中的引用行；`%Chk=own.chk`（无引用）原样断言保留（test_materialize:80） | 已落地 |
| #6 ComboFlowDialog 默认值 | 小写、与 GET initial.route 单值来源对齐 | d5c6ef2a：`DEFAULT_ROUTE = "#p B3LYP/6-31G(d) Opt Freq"` → `FALLBACK_ROUTE = "#p b3lyp/6-31g(d) opt freq"` + `initialRoute` ref；watch 中 `initialRoute.value = tplRes.data?.initial?.route ?? FALLBACK_ROUTE`，applyTemplate 回落与清空恢复共用；字面与后端 `config.py:153 COMBO_TEMPLATE_INITIAL_ROUTE = "#p b3lyp/6-31g(d) opt freq"` 逐字一致（实测 grep） | 已落地 |
| #7 placeholder | `%nprocshared=4` | d5c6ef2a ComboFlowDialog.vue：`placeholder="%NProcShared=4"` → `"%nprocshared=4"` | 已落地 |
| #8 黄警文案 | 小写无空格、与后端注入行一致 | d5c6ef2a CandidatesView.vue：`%NProcShared=${…}`→`%nprocshared=${…}`、`%Mem=${…} GB`→`%mem=${…}GB`（去空格）、head 项 `%${m}`→`%${m.toLowerCase()}`；后端 missing 载荷维持大写名（blocks.py:134、candidates.py:327 定案口径实测未动） | 已落地 |
| #9 后端文案/注释群 | 引用参数名一律小写 | b953de99 逐处：config.py:99/103（设置描述）、candidates.py:233/236/239（错误消息）+285（docstring）+40（R-8 注释）、resume.py:16/21/27、dispatcher.py:12、hq/gateway.py:73、workspace.py:4/74/76（另 R-8 表外 :5/35/51/77）、blocks.py:128-132、finalize.py:5/6/77、dependencies.py:3/6、reconcile.py:11——diff 逐处比对全部小写归一；models.py:361/393/663/666 再生面与 contract.ts:1507 按计划范围收窄条款不在 F1（已随批次 A 落，`git show b953de99 --stat` 证实未触 models.py/contract.ts） | 已落地 |
| #9 前端文案/注释（R-8 F2 补录 8 处） | 同上 | d5c6ef2a：QueueEditorModal.vue 7 处（:18-19 docstring、:33 removeOldChkTaskRef docstring、:100 initTarget 注释、:131 linkTitle 文案、**:201 运行值** `%OldChk=@task:` → `%oldchk=@task:`、:492 成员行勾选注释）+ BlockEditor.vue:476 样式注释——diff 逐处吻合 | 已落地 |

R-8 补录纪律核验：F1 五处、F2 八处均为「补录清单与修复同提交」——补录注随
d9504f8f/1f2f74bc 落计划文档（R-8 风险条款执行到位）。

## 四、语义不变式与测试有效性核验

**语义不变式（G16 大小写不敏感、仅改写形态）——逐环节实测：**

1. materialize `_rewrite_line`：`head.casefold() + sep + dep_name` 仅归一前缀，值
   改写逻辑不变；改写仅作用于 `parse_link0_refs` 命中的引用行（materialize.py
   循环 `lines[idx] = _rewrite_line(...)`），无引用行不触；物化后 `parse_link0_refs`
   零残留防御仍在（materialize.py:138-140）。
2. resume 注入 `%oldchk=@exec:` 与 materialize/consume 链解析兼容：引用识别
   `dependencies.py:60` `key.strip().casefold()`、形态前缀 `:66` casefold——小写注入行
   与存量大写行同判（test_confirm_creates_task_and_materializes 端到端覆盖）；
   finalize 消费侧 `_CHK_RE = re.compile(r"^%chk\s*=\s*(.+)$", re.IGNORECASE)`
   （finalize.py:30）——小写改写行可解析。
3. workspace.resolve_link0：key 判定 `k = key.strip().casefold()`（workspace.py:92），
   注入行小写化后自身再解析无歧义；派发组装链（dispatcher.py:218-226、
   pending.py:72）均经 resolve_link0 单点，`grep -rnE '%(NProcShared|Mem|CPU|OldChk|Chk)[=A-Z]' web/src`
   零命中——**无大写残留拼接**。
4. 前端 QueueEditorModal 生成行切小写对存量安全：解析正则 :26
   `/^%oldchk\s*=\s*@task:(\d+)$/i`、移除正则 :36、loadLinkStates 初始化正则 :164
   均实测带 `i` 标志；legacy 大写内容可识别可移除。
5. F2 #6 单值来源：前端 initial.route 取自 GET /combo-templates 响应
   （routers/combo_templates.py:40 回传 `config.COMBO_TEMPLATE_INITIAL_ROUTE`），
   本地 FALLBACK_ROUTE 仅作不可达兜底且字面与后端常量逐字一致。

**测试刷新有效性：**

- 小写形态真锁定：test_dispatch_engine 精确相等断言
  `splitlines()[1] == "%nprocshared=4"`/`[2] == "%mem=8GB"` 及 not-in 断言、
  test_resume 三处 f-string 精确匹配 `%oldchk=@exec:{eid}`、test_materialize 三处
  `%oldchk=dep-…` 前缀精确断言——非 casefold 后比较，确系锁形态。
- 输入侧大写夹具保留（覆盖大小写不敏感解析）：test_parse_blocks:65-66
  双形态循环、test_dispatch_engine `%CPU=…` 输入、test_block_save:180-181 混合
  大小写、test_dispatch_deps `%OldChk=@task:` 输入、test_queue_edit_links:76
  大写写读回环（save_block 行为不变口径下的存量内容透传覆盖）、
  test_finalize_pipeline `%Chk=…` 输入（resolve_chk IGNORECASE 消费）。
- 无恒真断言/静默跳过：`grep -rnE 'assert.*%(NProcShared|Mem|CPU|OldChk|Chk)[=A-Z]' web/tests`
  命中均为「大写输入 → 断言不注入/原样/正确解析」语义，无被削弱断言；全量
  pytest 零 skip。

**A24 黄警形态（代码 + API 级实测，视觉面以 FG2 浏览器留痕为准）：**

- API 实测（隔离实例 G16WEB_HOME=/tmp/g16web-review-f1f2、引擎关、:8399，用毕
  已清理）：导入仅声明 `%mem=2GB` 的候选 → `GET /candidates/1/preview` 返回
  `missing: ["NProcShared"], lines: ["%mem=2GB"]`；`GET /settings` 返回
  `link0_default_nproc=4 / link0_default_mem_gb=8`。
- 代码链：后端大写名（无 % 前缀）→ 前端 `` `%${m.toLowerCase()}` `` → `%nprocshared`；
  缺省补齐行 `` `%nprocshared=${nproc}` ``/`` `%mem=${mem}GB` `` 取同一
  link0_default_* 运行级设置——与后端注入行 `%nprocshared={declared}` /
  `%mem={_fmt_gb(8.0)}GB`（`_fmt_gb` 整数去尾零 → `8GB`）**逐字一致**。重构
  #109/#133 文案 = `%nprocshared、%mem 未声明 · 执行时将按默认值补齐
  （%nprocshared=4、%mem=8GB）`，与 FG2 留痕逐字吻合。

## 五、问题清单

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| F1F2-1 | P3 | 可维护性（留痕精度） | m4-combo-template-deploy-plan.md 附录 B FG1「复扫…crates/ 与 openapi.yaml 零命中」 | 广谱正则 `grep -rnE '%[A-Z]' crates` 实测命中 19 处（allocations_info_table.rs、pbs.rs、slurm.rs、cli.rs 等，全部为 chrono/strftime 日期格式串 `%H:%M:%S`/`%d.%m.%Y` 类）。「零命中」仅在 Link0 指令域正则 `%(NProcShared\|Mem\|CPU\|OldChk\|Chk)[=A-Z]` 下成立；按字面 `%[A-Z]` 口径复述与实测不符。openapi.yaml 广谱复扫确为零命中。复现：`grep -rnE '%[A-Z]' crates \| wc -l` → 19 | 下轮修订计划文档时将 FG1 该句改述为「crates/ 仅余日期格式串、Link0 指令域零命中」或注明复扫正则口径 |
| F1F2-2 | P3 | 可维护性（留痕精度） | 附录 B FG1「test_dispatch_engine（注入行 4 断言）」 | 实测 b953de99 在 test_dispatch_engine.py 刷新断言 5 处 6 条：L101/L102 精确相等 2、L132/L139 not-in 2、L170 物化文本复合断言 1 行（含 2 原子断言）。「4 断言」计 L170 为物化断言之外的口径未注明，计数存在歧义 | 同上，补注计数口径（如「注入行 4 + 物化文本 1」） |

无 P0/P1/P2 问题。无安全风险新增（未引入输入面变化；路径/子进程/编码约定未被
触碰）。跨平台约定符合（本次均为字符串字面与正则改动，无 os.path/shell/编码面）。

## 六、闸门实测记录（独立重跑，2026-10-14）

| # | 闸门 | 实测输出 | 判定 |
|---|---|---|---|
| 1 | `ls -l target/release/hq` | `-rwxr-xr-x … 17957408 Oct 12 11:23 target/release/hq`——在位且字节数与 FG1 口径 17,957,408 一致；F1 未触 crates/ Rust 代码（gateway.py 为 Python 侧抽象），无需重建 | 满足 §6 必检项 |
| 2 | `uv run pytest -q` | **739 passed, 2 warnings in 113.12s**——零失败、零跳过（warnings 为 starlette DeprecationWarning，环境噪声） | 过 |
| 3 | `uv run pytest web/tests/test_e2e_fake_g16.py -v` | **3 passed in 5.71s**：test_e2e_fake_g16_pipeline / test_e2e_http_gateway_pipeline / test_e2e_queue_skip_failed_continues 全部真实运行，无静默跳过 | 过 |
| 4 | `uv run python scripts/validate_progress.py` | `OK` | 过 |
| 5 | `uv run python scripts/gen_changelog_md.py --check` | `check_changelog_md: OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致` | 过 |
| 6 | `cd web/frontend && npm run build` | `✓ built in 5.51s`，vue-tsc 零错误（仅既有 chunk >500kB 提示，非闸门项） | 过 |
| 7 | `bash scripts/audit_frontend_offline.sh` | `web/frontend/dist 零外链资源引用（豁免 5 组白名单前缀）` | 过 |
| 8 | `uv run python scripts/check_tokens.py` | `暗色 92 变量 / 样板 92 变量；明亮 31/31；逐变量 diff 为空` | 过 |
| 9 | `uv run python scripts/check_contrast.py` | 全组合 ≥ 4.5:1（最低 failed 徽标 4.71:1） | 过 |

测试数口径注：FG1 时点 736 passed 与当前 739 passed 差 3 条，增量全部可归因——
`git diff b953de99..HEAD -- web/tests` 实测仅 test_combo_templates.py 与
test_deploy_scripts.py 增补，新增测试函数恰 3 个
（test_is_default_false_preserves_row_state、
test_is_default_omitted_or_false_preserves_default_owner、
test_setup_deps_usage_guards），系 F1/F2 之后批次（模板豁免粒度修复、部署脚本
防线）所加，与 F1/F2 无涉。

## 七、端到端与视觉审查记录

- F1 触及派发/续跑/物化链：hq 产物在位（见闸门 #1），e2e 3 例真实运行（闸门 #3）；
  另起隔离实例（G16WEB_HOME=/tmp/g16web-review-f1f2、G16WEB_ENGINE=0、:8399，
  development.md §6.1 口径）实测 health/导入/preview/settings 四接口正常，A24 载荷
  链 API 级闭环（详见第四节），实例与 /tmp 工作区用毕已清理（进程 kill、目录删除）。
- 视觉面（A24 浏览器黄警文案）：本环境无浏览器工具，未复测视觉；以 FG2 附录 B
  浏览器实测留痕（127.0.0.1:8300 构建产物 DOM 逐字提取）为准，且其记录文案与我
  的 API 载荷 + 前端代码链重构结果逐字一致（交叉印证），不影响本报告结论。

## 八、与 FG1/FG2 留痕的偏差对照

| 留痕项 | FG 自述 | 本次独立实测 | 判定 |
|---|---|---|---|
| FG1 全量回归 | 736 passed | 当时点 736 可归因（现 HEAD 739 = 736 + 后续批次 3 条新测试，逐函数对账） | 一致 |
| FG1 e2e | 3 例真实运行、hq 17,957,408 字节 | 3 passed、字节数逐位一致 | 一致 |
| FG1 复扫 crates/ | 「零命中」 | 广谱 `%[A-Z]` 下 19 处日期格式串；Link0 指令域零命中 | **措辞偏差**（F1F2-1） |
| FG1 test_dispatch_engine | 「注入行 4 断言」 | 5 处 6 条断言刷新 | **计数口径未注明**（F1F2-2） |
| FG1 #1–#5/#9 逐处 + R-8 五处 | 全部小写归一 | git show 逐处比对全部吻合 | 一致 |
| FG2 #6/#7/#8 + R-8 八处 | 全部落地 | git show 逐处比对全部吻合；FALLBACK_ROUTE 与后端常量逐字一致 | 一致 |
| FG2 前端复扫 | 零大写残留 | `grep -rnE '%[A-Z][A-Za-z]*[=\s（(、]' web/frontend/src` 零命中 | 一致 |
| FG2 四闸门 | build 5.04s / audit / tokens 92+31 / contrast ≥4.5 | build 5.51s（时长差异属环境噪声）、其余结论一致 | 一致 |
| FG2 A24 文案 | #109/#133 逐字两例 | 代码 + API 链重构结果与留痕逐字一致（视觉本体未复测，见第七节） | 一致 |

## 九、总体结论

**通过**：§1.1 后端/前端条目全部清零，F1/F2 验收标准（WBS 行）逐项满足；全部
闸门独立重跑全绿且 e2e 无静默跳过；仅两条 P3 留痕措辞精度问题（F1F2-1/F1F2-2），
属文档修订项，不阻断合入，建议随下轮计划文档修订顺带更正。
