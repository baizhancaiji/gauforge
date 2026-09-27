/**
 * useMultiSelect — 列表多选交互公共组合式（锚点 + 焦点双状态驱动）。
 *
 * 资源管理器式多选范式：锚点索引（anchorIndex，范围选择基准）与焦点索引
 * （focusedIndex，键盘导航位置）分立维护——
 * - Shift+点击：从锚点到当前行范围选择（Ctrl+Shift 追加式、普通 Shift
 *   替换式），Shift 不改变锚点，可反复调整范围；
 * - Ctrl/Cmd+点击：切换单项（复选框列宿主下普通点击同为 toggle，修饰键
 *   的增量价值在 Ctrl+Shift 追加范围）；
 * - 上下方向键：移动焦点并联动勾选（首次按键定位到首/尾行），Shift+方向键
 *   从锚点扩展选区、无修饰键则单选替换该行；
 * - Ctrl/Cmd+A 全选、Esc 清空；
 * - 焦点移动自动滚动定位（scrollIntoView block:nearest）。
 *
 * 行点击（预览选中语义）经 pointAt 同步锚点/焦点但不改变勾选，使
 * 「点行 → Shift+方向键扩展勾选」自然衔接。仅管理选中集合与索引状态，
 * 行渲染与滚动容器由宿主注入（ids 提取器 + 行元素读取器）；翻页/列表重载
 * 后页内索引失效，宿主须调 resetIndices（勾选集合保留——跨页勾选语义不变）。
 */
import { nextTick, ref } from "vue";

export type SelectId = number | string;

export interface MultiSelectOptions {
  /** 当前行 id 序（宿主列表按渲染序提供，索引即行序） */
  ids: () => SelectId[];
  /** 当前行元素序（键盘导航滚动定位用；与 ids 同序，容器未挂载时返回 null） */
  rows?: () => HTMLElement[] | null;
}

export function useMultiSelect(opts: MultiSelectOptions) {
  /** 已勾选 id 集合（跨页保留，翻页/重载不清空） */
  const checkedIds = ref<Set<SelectId>>(new Set());
  /** 锚点索引：范围选择基准点，-1 表示尚未建立 */
  const anchorIndex = ref(-1);
  /** 键盘焦点索引：-1 表示尚未建立 */
  const focusedIndex = ref(-1);

  /** 选中 [from, to] 闭区间内所有行；append=false 时先清空（替换式） */
  function selectRange(from: number, to: number, append = false) {
    const ids = opts.ids();
    if (!append) checkedIds.value = new Set();
    const next = new Set(checkedIds.value);
    const start = Math.max(0, Math.min(from, to));
    const end = Math.min(ids.length - 1, Math.max(from, to));
    for (let i = start; i <= end; i++) next.add(ids[i]);
    checkedIds.value = next;
  }

  /** 单选替换：清空后仅勾选第 index 行 */
  function selectOnly(index: number) {
    const ids = opts.ids();
    if (index < 0 || index >= ids.length) return;
    checkedIds.value = new Set([ids[index]]);
  }

  function toggle(id: SelectId) {
    const next = new Set(checkedIds.value);
    if (!next.delete(id)) next.add(id);
    checkedIds.value = next;
  }

  /** 全选当前页；锚点/焦点不动（范围基准仍有效） */
  function selectAll() {
    checkedIds.value = new Set(opts.ids());
  }

  /** 清空勾选并复位锚点/焦点 */
  function clearAll() {
    checkedIds.value = new Set();
    anchorIndex.value = -1;
    focusedIndex.value = -1;
  }

  /** 仅复位锚点/焦点（翻页/列表重载后页内索引失效时调用，勾选保留） */
  function resetIndices() {
    anchorIndex.value = -1;
    focusedIndex.value = -1;
  }

  /** 复选框点击统一入口：Shift 范围（Ctrl+Shift 追加）/ Ctrl·Cmd 与普通点击 toggle */
  function click(
    index: number,
    e: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean },
  ) {
    const ids = opts.ids();
    if (index < 0 || index >= ids.length) return;
    focusedIndex.value = index;
    if (e.shiftKey && anchorIndex.value !== -1) {
      selectRange(anchorIndex.value, index, e.ctrlKey || e.metaKey);
      return;
    }
    toggle(ids[index]);
    anchorIndex.value = index;
  }

  /** 行点击同步：锚点/焦点落到该行，不改变勾选（衔接键盘 Shift 扩展） */
  function pointAt(index: number) {
    const n = opts.ids().length;
    if (index < 0 || index >= n) return;
    anchorIndex.value = index;
    focusedIndex.value = index;
  }

  /** 焦点行滚动定位（等 DOM 更新后按宿主行元素序取行） */
  function scrollToIndex(index: number) {
    const rows = opts.rows?.() ?? null;
    if (!rows) return;
    nextTick(() => rows[index]?.scrollIntoView({ block: "nearest" }));
  }

  /** 键盘导航（宿主列表容器 keydown 接入）：Ctrl+A 全选 / Esc 清空 /
   *  上下方向键移动焦点并联动勾选（Shift 从锚点扩展） */
  function onKeydown(e: KeyboardEvent) {
    const ids = opts.ids();
    const n = ids.length;
    const multi = e.ctrlKey || e.metaKey;
    if (multi && e.key.toLowerCase() === "a") {
      e.preventDefault();
      selectAll();
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      clearAll();
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    if (!n) return;
    const delta = e.key === "ArrowDown" ? 1 : -1;
    const next =
      focusedIndex.value === -1
        ? delta > 0
          ? 0
          : n - 1
        : Math.max(0, Math.min(n - 1, focusedIndex.value + delta));
    focusedIndex.value = next;
    scrollToIndex(next);
    if (e.shiftKey && anchorIndex.value !== -1) {
      selectRange(anchorIndex.value, next, false);
    } else {
      selectOnly(next);
      anchorIndex.value = next;
    }
  }

  return {
    checkedIds,
    anchorIndex,
    focusedIndex,
    selectRange,
    selectOnly,
    toggle,
    selectAll,
    clearAll,
    resetIndices,
    click,
    pointAt,
    onKeydown,
  };
}
