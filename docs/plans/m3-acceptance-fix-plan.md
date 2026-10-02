# M3 人工验收问题修复计划（第一批：历史页抽屉七项 · 第二批：部署反馈五项）

> 状态：已执行完毕（2026-10-02，两批十二项全部落地，逐项验收留痕见
> [m3-acceptance.md](m3-acceptance.md) §5；走查中发现缺陷②「重启提示条
> 永不出现」随查随修）。第一批来源：M3 完成后人工验收（2026-10-02，用户实机走查 + 截图），
> 其中问题 4 的处置口径已于同日由用户更新为「正常置灰」（原「隐藏不显示」作废）。
> 第二批来源：v2.1.0 实际部署使用反馈（2026-10-02，用户提出五项：执行页监控读数
> 卡死、结果引用行、占用统计口径、设置页文案、待执行页拖拽动效）。
> 第一批范围：历史页详情抽屉（`HistoryView.vue`，/archive 归档视图复用同组件）及
> 其内嵌分析板块（`AnalysisPanel.vue` 与四个子组件）；第二批范围：SSE 消费 store、
> 占用统计服务与契约、设置文案定义、待执行页拖拽；均为 `web/` 前后端修复。
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

第二批（2026-10-02）取证：

- 问题 1（监控卡死）：代码级定位——`events.ts` 看门狗 60s 无帧主动 abort 后，
  `finally` 重连判定把该 abort 误判为主动关闭（`events.ts:439` 条件含
  `controller.signal.aborted`），既不重连、也不改写 `connection`（指示灯仍
  open）；后端侧核对无嫌疑（`sse.py:58-65` 慢消费=断开让客户端重连、
  `dispatcher.py:619-627` 引擎线程单轮异常不死亡）。
- 问题 3（占用口径）：`services/storage.py` 口径核对 + 本机实测
  `du -sb ~/g16web`——run/ 2 298 121 150 B ≈ 2.14 GiB，HOME 整树
  2 298 807 154 B，run/ 之外（hq 状态/inputs/db±wal）合计仅 ≈0.68 MB：
  读数小是数据本身小（文本输出为主、chk/rwf 超期已清理），非漏扫大目录；
  但「总占用」口径确实只覆盖 run/ 产物树。

## 1. 问题与根因总表

| # | 问题概述 | 根因定位 | 修复方案 | 验收 | 状态 |
|---|---|---|---|---|---|
| A-1 | 分析板块常驻抽屉，挤压预览与滚动 | `HistoryView.vue:598-599` 无条件渲染 `<AnalysisPanel>`，无开关状态 | 动作行加「分析」按钮（与输入/输出同级，置于原「导出 .out」位）：`anaOpen` 默认 false，点击展开/再点收起；与预览互斥（开一边关另一边）；分析板块渲染于与预览同一展示区（见 §2） | 打开抽屉默认仅字段+动作行；「分析」开合正常；分析展开时点「输入/输出」则分析收起，反之亦然 | 已修复（71a4af16 分析按钮化互斥同区展示，惰性挂载） |
| A-2 | 输入/输出预览高度不足、不贴可视区下缘 | `HistoryView.vue:904-913` `.tv-body` 限高 `var(--peek-max-height)`（300px，`tokens.css:66`）；`.text-view` 非 flex 拉伸，被常驻分析板块推到折叠线下 | 预览改为展示区本体：`flex: 1`（`min-height: 300px` 兜底防上游内容超高时被压没）+ `.tv-body` 去限高、`flex: 1` 内部滚动；抽屉 100% 高不变 | 预览上缘位于「输入/输出」按钮正下方（二者互斥已保证），下缘贴可视区底缘；上游内容超高时保底 300px 可滚 | 已修复（71a4af16 展示区本体拉伸贴底下缘，tv-body 内部滚动） |
| A-3 | 抽屉「导出 .out」被工具条批量导出取代，多余 | `HistoryView.vue:564` 锚点 + `:264-267` `outputUrl` computed | 删除该锚点与 computed（工具条批量导出 `:377-384` 不动）；空出位由 A-1「分析」按钮顶替 | 抽屉内无单条导出入口；工具条批量导出功能不受影响 | 已修复（71a4af16 删锚点与 computed，批量导出不受影响） |
| A-4 | tab 与「可用数据块」的「— 缺」后缀丑 | tab：`AnalysisPanel.vue:307` 模板后缀；块：`AnalysisOverview.vue:105` 后缀。置灰样式两处已有（`.ana-tab--off` / `.blk--off`） | 两处均仅删「— 缺」文案，保留置灰与缺失原因 title/既有类（2026-10-02 用户口径：块不隐藏、正常置灰，与 tab 同行为） | 缺失 tab/数据块呈纯置灰态，无「— 缺」字样；title 仍注明缺失原因 | 已修复（38431dee 两文件去后缀保留置灰与 title） |
| A-5a | 对数纵轴 `1/0.1/0.001…` 刻度不专业 | `ConvergenceChart.vue:52-60` log 轴 axisLabel 用默认十进制标签 | log 轴（SCF/几何共用的 `logCvFrame :67-75`）axisLabel 加 formatter：十的幂科学计数（rich text：`{base|10}{exp|n}`，指数小字号上移模拟上标；v=1 显示 `1`）。不用 Unicode 上标字符（U+207B 在 mono 栈有 tofu 风险）；横轴当前无 log 场景，formatter 仅挂 log 轴 | 纵轴刻度显示 10⁰/10⁻¹/10⁻²…（实拍留痕）；字号/颜色走设计令牌 | 已修复（b4ea721c 对数轴科学计数上标，字号颜色走令牌） |
| A-5b | 图下滑块及左右数字下半截被裁 | `ConvergenceChart.vue:61` grid `bottom: 46` + `containLabel: true`（只含刻度标签，不含轴名 nameGap 25 与 dataZoom `bottom: 2 / height: 14`，`:73`）——底部需 ≈69px 实留 46px，滑块与轴名区重叠并被画布下缘裁切 | 底部预留一次给足：`grid.bottom` 46→约 84，`.cv-chart` 高 240→280 补偿绘图区；具体数值实现时按走查校准 | 滑块完整可见、与轴名无重叠、两端数字可见；轴名中文无 tofu（本次实拍疑似单字异常，低清存疑，走查确认） | 已修复（b4ea721c grid.bottom 84/画布 280/dataZoom 内缩并显式开两端数值） |
| A-6 | 「类型」「轨道」下拉未展开时文字下缘被遮 | `base.css:64-73` 全局 `input/select/textarea` 设 `padding: 6px 8px`，`OrbitalsPanel.vue:310-318` `.ctl select` 限高 24px 未覆写 padding → 内容盒 ≈10px < 12px 中文行盒 | `.ctl select` 补 `padding: 0 var(--space-2)`（对齐 `.ws-input` 既有修法）。同类全量排查：`UpdateCard.vue:329-333` `.proxy-input`（input，24px 定高未覆写 padding）同中招，一并修 | 两下拉文字完整显示、展开正常；设置页代理输入框文字完整 | 已修复（b32122a4 两处补水平 padding；同类定高控件全量排查无遗漏） |
| A-7 | 「生成并渲染」的 3D 图出现在工作台左上角 | vendored `3dmol.es6.js:21590-21596` canvas 写死 `position: absolute; top: 0; left: 0`（第三方，不改）；`OrbitalsPanel.vue:370-377` `.orb-viewer` 无 position → 最近定位祖先是全屏 `.scrim`（`HistoryView.vue:799-806`，fixed inset 0），canvas 锚到视口左上 | `.orb-viewer` 补 `position: relative`（一行；`overflow: hidden` 已有即裁回容器） | 渲染 MO/静电势后 3D 图位于轨道页画布区内；缩放/清除/连续切换无残留；抽屉滚动无错位 | 已修复（f1594716 画布容器自建定位上下文；CSS 侧实机断言过，3D 视觉复验留待 WebGL 环境） |

> 备注：A-7 画布 `id="undefined"` 系 GLViewer 以容器 id 命名所致（我们传的是元素
> 非 id），无功能影响，不处理。

## 2. 抽屉结构改动要点（第一批 A-1/A-2/A-3 同一结构改动）

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

## 3. 第二批：部署反馈五项（v2.1.0 实际使用，2026-10-02）

| # | 问题概述 | 根因定位 | 修复方案 | 验收 | 状态 |
|---|---|---|---|---|---|
| A-8 | 执行中页 CPU/内存读数长时间挂机后冻结，刷新才恢复 | `events.ts:385-387` 看门狗 60s 无帧主动 `controller.abort()`；`events.ts:439` `finally` 判定 `controller.signal.aborted` 命中「主动关闭：不重连」分支——自 abort 与用户 stop 无法区分，断流后永不重连且 `connection` 仍显 open（无断连提示）；WSL2 部署 Windows 睡眠唤醒/网络静默后 TCP 半开即触发 | `finally` 判定收窄为 `if (closedByUs)`（`stop()` 恒先置 `closedByUs`，语义不变）；看门狗 abort 后自然流入重连分支（显示 reconnecting → 退避重连 → 快照重建基线） | 模拟断流（断后端/杀流）60s 内自动重连、指示灯经历 reconnecting→open、读数恢复，无需手动刷新；正常 stop 路径回归不变 | 已修复（6fa13202 finally 判定收窄为 closedByUs；断流走查 open→reconnecting→open 留痕） |
| A-9 | 抽屉「结果引用」恒显 analysis.json，无用户信息量 | `HistoryView.vue:552-555`；字段含义见下方答疑①——值域仅 `analysis.json`/null，UI 呈现无信息量 | 删除抽屉该行；后端字段与契约保留（DB 仍记录出处，排障可用） | 抽屉无「结果引用」行；契约与后端零改动 | 已修复（79b6927 删抽屉行，契约后端零改动） |
| A-10 | 「占用 77MB」口径疑问：期望总占用 | 见下方答疑②——现为 run/ 产物树整树（`services/storage.py` `usage()`，du -sb 同口径），非单任务；run/ 之外（db/hq 状态/inputs）未计入 | 口径扩为工作区根（G16WEB_HOME）整树：单遍历保持，total=整树 apparent size，per-execution 明细桶仍按 run/<id> 分桶、其余计入总量；契约描述同步修订（`openapi.yaml:852-855`）；UI 明细脚注注明口径 | 与 `du -sb <工作区根>` 对照一致（条目竞态容差）；明细与可清理量不变；over 阈值判定按新 total 生效 | 已修复（249af02f 契约描述 + b92b2332 整树实现与脚注；du 对照差 41KB 归因观测自扰） |
| A-11 | 设置页提示含括号补充、英文参数名、开发者向行为说明 | 文案定义在 `config.py:54-112`（12 运行级 + 2 启动级 description）；前端另展示参数名与 env 变量（`SettingsView.vue:176/178/204`），重启提示条直出 key（`:229`） | 按「只留必要解释」逐条裁剪（清单见下方答疑③）：去全部生效语义括注（徽标已表达）、范围说明、`M3 M3.7` 类内部注记；保留「凌晨 1:00 锚定」「0=禁用告警」；前端去参数名/env 展示（含只读区），重启提示条改显中文参数名 | 设置页无英文参数名/env 名；逐条对照裁剪清单走查；必要解释保留 | 已修复（4ff6fb9c 文案裁剪 + d9c1d457 去 env/key 展示 + c6a6afb4 走查缺陷②重启提示条修复） |
| A-12 | 待执行页拖拽仍是旧动效（无跟手让位） | `PendingView.vue:60` 用旧 `useDragSort`（HTML5 DnD）；新动效 `usePointerSort` 仅队列编辑框使用（当初因席位行高可变未迁） | 迁移 PendingView 席位重排至 `usePointerSort`，组合式扩展变高行支持（要点见下方④）；锁定席位门控语义保持；迁移后删除 `useDragSort.ts`（唯一使用方消失） | 跟手动效与队列编辑框一致；锁定席位门控回归走查（锁定原位放行、越界本地拒绝、后端 409 提示）；子表展开/收起后拖拽量测正确；队列编辑框动效不回归 | 已修复（be8eea80 变高行前缀和 + 逐行门控迁移，删 useDragSort；互换/门控/展开/回归走查过） |

### 答疑与要点

① **「结果引用」含义**：M3 分析入库的出处字段（`result_ref`）——分析数据
analysis.json 落盘成功即置位（degraded 亦置位），落盘失败为 null（`finalize.py:40-43`）。
设计意图是记录「分析数据从哪来」，属排障/审计信息；因值恒为 `analysis.json`，
对用户无信息量，按用户裁决移除 UI 呈现（字段与契约保留）。

② **占用统计口径**：现为 run/ 产物目录整树 apparent size（与 `du -sb run/` 同
口径），**是全部执行目录的总占用，不是单任务**；77MB 量级正常——输出以文本为主，
chk/rwf 超保留期清理后不占额（本机对照实测 run/ 外数据仅 ≈0.68 MB，见 §0）。
修复后扩为工作区根整树，明细脚注注明「口径：工作区根整树」。

③ **设置文案逐条裁剪清单**（`config.py`，`←` 后为新文案）：

| key | 现文案 | 新文案 |
|---|---|---|
| workspace_root | 工作区根目录（任务/结果/归档布局） | 工作区根目录 |
| bind_address | 监听地址 | 监听地址（不变；仅去 env/key 展示） |
| listen_port | 监听端口（保存后重启生效） | 监听端口 |
| pending_seat_limit | 待执行席位数上限（对已有席位追溯生效） | 待执行席位数上限 |
| parallel_window | 并行执行窗口（在跑不追溯，窗口按新值收敛） | 并行执行窗口 |
| chk_rwf_retention_days | chk/rwf 保留天数（仅对其后新任务生效） | chk/rwf 保留天数 |
| stall_threshold_minutes | 停滞告警阈值分钟数（仅对其后新任务生效） | 停滞告警阈值分钟数 |
| page_size | 列表分页大小（候选/队列/历史页统一） | 列表分页大小 |
| sse_heartbeat_seconds | SSE 心跳间隔秒数 | SSE 心跳间隔秒数（不变） |
| link0_default_nproc | Link0 %NProcShared 缺省值（仅对其后新任务生效） | Link0 %NProcShared 缺省值 |
| link0_default_mem_gb | Link0 %Mem 缺省值 GB（仅对其后新任务生效） | Link0 %Mem 缺省值 GB |
| g16_root | G16 发行目录（g16root 布局；仅对其后新任务生效） | G16 发行目录 |
| update_check_interval | 自动检查更新周期（凌晨 1:00 锚定、错过窗口启动补查；只发现不安装） | 自动检查更新周期（凌晨 1:00 锚定） |
| disk_usage_warn_gb | 空间占用告警阈值 GB（0=禁用告警；超阈仅琥珀警示、绝不自动清理，手动清理沿用历史页入口；M3 M3.7） | 空间占用告警阈值 GB（0=禁用告警） |

前端同步：`SettingsView.vue` 启动级去 `env_var`/key 展示（`:176/:178`）、运行级
hint 去 `.key`（`:204`）、重启提示条 `restartKeys` 改显中文参数名（`:229`，经
key→description 映射）。范围/取值行（`rangeText`）与生效徽标保留。

④ **usePointerSort 变高行扩展要点**：等高模型（首行 `offsetHeight` × 步距，
`usePointerSort.ts:47-67`）改为逐行实测高度前缀和定位——`canvasStyle` 总高=
Σ行高+间隙、`offsetFor`/`resolveOver`/`followPointer` 按前缀和换算槽位；
子表展开/收起后重测（watch 展开态触发 `measure()`）。等高列表（队列编辑框）在
前缀和模型下行为不变，需回归走查。逐行门控：`enabled` 全局谓词扩为逐行
（锁定席位不可作拖源），`resolveOver` 落点跳过锁定槽位取最近可落槽；
提交链路不变（本地锁定不变式校验 → PUT /pending/order → applySnapshot）。

## 4. 提交组织与闸门

### 第一批（历史页抽屉七项）

提交顺序（1–5 每笔均可独立构建回滚）：

1. `fix(web)`：A-7 画布定位（一行样式）。
2. `fix(web)`：A-6 下拉/输入文字裁剪（两处 padding）。
3. `fix(web)`：A-4 去「— 缺」后缀（两文件）。
4. `fix(web)`：A-5 收敛图对数轴科学计数 + 底部布局预留。
5. `fix(web)`：A-1+A-3+A-2 抽屉动作行重组（分析开关与互斥、去单条导出、预览贴底）。

### 第二批（部署反馈五项）

6. `fix(web)`：A-8 SSE 看门狗自 abort 误判不重连（events.ts）。
7. `fix(web)`：A-9 抽屉去「结果引用」行。
8. `docs(api)`：A-10 契约口径描述修订（openapi StorageUsage，重跑两侧生成物）。
9. `fix(core)`：A-10 占用统计扩为工作区根整树（storage.py + 前端脚注）。
10. `fix(core)`：A-11 设置文案裁剪（config.py 描述串）；`fix(web)`：A-11 设置页
    去 env/key 展示 + 重启提示条中文名（两笔同批）。
11. `refactor(web)`：A-12 待执行页迁移 usePointerSort（含变高行扩展、删 useDragSort）。

### 两批共用收尾

12. `docs(plans)`：走查留痕回填 m3-acceptance.md。
13. `chore(progress)`：CHANGELOG.jsonl / progress.json 逐笔同步收尾。

每笔提交前闸门（§6.3）：`npm run build`、`uv run pytest -q`、
`uv run python scripts/validate_progress.py`、`uv run python scripts/check_tokens.py`、
`uv run python scripts/check_contrast.py`、
`bash scripts/audit_frontend_offline.sh`（前端批次必跑）。
A-10 契约修订笔另跑 `test_openapi_ssot.py`（并入 pytest）；A-8 走查需模拟断流
（停后端 ≥60s 观察自动重连）。

终验走查：8398 实机按 §1/§3 各条「验收」列逐项核对（含 A-7 实渲染 cube、
A-8 断流重连、A-12 锁定席位门控与子表展开拖拽），留痕 m3-acceptance.md。
