# G16 原生工具箱验收记录（D5 走查留痕 + D 阶段随查随修）

> 依据 [toolbox-plan.md](toolbox-plan.md) §7.2 执行并留痕。走查日期：
> 2026-11-17。走查环境：WSL2 单机、**真实工作区 `~/g16web`**（既有真实
> 终态条目：succeeded 36/51/29/50（crest）/052 等、failed 37（badroute
> 程序错误）/52（手动停止）/41（归档）、skipped 46 等）+ 真机 G16
> `~/g16`（ES64L-G16RevC.01）——体检/转换/cube/freqmem/solname/testrt
> 全链路真机承担；`G16WEB_ENGINE=0`（引擎关，纯工具域走查不涉派发），
> 独立实例 `127.0.0.1:8300`（`uv run python -m web.src.main`，HEAD
> bbfc12d2 起、随 C 批次落库推进至 ba9867a6）。GUI 走查经 Playwright
> 黑盒驱动（截图留存 `.playwright-mcp/` 与仓库根 `c8/c9/c10-*.png`，
> 均不入库），关键断言以服务端产物与 API 响应双源核对（m3/m4 走查
> 教训沿用：截图不作为唯一证据）。
>
> 本记录随走查实时登记，非收尾集中补录。§7.2 十二项逐条对账见 §2；
> 走查期发现缺陷一并修复见 §1（随查随修一缺陷一提交）。

## 1. D5 走查发现并修复的缺陷（随查随修）

| # | 缺陷 | 归因 | 修复 | 复验 |
|---|---|---|---|---|
| ① | 走查项 8 缺口：skipped 条目 cube 导出域 409「明示」无 UI 承载——CubeExportPanel 对 skipped 不渲染区块，与 chk 工具域「不展示入口」（404）口径混同 | C8 实现时两组件共用同一 v-if（仅 succeeded/failed），未区分两域契约差异（cube 域对 skipped 是 409 非 404） | `CubeExportPanel.vue` 根 section v-if 增加 skipped 分支：区块渲染、点击生成 → 后端 409 → 前端 note 明示「未运行条目无执行产物」（ba9867a6，随查随修另计提交） | playwright 实测 46 skipped：cube 区块渲染、点击生成出 409 语义文案；chk 工具域仍不渲染（404 口径不变） |

另：C9 批次实施期发现溶剂速查点击复制在剪贴板授权不可用时静默无反馈，
随批补 execCommand 选中兜底与「复制失败」提示（随 C9 落库 7818bcbc，
不另占 fix 编号）。

## 2. §7.2 走查路径逐条留痕（十二项）

### 1. 体检-转换-下载链（failed 条目）✓

052 refine-02（failed 手动停止，protected/ 保全 chk）：详情抽屉
「chk 工具」区 → chk 体检 → verdict 徽标「chk 健康」（真机 chkchk 实调）
→ 「转换为 fchk 并下载」→ `input.fchk` 落盘核对（`run/52/input.fchk`
头部锚点在位、ethanol combo-flow candidate #2 / FOpt RB3LYP 6-31G(d)）
→ 浏览器下载 `refine-02.fchk`（Downloaded 事件 + note「已下载
refine-02.fchk」）。「下载 fchk」常显入口同链可用。

### 2. 体检损坏明示与路径收口 ✓（损坏明示浏览器实测；越界单测承载）

037 badroute（failed 程序错误，protected/ 保全 chk，真机 badroute 类
损坏样本）：体检 → 琥珀徽标「chk 损坏 / 不完整（可提取部分结构）」+
原子数 0、坐标/基组/MO 系数「—」（缺失字段占位）+ 作业正常完成 ✗
（corrupted 真机形态：exit 134 + `NAtoms=` 锚点，与 §0.5/核验项 2
一致）→ 「转换为 fchk 并下载」→ 409 前置体检闸明示「chk 损坏 /
不完整，不执行转换（体检判定：损坏可提取）」（details.verdict 中文映射）。
`%chk=` 绝对路径 / `..` / symlink 逃逸三类越界 409 `path_outside`
（不读取越界文件）由 `test_chktools.py::test_chk_asset_path_outside`
单测承载（浏览器侧无受控越界条目，不污染真实工作区——重建口径见
test_chktools 夹具说明）。

### 3. failed 条目出 cube ✓

走查 1 的 052 fchk → 「导出 cube」区块（density / 中档默认）→ 生成并
下载 `refine-02-Density-中.cube`（真机 cubegen 实调）；037（体检损坏
拒转换 → fchk 缺失）→ cube 生成 → 502 明示「fchk 缺失 — 请先在上方
工具区执行 chk 转换后再生成 cube」（引导文案，succeeded/failed 同形）。
「已生成 cube 后 fchk 清理 GET 仍 200、缺失 cube 404」由
`test_cube_api.py::test_get_cube_after_fchk_cleaned` 单测承载。

### 4. cube 档位与 kind ✓

036 h2o_opt2（succeeded 闭壳层水）：density / 中档生成下载
`h2o_opt2-Density-中.cube`（服务端产物 `run/36/cubes/<sha256>.cube`
头部 `water opt Density=SCF` 核对，幂等 cube_id；档位幂等互异与
-2/-3/-4 直透由 `test_cube_api.py::test_npts_presets_and_idempotent_distinct`
承载）；α 密度（开壳层）→ 422 明示「α/β 密度要求开壳层体系 — 当前
条目为闭壳层，已拒绝生成」（fail-closed，真机半密度形态不放行）；MO
轨道号越界（25 > 19）→ 422 `details.max` 回显「MO 轨道号越界 — 本
体系可寻址范围至 19」。开壳层 OH 全链（α/β 出 cube、MO=34 过 35 拒）
由真机段 `test_cube_api.py::test_real_machine_alpha_beta_oh` 实跑
承载（真机 cubegen 实调，提交前闸门实测 PASSED 非 skip）。

### 5. testrt 阻断与合法形态 ✓

候选页导入 144 badroute-testrt.gjf（`#p b3lypxyz/6-31g(d)` 拼错方法名）
→ 行内提交确认框「提交」→ 422 ROUTE_SYNTAX_INVALID 拦截（**派发前**，
真机 testrt 实调），报错段在确认框提示位直接可见：「route 语法错误：
QPErr --- A syntax error was detected in the input line. … Last
state= "GCL" TCursr= 3880 …」（message 并入原文首段，前端零改动呈现）。
145 floor-warn.gjf（合法 route）同批提交成功入待执行（合法提交零 422）。
`!` 注释 / `@file` / `@file/N` / 引号值 / 多行合法形态与摘除降级黄警
（五类原因）由 `test_verify_route.py` 受控注入用例承载（提交路径用例
与真机在位解耦）；A6 核验项 1 真机留痕（合并单行送检 exit 0）在
toolbox-plan §2.7。

### 6. freqmem 两路径 ✓

工具箱页手输（3 原子 / 25 基函数 / 闭壳层 r / d / 对照 / 核数）→
结论卡「每线程需求：3.3 MW ≈ 0.03 GB」——与真机 freqmem 输出
（`freqmem 3 25 r p` → Minimum of 3.30 megawords per thread，核验项 5
留痕值逐位一致）对照一致；充足/不足按「声明 ≥ 每线程需求 × 核数」
总量口径呈现（差额与 nproc>1 总量口径说明随显）。「从历史带入」选
#036 → 预填 3 / 19 / 闭壳层 + 核数 2 + 对照 1GB（执行声明值，与详情
抽屉「CPU 2（声明）/ MEM 1 GB（声明）」一致）+ 注记「已带入 #36
（内存来源：任务声明；核数来源：任务声明）」；无声明执行标「默认值」
口径由 `test_toolbox.py::test_prefill_declared_vs_default` 承载。

### 7. 溶剂速查 ✓

「加载溶剂数据」→ 184 条（solname 真机实调，count=184 与 fixture
解析逐位一致）；搜索 water（大小写不敏感子串）→ 命中 Water / H2O；
行点击复制 → 提示「已复制 Water」（剪贴板授权不可用时兜底：选中
单元格文本 execCommand 复制 + 失败提示）。受控 g16_root 变更失效
重取（symlink 换目标）由 `test_toolbox.py::test_solvents_symlink_
target_change_invalidates` 承载。

### 8. 归档与 skipped 边界 ✓

归档页 41 anion_BC2_393（归档 failed）→ 抽屉 chk 工具区入口可用 →
体检「chk 健康」（归档同口径放行）。skipped 046：chk 工具域不渲染
入口（404 契约）；cube 导出域区块渲染、点击生成 → 409 明示「未运行
条目无执行产物」（§1 缺陷①修复后复验）。

### 9. 每核下限黄警 ✓

候选页 145 floor-warn.gjf（`%mem=2GB` + `%nprocshared=8` 失衡声明）
→ 提交成功（fail-open 不阻断，入待执行）+ 黄警在提交提示位可见：
「⚠ L1 每核内存低于下限：声明 2GB / 8 核（下限 8GB/核，按每线程
需求合计）。提交不阻断；freq 任务精确内存需求请用工具箱 freqmem
校验」（line=1 取 %mem 声明行、keyword=%mem、message 携带核算值/
核数/下限与 freqmem 入口指引）。修正 %mem 后黄警消失与 g16_root 空
目录不影响触发（纯算术零依赖）由 `test_mem_floor.py` 承载。

### 10. 批量 fchk 导出 ✓

混合批次（036 succeeded 已有 fchk / 052 failed protected chk / 046
skipped）→ 导出下拉「导出 .fchk」→ 进度注记「fchk 导出 — 已完成
3/3 · 复用 1 · 转换 1 · 失败 0 · 缺失 1 · 已用时 1s」→ 完成自动
下载 `gauforge-fchk-20261117-215306.zip` → 服务端核对：条目
`['h2o_opt2.fchk', 'refine-02.fchk', '_导出说明.txt']`（fchk 条目
ZIP_DEFLATED、说明含「执行 46：未运行无执行产物」fchk 维度文案）、
testzip 完整；「下载」按钮重复下载第二包成功。仅已有 fchk 批次
（036 + 029 naph_big 19MB）再发起 → 秒级 done（复用 1 · 缺失 1——
缺失项为 051 refine-01 无 chk 资产，说明「无 chk 资产（已清理或从未
产生）」逐条登记；19MB 大 fchk 流式打包/下载实测通过）。取消在
queued/running/packing 三级生效与 `.part`/ZIP 清理、fchk 保留、
TTL 到期、重启清扫由 `test_fchk_export_job.py` 13 用例承载（真实
工作区转换秒级，取消窗口过短不宜浏览器实测——服务端取消语义以
注入式单测覆盖，验收判据不弱化）。

### 11. 视觉与令牌一致性 ✓

明暗双主题目检五处新增面：历史详情 chk 工具区 / 导出 cube 区块
（抽屉内）、工具箱页两卡片、历史页 fchk 导出注记——层级、密度、
控件形态（btn 共享类、卡片分隔线、下拉/档位按钮组）与既有页一致，
双主题下前景/背景配对均由既有令牌覆盖。组件样式 diff 复核：新增/
改动样式仅 `var(--…)` 令牌引用，无字面值颜色/字号/字距/间距/圆角/
阴影/层级/时长/缓动，无组件内私设令牌（`grid-template-columns` 与
元素自身宽度为布局尺寸，沿既有口径）。`check_tokens` 零 diff、
`check_contrast` 全组合 ≥ 4.5:1、`audit_frontend_offline` 零外链。

### 12. 闸门 ✓

发布前全量 `uv run pytest` **1006 passed, 0 skipped**（hq 在位，
e2e 无静默跳过）；全部闸门脚本通过（validate_progress / check_tokens /
check_contrast / gen_changelog_md --check / audit_frontend_offline /
npm run build vue-tsc 零错误 / gen:types 与 gen_models.py 零 diff——
A6 批次再生后各批次未触契约文件，终态复核一致）。

## 3. roadmap 化学层定位对照核验

评估 §1 价值链（chk → fchk → cube 供外部软件）走查项 1/3/4/10 全链
实测打通；「工具箱导出域」与「分析预览域」分工不重叠——OrbitalsPanel
预览零改动（走查中 036 分析面板照常渲染），failed 条目解析管道口径
不变（AnalysisPanel 异常态文案指引工具区，C8 同批落位）。
