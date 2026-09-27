/**
 * usePointerSort — 指针事件驱动的等高行拖拽排序（画布式；§4.6 拖拽排序，
 * 2026-09-27 人为指定动效重做，参照指针跟手参考实现）。
 *
 * 与 useDragSort（HTML5 DnD，待执行页）分立：本组合式面向行高一致的紧凑
 * 列表（队列编辑对话框成员行），动效为——拿起项 transform 跟手（跟手阶段
 * 关过渡），其余项跨槽位边界带迟滞地让位/归位（transform 补间走合成层，
 * 不触发布局）；松手先平滑滑入目标槽位、归位动画结束后才提交重排，宿主
 * 重排时视觉已吻合，全程无跳变。滚动容器触边自动滚屏，成员超出限高亦可
 * 拖到位。
 *
 * 量测不硬编码：行高取自 DOM（offsetHeight），行距/补间时长取自设计令牌
 * （--space-1 / --dur-drag）；宿主画布只提供 position:relative，行 absolute。
 */
import { computed, nextTick, onScopeDispose, ref, type Ref } from "vue";

/** 迟滞量：指针越过槽位边界（0.5）后须再走出这么多格才切换落点，边界
 *  附近来回晃动不触发让位抖动；过大迟钝、过小易抖，0.1~0.2 手感平衡。
 *  拖拽手感常量，非视觉令牌。 */
const HYSTERESIS = 0.15;
/** 触边自动滚屏：判定带宽度与每帧步速（px/frame）。同上，手感常量。 */
const EDGE_BAND = 28;
const EDGE_SPEED = 8;

export interface PointerSortOptions {
  /** 行数（响应式读取） */
  count: () => number;
  /** 是否允许进入拖拽（只读/完成态拦截） */
  enabled: () => boolean;
  /** 定位画布（position:relative；行 absolute、transform 定位） */
  canvas: Ref<HTMLElement | null>;
  /** 画布所在滚动容器（触边自动滚屏） */
  scroller: Ref<HTMLElement | null>;
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
  /** 行高 / 行距（打开、行数变化与进入拖拽时量测） */
  const rowH = ref(0);
  const gapPx = ref(0);

  const step = computed(() => rowH.value + gapPx.value);
  /** 画布总高 = (n-1)×步距 + 行高；未量测前不设高，避免首帧裁切 */
  const canvasStyle = computed(() => {
    const n = opts.count();
    if (step.value <= 0 || n < 1) return undefined;
    return { height: `${(n - 1) * step.value + rowH.value}px` };
  });

  /** 行高/行距量测：行高取首行 offsetHeight，行距取令牌 --space-1 */
  function measure() {
    const el = opts.canvas.value;
    const row = el?.firstElementChild;
    if (!el || !(row instanceof HTMLElement)) return;
    const gap = Number.parseFloat(getComputedStyle(el).getPropertyValue("--space-1"));
    gapPx.value = Number.isFinite(gap) && gap >= 0 ? gap : 0;
    rowH.value = row.offsetHeight;
  }

  function dragDurationMs(): number {
    const v = Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--dur-drag"),
    );
    return Number.isFinite(v) && v >= 0 ? v : 0;
  }

  /** 第 i 项应在的 y：拿起项跟手；向下拖中间项上移一格、向上拖下移一格 */
  function offsetFor(i: number): number {
    const from = dragIndex.value;
    const to = overIndex.value;
    if (from === -1) return i * step.value;
    if (i === from) return dragY.value;
    if (from < to && i > from && i <= to) return (i - 1) * step.value;
    if (from > to && i >= to && i < from) return (i + 1) * step.value;
    return i * step.value;
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

  /** 带迟滞的目标槽位：从当前槽位出发，越过「边界 + 迟滞」才承认切换；
   *  迟滞区内保持不动，一旦越过立即取最近槽位，快速拖动也不滞后 */
  function resolveOver(pos: number): number {
    const n = opts.count();
    const cur = overIndex.value;
    if (cur === -1) return Math.round(pos);
    if (pos > cur + 0.5 + HYSTERESIS) return Math.min(n - 1, Math.round(pos));
    if (pos < cur - 0.5 - HYSTERESIS) return Math.max(0, Math.round(pos));
    return cur;
  }

  let grabOffset = 0;
  let lastClientY = 0;
  let dragEl: HTMLElement | null = null;
  let rafId = 0;
  let settleTimer = 0;

  function followPointer() {
    const el = opts.canvas.value;
    const n = opts.count();
    if (!el || n < 1 || step.value <= 0) return;
    const rect = el.getBoundingClientRect();
    // 夹住上下界，防止把行拖出画布（触边滚屏时 rect 随滚动更新）
    const y = Math.max(0, Math.min((n - 1) * step.value, lastClientY - rect.top - grabOffset));
    dragY.value = y;
    const next = resolveOver(y / step.value);
    if (next !== overIndex.value) overIndex.value = next;
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

  /** 按下：记抓取偏移与槽位基准，指针捕获后移出元素仍持续收 move */
  function onDown(e: PointerEvent, index: number) {
    if (!opts.enabled() || dragIndex.value !== -1 || isDropping.value) return;
    if (e.pointerType === "mouse" && e.button !== 0) return; // 只响应左键
    if ((e.target as HTMLElement | null)?.closest("button")) return; // 行内按钮不劫持
    measure(); // 进入拖拽前重测，行高/令牌取最新
    if (step.value <= 0) return;
    const row = e.currentTarget;
    if (!(row instanceof HTMLElement)) return;
    grabOffset = e.clientY - row.getBoundingClientRect().top;
    dragIndex.value = index;
    overIndex.value = index; // 初值给自身，迟滞才有基准
    dragY.value = index * step.value;
    lastClientY = e.clientY;
    dragEl = row;
    row.setPointerCapture(e.pointerId);
    e.preventDefault(); // 阻止文本选区与原生滚动手势
  }

  function onMove(e: PointerEvent) {
    if (dragIndex.value === -1 || isDropping.value) return;
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
    dragY.value = to * step.value;

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
  }

  onScopeDispose(reset);

  return {
    dragIndex,
    overIndex,
    isDropping,
    canvasStyle,
    measure,
    styleFor,
    onDown,
    onMove,
    onUp,
    reset,
  };
}
