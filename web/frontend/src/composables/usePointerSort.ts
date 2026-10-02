/**
 * usePointerSort — 指针事件驱动的行拖拽排序（画布式；§4.6 拖拽排序，
 * 2026-09-27 人为指定动效重做，参照指针跟手参考实现；A-12 扩展变高行）。
 *
 * 动效：拿起项 transform 跟手（跟手阶段关过渡），其余项跨槽位边界带迟滞
 * 地让位/归位（transform 补间走合成层，不触发布局）；松手先平滑滑入目标
 * 槽位、归位动画结束后才提交重排，宿主重排时视觉已吻合，全程无跳变。
 * 滚动容器触边自动滚屏，行超出限高亦可拖到位。
 *
 * 定位模型（A-12 前缀和化，2026-10-02）：逐行实测 offsetHeight，槽位位置
 * 按前缀和（Σ行高+行距）换算——行高可变（如席位行子表展开）时让位与落点
 * 仍精确对位；等高列表在前缀和模型下行为不变。量测不硬编码：行高取自
 * DOM（offsetHeight）、行距取画布实际 rowGap、补间时长取 --dur-drag；
 * 宿主画布只提供 position:relative，行 absolute。子表展开/收起等行高变化
 * 由宿主 watch 后重调 measure()。
 *
 * 逐行门控（A-12）：enabledAt 谓词逐行判定——不可拖行（如锁定席位）不能
 * 作拖源，落点解析跳过不可落槽位取最近可落槽；不传时全部可拖（原全局
 * enabled 仅作整体开关）。
 */
import { computed, nextTick, onScopeDispose, ref, type Ref } from "vue";

/** 迟滞量：指针越过槽位边界（0.5）后须再走出这么多格才切换落点，边界
 *  附近来回晃动不触发让位抖动；过大迟钝、过小易抖，0.1~0.2 手感平衡。
 *  拖拽手感常量，非视觉令牌。 */
const HYSTERESIS = 0.15;
/** 触边自动滚屏：判定带宽度与每帧步速（px/frame）。同上，手感常量。 */
const EDGE_BAND = 28;
const EDGE_SPEED = 8;
/** 拖动位移判定阈值（px）：超过才视作拖动（宿主可据此忽略拖后的点击）。 */
const MOVED_THRESHOLD = 4;

export interface PointerSortOptions {
  /** 行数（响应式读取） */
  count: () => number;
  /** 是否允许进入拖拽（整体开关：只读/完成态拦截） */
  enabled: () => boolean;
  /** 逐行门控（可选）：返回 false 的行不可作拖源，落点解析跳过之取最近
   *  可落槽位（如待执行页锁定席位不可作拖源/落点） */
  enabledAt?: (index: number) => boolean;
  /** 定位画布（position:relative；行 absolute、transform 定位） */
  canvas: Ref<HTMLElement | null>;
  /** 画布所在滚动容器（触边自动滚屏） */
  scroller: Ref<HTMLElement | null>;
  /** 行元素选择器（可选）：画布直接子元素中的行标记；有非行子元素
   *  （如等待区分隔注记）的宿主须提供，默认全部子元素视为行 */
  rowSelector?: string;
  /** 归位动画结束后提交 from→to 重排（此时视觉已就位，重排无跳变） */
  commit: (from: number, to: number) => void;
}

export function usePointerSort(opts: PointerSortOptions) {
  /** 被拿起项原始下标；-1 = 未在拖拽 */
  const dragIndex = ref(-1);
  /** 当前预计插入槽位（带迟滞后的结果） */
  const overIndex = ref(-1);
  /** 被拿起项当前 y（相对画布顶部） */
  const dragY = ref(0);
  /** 处于「松手归位」阶段（过渡已恢复、等待提交） */
  const isDropping = ref(false);
  /** 本次按压是否发生实质拖动（宿主可据以忽略拖后的点击，如展开切换） */
  const moved = ref(false);
  /** 逐行高度（measure 实测；量测前空表兜底 0 → 画布不设高防首帧裁切） */
  const rowHeights = ref<number[]>([]);
  const gapPx = ref(0);

  /** 槽位 i 的 y 位置：前缀和 Σ_{j<i}(h_j + gap)。行高缺失按 0 兜底。 */
  function offsetAt(i: number): number {
    let y = 0;
    for (let j = 0; j < i && j < rowHeights.value.length; j++) {
      y += rowHeights.value[j] + gapPx.value;
    }
    return y;
  }

  /** 画布总高 = Σ行高 + (n-1)×行距；未量测前不设高 */
  const canvasStyle = computed(() => {
    const n = opts.count();
    if (n < 1 || rowHeights.value.length !== n) return undefined;
    const sum = rowHeights.value.reduce((a, h) => a + h, 0);
    return { height: `${sum + Math.max(0, n - 1) * gapPx.value}px` };
  });

  /** 行高量测：逐行 offsetHeight（rowSelector 过滤非行子元素），行距取
   *  画布实际 rowGap（间距令牌由宿主 CSS 表达，此处不假定具体令牌）。
   *  行数变化/子表展开收起后由宿主重调。 */
  function measure() {
    const el = opts.canvas.value;
    if (!el) return;
    const gap = Number.parseFloat(getComputedStyle(el).rowGap);
    gapPx.value = Number.isFinite(gap) && gap >= 0 ? gap : 0;
    const children = opts.rowSelector
      ? Array.from(el.querySelectorAll(opts.rowSelector))
      : Array.from(el.children);
    rowHeights.value = children
      .filter((n): n is HTMLElement => n instanceof HTMLElement)
      .map((n) => n.offsetHeight);
  }

  function dragDurationMs(): number {
    const v = Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--dur-drag"),
    );
    return Number.isFinite(v) && v >= 0 ? v : 0;
  }

  /** 第 i 项应在的 y：拿起项跟手；向下拖中间项上移一格、向上拖下移一格
   *  （「一格」= 让位目标槽位的前缀和位置） */
  function offsetFor(i: number): number {
    const from = dragIndex.value;
    const to = overIndex.value;
    if (from === -1) return offsetAt(i);
    if (i === from) return dragY.value;
    if (from < to && i > from && i <= to) return offsetAt(i - 1);
    if (from > to && i >= to && i < from) return offsetAt(i + 1);
    return offsetAt(i);
  }

  /** 行内样式：跟手阶段必须关掉 transform 过渡，否则滞后于指针；
   *  其余阶段交给 CSS（--dur-drag --ease-std）。 */
  function styleFor(i: number): Record<string, string> {
    const style: Record<string, string> = {
      transform: `translateY(${offsetFor(i)}px)`,
    };
    if (i === dragIndex.value && !isDropping.value) style.transition = "transform 0s";
    return style;
  }

  /** 像素 y → 槽位：按「行区间」划分（槽位 i 覆盖其前缀位置前后各半
   *  个行距）；最后一行收尾整个下方区间 */
  function slotAt(y: number): number {
    const n = opts.count();
    for (let i = 0; i < n; i++) {
      const top = offsetAt(i);
      const bottom = top + (rowHeights.value[i] ?? 0) + gapPx.value;
      if (y < bottom) return i;
    }
    return Math.max(0, n - 1);
  }

  /** 最近可落槽位：落点解析跳过 enabledAt=false 的槽位（锁定席位等），
   *  向两侧取最近可落槽；全部不可落返回 -1（调用方不切换落点） */
  function nearestDroppable(slot: number): number {
    const gate = opts.enabledAt;
    if (!gate) return slot;
    const n = opts.count();
    for (let d = 0; d < n; d++) {
      if (slot - d >= 0 && slot - d < n && gate(slot - d)) return slot - d;
      if (slot + d < n && gate(slot + d)) return slot + d;
    }
    return -1;
  }

  /** 带迟滞的目标槽位：从当前槽位出发，越过「边界 + 迟滞」才承认切换；
   *  迟滞区内保持不动，一旦越过立即取最近槽位，快速拖动也不滞后 */
  function resolveOver(slot: number): number {
    const cur = overIndex.value;
    if (cur === -1) return nearestDroppable(slot);
    if (slot > cur + 0.5 + HYSTERESIS) return nearestDroppable(slot);
    if (slot < cur - 0.5 - HYSTERESIS) return nearestDroppable(slot);
    return cur;
  }

  let grabOffset = 0;
  let downX = 0;
  let downY = 0;
  let lastClientY = 0;
  let dragEl: HTMLElement | null = null;
  let rafId = 0;
  let settleTimer = 0;

  /** 拖拽可及的最大 y（最后一行的前缀位置），防止把行拖出画布 */
  function maxDragY(): number {
    const n = opts.count();
    return n > 0 ? offsetAt(n - 1) : 0;
  }

  function followPointer() {
    const el = opts.canvas.value;
    const n = opts.count();
    if (!el || n < 1 || rowHeights.value.length !== n) return;
    const rect = el.getBoundingClientRect();
    // 夹住上下界，防止把行拖出画布（触边滚屏时 rect 随滚动更新）
    const y = Math.max(0, Math.min(maxDragY(), lastClientY - rect.top - grabOffset));
    dragY.value = y;
    const next = resolveOver(slotAt(y));
    if (next !== -1 && next !== overIndex.value) overIndex.value = next;
  }

  /** 触边自动滚屏：指针停在判定带内则逐帧滚动并按同一指针位置重算，
   *  离开判定带或拖拽结束即停 */
  function autoScrollTick() {
    rafId = 0;
    const sc = opts.scroller.value;
    if (!sc || dragIndex.value === -1 || isDropping.value) return;
    const rect = sc.getBoundingClientRect();
    let dir = 0;
    if (lastClientY < rect.top + EDGE_BAND) dir = -1;
    else if (lastClientY > rect.bottom - EDGE_BAND) dir = 1;
    if (dir === 0) return;
    sc.scrollTop += dir * EDGE_SPEED;
    followPointer();
    rafId = requestAnimationFrame(autoScrollTick);
  }

  /** 按下：记抓取偏移与槽位基准，指针捕获后移出元素仍持续收 move；
   *  逐行门控不通过的行不进入拖拽 */
  function onDown(e: PointerEvent, index: number) {
    if (!opts.enabled() || dragIndex.value !== -1 || isDropping.value) return;
    if (opts.enabledAt && !opts.enabledAt(index)) return;
    if (e.pointerType === "mouse" && e.button !== 0) return; // 只响应左键
    if ((e.target as HTMLElement | null)?.closest("button")) return; // 行内按钮不劫持
    measure(); // 进入拖拽前重测，行高/令牌取最新
    if (rowHeights.value.length !== opts.count()) return;
    const row = e.currentTarget;
    if (!(row instanceof HTMLElement)) return;
    grabOffset = e.clientY - row.getBoundingClientRect().top;
    dragIndex.value = index;
    overIndex.value = nearestDroppable(index); // 初值给自身，迟滞才有基准
    dragY.value = offsetAt(index);
    lastClientY = e.clientY;
    downX = e.clientX;
    downY = e.clientY;
    moved.value = false;
    dragEl = row;
    row.setPointerCapture(e.pointerId);
    e.preventDefault(); // 阻止文本选区与原生滚动手势
  }

  function onMove(e: PointerEvent) {
    if (dragIndex.value === -1 || isDropping.value) return;
    if (!moved.value
        && Math.hypot(e.clientX - downX, e.clientY - downY) > MOVED_THRESHOLD) {
      moved.value = true; // 相对按压点位移超阈值才认拖动
    }
    lastClientY = e.clientY;
    followPointer();
    if (!rafId) rafId = requestAnimationFrame(autoScrollTick);
  }

  /** 松手：阶段 1 拿起项恢复过渡、平滑滑入目标槽位；阶段 2 归位动画结束
   *  后再提交重排（视觉位置已吻合，不跳变） */
  async function onUp() {
    if (dragIndex.value === -1 || isDropping.value) return;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    const from = dragIndex.value;
    const to = overIndex.value;

    isDropping.value = true;
    await nextTick(); // 等恢复过渡的样式挂上 DOM
    if (dragEl) void dragEl.offsetHeight; // 强制 reflow，否则过渡不生效
    dragY.value = offsetAt(to);

    settleTimer = window.setTimeout(() => {
      if (from !== to) opts.commit(from, to);
      dragIndex.value = -1;
      overIndex.value = -1;
      isDropping.value = false;
      dragY.value = 0;
      dragEl = null;
    }, dragDurationMs());
  }

  /** 复位（对话框关闭等）：丢弃进行中的拖拽与未落定的提交 */
  function reset() {
    if (rafId) cancelAnimationFrame(rafId);
    if (settleTimer) window.clearTimeout(settleTimer);
    rafId = 0;
    settleTimer = 0;
    dragEl = null;
    dragIndex.value = -1;
    overIndex.value = -1;
    isDropping.value = false;
    dragY.value = 0;
    moved.value = false;
  }

  onScopeDispose(reset);

  return {
    dragIndex,
    overIndex,
    isDropping,
    moved,
    /** 画布行距（measure 实测；宿主非行元素如分隔注记按前缀和定位时用） */
    gap: gapPx,
    canvasStyle,
    measure,
    offsetAt,
    styleFor,
    onDown,
    onMove,
    onUp,
    reset,
  };
}
