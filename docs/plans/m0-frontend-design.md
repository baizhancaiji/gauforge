# M0 前端视觉与 UX 设计规范（C 阶段设计输入）

> 状态：设计规范。本文件是 [m0-plan.md](m0-plan.md) 任务 C1–C4 的视觉/UX 设计
> 输入，即 roadmap §1 原则 7「视觉基调 M0 定稿」的定稿载体（随 A5 走查一并确认）。
> 可视化样板：[assets/m0-ui-preview.html](assets/m0-ui-preview.html)
> （浏览器直接打开，含六页视图与组件墙，侧栏导航全页可切换）。
> 本规范与 roadmap 冲突时以 roadmap 为准；「简约、信息密度优先、装饰从简」是
> 硬约束，本文全部设计决定服从它。

## 1. 设计方向：实验台仪器面板（Lab Bench Instrument）

**用户与场景**：计算化学研究者单人使用；任务一跑数小时到数天，界面会被
**长时间开着盯进度**；核心动作是扫一眼状态、发现问题、少量精确操作。

**概念**：界面 = 实验台上的一台仪器前面板 + 一叠记录纸。深色墨蓝底（监控场景
护眼、状态色显性）、等宽数字（仪器读数语义）、磷光青作为唯一品牌强调色
（仪器电源灯的联想）、极淡的记录纸网格背景（实验室物质感）。

**执行基调**：精密极简（refined minimalism）——克制的间距与字体系统、发丝线
分隔、状态色语义系统是全部「装饰」。**任何视觉元素必须携带仪器语义**（状态灯、
通道编号、刻度、读数），不存在纯装饰元素。

**记忆点**（评审时一眼可辨的三件事）：

1. **通道卡**：执行中页每个在跑任务一张编号通道卡（`CH 04`），大号等宽读数
   实时跳变，running 态卡边框磷光呼吸；
2. **全局状态灯排**：顶栏右侧三枚 LED 读数（在跑/排队/告警），全站可见；
3. **mono 页码导航**：侧栏每页带 `01–06` 等宽序号与英文小字，仪器通道编号语义。

**反方向**（明确不做）：浅色营销风、渐变横幅、玻璃拟态、大圆角卡片阵列、
彩色插画空状态、视差与滚动动效、紫色系。

## 2. 设计令牌（design tokens）

单一来源 `web/frontend/src/styles/tokens.css`（C1 建立，全部组件只引用变量，
禁止散落硬编码色值/字号）。

### 2.1 色彩

```css
/* 基底（深石墨蓝黑，默认主题——长时间监控场景主用；明暗双主题见本节末） */
--bg-base:    #0c1116;   /* 页面基底 */
--bg-raised:  #111820;   /* 卡片 / 面板 / 表格容器 */
--bg-overlay: #17212b;   /* 浮层 / 下拉 / 模态 */
--bg-inset:   #0a0e12;   /* 输入框 / 代码 / 预览块内嵌 */
--bg-side:    #0c1116;   /* 侧栏底（亮色取白与纸底分层） */
--border-hair:   #1e2a36; /* 发丝线（表格分隔、卡片描边） */
--border-strong: #2e3f4e; /* 强描边（焦点、悬浮层） */

/* 前景 */
--text-primary:   #dde7ef;
--text-secondary: #8da2b5;
--text-faint:     #5a6d80;

/* 品牌 / 交互强调（磷光青） */
--accent:     #38d4c2;
--accent-dim: #2a9c8f;   /* hover/按下收敛 */
--accent-ink: #062019;   /* 青底上的深字 */

/* 状态语义色（全站信号系统，与任务状态机一一对应） */
--state-staged:    #7f96ab; /* 灰蓝：已入队等待 */
--state-running:   #38d4c2; /* 磷光青 = 品牌色同源，running 是界面主角 */
--state-succeeded: #4cc38a; /* 试剂绿 */
--state-failed:    #e5534b; /* 信号红 */
--state-skipped:   #d9a03f; /* 琥珀（同时兼警告色 --warn） */
--state-archived:  #55677a; /* 暗灰 */
--state-idle:      #55677a; /* 队列未提交（与 archived 同值的独立语义变量） */

/* 功能色 */
--warn:   #d9a03f;
--danger: #e5534b;  /* 危险动作（删除/停止确认）与 failed 同源 */

/* 语义衍生（透明度由 tokens 统一给出，不手调） */
--chip-bg-alpha: 0.12;   /* 徽标底 = 状态色 12% */
--row-hover: rgba(56, 212, 194, 0.04);
--glow-running: 0 0 0 1px rgba(56,212,194,0.35), 0 0 24px rgba(56,212,194,0.12);
--grid-line: rgba(141,162,181,.035);   /* 记录纸网格线（§3 背景纹理） */
--grid-dot:  rgba(141,162,181,.05);    /* 十字基准点 */
--shadow-pop: 0 8px 28px rgba(4,8,12,.45);  /* 浮层 / Toast 投影 */
```

对比度校验要求：正文 `--text-primary`/`--text-secondary` 对 `--bg-base` ≥ 4.5:1；
状态色作为徽标文字对 12% 徽标底 ≥ 4.5:1（§7 验收项）。

**明亮主题（Light · 记录纸）**：双主题并存，默认暗色（长时间监控主场景），
顶栏右端切换按钮切换、localStorage 记忆。亮色 = 同一气质的「打印实验报告」：
冷白纸底 + 同 hue 加深的强调与状态色，发光收敛为实线描边。tokens 以
`html[data-theme="light"]` 整组覆盖（值以样板为准）：

```css
html[data-theme="light"]{
  --bg-base:#f2f5f7; --bg-raised:#ffffff; --bg-overlay:#ffffff; --bg-inset:#eaeef2;
  --bg-side:#ffffff;          /* 侧栏亮色取白，与主区纸底分层 */
  --border-hair:#dbe2e8; --border-strong:#aebcc8;
  --text-primary:#1c2a35; --text-secondary:#4d6072; --text-faint:#80909e;
  --accent:#0b8a7b; --accent-dim:#0a7266; --accent-ink:#ffffff;
  --state-staged:#5b7186; --state-running:#0b8a7b; --state-succeeded:#1a7c4c;
  --state-failed:#c23a31; --state-skipped:#8f6a1f; --state-archived:#8795a3;
  --state-idle:#8795a3;
  --warn:#8f6a1f; --danger:#c23a31;   /* 与 skipped/failed 同源关系在两主题下保持 */
  --glow-running:0 0 0 1px rgba(11,138,123,.45);   /* 无泛光，纯描边 */
  --row-hover:rgba(11,138,123,.05);
  --grid-line:rgba(28,42,53,.045); --grid-dot:rgba(28,42,53,.06);
  --shadow-pop:0 8px 24px rgba(28,42,53,.16);
}
```

纪律：两主题共用同一套组件结构与语义变量名，任何组件**只引用变量、不写
主题分支**——新增颜色需求若两主题都要调，只加变量不改组件。

### 2.2 字体

| 用途 | 栈 | 说明 |
|---|---|---|
| UI/数据 | `"IBM Plex Mono", "Noto Sans SC", ui-monospace, monospace` | 导航、按钮、状态徽标、表格数字列、时间戳、哈希、监控读数 |
| 正文 | `"IBM Plex Sans", "Noto Sans SC", system-ui, sans-serif` | 描述文字、表单说明、预览文本 |
| 中文回落 | `"Noto Sans SC", "PingFang SC", "Microsoft YaHei"` | 并入上面两栈 |

选型理由：IBM Plex 家族有明确的工程仪表血统，Mono 数字读数气质贴合仪器面板；
避开 Inter/Roboto/Space Grotesk 等通用选择。全部经 Google Fonts 引入
（`IBM Plex Mono` 400/500/600、`IBM Plex Sans` 400/500、`Noto Sans SC` 400/500），
离线回落系统栈不破版。

字号阶梯（信息密度取紧凑档）：

| token | 值 | 用途 |
|---|---|---|
| `--text-xs` | 11px / 1.4 | 徽标、注释、表头 |
| `--text-sm` | 12.5px / 1.5 | 表格次要列、表单辅助 |
| `--text-md` | 13.5px / 1.6 | 正文、表格主列 |
| `--text-lg` | 16px / 1.5 | 区块标题 |
| `--text-xl` | 20px / 1.3 | 页面标题 |
| `--text-readout` | 28px / 1 | 通道卡监控大读数（tabular-nums） |

所有数字列 `font-variant-numeric: tabular-nums`（时间/耗时/资源读数对齐）。

### 2.3 间距、圆角、层级

- 间距：`--space-1: 4px` 起，4/8/12/16/20/24/32/40/48（4 的倍数制）。
- 圆角：`--r-sm: 3px`（徽标）、`--r-md: 6px`（卡片/按钮/输入）、`--r-lg: 10px`（模态）。
- 层级：`z-nav 100 / z-dropdown 200 / z-modal 300 / z-toast 400`。
- 深色界面阴影弱化：层级靠描边与底色阶梯；唯一「发光」保留给 running 态
  （`--glow-running`），发光即「通电」语义，不滥用；亮色主题下发光收敛为
  1px 实线描边（纸面不泛光）。

## 3. 全局框架

```text
┌──────────┬──────────────────────────────────────────────┐
│ 侧栏 216px│ 顶栏：页标题 + mono 页码      状态灯排 ●●●     │
│          ├──────────────────────────────────────────────┤
│ g16web▌  │                                              │
│ 01 候选   │          主内容区（页面视图）                  │
│ 02 队列   │                                              │
│ 03 待执行 │                                              │
│ 04 执行中 │                                              │
│ 05 历史   │                                              │
│ 06 设置   │                                              │
│ ──────   │                                              │
│ HQ ● 已连 │                                              │
└──────────┴──────────────────────────────────────────────┘
```

- **侧栏**（固定 216px，深 `--bg-base`，右发丝线）：
  - 字标区：`g16web` mono 600 + 磷光青 6px 方块（电源灯，服务在线时常亮、
    断线变 `--danger` 并闪烁——接 SSE 连接态）；
  - 导航项：`序号(mono faint) + 中文名 + 英文小字(faint 10px)`，当前项左侧
    2px 磷光青指示条 + 文字转 `--text-primary`；
  - 底部：HQ 连接状态行（LED 点 + `HQ 已连接`/`HQ 未连接`）——M0 为静态占位
    （恒「未连接」淡化态，不接事件），M1 接入真实连接态（§9）。
- **顶栏**（56px，`--bg-raised`，下发丝线）：
  - 左：页面中文标题（`--text-xl`）+ 旁边 mono 页码 `02 / QUEUES`（faint）；
  - 右：**状态灯排**——`在跑 2`（磷光青）、`排队 3`（灰蓝）、`告警 1`（琥珀，
    无告警时整枚淡化 40%）；数字 mono tabular；数据源为 SSE（M0 接 mock 流）；
    灯排右端为明暗主题切换按钮（`◐ 亮色`/`◑ 暗色`，secondary 样式小按钮）。
- **背景纹理**：`--bg-base` 上叠记录纸网格——24px 网格线 `--grid-line` +
  96px 周期十字基准点 `--grid-dot`（两主题各给值，组件不写死 rgba）；
  克制到「几乎察觉不到，去掉后界面发空」。卡片/表格容器不透网格
  （`--bg-raised` 实底），网格只出现在留白区。

## 4. 组件规范

### 4.1 状态徽标 StatusChip

任务/队列状态的唯一展示件：`● SUCCEEDED` —— mono 11px 大写、状态色文字、
状态色 12% 底、3px 圆角药丸、左侧 6px 实心状态点。running 的点 2.4s 呼吸
（opacity 0.5↔1）。任务六态对应 `--state-*`；队列四态复用同族变量
（`未提交 idle`=`--state-idle` / `已提交 staged` / `执行中 running` /
`已完成 succeeded`）。
**同一状态在全站任何页面颜色与措辞完全一致**——这是信号系统的纪律。

### 4.2 按钮

高 32px、mono 12.5px、`--r-md` 圆角、留白左右 16px。

| 类 | 样式 | 用途 |
|---|---|---|
| primary | `--accent` 实底 + `--accent-ink` 深字 | 每视图至多一个（提交/保存） |
| secondary | `--border-strong` 描边 + `--text-secondary` | 一般动作 |
| ghost | 无框，hover 显 `--row-hover` 底 | 表格行内动作（预览/移除） |
| danger | `--danger` 描边 + `--danger` 字 | 停止/删除（二次确认模态配合） |

### 4.3 数据表格

信息密度核心件：行高 40px、发丝分隔线、无斑马纹、hover 行 `--row-hover`、
粘性表头（`--bg-raised` + 底部发丝线）、表头 11px faint 大写。数字/时间/
哈希/id 列一律 mono。行内动作区右对齐、ghost 按钮。加载态：表格区 40% 透明
+ 底部 1px 磷光扫描线往返（唯一 loading 动效）。

### 4.4 通道卡 ChannelCard（执行中页核心件）

```text
┌ CH 04 ────────────────────── ● RUNNING ┐
│ phenol-opt.gjf            队列 AB2CDE   │
│ 提交 08:10:02 启动 08:10:04 已运行 3h 12m │
│                                        │
│   CPU 386%        MEM 512 MB           │
│   ──────────      ──────────           │
│   OPT STEP 5      SCF CYCLE 3          │
│ ⚠ 停滞告警 12m（恢复于 08:31）           │
└────────────────────────────────────────┘
```

- 卡宽固定 340px，网格自适应排列（1–6 卡同屏=并行窗口）；
- 卡头：`CH <执行id 右对齐三位>` mono + 状态徽标；
- 读数区：CPU%/MEM 用 `--text-readout` 大号 mono（跳变即更新，仪器语义，
  不做数字滚动动画），OPT STEP/SCF 为次级读数（16px mono）；
- running 态：卡描边 `--glow-running` 微呼吸；停滞告警时卡头追加琥珀灯行；
- SSE 事件 `execution.monitor` / `execution.progress` / `execution.stalled`
  直接驱动对应字段（M0 接 mock 流演示）。

### 4.5 席位行 SeatRow（待执行页核心件）

- 纵向列表，顺序即执行序列；每席位一横条（高 48px，队列席位可展开）：
  左端 `S<seat_id>` mono + 类型标签（`TASK`/`QUEUE` 11px 徽标式），中部
  任务文件名或队列名+成员概览，右端状态/动作；
- **并行窗口边界可视化**：被窗口触及的席位整条加左侧 2px 磷光条 + `WINDOW`
  mono 标记，其后席位为等待区——用户一眼看出「执行序列推进到哪」；
- 容量仪表在页首：`OCCUPIED 2/3` 分段 LED 条（3 段，占用段磷光青）+
  `WINDOW 2` 读数。

### 4.6 模态 / Toast / 空态 / 表单

- **模态**（确认框）：`--bg-overlay` + backdrop `rgba(12,17,22,0.72)` +
  blur(2px)，`--r-lg`，标题 mono；危险确认的确认按钮用 danger 类
  （停止/删除的二次确认都在这里，不在页面内联）。
- **Toast（任务结束通知）**：右上角从屏幕右缘滑入（240ms，translateX 28px），
  5s 自消，可手动关闭，多条纵向堆叠；`--bg-overlay` 底 + 左侧 3px 状态色条 +
  `--shadow-pop` 投影。**触发规则**：任务到达终态即通知（SSE `history.appended`
  事件驱动），**skipped 不通知**——它只在队列语境下有意义，由队列状态事件与
  页面内徽标表达；名称取「直接提交任务的 title / 队列成员所属队列名」，
  超 15 字符截断加 `…`；文案 `名称: 状态`（如 `water opt: succeeded`），
  状态词着 succeeded 绿 / failed 红，色条同色。
- **空态**：居中发丝线方框（48px）内一个极简刻度符号 + mono 短句
  （如 `暂无候选任务 · 导入 .gjf 文件后显示于此`）。不用插画。
- **表单控件**：输入框 `--bg-inset` 底 + `--border-hair` 描边，焦点转
  `--accent` 描边 1px；label 12.5px + 辅助说明 11px faint；
  设置项生效语义用微型徽标（`即时`/`即时且追溯`/`新任务生效`/`重启生效`，
  对应 m0-plan §2.2 `effect` 四值枚举）。

## 5. 六页布局与 UX 细则（M0 空壳渲染范围）

样板 HTML 覆盖全部六页视图与组件墙；页面归并为四种原型（表格型/席位型/
通道卡型/表单型），同原型页面共享布局骨架：

| 页面 | 原型 | 布局要点 | M0 空壳渲染 |
|---|---|---|---|
| 01 候选任务 | 表格型（双栏） | 左 55% 列表（id/文件名/title/来源徽标——失败退回附琥珀归因注记 `failure_note`），右侧粘性预览卡：TITLE/LINK0/ROUTE/CHARGE·MULT/MOLECULE 读数/**ADDITIONAL SECTIONS**（附加输入节有序列表，无则空态；m0-plan §2.2）分块 mono 展示 + 原子数与分子式（Hill 记法元素统计，如 `H2O1`/`C6H6O1`，计数 1 显式）读数；Link0 缺失项琥珀注记（M1 提交警告的伏笔） | 全字段 + 预览卡切换 |
| 02 队列 | 表格型 | 队列列表（id mono/名称/成员数徽标/状态/回退标记 `已回退 ×2` 琥珀）；行可展开成员概览（任务 id/文件名/分子式/状态徽标）与失败归因 | 列表 + 展开态 |
| 03 待执行 | 席位型 | §4.5；席位展开队列成员子表 | 容量仪表 + 席位 + 窗口边界 |
| 04 执行中 | 通道卡型 | §4.4 通道卡网格；无在跑时显示空态 + `WINDOW n` 读数 | mock SSE 驱动读数跳变 |
| 05 历史 | 表格型 | 全宽表格（id/任务/状态徽标/归因/提交→结束/耗时/资源/队列归属）；顶部仅状态筛选——**归档条目不列于此**（归档页为 M1 增设的独立路由，roadmap §2.1「归档为独立页面」、m0-plan 决策点 10）；行点击 → 详情抽屉：全字段（含 `input_hash`/`monitor_summary`/`chk_snapshot`/`result_ref`）+ 动作（输入查看、输出预览/导出、归档、failed/skipped 重新排队/退回候选——M1 语义 M0 mock） | 表格 + 徽标全态 + 详情抽屉 |
| 06 设置 | 表单型 | 限宽 880px：启动级只读区（锁定图标 + 值 mono）在上，运行级分组表单在下，每项带生效语义徽标；保存按钮 + `重启生效` 项的提示条 | 分组 + 可交互控件（写 mock） |

信息架构纪律（roadmap §1 原则 7）：视觉设计不为任何页面增加新信息层级；
六页的信息结构 = m0-plan.md §2.5 映射表所列界面元素，一个不多、一个不少。

## 6. 动效规范（CSS-only，克制）

| 动效 | 规格 | 语义 |
|---|---|---|
| 视图切换 | 内容区 opacity 0→1 + translateY(6px→0)，160ms ease-out | 导航反馈 |
| 列表入场 | 行/卡 stagger：每行 delay 18ms（>8 行截断统一入场），220ms | 一次编排好的加载（全站仅此一处 stagger） |
| running 呼吸 | 状态点/通道卡发光 opacity 0.65↔1，2.4s ease-in-out | 「通电中」 |
| 加载扫描线 | 表格底部 1px 磷光线往返 1.2s | 数据在途 |
| hover | 行/按钮 120ms 过渡 | 命中反馈 |

硬规则：`@media (prefers-reduced-motion: reduce)` 下全部动效关闭；数字读数
永不滚动/闪烁（跳变）；无任何全屏位移、弹跳、渐变扫光。

## 7. 可访问性与可用性底线

- 对比度：§2.1 列举的组合 ≥ 4.5:1（C1 落 tokens 时用工具实测记录）。
- 键盘：全部交互可 Tab 触达、焦点可见（`--accent` 1px 外描边 + 2px 偏移）；
  模态内焦点圈定、Esc 关闭。
- 语义：状态不只靠颜色——徽标自带文字（`● FAILED`），色弱可用。
- 中文文案：动词开头、句尾不加句号；数字与单位间加空格（`3h 12m`、`512 MB`）。

## 8. M0 落地与验收

1. C1 建立 `src/styles/tokens.css`（§2 全量，含明暗双主题变量组）+
   `base.css`（reset/框架/背景纹理/主题切换），字体经 CDN 引入并带离线回落栈；
2. C3/C4 六页组件严格引用 tokens，禁止组件内硬编码色值/字号（走查抽查）；
3. 验收（并入 m0-plan.md §8）：六页按本规范渲染 mock 数据；与
   `assets/m0-ui-preview.html` 样板并排走查，视觉一致性人工确认
   （tokens 同源即一致）；`prefers-reduced-motion` 下动效为零。

## 9. 演进预留（不在 M0 实施）

- M1：真实 SSE 接入后，状态灯排/通道卡读数/席位窗口边界由事件流驱动
  （数据接口已按 m0-plan.md §3 对齐）；HQ 断线态（侧栏电源灯闪烁）接入。
- M2：编辑态样式（输入框/校验错误 `--danger` 描边 + 11px 错误注记、拼写检查
  非阻断警告琥珀注记 `--warn`——m0-plan 决策点 11）、
  拖拽排序的位移动效（120ms、无弹性）。
- M3：结果分析视图（能量曲线/谱图）沿用 tokens——图表轴线 `--border-hair`、
  曲线 `--accent`、收敛点 `--state-succeeded`；3Dmol.js 画布区配
  `--bg-inset` 底与工具条，暗色适配天然成立。
