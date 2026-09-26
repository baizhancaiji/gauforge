<script setup lang="ts">
/**
 * 标准表格底部套件（m0-frontend-design §4.3）：列表底栏 = 分页控件绝对居中
 * + 「共 n 项」计数右对齐，同置一个底部 flex 容器互不影响。候选/队列/历史
 * 三页表格统一应用（分页取数口径由宿主决定：候选/历史为后端 offset 分页、
 * 队列为前端切片，本组件只管页码状态与交互）。
 * 显隐规则：总数小于分页大小即单页容纳全部时，分页控件整体隐藏且不占位，
 * 仅剩计数。页码输入框仅收自然数（inputmode=numeric + 非数字过滤）、
 * Enter 跳转无独立按钮；跳转页码钳制 Math.max(1, Math.min(t, totalPages))：
 * 0 落首页、超上限落尾页。首/上一/下一/尾页为线性 SVG 图标按钮
 * （stroke=currentColor，不用字符箭头）。
 */
import { computed, ref, watch } from "vue";

const props = defineProps<{
  /** 列表总条数（后端信封 total 或前端全量数组长度） */
  total: number;
  /** 当前页（1 起） */
  page: number;
  /** 分页大小（设置项 page_size，三页全局统一） */
  pageSize: number;
}>();
const emit = defineEmits<{ change: [page: number] }>();

const totalPages = computed(() =>
  Math.max(1, Math.ceil(props.total / Math.max(1, props.pageSize))),
);
/** 显隐规则：total ≥ page_size 才出现（§4.3） */
const visible = computed(() => props.total >= Math.max(1, props.pageSize));

const draft = ref(String(props.page));
watch(
  () => props.page,
  (p) => {
    draft.value = String(p);
  },
);

function go(target: number) {
  const clamped = Math.max(1, Math.min(target, totalPages.value));
  draft.value = String(clamped);
  if (clamped !== props.page) emit("change", clamped);
}

/** 输入过滤：仅保留数字字符（自然数，含 0——0 由边界钳制落首页） */
function onInput() {
  draft.value = draft.value.replace(/\D+/g, "");
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") go(Number(draft.value || String(props.page)));
}
/** 未回车即失焦 → 回落当前页显示，避免草稿值与实际页码不一致 */
function onBlur() {
  draft.value = String(props.page);
}
</script>

<template>
  <div class="pager-bar">
    <nav v-if="visible" class="pager" aria-label="列表分页">
      <button
        class="pg-btn"
        type="button"
        :disabled="page <= 1"
        aria-label="首页"
        @click="go(1)"
      >
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M11 3.5 6.5 8l4.5 4.5" />
          <path d="M6 3.5 1.5 8 6 12.5" />
        </svg>
      </button>
      <button
        class="pg-btn"
        type="button"
        :disabled="page <= 1"
        aria-label="上一页"
        @click="go(page - 1)"
      >
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M10 3.5 5.5 8 10 12.5" />
        </svg>
      </button>
      <span class="pg-text">第</span>
      <input
        v-model="draft"
        class="pg-input"
        type="text"
        inputmode="numeric"
        :aria-label="`跳转页码，共 ${totalPages} 页`"
        @input="onInput"
        @keydown="onKeydown"
        @blur="onBlur"
      />
      <span class="pg-text">页 / 共 {{ totalPages }} 页</span>
      <button
        class="pg-btn"
        type="button"
        :disabled="page >= totalPages"
        aria-label="下一页"
        @click="go(page + 1)"
      >
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M6 3.5l4.5 4.5L6 12.5" />
        </svg>
      </button>
      <button
        class="pg-btn"
        type="button"
        :disabled="page >= totalPages"
        aria-label="尾页"
        @click="go(totalPages)"
      >
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M5 3.5 9.5 8 5 12.5" />
          <path d="M10 3.5 14.5 8 10 12.5" />
        </svg>
      </button>
    </nav>
    <span class="pg-count mono">共 {{ total }} 项</span>
  </div>
</template>

<style scoped>
/* 底栏：计数右对齐（flex-end），分页控件绝对居中、与计数互不影响（§4.3） */
.pager-bar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
  padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--border-hair);
}
.pager {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.pg-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--control-height-sm);
  height: var(--control-height-sm);
  border-radius: var(--r-md);
  color: var(--text-secondary);
  transition:
    background-color var(--dur-fast) var(--ease-std),
    color var(--dur-fast) var(--ease-std);
}
.pg-btn svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.pg-btn:hover:not(:disabled) {
  background: var(--row-hover);
  color: var(--text-primary);
}
.pg-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.pg-text {
  font-size: var(--text-sm); /* 文案含中文（第/页/共），混排纪律 1 不加字距 */
  color: var(--text-faint);
  white-space: nowrap;
}
.pg-input {
  width: var(--space-12);
  height: var(--control-height-sm);
  padding: 0;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.pg-count {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
</style>
