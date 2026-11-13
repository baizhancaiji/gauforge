# 队列编辑拖拽排序变高行错位修复与警告徽标化 · 实施计划（目标 3.6.0）

> 状态：**已实施并验收（2026-11-14，版本随 unreleased 与 link1-multistep-plan 并窗冻结，
> 默认 3.6.0）**
> 验收留痕：六提交（a1e84774 计划落盘 / a903bbdd 方案A 交换后布局 / 2e8e5527 方案B 落定重测 /
> e34bc940 T3a 存在性前置 / 8087874c T3b 徽标折叠 / 本进度同步提交）；六闸门全过
> （vue-tsc+vite build / audit_frontend_offline / check_tokens / check_contrast /
> gen_changelog_md --check / validate_progress）+ 全量 pytest 893 passed。
> 浏览器实测绿集合（复跑口径：隔离实例 127.0.0.1:8399、G16WEB_HOME=/tmp/g16web-diag、
> G16WEB_ENGINE=0、本批 dist 构建产物、playwright-core 直连 chromium headless 真实指针
> 事件，脚本与截图 /tmp/diag-drag/36-*.png；候选构造同 §1.2——warn_opt 含
> `int=ultrafine` 拼写警告、clean_td 无警告、dead_input 删 inputs 文件构造 preview 404）：
>
> | 判据 | 实测 | 红集合对照 |
> |---|---|---|
> | 2 短行上拖·拖拽中 | 槽位对齐点（dragY=0）：被拖短行 [0,34]，让位长行 top=34，间隙 **0.0px** ≤ 行距0+1px | 红集合长行让位 y=83 留空 42px |
> | 3 短行上拖·落定后 | 行序 [短,长] 间隙 **0px** | 红 49px → 归零 |
> | 4 长行上拖·拖拽中/落定后 | 被拖长行 [0,82.8]、让位短行 [83,117]，重叠 **0**（0.2px 间隙），警告块 [33,77.8] 零遮挡；落定稳定后维持，**无需点击自愈** | 红 34px 重叠 + 警告块被盖 28px → 归零 |
> | 5 短行下拖 | 槽位对齐点（dragY=83=交换后槽1前缀）：重叠 **-0.2px**（亚像素间隙），落定全程零重叠 | 红：落定目标落进让位高行盒 |
> | 6 待执行页席位拖拽 | 展开席位（h=166.2）拖至槽0：让位席位 top=174（前缀 166.2+行距8），重叠 **0**（间隙 7.8px≈行距8）；落定 300ms 即时正确（T2 重测兜底，不依赖 SSE），SSE 到达后同值 | 红 58px 重叠 + 需等 SSE 自愈 → 归零 |
> | 1 等高行回归 | 成员子表拖拽：让位行 top=38=34+行距4，间隙=行距 **4.0px**，落定紧贴；交换后前缀与 offsetAt 逐位相等（数学等价） | 现状一致 |
> | 7 控制台 | 三拖拽脚本 pageerror/console.error **0** | — |
> | 8 锁定席位拒绝路径 | 合成 running 执行锁定席位0（executions 插行）：跨锁定席位拖拽被 enabledAt 门控前置重定向（nearestDroppable 跳过锁定槽）→ 无提交、行弹回原位、弹回后间隙 8/7.6px 零滞留；合法重排放行且锁定席位保持原下标。「重排越界 — 锁定席位必须保持原位」文案为 SSE 竞态防御路径，纯指针交互不可达（门控先行生效），真实引擎在途任务走查留待引擎实例 | §2.1 commit 拒绝边界实测 |
> | 9 徽标 | 默认收起（展开区 0 元素）单行 h=34；点徽标展开 h=34→82.8、下方条目挤开 49px≈警告块高、aria-expanded=true；再点收起紧贴恢复、aria 全 false；`⚠ ?` 分支（preview 404）展开显占位「成员输入预览不可用 — 无法核验」；memberOnly（submitted）弹窗徽标显隐与编辑态同口径（口径一致、取数被既有 _readable_row 形态守卫 404 → ⚠ ? 如实呈现，非本批回归）；直接提交 done 后徽标消失、提交回执区（q-warns）不动 | — |
> | 10 行精简 | `.m-title` 元素数 0（创建/编辑/memberOnly/只读四态一致），仅文件名；徽标最小宽（视口 608）badge 右缘 507 ≤ modal 右缘 584 不裁切 | — |
> | 11 只读态 | sqlite 置 completed 后只读弹窗徽标 0、占位 0（T3a 真 DOM 验证）；foot 仅「取消」 | — |
>
> 跟手期瞬态说明（非缺陷、现状同类）：指针中途位置（dragY≠槽位 y）被拖行与让位行存在
> 随指针逼近槽位而收窄的瞬态重叠（如 7px→0），与等高行拖拽跟手残留同类；短行下拖越过
> 更高行时指针带内存在 overIndex 随交换/恒等分带交替翻转的跟手抖动（落定与最终几何不
> 受影响），属交换分带×夹取交互的已知瞬态，本批次按 §5 边界不扩展夹取模型，后续如需
> 治理另立批次。
> 排期口径：单人实施，任务粒度=一个可审查提交；规模标记 S（≤半天）/ M（约一天）。
> 行号锚点为计划落盘时点（HEAD=5df5e779）实际行号，实施会使其漂移，**以符号名为准**。
> 执行纪律：文档一提交 → 实现四提交（组合式两缺陷分提、只读占位修正一提交、UX 一提交）→ 实测验收留痕 →
> 进度同步，共六提交；每提交单类变更（AGENTS §5.1）。
> 缺陷定性说明：本缺陷无 pytest 可达 seam（纯浏览器指针事件+布局行为，前端无 JS
> 测试基建），红/绿证据以浏览器实测脚本数值留痕替代「测试先行红入库」——红集合
> 已于 2026-11-13 诊断时捕获（§1.2），实施后同口径复跑为绿集合（§4 判据 2–7）。

## 1. 缺陷分析与实测证据

### 1.1 现象（2026-11-13 报障，3.5.0）

队列编辑弹窗（新建/编辑共用）成员列表拖动排序三症状：

1. 长行（含核验警告）上拖落定后，短行盖住警告文本（报障图一）；
2. 短行上拖落定后，两行间出现大空隙（报障图二）；
3. 点击任一行后二者突然紧贴恢复。

### 1.2 实测复现（2026-11-13，隔离实例全数值）

环境口径：隔离实例 `127.0.0.1:8399`、`G16WEB_HOME=/tmp/g16web-diag`、
`G16WEB_ENGINE=0`、`web/frontend/dist`（HEAD 构建产物）、playwright-core 直连
chromium headless 驱动真实指针事件。候选构造：导入含 `int=ultrafine` 关键字的
候选产生 L 行拼写警告（长行 h=82.8）与无警告候选（短行 h=34）各一。三场景的
成队初始行序与操作（行序指画布自上而下的槽位序；队列画布无 grid gap、行距
0，席位画布行距 = --space-2 = 8px）：

- 队列编辑·短行上拖：成队 [长行(0), 短行(1)]，短行自槽位 1 上拖至槽位 0；
- 队列编辑·长行上拖：续用上一场景落定后的队列（首次提交重排后行序已是
  [短行(0), 长行(1)]），长行自槽位 1 上拖至槽位 0；
- 待执行页席位：成队 [席位1 收起 h=58(0), 席位2 队列席位子表展开
  h=166.2(1)]，席位2 自槽位 1 上拖至槽位 0。

行盒几何（相对画布顶，px）：

| 阶段 | 实测 | 判定 |
|---|---|---|
| 短行上拖·拖拽中 | 长行让位至 y=83，被拖行只占 [7,41]，中间空 42px | 让位数学错（根因①） |
| 短行上拖·落定后 | 行间间隙 **49px**（应 ≤ 行距+1px） | 症状②坐实 |
| 长行上拖·拖拽中 | 短行让位至 [34,68]，整体没入长行行盒 [2,84.8]（重叠 34px，其中警告块 [40,84.8] 被盖 28px） | 症状①坐实 |
| 长行上拖·落定后 | 短行行盒与长行行盒重叠 **34px 滞留不消失** | 症状①滞留（根因②） |
| 点击任一行 | 行高重测，间隙 0.2px 自愈 | 症状③坐实 |
| 待执行页席位拖拽中（席位2 子表展开 h=166.2 vs 席位1 收起 h=58） | 席位1 让位至 y=66（旧前缀 58+行距 8），整体没入席位2 行盒 → **重叠 58px**；落定后经 SSE→watch→measure 自愈 | 同缺陷另一消费方 |

复现脚本与截图在 `/tmp/diag-drag/`（drag_repro.cjs / seat_repro.cjs 及 *.png，
**临时产物不入库**；若已失可按本节环境口径与三场景构造重建），驱动
pointerdown/move/up 拖拽，逐阶段量测 `.q-mem`/`.q-mem-warns`/`.seat` 盒几何。

### 1.3 根因

**① 让位数学用「拖前」前缀和（组合式缺陷，拖拽中即错）** —
`web/frontend/src/composables/usePointerSort.ts:109-117` `offsetFor`：被让位行
落到 `offsetAt(i±1)`，即拖拽**前**顺序的前缀和。变高行交换后，「下一槽位」的 y
应按**交换后**高度序列（被拖行高度参与前缀）计算。同文件 `slotAt`（L131-139）
落点分带、`maxDragY`（L173-176）夹取、`onUp` 落定目标（L255 `dragY =
offsetAt(to)`）共四处同源——**拖拽期一切 y 定位都建立在等高假设上**。等高行时
前缀和退化为等差数列故历史正确；A-12 变高行扩展（2026-10-02）只前缀和化了静止
布局，拖拽期几何没跟上。三类错位的机理：

- 矮行上拖 → 高行让位到旧前缀位置 → 下方留空隙（差≈两行高差）；
- 高行上拖 → 矮行让位到旧前缀位置 → 钻进高行警告区被盖；
- 矮行**下**拖 → 落定目标 `offsetAt(to)` 落进让位高行盒内 → 归位动画期间重叠
  （现状即有，本次一并修）。

**② 提交重排后不重测（宿主策略缺口，滞留点）** —
`web/frontend/src/components/QueueEditorModal.vue:392-397` 只 watch
`members.value.length`；`commit` 的 splice 换序不改长度 → `rowHeights`（按位置
索引）与新 DOM 顺序倒置 → 错误几何无限期滞留，直到下次 `onDown` 的
`measure()`（`usePointerSort.ts:213`）自愈——症状③的由来。

**暴露窗口**：3.4.0 B9 G13 裁决⑤给成员行加内联常显警告区
（`QueueEditorModal.vue:640-650`），拖拽行首次变高，①②同时显形（2026-11-13
3.5.0 期报障）。属 3.4.0 引入缺陷的修复。

**消费方风险面**（同一组合式全部消费方）：

| 消费方 | 缺陷①拖拽中 | 缺陷②滞留 | 依据 |
|---|---|---|---|
| QueueEditorModal | 触发 | 触发（无限期） | §1.2 实测 |
| PendingView（席位） | 触发（重叠 58px 实测） | 不滞留：`commit→PUT→applySnapshot→watch(seats)→measure`（views/PendingView.vue:135） | §1.2 实测 |
| PendingSeatMembers（成员子表） | 不触发（单行 nowrap 等高掩盖） | 不滞留（watch(members)，components/PendingSeatMembers.vue:107） | 代码核实 |

### 1.4 关联缺陷（T3a 独立提交修正）

`QueueEditorModal.vue:641` 占位分支条件
`!done && linksReady && !linkState(i)?.available`：只读态 `loadLinkStates`
提前返回（L155-158）置 `linksReady=true` 而 `linkStates` 为空 Map →
`linkState(i)` 为 undefined → 条件恒真 → 只读弹窗每行渲染「成员输入预览不可用
— 无法核验」，违背 L150「只读/已提交完成态不预显」注释意图。修正（T3a）：
补 `linkState(i)` 存在性前置（预览取数只发生 create/edit/memberOnly）。

## 2. 修复方案

### 2.1 方案 A（根治①）：拖拽期几何改为「交换后布局」

**模型**：拖拽中的可见排布 = 高度序列把 `rowHeights[from]` 移除后插入 `to`。
让位、落点分带、夹取、落定目标全部按该交换后序列的前缀和计算。等高行时交换后
前缀与 `offsetAt` 逐位相等（等差数列），**既有行为零变化**——这是回归安全证明。

**新增（usePointerSort.ts）**：

```ts
/** 拖拽期交换后布局：rowHeights 移除 from 插入 to 的高度序列与前缀和
 *  （swapPrefix[s] = 交换后槽位 s 的 y）。等高行退化为 offsetAt 同值。 */
let swapHeights: number[] = [];
let swapPrefix: number[] = [0];

function rebuildSwapLayout(): void {
  const from = dragIndex.value;
  const to = overIndex.value;
  const hs = [...rowHeights.value];
  if (from >= 0 && to >= 0 && from !== to) {
    const [moved] = hs.splice(from, 1);
    if (moved != null) hs.splice(to, 0, moved);
  }
  swapHeights = hs;
  const prefix: number[] = [0];
  for (let j = 0; j < hs.length; j++) prefix.push(prefix[j]! + hs[j]! + gapPx.value);
  swapPrefix = prefix;
}

/** 交换后布局中槽位 s 的 y；未拖拽/量测未就绪回退 offsetAt */
function swapPrefixAt(slot: number): number {
  if (dragIndex.value === -1 || swapHeights.length !== opts.count()) return offsetAt(slot);
  return swapPrefix[slot] ?? offsetAt(slot);
}
```

**八处接线**（含 2.2 的 B，均在同一文件）：

| # | 位置（符号） | 现状 | 改为 |
|---|---|---|---|
| 1 | `onDown`（L219 `overIndex` 初值后） | — | `rebuildSwapLayout()` |
| 2 | `followPointer`（L186-187 overIndex 变更处） | 仅赋值 | 变更后 `rebuildSwapLayout()` |
| 3 | `offsetFor`（L114） | `offsetAt(i - 1)` | `swapPrefixAt(i - 1)`（from<to 让位链） |
| 4 | `offsetFor`（L115） | `offsetAt(i + 1)` | `swapPrefixAt(i + 1)`（from>to 让位链） |
| 5 | `slotAt`（L133-137） | `offsetAt(i)`/`rowHeights[i]` 分带 | `swapPrefixAt(i)`/`swapHeights[i]` 分带（落点与视觉一致） |
| 6 | `maxDragY`（L175） | `offsetAt(n-1)` | `swapPrefixAt(n-1)` |
| 7 | `onUp`（L255 落定目标） | `dragY = offsetAt(to)` | `dragY = swapPrefixAt(to)`（修下拖落定重叠） |
| 8 | `onUp` settle（L257-264，方案 B） | commit 后无重测 | 见 §2.2 |

**时序与边界**：`rebuildSwapLayout` 仅在拖拽中调用（onDown/followPointer），
O(n)、n≤10 无性能问题；`reset()` 无需清理（dragIndex=-1 时 `swapPrefixAt` 回退
`offsetAt`，残留缓存不被读取）；`commit` 被宿主拒绝（如 PendingView 越界拒）
时 DOM 未变，dragIndex=-1 后各行按 `offsetAt` 弹回原位，量测仍与旧序一致，无需
处理；`enabledAt` 门控的 `nearestDroppable` 只改槽位下标，交换模型对门控透明；
maxDragY 改按交换后末槽前缀夹取，被拖行高于末槽常驻行且自身不在末槽时仍可能
小幅溢出画布下缘——与现状同类弱点、非回归，本批次不扩展夹取模型。

**数值验证**（对 §1.2 场景手推，gapPx 按 0 简化，非零时各前缀逐项累加 gap、
结论不变）：h=[83,34] 拖 34 上行（from=1→to=0）：
swapHeights=[34,83]、swapPrefix=[0,34,117] → 让位行（i=0）落
swapPrefixAt(1)=34，紧贴被拖行（h=34）下方；h=[34,83] 拖 83 上行：
swapPrefix=[0,83,117] → 短行让位至 83，警告块零重叠。

### 2.2 方案 B（根治②）：落定提交后自动重测

`onUp` 的 settle 定时器回调内，commit 后等渲染落 DOM 再重测：

```ts
settleTimer = window.setTimeout(() => {
  if (from !== to) opts.commit(from, to);
  dragIndex.value = -1;
  overIndex.value = -1;
  isDropping.value = false;
  dragY.value = 0;
  dragEl = null;
  if (from !== to) void nextTick().then(() => measure()); // 交换后行高重测
}, dragDurationMs());
```

要点：**收进组合式而非各宿主 watch**（最短路径，三消费方同时受益）；`measure()`
在 canvas 卸载时早退（L88-89 既有）天然防关闭竞态；flags 先复位再重测，期间新
pointerdown 走 `onDown` 自带 `measure()`，幂等无竞态；PendingView /
PendingSeatMembers 既有 watch 重测与本次重测同值双跑，无害。

### 2.3 方案 C（用户期望 UX）：警告默认收起、徽标点击展开、行只显文件名

用户验收口径（2026-11-13 报障原文）：警告折叠为样式徽标显式警告及数目；点击
徽标才从条目下方展开警告内容，自动挤开下面的条目；再次点击收起，下方条目自动
紧贴；默认不展开；成员行只显示文件名，不显示 title。

**状态**（QueueEditorModal.vue script setup）：

```ts
import { reactive, ... } from "vue"; // reactive 增补进既有 import
/** 成员警告展开态（按任务 id，重排随行携带；默认收起，点徽标展开） */
const warnsOpen = reactive<Record<number, boolean>>({});
const memberWarnCount = (i: number) => linkState(i)?.warnings?.length ?? 0;
/** 展开/收起后行高变化：nextTick 落 DOM 后重测前缀和（PendingView
 *  watch(expanded) 同款——展开把下方条目挤开/收起紧贴由行 transform 过渡
 *  自动补间，零新增动画代码） */
async function toggleWarns(id: number) {
  warnsOpen[id] = !warnsOpen[id];
  await nextTick();
  sort.measure();
}
```

`watch(open)` 打开时清空 `warnsOpen`（逐 key delete）；`removeAt` 内
`delete warnsOpen[m.id]`。

**模板**（`.q-mem-main` 内，`.m-file` 之后、`.m-link` 之前；`.m-title` 整行删除）：

```html
<!-- 警告徽标（默认收起，点击行下展开清单再点收起；预览不可用显 ⚠ ?） -->
<button
  v-if="!done && linksReady && linkState(i) && (memberWarnCount(i) > 0 || !linkState(i)?.available)"
  class="warn-badge mono"
  type="button"
  :aria-expanded="warnsOpen[m.id] ? 'true' : 'false'"
  :aria-label="linkState(i)?.available
    ? `${m.filename} 有 ${memberWarnCount(i)} 条核验警告`
    : `${m.filename} 输入预览不可用`"
  :title="linkState(i)?.available ? '点击展开/收起核验警告' : '成员输入预览不可用（解析失败或形态锁定）'"
  @pointerdown.stop
  @click.stop="toggleWarns(m.id)"
>⚠ {{ linkState(i)?.available ? memberWarnCount(i) : "?" }}</button>
```

（v-if 已保证 `linkState(i)` 存在，`?.` 为模板表达式口径一致化，运行期安全。）

原两分支警告区（L640-650）改为以 `warnsOpen[m.id]` 为总闸的 v-if/v-else-if 链
（占位分支 `linkState(i)` 存在性前置承接 T3a，重写后保留）：

```html
<div
  v-if="warnsOpen[m.id] && !done && linksReady && linkState(i) && !linkState(i).available"
  class="q-mem-warns q-mem-warns--empty mono"
>成员输入预览不可用 — 无法核验</div>
<div v-else-if="warnsOpen[m.id] && !done && linkState(i)?.warnings?.length" class="q-mem-warns" role="status">
  …（清单条目原样）
</div>
```

展开容器与清单样式（`.q-mem-warns` 琥珀、限高滚动）原样保留。

**CSS**：删 `.m-title` 块（L869-876），`.m-file` 保持 `flex: 1 1 auto;
min-width: 0` 独占余宽；徽标新块（口径与候选页 `CandidatesView.vue:1021-1029`
`.warn-badge` 逐令牌一致，button 形态补重置）：

```css
.warn-badge {
  display: inline-block;
  font-size: var(--text-xs);
  color: var(--warn);
  background: none;
  border: 1px solid color-mix(in srgb, var(--warn) 45%, transparent);
  border-radius: var(--r-md);
  padding: 0 var(--space-1);
  white-space: nowrap;
  cursor: pointer;
  flex: none;
}
```

**交互边界核查**：徽标是 `<button>`，`onDown` 的 `closest("button")` 门
（usePointerSort.ts:212）+ `@pointerdown.stop` 双保险，拖拽不劫持、拖拽中不可点
（指针被捕获）；只读态 `linkState(i)` 恒 undefined → 徽标与占位均不渲染
（§1.4 已由 T3a 修正并在此保留）；done 后 `linkStates` 重拉清空 → 徽标消失，提交回执区（`q-warns`）
不动；展开态拖拽属变高场景，由 A/B 兜底；settle 窗口（松手归位至提交间）点
徽标展开/收起仅使 rowHeights 与交换布局短暂过期，由落定提交后的自动重测
（§2.2）兜底自愈，无需拦截；`MemberRow.title` 字段保留不渲染
（CandidatesView 传参不动，接口零改动）。

注释同步（随 T3b）：文件头布局说明的成员列表构成句去 title 表述；
`LinkState.warnings` 字段注释与警告区模板注释的「常显预显」语义随徽标折叠
更新（B9 G13 裁决⑤呈现形态变更、取数路径不变），保持注释与实现一致。

## 3. 任务分解与提交序列

| 阶段 | 内容 | 提交 | 规模 |
|---|---|---|---|
| T0 | 落盘本计划 | `docs(plans): 落盘队列编辑拖拽排序错位修复实施计划` | S |
| T1 | 方案 A 八处接线（§2.1 表 1–7 项） | `fix(frontend): 重构拖拽排序为交换后布局定位修复变高行错位` | M |
| T2 | 方案 B settle 后重测（§2.1 表第 8 项） | `fix(frontend): 补齐拖拽落定提交后行高重测消除错位滞留` | S |
| T3a | 只读占位恒显修正：占位分支补 `linkState(i)` 存在性前置（§1.4） | `fix(frontend): 补队列成员警告占位分支存在性前置修正只读态恒显` | S |
| T3b | 方案 C 徽标折叠 + 行精简 + 注释同步（§2.3，占位分支存在性前置承接 T3a） | `feat(frontend): 改队列成员警告为徽标折叠显隐并精简行文案` | M |
| T4 | 实测验收：`npm run build`（vue-tsc）→ `audit_frontend_offline.sh` / `check_tokens.py` / `check_contrast.py` → 复现脚本绿集合复跑（§4 判据 2–7 数值归零）→ 手动走查矩阵（§4 判据 1、8–11），`uv run pytest` 与 `validate_progress.py` 照跑，记录留痕（绿集合逐条数值与复跑口径） | （无独立提交，证据随 T5 落本计划状态行回填文本；/tmp 复现脚本为工具不入库） | M |
| T5 | CHANGELOG.jsonl unreleased 追加（T3a fixed 与 T3b added 分条）+ `CHANGELOG.md` 经 `scripts/gen_changelog_md.py` 再生成并通过 `--check` + progress.json 同步 + 本计划状态行回填「已实施并验收」注明留痕位置（§4 绿集合数值与复跑口径） | `chore(progress): 同步队列编辑拖拽修复批次进度` | S |

**版本窗口**：T1/T2/T3a 为 fix、T3b 含交互变更 → 按 changelog-spec §1.7 冻结
时判 minor，目标 3.6.0（与 link1-multistep-plan 并窗冻结，以届时 unreleased
实际并窗情况为准，版本号统一定）；若需缺陷修复先行，可拆窗 3.5.1（仅
T1/T2/T3a），T3b 留 3.6.0——待用户裁决，默认并窗。

## 4. 验收判据（复现脚本=/tmp/diag-drag/drag_repro.cjs、seat_repro.cjs，绿集合逐条数值）

1. 等高行回归：PendingSeatMembers 拖拽行为与现状一致（交换后前缀与 offsetAt
   逐位相等，数学等价）；无警告等高成员队列拖拽回归走查并入 T4 手动走查矩阵；
2. 短行上拖·拖拽中：高行让位紧贴被拖行下方，间隙 ≤ 行距+1px；
3. 短行上拖·落定后：间隙 ≤ 行距+1px（红集合 49px → 归零）；
4. 长行上拖·拖拽中与落定后：短行行盒与长行行盒重叠 = 0px（红集合 34px → 归零，
   警告块零遮挡），无需点击自愈；
5. 短行**下**拖：落定动画全程行盒零重叠（落定目标修正）；
6. 待执行页：席位展开后拖拽中重叠 = 0px（红集合 58px → 归零），落定后即时正确；
7. 控制台零错误、零新增告警；
8. 待执行页锁定席位拒绝路径：跨锁定席位拖拽被本地校验拒绝时提示「重排越界 —
   锁定席位必须保持原位」，行弹回原位无错位滞留（§2.1 commit 拒绝边界与 §2.2
   重测幂等的实测项；锁定席位须真实在途任务产生，G16WEB_ENGINE=0 的隔离实例
   无锁定席位，该项在开启引擎的实例走查）；
9. 徽标：默认收起行高单行；点击展开下方条目被挤开（200ms 补间）、再点收起紧贴；
   `aria-expanded` 随动；`⚠ ?` 分支展开显占位文案；已提交（memberOnly）弹窗
   徽标显隐与编辑态同口径（预览取数覆盖该态）；
10. 队列编辑弹窗成员行不再渲染 title 文案，仅文件名（长名省略号随弹窗拖宽
    伸缩，§2.5 既有行为不回归）；最坏「⚠ 99」徽标在弹窗最小宽不裁切；
11. 只读态队列弹窗零徽标零占位（T3a 修正验证）；闸门六项
    （build/audit/tokens/contrast/pytest/gen_changelog_md --check）+
    validate_progress 全过。

## 5. 明确不做（边界）

- 不动 `MemberRow` 接口与 CandidatesView 传参（仅去渲染）；
- 不动 PendingView / PendingSeatMembers 模板与量测策略（组合式修复自动受益，
  避免三处重复修补）；
- 不引入 JS 单测基建、不改 `measure()` 的 offsetHeight 整数口径（≤1px 亚像素
  漂移维持现状）；
- 不改只读/完成态警告通道设计（提交回执区 `q-warns` 原样）；
- 不新增设计令牌（徽标逐令牌复用既有组合，过 check_tokens/check_contrast 无新面）；
- 不做「展开时禁拖」之类的保守拦截（A/B 后几何已正确，拦截属多余状态）。
