# G16 工具箱走查修订验收记录（D7 走查留痕）

> 依据 [toolbox-revision-plan.md](toolbox-revision-plan.md) §7.2 执行并
> 留痕。走查日期：2026-11-18。走查环境：WSL2 单机、**隔离工作区
> `/tmp/g16web-revision`**（临时实例，用后即删；种子六条目详见 §1，
> 其中 038 条目取真机 `~/g16web/run/38` 的 fchk 与 protected 保全 chk
> 复制件、金标准水/OH 取 `~/g16/tests` 真件）+ 真机 G16 `~/g16`
> （cubegen / formchk / chkchk 全链路真机承担）+ mock `cubegen`
> 失败脚本（残余失败路径专用，走查后 g16_root 已复原）。`G16WEB_ENGINE=0`
> （引擎关，纯前端/工具域走查不涉派发），隔离实例 `127.0.0.1:8398`
> （内联 uvicorn，走查起点 HEAD = 92734e50 即 B18 后端批落库 + C11
> 前端改动在工作区、构建产物含全部修订——提交 4 随走查通过后落库）。
> GUI 走查经 Playwright 黑盒驱动（截图存仓库根 `c11-*.png` 与
> `.playwright-mcp/`，均不入库）；落盘产物以浏览器 Download 事件实际
> 文件名 + ZIP 内容双源核对（截图不作为唯一证据）。
>
> 本记录随走查实时登记，非收尾集中补录。§7.2 十项逐条对账见 §2；
> 后端 §2.8 真机核验项随批留痕见 §3；走查期**未发现新缺陷**
> （零随查随修提交，见 §4 说明）。

## 1. 走查种子条目册（隔离工作区）

| id | filename | 状态 | 产物 | 承载路径 |
|---|---|---|---|---|
| 1 | water-pop.gjf | succeeded | 金标准水 fchk + 闭壳 analysis | 1/4/5/6/7、闭壳全选 422 |
| 2 | oh-open.gjf | succeeded | 金标准 OH fchk + 开壳 analysis | 4（批量/全选真机） |
| 3 | anion_BC1.gjf | failed | 真机 38 fchk + 真 chk 保全（复制件） | 2/3（038 反例真件） |
| 4 | old-fail.gjf | failed | 真 chk 保全、无 fchk | 2（转换链） |
| 5 | skipped-never.gjf | skipped | 无 | 8（409 明示入口） |
| 6 | crest-like.gjf | succeeded | 无任何产物 | 2（无 fchk 下载 404 等价分支） |

种子假象说明（非缺陷）：条目 3/4 详情「状态 / 归因」行显示「正常结束」
系种子 finalize 未携带 cause 的既有兜底形态（`HistoryView.vue` 该行
渲染本批零改动；真实派发链路 failed 条目 cause 必有值），不属本批范围。

## 2. §7.2 走查路径逐条留痕（十项）

### 1. 转换面板三态互斥 ✓

终态条目（water-pop）抽屉：动作行 = 输入 / 输出 / **转换** / 分析 /
归档 / 关闭——chk 工具区与导出 cube 区块不再常驻（开抽屉默认不渲染，
`git diff` 证实迁挂转换区）。点「转换」→ 面板展开（chk 工具区在上、
导出 cube 在下纵向排列），按钮展开态 accent 描边；开「分析」→ 转换区
收起（DOM 断言 convVisible=false、分析按钮 on）；开「输入」预览 →
分析区收起、仅文本预览显示；再点「转换」→ 预览收起、转换区重开。
非终态恰当时机按钮不渲染：skipped 条目转换按钮照常渲染（§2.1 可见性
口径 skipped ∈ 终态集）；抽屉切换条目时三态全量重置（open() 重置）。

### 2. 按钮主次 ✓

- DOM 断言按钮区顺序与样式：`chk 体检`（btn--secondary）→
  `下载 fchk`（**btn--primary**，第一主操作）→ `转换为 fchk 并下载`
  （btn--secondary）；title 逐字符合 §2.2 定稿（「fchk 已生成时可直接
  下载；缺失时请先执行转换」/「fchk 缺失或需重转时使用；此前已生成过
  则直接下载」），零内部词（无「幂等」「自动物化」）。
- succeeded 有 fchk（water-pop）：「下载 fchk」直接落盘
  `water-pop.fchk`（Download 事件实测）。
- failed 无 fchk（old-fail）：「下载 fchk」→ 404 提示「fchk 不存在 —
  请先执行转换」→ 「转换为 fchk 并下载」→ 真机 formchk 转换成功自动
  下载 `old-fail.fchk`。
- succeeded 无产物（crest-like，crest 条目等价分支——succeeded 而无
  fchk 同走下载 404）：提示同「fchk 不存在 — 请先执行转换」。

### 3. 038 预校验案例 ✓

anion_BC1（#3，真机 38 fchk/chk 复制件）：转换面板 → 体检 → verdict
「chk 健康」徽标照常（chkchk 真调，verdict=ok 不验数据段口径不变）→
勾选 Density → 生成 → 422 明示「fchk 缺少密度数据 — 异常结束任务的
chk 通常不含密度数据，无法生成」（§2.4 映射表定稿文案逐字一致）；
勾选 Density+Spin+Alpha+Beta 多选 → 422 逐 kind 罗列四行（「kind 中文
标签 — 原因」逐行、mono 呈现）：密度缺 `Total SCF Density`、自旋缺
`Spin SCF Density`、α/β `closed_shell`（先经既有 shell 判定，038 闭壳
层形态被既有闸拦截）——零生成（无 cubegen 调用、下载事件为零）；
仅勾选 MO（轨道号 5）→ 生成成功落盘 `anion_BC1-MO-5-medium.cube`
（真机 cubegen 实调——038 MO 系数在场可生成口径实测成立）。

### 4. 批量多选与全选 ✓

- OH 开壳层（#2）：勾选 Density+MO → 生成 → ZIP 落盘
  `oh-open-MO-Density-medium.zip`（包名类型段规范序 MO-Density），
  ZIP 内容核对：`testzip()=None`、条目 `oh-open-MO-5-medium.cube` +
  `oh-open-Density-medium.cube`（逐 kind 命名、MO 含轨道号段、平铺）。
- 全选六类 → 包名 `oh-open-all-medium.zip`（`all` 段）。
- 闭壳层健全条目（water-pop）全选六类 → 422 逐 kind 罗列（Spin
  data_missing + α/β closed_shell 三行；MO/Potential/Density 段齐备
  不罗列）。
- 细档 + 多类 → 提示「多类型 × 细档 — 体积叠加（每类数十 MB 量级）」
  可见（单类细档提示保留，二者互斥切换正确）。
- 批量幂等复用：全选二次请求零重复生成（服务端 pytest 真机用例另证
  六类各一次、重试零新增）。

### 5. 命名英文 ✓

三档位产物落盘名实测：`water-pop-Potential-Density-coarse.zip` /
`oh-open-all-medium.zip` / `water-pop-Potential-Density-fine.zip`——
粗/中/细分别映射 coarse/medium/fine，无中文单字残留；单类 MO 含轨道
号段（`anion_BC1-MO-5-medium.cube`）。落盘名与服务端 Content-Disposition
同公式（前端命名，服务端测试断言双文件名一致）。

### 6. 导出菜单更名 ✓

勾选 anion_BC1 + old-fail 两行 → 导出下拉菜单项实测：
「导出 .chk」/「**导出 .out 和 .chk**」（title「导出 .out 和 .chk —
同包导出（ZIP）」）/「导出 .fchk」——「全部导出」不复存在；点击 →
ZIP 落盘，内容核对 = `anion_BC1.out + anion_BC1.chk + old-fail.out +
old-fail.chk`，**不含 fchk**（old-fail 刚转换落盘的 input.fchk 未入
包——scope=all 实为 out+chk 的语义误读消除实证）；导出 .out /
导出 .chk / 导出 .fchk 三项零回归（split button 主操作与菜单结构不变）。

### 7. 残余失败透出 ✓

g16_root 切换 mock 目录（失败 cubegen 脚本）→ water-pop 勾静电势 →
生成 → 502 提示「静电势生成失败（cubegen 非零退出或超时）— 工具输出
摘录：Error: bad gaussian cube request」——failing kind（中文标签）+
工具输出尾部摘录可见；界面表述「工具输出摘录」无 stderr 等实现词。
走查后 g16_root 已复原 `~/g16`。

### 8. skipped 边界 ✓

skipped 条目（skipped-never）→ 「转换」按钮渲染 → 面板内仅导出 cube
域（chk 工具区不渲染——DOM 断言 .chktools=false）→ 生成 → 409 明示
「未运行条目无执行产物」（ba9867a6 形态保持）。

### 9. 视觉、令牌与文案纪律 ✓

- 明暗双主题目检：转换面板、复选按钮组（选中态 accent）、全选按钮、
  下载 fchk 主按钮在两主题下渲染正确（截图 `c11-conv-panel-real-dark.png`
  / `c11-conv-panel-light.png`）。
- 组件样式 diff 复核：新增 `.ce-kind`/`.ce-kind--on`/`.ce-all` 及
  `.ce-note` 白空格一行——全部 `var(--…)` 既有令牌引用，零字面值、
  零私设令牌、零主题分支（grep 复核 + check_tokens/check_contrast
  过闸）。
- 用户可见文案目检零内部词：按钮/提示/注释逐条核对（「转换」「分析」
  「下载 fchk」「生成中（N 类）…」「工具输出摘录」「请检查设置中的
  G16 安装目录」等），无状态枚举值、布局词、实现概念（幂等/物化/
  锚点/stderr）、内部字段名（g16_root）上界面；reason 值不出现在
  界面（kind+reason 前端映射中文）；分隔统一「—」，无新增「·」。

### 10. 闸门 ✓

`npm run build`（vue-tsc 零错误）、`scripts/check_tokens.py`、
`scripts/check_contrast.py`（全组合 ≥ 4.5:1）、
`scripts/audit_frontend_offline.sh`（零外链）、`uv run pytest` 全量
1037 passed 0 skipped（hq 在位，随提交 3 落库实测）、组件样式 diff
复核——逐项过闸（提交 4 随批复跑 build 与前端三闸门）。

## 3. §2.8 真机核验项留痕

1. **038 反例预校验落点复核 ✓**：根因锚定（2026-11-18 实测：真 38
   fchk 有 MO 系数、缺 `Total SCF Density`）+ 实现后真机回归（§2
   路径 3 全套：体检照常 / Density 422 明示 / 多选逐 kind / MO 真机
   生成落盘）；hermetic 反例 fixture（`fchk_038_shape.txt`）pytest
   矩阵同形覆盖（test_cube_api 63 passed 内）。
2. **OH α/β 段依赖复核 ✓**：真机 OH 全段（Alpha+Beta MO coefficients
   + Total SCF Density + Spin SCF Density）α/β 生成成功不误伤
   （test_real_machine_alpha_beta_oh + 批量全选真机用例双证）；缺 Spin
   段开壳层形态 422 fail-closed 由 `FCHK_OPEN_NO_SPIN` 用例承载。
3. **批量全选基线 ✓**：真机 OH 全选六类 × medium 端到端
   （test_real_machine_batch_all_six_oh 留痕输出）：**耗时 2.1s、
   ZIP 6.2MB（压缩）、条目合计 18.0MB**——量级支撑 §2.3 体积叠加提示
   「每类数十 MB 量级」的表述校准（OH 小体系每类 ~3MB，大体系按原子
   数立方增长；提示量级表述保守成立）；闭壳健全条目全选 422 逐 kind
   罗列（§2 路径 4 + pytest 用例双源）。

## 4. 随查随修

本波走查**未发现缺陷**——零随查随修提交。走查发现的种子假象（§1
归因行显示）与 console 404（种子条目无输入文件的预期网络日志）均非
产品缺陷，留痕不修。
