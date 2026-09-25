# M0 前端视觉与 UX 设计规范（C 阶段设计输入）

> 状态：设计规范。本文件是 [m0-plan.md](m0-plan.md) 任务 C1–C4 的视觉/UX 设计
> 输入，即 roadmap §1 原则 7「视觉基调 M0 定稿」的定稿载体（随 A5 走查一并确认）。
> 可视化样板：[assets/m0-ui-preview.html](assets/m0-ui-preview.html)
> （浏览器直接打开，含六页视图与组件墙，侧栏导航全页可切换）。
> 本规范与 roadmap 冲突时以 roadmap 为准；「简约、信息密度优先、装饰从简」是
> 硬约束，本文全部设计决定服从它。
> 修订 v2（2026-09-24 设计评审）：全组合对比度核算修正；字体自托管；文字三轴
> 层级；令牌补全（缓动/字距/字重/页面度量/交互衍生色/图表序列色）；徽标响度
> 分级；琥珀语义拆分；组件状态矩阵；表格加载两态与截断规则；样板逐变量同步
> 机制。**本文件是 tokens 的唯一来源，样板由此再生成并机械校验（§8）。**
> v2 的视觉落地与端到端验收已经 C 阶段六页 GUI 走查（26 项逐页）与 D1 验收
> 复核通过，记录见 [m1-acceptance.md](m1-acceptance.md) §1/§3；令牌对齐、
> 对比度实测、基础接管清单、reduced-motion 与并排走查的专项留痕见同文
> §1.5（2026-09-25 二审查收尾补记）。

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

**反方向**（明确不做）：浅色营销风、渐变横幅、玻璃拟态（含 backdrop 模糊）、
大圆角卡片阵列、彩色插画空状态、视差与滚动动效、紫色系。

**信号响度原则**（本版新增，贯穿 §4）：仪器表盘上只有通电与告警的灯在亮。
视觉信号分两档——**响亮档**（running / failed：彩底、呼吸、发光）与
**安静档**（staged / succeeded / skipped / archived：圆点 + 文字、无底色）。
常态降噪，异常才显性；「全都在强调 = 全都没有强调」。

## 2. 设计令牌（design tokens）

单一来源 `web/frontend/src/styles/tokens.css`（C1 建立，全部组件只引用变量，
禁止散落硬编码色值/字号/字距/缓动）。样板的变量块与本文件逐变量同步（§8 验收项）。

### 2.1 色彩

```css
/* 基底（深石墨蓝黑，默认主题——长时间监控场景主用；明暗双主题见本节末） */
--bg-base:    #0c1116;   /* 页面基底 */
--bg-raised:  #111820;   /* 卡片 / 面板 / 表格容器 */
--bg-overlay: #17212b;   /* 浮层 / 下拉 / 模态 */
--bg-inset:   #0a0e12;   /* 输入框 / 代码 / 预览块内嵌 / 骨架行 */
--bg-side:    #0c1116;   /* 侧栏底（亮色取白与纸底分层） */
--border-hair:   #1e2a36; /* 发丝线（表格分隔、卡片描边） */
--border-strong: #2e3f4e; /* 强描边（焦点内环、悬浮层） */

/* 前景（三档明度强制拉开 ≈15 / ≈9 / ≈5.9:1；层级同时有字重、字号两轴，见 §2.2） */
--text-primary:   #dde7ef;
--text-secondary: #9db2c5;
--text-faint:     #7b8fa2;

/* 品牌 / 交互强调（磷光青） */
--accent:       #38d4c2;
--accent-hover: #4ee0cf;   /* primary 悬浮提亮（亮色主题覆盖为加深方向） */
--accent-dim:   #2a9c8f;   /* 按下收敛 */
--accent-ink:   #062019;   /* 青底上的深字 */

/* 状态语义色（全站信号系统，与任务状态机一一对应） */
--state-staged:    #7f96ab; /* 灰蓝：已入队等待 */
--state-running:   #38d4c2; /* 磷光青 = 品牌色同源，running 是界面主角 */
--state-succeeded: #4cc38a; /* 试剂绿 */
--state-failed:    #ec5f57; /* 信号红 */
--state-skipped:   #d9a03f; /* 琥珀（安静档展示，见琥珀纪律） */
--state-archived:  #71849a; /* 暗灰 */
--state-idle:      #71849a; /* 队列未提交（与 archived 同值的独立语义变量） */

/* 功能色 */
--warn:   #d9a03f;  /* 仅「需要行动的警告」，见琥珀纪律 */
--danger: #ec5f57;  /* 危险动作（删除/停止确认）与 failed 同源 */

/* 语义衍生（透明度由 tokens 统一给出，不手调） */
--chip-bg-alpha: 0.12;   /* 响亮档徽标底 = 状态色 12% */
--row-hover: rgba(56, 212, 194, 0.04);
--backdrop-dim: rgba(12, 17, 22, 0.45);    /* 抽屉遮罩：纯压暗无模糊 */
--backdrop-modal: rgba(12, 17, 22, 0.75);  /* 模态遮罩（§4.6） */
--glow-running: 0 0 0 1px rgba(56,212,194,0.35), 0 0 24px rgba(56,212,194,0.12);
--grid-line: rgba(141,162,181,.035);   /* 记录纸网格线（§3 背景纹理） */
--grid-dot:  rgba(141,162,181,.05);    /* 十字基准点 */
--shadow-pop: 0 8px 28px rgba(4,8,12,.45);  /* 浮层 / Toast 投影 */

/* 图表序列色（M3 预留，M0 不进任何组件；同 hue 邻域明度 + 灰蓝系，禁彩虹） */
--viz-1: #38d4c2;   /* 主曲线，与 accent 同源 */
--viz-2: #6fc0b4;   /* 青 · 淡 */
--viz-3: #9db2c5;   /* 灰蓝 */
--viz-4: #d9a03f;   /* 琥珀（多序列区分用） */
--viz-5: #71849a;   /* 暗灰 */
```

**对比度核算表**（由 `scripts/check_contrast.py` 闸门脚本按 WCAG 相对亮度
公式实测并逐项核对，全组合 ≥ 4.5:1；下表为实测回填值，作为后续改色的
回归基准）：

| 组合 | 暗色 | 亮色 |
|---|---|---|
| `--text-primary` / `--bg-base` | 15.13:1 | 13.39:1 |
| `--text-secondary` / `--bg-base` | 8.68:1 | 5.93:1 |
| `--text-faint` / `--bg-base` | 5.68:1 | 4.66:1 |
| running 徽标文字 / 响亮档 12% 底 | 7.67:1 | 4.89:1 |
| failed 徽标文字 / 响亮档 12% 底 | 4.71:1 | 4.72:1 |
| 安静档状态色 / `--bg-raised` | 4.65–8.07:1 | 5.57–6.15:1 |
| primary 按钮 ink / accent 底 | 9.25:1 | 5.81:1 |

**accent 使用纪律**（语义优先级：信号 > 交互 > 禁止装饰）。允许的完整清单：
running 信号（发光/呼吸/彩底）、侧栏电源灯、primary 按钮（每视图 ≤1）、
焦点双环的外环、行 hover/选中 tint、导航指示条。焦点环采用「`--border-strong`
内环 + `--accent` 外环」双环式，与 running 泛光在形态上区分——**交互态不冒充
通电态**。清单之外的新用法必须先增补本清单再落地。

**琥珀纪律**（`--warn` 只表示「需要行动」）。允许：停滞告警、Link0 缺失注记、
顶栏告警灯、保存条重启提示。skipped 是**正常终态**、队列回退是状态描述——两者
一律走安静档（琥珀圆点 + 文字、无底色），不占用告警响度。设置页生效语义徽标
（即时/新任务生效/重启生效）一律中性 plain 档，不使用状态色。

**明亮主题（Light · 记录纸）**：双主题并存，默认暗色（长时间监控主场景），
顶栏右端切换按钮切换、localStorage 记忆。亮色 = 同一气质的「打印实验报告」：
冷白纸底 + 同 hue 加深的强调与状态色（墨更深、饱和度略降），发光收敛为实线
描边。tokens 以 `html[data-theme="light"]` 整组覆盖（**值以本文件为唯一来源**，
样板由本文件再生成）：

```css
html[data-theme="light"]{
  --bg-base:#f2f5f7; --bg-raised:#ffffff; --bg-overlay:#ffffff; --bg-inset:#eaeef2;
  --bg-side:#ffffff;          /* 侧栏亮色取白，与主区纸底分层 */
  --border-hair:#dbe2e8; --border-strong:#aebcc8;
  --text-primary:#1c2a35; --text-secondary:#4d6072; --text-faint:#5f7080;
  --accent:#0a7266; --accent-hover:#096a5f; --accent-dim:#085c52; --accent-ink:#ffffff;
  --state-staged:#526778; --state-running:#0a7266; --state-succeeded:#177246;
  --state-failed:#bd352b; --state-skipped:#7d5c19; --state-archived:#5b6a76;
  --state-idle:#5b6a76;
  --warn:#7d5c19; --danger:#bd352b;   /* 与 skipped/failed 同源关系在两主题下保持 */
  --glow-running:0 0 0 1px rgba(10,114,102,.45);   /* 无泛光，纯描边 */
  --row-hover:rgba(10,114,102,.05);
  --backdrop-dim:rgba(28,42,53,.35); --backdrop-modal:rgba(28,42,53,.45);
  --grid-line:rgba(28,42,53,.045); --grid-dot:rgba(28,42,53,.06);
  --shadow-pop:0 8px 24px rgba(28,42,53,.16);
  color-scheme:light;   /* 原生控件（滚动条角落/下拉）随主题 */
}
```

纪律：两主题共用同一套组件结构与语义变量名，任何组件**只引用变量、不写
主题分支**——新增颜色需求若两主题都要调，只加变量不改组件。图表序列色亮色
组同法加深，M3 定稿时补组。

### 2.2 字体

| 用途 | 栈 | 说明 |
|---|---|---|
| UI/数据 | `"IBM Plex Mono", "Noto Sans SC", ui-monospace, monospace` | 导航、按钮、状态徽标、表格数字列、时间戳、哈希、监控读数 |
| 正文 | `"IBM Plex Sans", "Noto Sans SC", system-ui, sans-serif` | 描述文字、表单说明、预览文本 |
| 中文回落 | `"Noto Sans SC", "PingFang SC", "Microsoft YaHei"` | 并入上面两栈 |

选型理由：IBM Plex 家族有明确的工程仪表血统，Mono 数字读数气质贴合仪器面板；
避开 Inter/Roboto/Space Grotesk 等通用选择。

**分发（自托管，本版起为硬性要求）**：身份字体按基础设施对待，不走 CDN——
g16web 的典型运行环境是内网/离线实验室机器，外链字体失败会让整套仪器身份静默
坍塌为系统字 dashboard。实现口径为 **@fontsource 构建期打包**（`main.ts` 引入、
版本经 package.json 锁定，woff2 随构建产物分发）：

1. `@fontsource/ibm-plex-mono` 400/500/600、`@fontsource/ibm-plex-sans`
   400/500、`@fontsource/noto-sans-sc` 400/500 按 npm 依赖锁定（`package.json`），
   构建期打包进产物，运行期零外链；Noto Sans SC 由 fontsource 按
   unicode-range 子集分片，浏览器仅加载实际用字分片；
2. `font-display` 统一 `swap`（fontsource 默认），加载期以回落栈渲染不破版；
   产物文件名带内容哈希，无法静态 preload，不做 preload 要求；
3. 离线可用（硬性要求）：字体随构建产物分发，内网/离线环境不回退 CDN、
   不破版；组件字体栈回落段为最后防线。

**混排纪律**（mono 拉丁 + Sans 中文同屏，规则只有四条）：

1. 中文字形不小于 **12px**，实现口径统一为**承载中文一律升 `--text-sm`
   （12.5px）**；纯拉丁微标签（CH、读数标签、页码）可至 10px 下限；
   **同一样式类同时承载中文与拉丁时，以中文档位为准**；
2. 中文一律**不加 letter-spacing**（全大写拉丁才加）；
3. mono 数字与中文同格时：数字 500、中文 400，对齐视觉重量；
4. 任何混排规则疑问，回到「仪器铭牌」意象裁决。

**字重映射**（400/500/600 三档，全站只按下表使用）：

| 角色 | 字重 |
|---|---|
| 侧栏字标 | mono 600 |
| 页面标题 | Sans 500 |
| 大读数（28px）与次级读数 | mono 500 |
| 表头 / 区块刻度标签 / 徽标文字 | mono 500 |
| 导航当前项中文 | 500（其余 400） |
| 正文 / 次要列 / 表单说明 | 400 |

字号阶梯（信息密度取紧凑档）：

| token | 值 | 用途 |
|---|---|---|
| `--text-2xs` | 10px / 1.4 | 纯拉丁微标签下限（导航英文小字、读数标签、刻度/装饰符号，即混排纪律 1 的 10px 下限承载档）；**承载中文一律升 `--text-sm`** |
| `--text-xs` | 11px / 1.4 | 纯拉丁大写微标签（表头、徽标、注释）；**含中文一律升 `--text-sm`**（混排纪律 1） |
| `--text-sm` | 12.5px / 1.5 | 表格次要列、表单辅助（中英皆可） |
| `--text-md` | 13.5px / 1.6 | 正文、表格主列 |
| `--text-lg` | 16px / 1.5 | 页面标题、区块标题 |
| `--text-xl` | 20px / 1.3 | 大标题（M0 未使用，保留） |
| `--text-readout` | 28px / 1 | 通道卡监控大读数（tabular-nums） |

所有数字列 `font-variant-numeric: tabular-nums`（时间/耗时/资源读数对齐）。

### 2.3 间距、圆角、层级、页面度量

- 间距：`--space-1: 4px` 起，4/8/12/16/20/24/32/40/48（4 的倍数制）。
- 圆角：`--r-sm: 3px`（徽标）、`--r-md: 6px`（卡片/按钮/输入）、`--r-lg: 10px`（模态）。
- 层级：`z-nav 100 / z-dropdown 200 / z-modal 300 / z-toast 400`。
- **页面度量（本版新增，六页统一）**：`--side-width: 216px`（侧栏固定宽）、
  `--topbar-height: 56px`（顶栏高）、`--page-pad: 24px`（内容区内边距）、
  `--content-max: 1280px`（全部页面含表格页的宽度上限——超宽屏上表格行不许
  无限拉伸）、`--gap-card: 16px`（通道卡网格与双栏间距）、
  `--channel-card-width: 340px`（通道卡网格 minmax 基准，§4.4）。
- **最小支持视口 1280×720，不做响应式**；更窄窗口出横向滚动，不折叠布局。
- 深色界面阴影弱化：层级靠描边与底色阶梯；唯一「发光」保留给 running 态
  （`--glow-running`），发光即「通电」语义，不滥用；亮色主题下发光收敛为
  1px 实线描边（纸面不泛光）。

### 2.4 缓动与字距（本版新增）

```css
--ease-std:   cubic-bezier(.2,.8,.3,1);   /* 全站标准出场，一切动效默认 */
--ease-glide: cubic-bezier(.16,.84,.3,1); /* 唯一个性曲线，仅 Toast 使用 */
--ls-micro: .08em;  /* 全大写拉丁微标签：表头、徽标 */
--ls-wide:  .14em;  /* 刻度标签：区块 lab、CH 通道号、读数标签、页码、导航英文小字 */
```

全站只允许以上两条曲线加**呼吸曲线 `ease-in-out`**（CSS 关键字，仅呼吸类
动效使用，登记见 §6）、两档字距；组件内禁止出现其他缓动值 /
`transition-timing` / `letter-spacing` 值（§8 走查抽查项）。

## 3. 全局框架

```text
┌──────────┬──────────────────────────────────────────────┐
│ 侧栏 216px│ 顶栏：页标题 + mono 页码      状态灯排 ●●●     │
│          ├──────────────────────────────────────────────┤
│ g16web▌  │                                              │
│ 01 候选   │          主内容区（页面视图）                  │
│ 02 队列   │     --page-pad 24px · --content-max 1280px   │
│ 03 待执行 │                                              │
│ 04 执行中 │                                              │
│ 05 历史   │                                              │
│ 06 设置   │                                              │
│ ──────   │                                              │
│ HQ ○ 未连 │                                              │
└──────────┴──────────────────────────────────────────────┘
```

- **侧栏**（固定 216px，深 `--bg-base`，右发丝线）：
  - 字标区：`g16web` mono 600 + 磷光青 8px 方块（电源灯，服务在线时常亮、
    断线变 `--danger` 并闪烁——接 SSE 连接态）；
  - 导航项：`序号(mono faint) + 中文名 + 英文小字(mono faint 10px,
    --ls-wide)`，当前项左侧 2px 磷光青指示条 + 中文转 500 + 文字转
    `--text-primary`；
  - 底部：HQ 连接状态行（LED 点 + `HQ 已连接`/`HQ 未连接`/`HQ 未启用`）——
    M0 为静态占位，M1 收尾已真实化（hq.status 事件 + 快照 `hq` 字段驱动，
    up=accent 辉光、down=danger 闪烁、off=淡化；2026-09-25 契约增量，
    见 sse.md §2；电源灯颜色已随 SSE 连接态指示）。
- **顶栏**（56px，`--bg-raised`，下发丝线）：
  - 左：页面中文标题（`--text-lg` 16px、Sans 500）+ 旁边 mono 页码
    `02 / QUEUES`（faint、`--ls-wide`）；
  - 右：**状态灯排**——`在跑 2`（磷光青）、`排队 3`（灰蓝）、`告警 1`（琥珀，
    无告警时整枚淡化 40%）；数字 mono tabular；数据源为 SSE（M0 接 mock 流）；
    灯排右端为明暗主题切换按钮（`◐ 亮色`/`◑ 暗色`，secondary 样式小按钮）；
    **主题切换为瞬时切换、无过渡**（§6）。
- **背景纹理**：`--bg-base` 上叠记录纸网格——24px 网格线 `--grid-line` +
  96px 周期十字基准点 `--grid-dot`（两主题各给值，组件不写死 rgba）；
  克制到「几乎察觉不到，去掉后界面发空」。卡片/表格容器不透网格
  （`--bg-raised` 实底），网格只出现在留白区。
- **基础接管清单**（base.css 固定项，走查必查——不接管即廉价）：
  滚动条（10px，thumb `--border-strong`、track 透明）；`::selection`
  （accent 25% 底）；`caret-color: var(--accent)`；input autofill 底色修正；
  `color-scheme` 随主题（暗 dark / 亮 light）；全局 `:focus-visible`
  （§7 双环）。

## 4. 组件规范

### 4.1 状态徽标 StatusChip（两档响度）

任务/队列状态的唯一展示件：`● SUCCEEDED` —— mono 11px 大写、状态色文字
（承载中文措辞的徽标按混排纪律 1 升 `--text-sm` 并去字距）。
按信号响度分两档：

- **响亮档**（running / failed）：状态色 12% 底 + 3px 圆角药丸 + 左侧 6px
  实心状态点 + mono 500；running 的点 2.4s 呼吸（opacity 0.5↔1）；
- **安静档**（staged / succeeded / skipped / archived）：**无底色**，仅
  6px 状态点 + 状态色文字（直接对容器底计算对比度）。

场景规则：表格/列表内默认安静档；执行中页通道卡、停滞告警行、顶栏语义
展示用响亮档。任务六态对应 `--state-*`；队列四态复用同族变量
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

**状态矩阵**（全类一致，缺一即廉价）：

| 状态 | 规则 |
|---|---|
| hover | primary → `--accent-hover` 底；secondary → 描边转 `--text-faint`、文字转 primary；ghost → `--row-hover` 底；danger → `--danger` 10% 底 |
| pressed | primary → `--accent-dim` 底；其余描边/底色各加深一档 |
| disabled | 保形、整体 40% 不透明、`cursor:not-allowed`、无发光无呼吸 |
| focus-visible | 双环：`--border-strong` 内环 + `--accent` 外环（1px、2px 偏移），与 §7 全局环一致 |
| loading | 仅 primary：文案换「提交中 …」+ 按钮底部 1px 磷光扫描线（同表格加载线），期间禁点 |

### 4.3 数据表格

信息密度核心件：行高 40px、发丝分隔线、无斑马纹、hover 行 `--row-hover`、
粘性表头（`--bg-raised` + 底部发丝线）、表头 faint 大写（`--ls-micro`；表头
样式类承载中文，按混排纪律 1 以中文档位为准——升 `--text-sm` 并去字距）。
数字/时间/哈希/id 列一律 mono。行内动作区右对齐、ghost 按钮。

- **加载两态**（本版拆分）：首载 = `--bg-inset` 骨架行 3–5 行（220ms 一次性
  入场，不循环闪烁）；有数据的刷新 = 内容保持不动，仅表格底部 1px 磷光扫描线
  往返（1.2s，唯一 loading 动效）。
- **单元格截断**：文件名/Route 列 mono 中段 ellipsis（保扩展名）+ `title`
  提示；其余长文本列尾段 ellipsis + `title`。
- **列宽**：各列给 min-width（id 48 / 时间戳 88 / 状态徽标 96 起），动作区
  末列吃剩余宽度；表格容器受 `--content-max` 约束。

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

- 卡网格 `repeat(auto-fill, minmax(340px, 1fr))`，间距 `--gap-card`；
- 卡头：`CH <执行id 右对齐三位>` mono（`--ls-wide`）+ 状态徽标（响亮档）；
- 读数区：CPU%/MEM 用 `--text-readout` 大号 mono 500（跳变即更新，仪器语义，
  不做数字滚动动画），OPT STEP/SCF 为次级读数（16px mono）；
- **读数节流与格式**（仪器刷新率语义）：SSE 原始事件先合并缓冲，UI 以 **1Hz**
  节流刷新；CPU 整数 %，MEM 自动进位（MB→GB，整数或 1 位小数），耗时
  `3h 12m`/`8m 46s`；读数区 `aria-live="off"`（终态交给 Toast，避免读屏轰炸）；
- running 态：卡描边 `--glow-running` 微呼吸；停滞告警时卡头追加琥珀灯行；
- SSE 事件 `execution.monitor` / `execution.progress` / `execution.stalled`
  直接驱动对应字段（M0 接 mock 流演示）；
- **断连与恢复态**（M1 收尾补记，2026-09-25）：SSE 非 open（连接中断/
  重连退避）时读数区整体降档至 45% 不透明度并在窗口元信息行显示
  「连接中断 · 读数延迟」琥珀注记——陈值明确标记、不误读为实时，重连
  open 后即恢复；快照重建为差量合并（存活卡保留既有读数、仅移除快照外
  僵尸卡），重建瞬间无读数闪烁；进度状态随快照恢复（sse.md §2），无须
  等待日志下一行。

### 4.5 席位行 SeatRow（待执行页核心件）

- 纵向列表，顺序即执行序列；每席位一横条（高 48px，队列席位可展开）：
  左端 `S<seat_id>` mono + 类型标签（`TASK`/`QUEUE` 11px 徽标式），中部
  任务文件名或队列名+成员概览，右端状态/动作；
- **并行窗口边界可视化**：被窗口触及的席位整条加左侧 2px 磷光条 + `在途`
  标记，其后席位为等待区——用户一眼看出「执行序列推进到哪」（`WINDOW`
  一词保留给「执行中」页的并行槽位读数语义，本页不复用）；
- 容量仪表在页首：`OCCUPIED 2/3` 分段 LED 条（3 段，占用段磷光青）。

### 4.6 模态 / Toast / 空态 / 表单

- **模态**（确认框）：`--bg-overlay` + backdrop `rgba(12,17,22,0.75)`
  **纯压暗、无模糊**（§1 反方向：不做玻璃拟态，含 backdrop blur）+
  `--r-lg`、`--shadow-pop`，标题 mono 500；危险确认的确认按钮用 danger 类
  （停止/删除的二次确认都在这里，不在页面内联）。
- **Toast（任务结束通知）**：右上角从屏幕右缘滑入（240ms `--ease-glide`，
  translateX 28px），落点在顶栏下方（top 68px，不遮挡状态灯排）；5s 自消，
  可手动关闭，多条纵向堆叠；`--bg-overlay` 底 + 左侧 3px 状态色条 +
  `--shadow-pop` 投影；`role="status"` + `aria-live="polite"`。
  **触发规则**：任务到达终态即通知（SSE `history.appended` 事件驱动），
  **skipped 不通知**——它只在队列语境下有意义，由队列状态事件与页面内
  徽标表达；名称取「直接提交任务的 title / 队列成员所属队列名」，超 15 字符
  截断加 `…`；文案 `名称: 状态`（如 `water opt: succeeded`），状态词着
  succeeded 绿 / failed 红，色条同色。
- **空态**：居中发丝线方框（48px）内一个极简刻度符号 + mono 短句
  （如 `暂无候选任务 · 导入 .gjf 文件后显示于此`）。不用插画。六页空态文案
  一律「状态 + 下一步动作」双段式。
- **表单控件**：输入框 `--bg-inset` 底 + `--border-hair` 描边，焦点转双环
  （§4.2 同款：内 `--border-strong` + 外 `--accent`）；disabled 保形 40% 不
  透明；label 12.5px + 辅助说明 12.5px faint（原 11px 与混排纪律 1 冲突，
  随 K1 口径统一升至 `--text-sm`；整句提示文字用 secondary）；
  select/checkbox/toggle 规格随 M2 补充（§9，2026-09-25 二审移项），沿用输入框同款描边体系；设置项生效
  语义用**中性**微型徽标（`即时`/`即时且追溯`/`新任务生效`/`重启生效`，plain
  档，对应 m0-plan §2.2 `effect` 四值枚举）。

## 5. 六页布局与 UX 细则（M0 空壳渲染范围）

样板 HTML 覆盖全部六页视图与组件墙；页面归并为四种原型（表格型/席位型/
通道卡型/表单型），同原型页面共享布局骨架。**全部页面统一 `--page-pad`
24px 内边距与 `--content-max` 1280px 宽度上限（§2.3）。**

| 页面 | 原型 | 布局要点 | M0 空壳渲染 |
|---|---|---|---|
| 01 候选任务 | 表格型（双栏） | 左列自适应（1fr）列表（id/文件名/title/来源徽标——失败退回附琥珀归因注记 `failure_note`），右侧 380px 粘性预览卡，`--gap-card` 间距：TITLE/LINK0/ROUTE/CHARGE·MULT/MOLECULE 读数/**ADDITIONAL SECTIONS**（附加输入节有序列表，无则空态；m0-plan §2.2）分块 mono 展示 + 原子数与分子式（Hill 记法元素统计，如 `H2O1`/`C6H6O1`，计数 1 显式）读数；Link0 缺失项琥珀注记（M1 提交警告的伏笔） | 全字段 + 预览卡切换 |
| 02 队列 | 表格型 | 队列列表（id mono/名称/成员数徽标/状态/回退标记 `已回退 ×2` 琥珀安静档）；行可展开成员概览（任务 id/文件名/分子式/状态徽标）与失败归因 | 列表 + 展开态 |
| 03 待执行 | 席位型 | §4.5；席位展开队列成员子表 | 容量仪表 + 席位 + 窗口边界 |
| 04 执行中 | 通道卡型 | §4.4 通道卡网格；无在跑时显示空态 + `WINDOW n` 读数 | mock SSE 驱动读数跳变 |
| 05 历史 | 表格型 | 全宽表格（id/任务/状态徽标/归因/提交→结束/耗时/资源/队列归属，受 `--content-max` 约束）；顶部仅状态筛选——**归档条目不列于此**（归档页为 M1 增设的独立路由，roadmap §2.1「归档为独立页面」、m0-plan 决策点 10）；行点击 → 详情抽屉：全字段（含 `input_hash`/`monitor_summary`/`chk_snapshot`/`result_ref`）+ 动作（输入查看、输出预览/导出、归档、failed/skipped 重新排队/退回候选——M1 语义 M0 mock） | 表格 + 徽标全态 + 详情抽屉 |
| 06 设置 | 表单型 | 限宽 880px：启动级只读区（锁定图标 + 值 mono）在上，运行级分组表单在下，每项带中性生效语义徽标；保存按钮 + `重启生效` 项的琥珀提示条 | 分组 + 可交互控件（写 mock） |

信息架构纪律（roadmap §1 原则 7）：视觉设计不为任何页面增加新信息层级；
六页的信息结构 = m0-plan.md §2.5 映射表所列界面元素，一个不多、一个不少。

## 6. 动效规范（CSS-only，克制；缓动一律 §2.4 token）

| 动效 | 规格 | 语义 |
|---|---|---|
| 视图切换 | 内容区 opacity 0→1 + translateY(6px→0)，160ms `--ease-std` | 导航反馈 |
| 列表入场 | 行/卡 stagger：每行 delay 18ms（>8 行截断统一入场），220ms `--ease-std` | 一次编排好的加载（全站仅此一处 stagger） |
| running 呼吸 | 状态点 opacity 0.65↔1（`breathe`）；通道卡发光 box-shadow 收敛↔泛光（`cardpulse`），均 2.4s ease-in-out | 「通电中」 |
| 停滞告警呼吸 | 停滞琥珀灯点 opacity 1↔0.4，1.6s ease-in-out（`stallbreathe`，仅告警中） | 停滞提示（只提示不终止） |
| 断线闪烁 | 侧栏电源灯 opacity 1↔0.3，1.2s ease-in-out（`pulse`，仅断线态） | 服务失联 |
| 加载扫描线 | 表格/按钮底部 1px 磷光线往返 1.2s | 数据在途 |
| hover | 行/按钮 120ms `--ease-std` | 命中反馈 |
| 行展开/收起 | `grid-template-rows 0fr↔1fr`，160ms `--ease-std`；展开图标随状态旋转 90° | 揭示成员/归因 |
| 详情抽屉 | 右侧滑入 translateX(100%→0) 200ms `--ease-std` + 内容 16px 位移 | 深入上下文 |
| Toast | translateX 28px，240ms `--ease-glide`（全站唯一使用该曲线） | 事件到达 |
| 主题切换 | **无过渡、瞬时切换** | 纸/墨切换不演戏（大面积颜色渐变扫过=廉价） |

硬规则：`@media (prefers-reduced-motion: reduce)` 下全部动效关闭；数字读数
永不滚动/闪烁（跳变）；无任何全屏位移、弹跳、渐变扫光、背景模糊。

## 7. 可访问性与可用性底线

- 对比度：§2.1 核算表所列组合 ≥ 4.5:1（由 `scripts/check_contrast.py` 闸门
  实测保证并回填该表，作为回归基准；`--text-faint` 仅用于 ≤11px 短标签，整句
  提示文字一律 `--text-secondary`）。
- 键盘：全部交互可 Tab 触达、焦点可见（双环：`--border-strong` 内环 +
  `--accent` 外环，1px 线、2px 偏移）；模态内焦点圈定、Esc 关闭。
- 语义：状态不只靠颜色——徽标自带文字（`● FAILED`），色弱可用；Toast
  `role="status"`，读数区 `aria-live="off"`。
- 中文文案：动词开头、句尾不加句号；数字与单位间加空格（`3h 12m`、`512 MB`）。

## 8. M0 落地与验收

1. C1 建立 `src/styles/tokens.css`（§2 全量，含明暗双主题变量组与缓动/字距
   token）+ `base.css`（reset/框架/背景纹理/主题切换/基础接管清单 §3）；
   **字体自托管随构建打包（§2.2 @fontsource），运行期零外链**；
2. C3/C4 六页组件严格引用 tokens，禁止组件内硬编码色值/字号/字距/缓动
   （走查抽查）；
3. 验收（并入 m0-plan.md §8）：
   - 六页按本规范渲染 mock 数据，与样板并排走查，视觉一致性人工确认；
   - **样板 `:root` 与 `tokens.css` 逐变量 diff 为空**（提供
     `scripts/check-tokens.py` 或构建期由 tokens.css 注入样板变量块——本项
     为机械检查，人工目检不替代）；
   - **对比度实测值回填 §2.1 核算表**，全部组合 ≥ 4.5:1；
   - 基础接管清单走查（滚动条/选区/caret/autofill/color-scheme/focus-visible）；
   - `prefers-reduced-motion` 下动效为零。

## 9. 演进预留（不在 M0 实施）

- M1：真实 SSE 接入后，状态灯排/通道卡读数（1Hz 节流）/席位窗口边界由事件流
  驱动（数据接口已按 m0-plan.md §3 对齐）。
- M2：select/checkbox/toggle 规格——M1
  未实施，2026-09-25 二审经文档 diff 自 M1 行移入（与 m1-acceptance.md §1.3
  存案一致）；编辑态样式（输入框/校验错误 `--danger` 描边 + 11px 错误注记、拼写检查
  非阻断警告琥珀注记 `--warn`——m0-plan 决策点 11）、
  拖拽排序的位移动效（120ms、无弹性）。（HQ 断线态已不在 M2：侧栏状态行
  于 M1 收尾随 hq.status 契约增量真实化，2026-09-25。）
- M3：结果分析视图（能量曲线/谱图）沿用 tokens——图表轴线 `--border-hair`、
  主曲线 `--viz-1`（accent 同源）、多序列用 `--viz-2…5`（§2.1 已预留，亮色组
  届时补）、收敛点 `--state-succeeded`；3Dmol.js 画布区配 `--bg-inset`
  底与工具条，暗色适配天然成立。
