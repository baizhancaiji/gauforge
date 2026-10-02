# M3 验收记录（D1 走查留痕 + D 阶段缺陷修复）

> 依据 [m3-plan.md](m3-plan.md) §4.15/§7.2 执行并留痕。走查日期：2026-10-01。
> 走查环境：WSL2 单机，**真机 g16 全链路**——HQ server/worker 真实派发
> （`target/release/hq` 走查前重建），执行、收尾（formchk/解析）与 cubegen
> 均由真机 G16（`~/g16`）承担；隔离工作区 `/tmp/m3acc/home`
> （`G16WEB_HOME`），独立实例 `127.0.0.1:8398`（内联 uvicorn，引擎开）。
> GUI 走查经浏览器黑盒驱动（截图留存本地 `/tmp/trae/screenshots/`，不入库；
> 该目录混有更早批次，以 p1-*/p2-* 等前缀区分）。
> 本记录随走查实时登记（每路径完成即落对应条目），非收尾集中补录。
>
> **2026-10-01 23:57 中止交接（未收口）**：按用户指示停止 D1 走查、由他人
> 接手续作。已验：路径 1、路径 2、路径 4（API 六态）；未成：路径 3（两次
> 尝试均未产出强停条目，归因见 §3 行 3）；未启：路径 5/6/7 与收口、D2 发布
> 2.2.0。现场保留 `/tmp/m3acc`（服务 `127.0.0.1:8398` 交接核查时仍在运行、
> 响应 200；日志 `logs/server.log`；截图 `/tmp/trae/screenshots/`）。接手要点
> 见 `progress.json` 的 `next_steps`。
>
> **2026-10-02 接手续作（D1 收口）**：现场核查通过后（服务仍在跑、
> `/tmp/m3acc` 与 hq 产物完好），续作完成路径 1/2/4 的 GUI 待补项、路径 3
> 重做（经 API 层 stop 一次成功）、路径 5/6/7 首验，发现缺陷一处随查随修
> （§2 缺陷①，收敛图轴名裁剪）。七条路径全部通过，全量闸门通过（569 测试
> + 五项脚本闸门 + hq 在位，见 §4）。**D2（2.2.0 冻结五步）按用户指示留待
> 用户完成真实验收后另行执行**。接手批截图留存
> `.playwright-mcp/`（p1b-\*/p2b-\*/p3-\*/p4-\*/p5-\*/p6-\*/p7-\* 前缀，
> gitignore 内不入库；与交接批 `/tmp/trae/screenshots/` 的 p1-\*/p2-\* 区分）。

## 1. 走查环境准备记录（与走查动作的区分）

- 隔离工作区 `/tmp/m3acc/home`（`run/`、`inputs/`、`hq/` 等布局由服务
  首次启动生成）；样本与现场不入库、可重建（本节即重建口径）。
- 真机样本 `/tmp/m3acc/samples/`（经 GUI 导入候选）：
  - `h2o_optfreq.gjf`：水分子 `#p opt freq b3lyp/6-31g(d) pop=reg`
    （路径 1 主样本，真机 4s 完成）；
  - `benzene_opt.gjf`：苯环 `#p opt b3lyp/6-31g(d)`（路径 3 强停目标①，
    真机 4s 完成，窗口不足）；
  - `benzene_slow.gjf`：苯环 `#p opt freq b3lyp/6-311+g(2d,p)`（强停
    目标②，真机 1m41s 完成，窗口仍不足；接手可在此基础换更重方法）；
  - `degraded_sample.gjf`：`#p hf/sto-3g` + 末行 `! TEMPLATE: <fixture 路径>`
    （路径 5 降级构造样本；候选 3 仍留存未提交，接手直接可用）。
- 路径 4 路径守卫样本：工作区内 `/tmp/m3acc/home/samples/` 下
  `h2o_optfreq_popreg.out`（金标准输出副本，有效用例）、`escape.out`
  （符号链接 → 工作区外，symlink 逃逸用例）；工作区外
  `/tmp/m3acc/outside.out`（`../`、绝对路径与 symlink 三态共用目标）。
- `! TEMPLATE:` 注入包装器 `/tmp/m3acc/fakebin/g16`（走查专用、不入库）：
  读取输入内 `! TEMPLATE:` 行，将模板文件（仓库 `web/tests/fixtures/`
  截断样本）复制为 `input.log` 并以 0 退出——经真实派发/收尾管线构造
  「succeeded + 非 G16 格式输出 → 解析 degraded」落地（与 B5 fixtures
  单测同源、非旁路）；路径 5 走查时把 `g16_root` 暂切该目录、提交候选 3
  后恢复。
- 受控注入空目录 `/tmp/m3acc/nocubegen/`（路径 2 的 503 注入：
  `g16_root` 暂指该目录致 cubegen 探测失败）。
- 运行级设置：走查期取缺省（`g16_root=~/g16`、`disk_usage_warn_gb=50`）；
  受控注入项（路径 2/6）临时改写后即时恢复，逐条在对应路径留痕。
- GUI 驱动：浏览器黑盒（内置浏览器自动化），截图实际留存
  `/tmp/trae/screenshots/`（p1-*/p2-* 已留；不入库）。

**接手批（2026-10-02）现场与注入补充**（前置均核查在位；走查后即时恢复）：

- 现场继承：服务 `127.0.0.1:8398` 进程存活、3 个 succeeded 执行与
  fakebin/nocubegen 注入目录原样在位；接手批前端经 `npm run build` 重建
  （缺陷①修复随批生效）后刷新走查。
- 新增执行：execution 004（`benzene_slow.gjf` 重提，强停目标，API 层 stop）；
  execution 005（候选 3 `degraded_sample.gjf`，`g16_root` 暂切
  `/tmp/m3acc/fakebin` 提交、完成后恢复 `~/g16`）。
- 路径 2 复现注入：cube POST 先命中幂等缓存（p2 已生成的同参 cube 直接
  200 返回、不触 cubegen 探测），故 503 注入须换新参数（LUMO=MO 6）；
  502 注入为 `input.fchk` 备份后写垃圾（恢复后同参重试 200）。
- 路径 6 受控注入两项：① 孤儿目录 `run/bench-orphan/pad.bin`（1.1 GB，
  验证孤儿目录计入总量不产生明细 + 越阈触发，走查后删除）；② 执行 002
  `finished_at` DB 层前移 8 天（保留期 7 天使可清理量显现——自然等待
  不可行，DB 层注入仅施于隔离走查实例并在此留痕，走查后复位）；阈值
  `disk_usage_warn_gb` 50→1→50。
- 越阈窗口文件清点：47 文件 / 1,229,581,715 B，20 秒后逐位不变（无自动
  清理实证）；手动清理后 46 文件（`benzene_opt.chk` 移除）。
- 截图：接手批 `.playwright-mcp/`（p1b-conv-{scf,geo,energy}-fixed、
  p2b-{503,502}-gui、p3-failed-entry、p4-gui-{reject,workspace-orbit}、
  p5-degraded-gui、p6-{storage-panel,over-threshold,after-cleanup}、
  p7-light-degraded）。

## 2. D1 走查发现并修复的缺陷（随查随修，一缺陷一提交）

| # | 缺陷 | 归因 | 修复 | 复验 |
|---|---|---|---|---|
| ① | 能量收敛图 x 轴名（「SCF 迭代（跨几何步累计）」/「几何步」）被画布右缘裁剪不可读（SCF 源呈现缺字形方框观感） | ECharts 轴名默认 `nameLocation: end` 定位名文本向轴末端外溢出，`grid.right=30` 容不下中文短语 | `ConvergenceChart.vue` x 轴名改中置下挂（`nameLocation: middle` + `nameGap: 25`）、`grid.bottom` 28→46 预留轴名带；数据缩放条位置不动 | 三源切换复验截图轴名完整（p1b-conv-\*-fixed）；`npm run build` + check_tokens/check_contrast/audit_frontend_offline 随批通过 |

交接批（2026-10-01）未见产品缺陷；路径 3 两次尝试均未产出「手动停止」条
目：经证据核查为强停操作未触达服务端（走查操作问题，非产品缺陷），归因
与证据见 §3 行 3。

## 3. D1 端到端走查（§7.2 七条留痕，对照 roadmap M3 验收段）

| # | 验收项 | 结果 | 留痕 |
|---|---|---|---|
| 1 | freq 分析全链 | 通过（交接批两点待补强已补：概览全字段对照、收敛三源切换；随批修复缺陷①） | p1-\*（交接批）、p1b-conv-\*-fixed（接手批） |
| 2 | 轨道与静电势 | 通过（交接批 API 全断言；接手批补 GUI 503/502 文案区分） | p2-\*（交接批）、p2b-\*-gui、p2-503/502.log |
| 3 | 异常条目 + 失败样例 | 通过（接手批重做：API 层 stop 一次成功） | p3-failed-entry、execution 004 |
| 4 | `.out` 只读分析 | 通过（交接批 API 六态 + 接手批 GUI 越界提示与 workspace 轨道清单） | logs/p4-api.log、p4-gui-\* |
| 5 | result_ref 三态 | 通过（接手批：三态 API + GUI missing[] 展示） | p5-degraded-gui、execution 005 |
| 6 | 占用面板（M3.7） | 通过（接手批：du 逐位对照、越阈琥珀警示、无自动清理、清理即时反映） | p6-\* |
| 7 | 闸门与设计并排 | 通过（接手批：569 测试 + 五项脚本闸门 + 明暗双主题目检） | §4 闸门清单、p7-light-degraded |

**路径 1（freq 分析全链）**：execution 001（`h2o_optfreq.gjf`，真机 4s
succeeded，analysis.json 全块可用）。GUI：历史行 → 详情抽屉 → 分析区四
tab（概览 / 能量收敛 / 频率与 IR / 轨道与静电势）齐备；频率 tab IR 棒图
渲染、表格前三行 1712.97 / 3727.31 / 3849.33 cm⁻¹ 与虚频计数「虚频 0 个」
（与 `GET /history/1/analysis/frequencies` 基准逐位一致）；轨道 tab 能量
清单 19 项、HOMO 预置轨道 5（显示 -7.92 eV / A"，与 analysis.json
逐位一致：-7.9237 eV、A"）；convergence 三源控件（SCF 迹线 / 几何收敛 /
能量序列）齐备且默认曲线渲染正常（三源逐个切换的截图留痕待补强）；
概览 tab 全字段逐字抄录待补强（API 侧已独立核对 Result 全集：state=parsed、
natom=3、nmo=nbasis=19、freq_count=3、虚频 0、B3LYP/6-31G(d)、
Gaussian 2016+C.01、cclib）。
留痕：p1-*.png（本地）。

**路径 2（轨道与静电势）**：同上 execution 001 详情，轨道 tab 预置
MO=5（HOMO）→「生成并渲染」→ 服务端落盘 `run/1/cubes/00edb73c….cube`
（6,746,014 B、80³ 网格、标题行「… MO=5」），cube_id 与参数摘要口径
sha256(`MO|5|80|1`) 逐位一致；`GET /analysis/cube/{id}` 200、
content-type=chemical/x-cube、字节与落盘一致；3Dmol 等值面渲染成功
（正负双色 lobes，canvas 958×520），isoval ±0.02 → ±0.05 切换后状态
文本更新（「已渲染：MO 5 / isoval ±0.05」）；kind 切「静电势」→
「已渲染：静电势 Potential=SCF」，VDW 表面 + RWB 色彩映射渲染成功
（本环境 WebGL 可用，非 headless 限制——与 progress 旧预告相反，如实
更正）。受控注入两项：① `g16_root` 临时改指空目录
`/tmp/m3acc/nocubegen` → POST cube 503 `CUBE_EXECUTABLE_MISSING`
（details 回显 g16_root）→ 复设置即恢复；② `input.fchk` 备份后写入垃圾
→ POST cube 502 `CUBE_GENERATION_FAILED`（非零退出 -6、stderr_tail 含
cubegen 回溯）→ 恢复 fchk → 同参数重试 200 成功（可重试）。GUI 层
503/502 文案区分（C4 质量标准）待补。
留痕：p2-*.png（本地）、`/tmp/m3acc/logs/p2-503.log`、`p2-502.log`。

**路径 3（异常条目 + 失败样例）**：未完成（交接）。两次尝试均未产出强停
条目：① `benzene_opt.gjf`（execution 2）真机 4s 正常完成（23:28:15→19
+08），无强停窗口；② 补造 `benzene_slow.gjf`（execution 3，opt+freq
6-311+G(2d,p)）真机 1m41s 正常完成（23:35:54→23:37:35 +08，wall_time
101s），窗口仍不足。证据核查：`logs/server.log`（739 行、实例全生命
周期、含逐请求访问行）内 `stop` 与 `executions/` 子路径零命中——两次
「强停」操作均未触达服务端（走查操作未落实为 API 调用），非服务端竞态；
两执行终态均 succeeded、result_ref 非 null、chk_snapshot 未保全（正常
完成路径行为）。教训与重做指引：强停目标须选 ≥10 分钟窗口任务（更重
方法/基组）或提交后立即经 API 层 stop 并核验 GUI 异常条目呈现；子代理
抄录不可靠（本段已实测两处失真），关键断言一律以服务端 API 为准。

**路径 4（工作区 .out 只读分析 + 越界拒绝）**：API 层六态全通过
（`/tmp/m3acc/logs/p4-api.log`）：① 有效样本
`samples/h2o_optfreq_popreg.out` → 200（四块 blocks 全 true、
state=parsed、natom=3、freq=3）；② `../outside.out` → 400
WORKSPACE_PATH_OUTSIDE；③ 绝对路径 `/tmp/m3acc/outside.out` → 400；
④ symlink 逃逸 `samples/escape.out` → 400；⑤ 后缀非白名单
`samples/note.txt` → 400（后缀先于存在性判定）；⑥ 不存在
`samples/none.out` → 404 NOT_FOUND。GUI 侧（工作区输入框与越界提示
呈现）待走查。

**路径 1 补强（接手批，概览全字段对照 + 收敛三源切换）**：概览 tab 全
字段与 `GET /history/1/analysis` 逐位对照一致——解析状态「正常解析」
（state=parsed）、cclib 1.8.1 / Gaussian 2016+C.01、B3LYP/6-31G(d)、
原子/轨道/基函数 3/19/19、SCF 能量 -76.408954 Ha（-2079.193 eV，末位
显示舍入，API -2079.1934678896164）、优化收敛「已收敛」、频率数
3（虚频 0）、HOMO 序号 4、可用数据块四枚芯片齐备（能量收敛/频率与
IR/轨道/热化学）。收敛 tab 三源逐个切换截图（SCF 迹线对数判据曲线 /
几何收敛四判据 + 阈值虚线 / 能量序列 Hartree 主轴），随批发现并修复
缺陷①（轴名裁剪，§2）后复验三源轴名完整。

**路径 2 补强（接手批，GUI 503/502 文案区分）**：要点：幂等缓存命中
不触发 cubegen 探测（同参 POST 直接 200 返回 p2 已生成 cube），503
注入须换新参数。实测：`g16_root` 暂切 `/tmp/m3acc/nocubegen` → 选
LUMO（MO 6，新 cube_id）→ POST 503（服务端日志留痕）→ GUI 红色警示
「cubegen 不可用 — 请检查 g16_root 设置（503）」；恢复 `~/g16`、
`input.fchk` 写垃圾 → 选轨道 7 → POST 502 → GUI「cube 生成失败
（502）」并附 stderr 尾部（cubegen 回溯栈）；恢复 fchk 后同参重试
POST 200、cube 落盘（6,746,014 B）且 GET 200。渲染成功态由交接批
WebGL 可用环境留痕（p2-\*）；接手批驱动浏览器无 WebGL，POST/GET 成功
后渲染段被前端 WebGL 探测显式拦截并提示「当前浏览器/环境不支持
WebGL — 轨道等值面无法渲染」——环境限制下失败态呈现正确（区分文案、
不静默白屏），非产品缺陷。

**路径 3 重做（接手批，按交接批归因改走 API 层 stop）**：导入
`benzene_slow.gjf` 为候选 5 → 提交 → 运行 10 秒时
`POST /executions/4/stop`（204）→ 终态 `failed` + cause
`manually_stopped`、`wall_time_s=10`。失败样例抽查：`run/4/` 保留
scratch 中间文件（Gau-\*.inp/d2e/int/skr）与截断 `input.log`（grep
「Normal termination」零命中）；chk 保全快照 `protected/` 落盘
（`benzene_slow.chk` 3,629,056 B + `Gau-24843.rwf` 21,098,496 B）、
`chk_snapshot={"protected":true,"location":"protected"}` 落库；
`result_ref=null`。GUI：历史行「失败 / 手动停止」→ 详情 chk 保全
「已保全（protected/）」、结果引用「—」、分析区不渲染四 tab、以注记
「异常结束的执行不进入解析管道 — 分析不可用，仅可查看 / 导出原文」
替代（409 语义的 UI 承载），「输出」预览打开原文（尾部截断于
FoFCou 段）与「导出 .out」链接在位。走查操作教训固化：强停以 API 层
`POST /executions/{id}/stop` 执行并核验 GUI 呈现（子代理 GUI 操作
不可靠，交接批已实测两处失真；关键断言一律以服务端 API 为准）。

**路径 5（result_ref 三态）**：① succeeded（parsed）：execution 001
`result_ref="analysis.json"`（交接批已验，接手批复核）；② succeeded
（degraded）：`g16_root` 暂切 `/tmp/m3acc/fakebin` 提交候选 3
（`! TEMPLATE:` 注入 `analysis_truncated_freq.out` 截断样本，经真实
派发/收尾管线非旁路）→ execution 005 `state=succeeded` 且
`result_ref="analysis.json"`（degraded 落盘成功即置位，§2.1 口径）；
`GET /history/5/analysis`：state=degraded、parse_error=
「metadata.success=False（无 Normal termination 记录？）」（降级分支
②）、blocks 四缺一（thermochemistry=false）、missing[] 五项
（enthalpy/entropy/freeenergy/geovalues/zpve）；GUI 概览「降级解析」
琥珀标注 + 降级原因 + 缺失属性全展示、可用数据块「热化学 — 缺」；
原文导出 200（52,000 B）不受降级影响；③ failed：execution 004
`result_ref=null`（恒 null），GUI 结果引用「—」。

**路径 6（占用面板，M3.7）**：① 口径对照：`du -sb run/` = 76,144,019
与 `GET /storage/usage` total_bytes 逐位一致；明细五行按总占用降序
（28.7/25.3/15.9/6.1 MB/73 KB），GUI 面板表与端点一致、可清理量全
0。② 孤儿目录注入 1.1 GB：total 增至 1,229,581,715、明细仍 5 条
（孤儿计入总量不产生明细）；阈值 `disk_usage_warn_gb` 50→1 →
`over=true`（total ≥ 2³⁰），GUI 琥珀警示「总占用已超阈值 1 GB — 请
手动清理」+ 按钮「占用 1.1 GB ⚠」；越阈窗口 20 秒文件清点逐位不变
（47 文件，无自动清理实证——统计为纯拉取式、无定时器）。③ 可清理
量显现（执行 002 finished_at DB 层前移 8 天的受控注入）：entry 2
`reclaimable_bytes=1,662,976`（恰为顶层 `benzene_opt.chk` 大小，
与清理判定单一实现口径同源）；GUI「清理 chk/rwf」→ 确认框（边界
语义说明）→ 清理返回「检查 4 项 — 移除 chk 1 — rwf 0」→
`benzene_opt.chk` 删除、文件 47→46、total 精确下降 1,662,976、
reclaimable 归 0，面板无刷新即时更新（002 行 15→14 MB、可清理
0 KB）。④ 现场恢复：孤儿目录删除、阈值复位 50、finished_at 复位，
终态 total 74,481,043 与 `du -sb` 再对逐位一致。

**路径 7（闸门与设计并排）**：全量 `uv run pytest` 569 通过（零跳
过；hq 产物在位）；`scripts/validate_progress.py` OK、
`scripts/gen_changelog_md.py --check` OK、`npm run build`（vue-tsc
零错误）通过、`scripts/check_tokens.py` OK（暗 91 + 亮 30 变量逐位
一致）、`scripts/check_contrast.py` OK（全组合 ≥ 4.5:1）、
`scripts/audit_frontend_offline.sh` 零外链（豁免 5 组白名单）、
`npm run gen:types` 再生零 diff。设计并排目检：分析区四 tab 结构、
blocks 驱动可见性、workspace 模式置灰注记、占用面板琥珀警示文案与
§2.4/§2.6 规格一致；亮色主题下 degraded 概览（降级解析琥珀标注）
目检通过（p7-light-degraded）。

## 4. M3 DoD 对照（§7.1 十条）与 D2 交接

| DoD | 结果 | 留痕 |
|---|---|---|
| 1 freq 输出 IR 谱图/频率表/收敛三源切换 | 通过 | 路径 1（交接批 + 接手批补强） |
| 2 同执行内轨道 cubegen + 3Dmol 等值面（正负双色）、静电势映射 | 通过 | 路径 2（交接批 WebGL 环境）+ 接手批 503/502 文案 |
| 3 异常执行仅原文查看/导出，分析区置灰注记 | 通过 | 路径 3 |
| 4 工作区 `.out/.log` 只读分析、越界明示拒绝、workspace 轨道仅清单 | 通过 | 路径 4（API 六态 + GUI） |
| 5 result_ref 三态口径（degraded 非 null、failed 恒 null） | 通过 | 路径 5 |
| 6 金标准回归闸门常驻 + 降级三分支单测 | 通过 | 全量 pytest 569（test_analysis_parse 等在册） |
| 7 占用统计可查、超阈警告、仅警告不自动清理、清理即时反映 | 通过 | 路径 6 |
| 8 全量测试与闸门脚本通过、cclib 仅 `.venv`、构建产物零外链 | 通过 | 路径 7 |
| 9 工作项销号 M3.1–M3.7 | 销号依据：M3.1/C2（路径 1/4）、M3.2/B1/B2（路径 5 解析管道与 result_ref）、M3.3/C3（路径 1）、M3.4/B4/C4（路径 2）、M3.5/B3（路径 4）、M3.6/A1/B2（路径 5）、M3.7/B12/C8（路径 6） | §3 各路径 |
| 10 2.2.0 冻结五步、tag v2.2.0 | **未执行**（按用户指示待真实验收后 D2） | — |

**D2 交接要点**（AGENTS.md §5.2 五步，届时执行）：确认 unreleased
changes 完整 → 冻结 2.2.0（version/date/semver）→ 追加空 unreleased
行 → progress.json 清空 unreleased、更新 latest_released_version →
本地打 tag v2.2.0（不推送远端，推送须用户当次授权）。

## 5. 人工验收修复批走查（2026-10-02，m3-acceptance-fix-plan 两批十二项）

> 修复计划：[m3-acceptance-fix-plan.md](m3-acceptance-fix-plan.md)（第一批
> 抽屉七项 A-1~A-7、第二批部署反馈五项 A-8~A-12）。逐项修复独立提交后
> 实机走查（127.0.0.1:8398，隔离工作区 /tmp/m3acc/home，Playwright 黑盒
> + API 层断言并用）；走查中发现缺陷一处随查随修（§5.2）。本节随走查
> 实时登记，非收尾集中补录。

### 5.1 逐项验收留痕

| # | 验收项 | 结果 | 留痕要点 |
|---|---|---|---|
| A-7 | 3D 图锚定轨道画布区 | 通过（CSS 侧实机断言；3D 视觉复验留待 WebGL 环境） | `.orb-viewer` computed `position: relative` + `overflow: hidden`、几何位置在抽屉画布区内（不再锚视口左上）；cube 生成/下载链路 200，渲染段被环境 WebGL 探测显式拦截并提示（与路径 2 补强同限，非产品缺陷）；WebGL 环境的实渲染视觉复验与交接批 p2-* 留痕口径一致 |
| A-6 | 小尺寸下拉/输入文字完整 | 通过 | `.ctl select`/`.proxy-input` 补 `padding: 0 var(--space-2)`；其余 `--control-height-sm` 使用处全量排查（按钮类不适用、.pg-input/.ws-input 已覆写）无同类遗漏 |
| A-4 | 缺失 tab/数据块纯置灰 | 通过 | 缺失 tab 与可用数据块无「— 缺」后缀，置灰态与 title 缺失原因保留 |
| A-5a | 对数轴十的幂刻度 | 通过 | 纵轴实拍 `10⁻¹…10⁻¹⁰`（rich 文本上标模拟），字号/颜色走令牌 |
| A-5b | 滑块带完整布局 | 通过 | grid.bottom 84 + dataZoom bottom 12/左右内缩 52：滑块完整可见、与轴名无重叠、**两端窗口数值可见**（ECharts slider 两端 label 在滑块带外侧、`showDetail`/`handleLabel.show` 须显式开启，value 轴默认不显示——根因与计划预判「被裁」不同，实现时实测修正） |
| A-1 | 分析板块按钮化互斥 | 通过 | 打开抽屉默认仅字段+动作行（aria-expanded=false）；点「分析」展开（惰性挂载）、点「输入/输出」分析收起、再点「分析」预览收起，三态往返正确 |
| A-2 | 预览贴可视区下缘 | 通过 | 预览底缘 880 + 抽屉 padding 20 = 视口 900 贴底；.tv-body 去限高改内部拉伸滚动 |
| A-3 | 去抽屉单条导出 | 通过 | 抽屉动作行无「导出 .out」；工具条批量导出不受影响 |
| A-9 | 去结果引用行 | 通过 | 抽屉字段组无「结果引用」行；契约与后端零改动（SSOT 测试过） |
| A-8 | 断流自动重连 | 通过 | SIGSTOP 实际监听进程（uvicorn，pid 按 `ss -tlnp` 定位；**注意 `uv run` 包装父进程 STOP 不影响服务**，首轮误停无效果）72s：data-conn 观察记录 `open → 03:55:43 reconnecting → 03:55:53 open`——看门狗自 abort 后自动退避重连、指示灯经历中间态、无需手动刷新；正常 stop 路径（closedByUs）语义不变 |
| A-10 | 占用整树口径 | 通过 | 本机对照 `du -sb ~/g16web`：usage 2,298,786,503 vs du 2,298,745,514，差 40,989 B（0.002%）归因为观测进程自身 SQLite WAL 增长（稳定复现、du 于进程退出后测得 wal 收缩，属观测自扰非口径偏差）；明细 35 条按 run/<id> 分桶不变；测试侧工作区根移至 tmp 子目录与测试库分离防 WAL 波动竞态 |
| A-11 | 设置文案只留必要解释 | 通过 | 12 运行级 + 2 启动级 label 全为新文案（无生效括注/范围说明/里程碑号）；「凌晨 1:00 锚定」「0=禁用告警」保留；页面无 env 名/英文参数名（含只读区）；重启提示条显中文参数名「监听端口」 |
| A-12 | 拖拽跟手动效 | 通过 | 待执行页三席位（1 锁定 + 队列席位 + 任务席位）：互换提交 PUT `{"seat_order":[12,14,13]}` 前后端同步、锁定席位拖源拦截（pointerdown 不进入拖拽）、拖等待行至锁定槽落点钳回最近可落槽顺序不变、子表展开行高 58→170 画布总高前缀和跟随、拖后点击不误展开（moved 阈值）而纯点击正常展开；队列编辑框等高回归：成员 021 拖至末位顺序重排成功、让位位移与等高步距一致 |

### 5.2 走查发现并修复的缺陷（随查随修）

| # | 缺陷 | 归因 | 修复 | 复验 |
|---|---|---|---|---|
| ② | 设置页保存 on_restart 项后重启提示条永不出现（A-11 验收受阻） | `SettingsView.vue` doSave 中 restartKeys 对比放在 `initForm(data.runtime)` 之后——保存响应先经 initForm 将 form/original 同化为响应值，对比恒等 | 对比提前至 initForm 之前（保存前 form vs original），提示条渲染仍经 key→description 显中文参数名 | 改监听端口保存 → 提示条「⚠ 以下修改需重启 g16web 后生效：监听端口」；c6a6afb4 |

### 5.3 走查后现场恢复

- A-8 断流走查的 SIGSTOP/SIGCONT 全部复位（进程 19885 CONT 后响应 200）；
- A-11 走查改动的监听端口已恢复 8300（保存未重启，运行端口全程 8398 不变）；
- A-12 走查的测试队列/候选/临时文件全部清理（候选归零、席位空、
  /tmp/m3acc-drag 删除）；服务经重启加载新后端（A-10/A-11 随批生效）。