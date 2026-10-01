# M3 人工验收问题修复计划（历史页抽屉七项）

> 状态：待执行。来源：M3 完成后人工验收（2026-10-02，用户实机走查 + 截图），
> 其中问题 4 的处置口径已于同日由用户更新为「正常置灰」（原「隐藏不显示」作废）。
> 范围：历史页详情抽屉（`HistoryView.vue`，/archive 归档视图复用同组件）及其内嵌
> 分析板块（`AnalysisPanel.vue` 与四个子组件）；全部为 `web/frontend/` 前端修复。
> 依据：[m3-plan.md](m3-plan.md) §2.4、[m0-frontend-design.md](m0-frontend-design.md)
> §4.2/§4.3、[../../../web/frontend/src/styles/tokens.css](../../../web/frontend/src/styles/tokens.css)。
> 执行纪律：逐项独立提交（单类变更、中文动词开头 summary），状态列由执行者回填
> 提交摘要；走查留痕回填 [m3-acceptance.md](m3-acceptance.md)。

## 0. 复核概况与独立复现

定位方法：代码回读（抽屉结构、分析组件四件、设计令牌、base.css 全局控件样式、
vendored 3Dmol 画布定位）+ Playwright 实机复核（127.0.0.1:8398，视口 1544×900，
2026-10-02）。实机实测：

- 问题 2：点「输出」后 `.text-view` 顶缘 y≈898（视口高 900，几乎整体在折叠线以下），
  `.tv-body` 实测 `max-height: 300px`；动作行下缘 y≈402——预览与按钮之间被常驻
  分析板块隔开近 500px。
- 问题 5：收敛图 canvas 实拍 479×240（dpr=1）——纵轴刻度为
  `1 / 0.1 / … / 0.00000001` 小数串；底部滑块带被裁切、两端数字不可见。
- 问题 6：「类型」「轨道」两 select 实测 `height: 24px / padding: 6px 8px /
  font-size: 12px`（内容盒 ≈10px）；对照组 `.ws-input` 自带 `padding: 0 8px`
  同高无裁剪——机理闭环。
- 问题 7：代码级定位（第三方画布绝对定位 + 容器无定位祖先），实机复核在修复后
  走查补做（渲染 cube 有落盘副作用，定位阶段不触发）。

## 1. 问题与根因总表

| # | 问题概述 | 根因定位 | 修复方案 | 验收 | 状态 |
|---|---|---|---|---|---|
| A-1 | 分析板块常驻抽屉，挤压预览与滚动 | `HistoryView.vue:598-599` 无条件渲染 `<AnalysisPanel>`，无开关状态 | 动作行加「分析」按钮（与输入/输出同级，置于原「导出 .out」位）：`anaOpen` 默认 false，点击展开/再点收起；与预览互斥（开一边关另一边）；分析板块渲染于与预览同一展示区（见 §2） | 打开抽屉默认仅字段+动作行；「分析」开合正常；分析展开时点「输入/输出」则分析收起，反之亦然 | 待执行 |
| A-2 | 输入/输出预览高度不足、不贴可视区下缘 | `HistoryView.vue:904-913` `.tv-body` 限高 `var(--peek-max-height)`（300px，`tokens.css:66`）；`.text-view` 非 flex 拉伸，被常驻分析板块推到折叠线下 | 预览改为展示区本体：`flex: 1`（`min-height: 300px` 兜底防上游内容超高时被压没）+ `.tv-body` 去限高、`flex: 1` 内部滚动；抽屉 100% 高不变 | 预览上缘位于「输入/输出」按钮正下方（二者互斥已保证），下缘贴可视区底缘；上游内容超高时保底 300px 可滚 | 待执行 |
| A-3 | 抽屉「导出 .out」被工具条批量导出取代，多余 | `HistoryView.vue:564` 锚点 + `:264-267` `outputUrl` computed | 删除该锚点与 computed（工具条批量导出 `:377-384` 不动）；空出位由 A-1「分析」按钮顶替 | 抽屉内无单条导出入口；工具条批量导出功能不受影响 | 待执行 |
| A-4 | tab 与「可用数据块」的「— 缺」后缀丑 | tab：`AnalysisPanel.vue:307` 模板后缀；块：`AnalysisOverview.vue:105` 后缀。置灰样式两处已有（`.ana-tab--off` / `.blk--off`） | 两处均仅删「— 缺」文案，保留置灰与缺失原因 title/既有类（2026-10-02 用户口径：块不隐藏、正常置灰，与 tab 同行为） | 缺失 tab/数据块呈纯置灰态，无「— 缺」字样；title 仍注明缺失原因 | 待执行 |
| A-5a | 对数纵轴 `1/0.1/0.001…` 刻度不专业 | `ConvergenceChart.vue:52-60` log 轴 axisLabel 用默认十进制标签 | log 轴（SCF/几何共用的 `logCvFrame :67-75`）axisLabel 加 formatter：十的幂科学计数（rich text：`{base|10}{exp|n}`，指数小字号上移模拟上标；v=1 显示 `1`）。不用 Unicode 上标字符（U+207B 在 mono 栈有 tofu 风险）；横轴当前无 log 场景，formatter 仅挂 log 轴 | 纵轴刻度显示 10⁰/10⁻¹/10⁻²…（实拍留痕）；字号/颜色走设计令牌 | 待执行 |
| A-5b | 图下滑块及左右数字下半截被裁 | `ConvergenceChart.vue:61` grid `bottom: 46` + `containLabel: true`（只含刻度标签，不含轴名 nameGap 25 与 dataZoom `bottom: 2 / height: 14`，`:73`）——底部需 ≈69px 实留 46px，滑块与轴名区重叠并被画布下缘裁切 | 底部预留一次给足：`grid.bottom` 46→约 84，`.cv-chart` 高 240→280 补偿绘图区；具体数值实现时按走查校准 | 滑块完整可见、与轴名无重叠、两端数字可见；轴名中文无 tofu（本次实拍疑似单字异常，低清存疑，走查确认） | 待执行 |
| A-6 | 「类型」「轨道」下拉未展开时文字下缘被遮 | `base.css:64-73` 全局 `input/select/textarea` 设 `padding: 6px 8px`，`OrbitalsPanel.vue:310-318` `.ctl select` 限高 24px 未覆写 padding → 内容盒 ≈10px < 12px 中文行盒 | `.ctl select` 补 `padding: 0 var(--space-2)`（对齐 `.ws-input` 既有修法）。同类全量排查：`UpdateCard.vue:329-333` `.proxy-input`（input，24px 定高未覆写 padding）同中招，一并修 | 两下拉文字完整显示、展开正常；设置页代理输入框文字完整 | 待执行 |
| A-7 | 「生成并渲染」的 3D 图出现在工作台左上角 | vendored `3dmol.es6.js:21590-21596` canvas 写死 `position: absolute; top: 0; left: 0`（第三方，不改）；`OrbitalsPanel.vue:370-377` `.orb-viewer` 无 position → 最近定位祖先是全屏 `.scrim`（`HistoryView.vue:799-806`，fixed inset 0），canvas 锚到视口左上 | `.orb-viewer` 补 `position: relative`（一行；`overflow: hidden` 已有即裁回容器） | 渲染 MO/静电势后 3D 图位于轨道页画布区内；缩放/清除/连续切换无残留；抽屉滚动无错位 | 待执行 |

> 备注：A-7 画布 `id="undefined"` 系 GLViewer 以容器 id 命名所致（我们传的是元素
> 非 id），无功能影响，不处理。

## 2. 抽屉结构改动要点（A-1/A-2/A-3 同一结构改动）

```text
现：字段 dl 组 → .actions(输入|输出|导出.out|归档|关闭) → AnalysisPanel(常驻) → .text-view(v-if 预览)
改：字段 dl 组 → .actions(输入|输出|分析[toggle]|归档|关闭) → 展示区(v-if 互斥：.text-view 或 .sub-region>AnalysisPanel)
```

- 互斥实现：`viewText()` 内 `anaOpen.value = false`；`toggleAna()` 内
  `textView.value = null`。`open()`（打开抽屉）重置 `anaOpen = false`。
- 展示区容器：`flex: 1 1 auto; min-height: 300px; display: flex;
  flex-direction: column`——上游字段放得下时拉伸贴抽屉下缘，放不下时保底
  300px 依赖抽屉滚动（`.drawer` overflow:auto 不变）。
- 预览：`.text-view` 即展示区本体，`.tv-body` 去 `max-height`、改 `flex: 1`；
  `scrollIntoView`（`:262`）保留（上游超高场景仍有用）。
- 分析板块：`<AnalysisPanel>` 由常驻挂载改 `v-if="anaOpen"` 挂载于 `.sub-region`
  （内容顶部对齐，不强制铺满）；附带行为变化——概览请求延迟到首次展开（惰性化，
  无需额外处理）；板块头部的工作区分析入口随板块整体开合，不动。
- 「分析」按钮：复用 `btn--secondary`，展开态加 accent 描边（同 `.preset--on`
  语义），`aria-expanded` 标注开合态。
- 归档视图（/archive 复用本组件）自动同享，无差异处理。

## 3. 提交组织与闸门

提交顺序（1–5 每笔均可独立构建回滚）：

1. `fix(web)`：A-7 画布定位（一行样式）。
2. `fix(web)`：A-6 下拉/输入文字裁剪（两处 padding）。
3. `fix(web)`：A-4 去「— 缺」后缀（两文件）。
4. `fix(web)`：A-5 收敛图对数轴科学计数 + 底部布局预留。
5. `fix(web)`：A-1+A-3+A-2 抽屉动作行重组（分析开关与互斥、去单条导出、预览贴底）。
6. `docs(plans)`：走查留痕回填 m3-acceptance.md。
7. `chore(progress)`：CHANGELOG.jsonl / progress.json 逐笔同步收尾。

每笔提交前闸门（§6.3）：`npm run build`、`uv run pytest -q`、
`uv run python scripts/validate_progress.py`、`uv run python scripts/check_tokens.py`、
`uv run python scripts/check_contrast.py`、
`bash scripts/audit_frontend_offline.sh`（前端批次必跑）。

终验走查：8398 实机按 §1 各条「验收」列逐项核对（含 A-7 实渲染 cube、
A-5b 实拍滑块），留痕 m3-acceptance.md。
