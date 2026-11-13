<script setup lang="ts">
/**
 * ConfirmModal — 二次确认模态（m0-frontend-design §4.6）：
 * --bg-overlay + backdrop 纯压暗（无模糊）+ --r-lg + --shadow-pop；
 * 标题 mono 500；危险确认按钮用 danger 类。焦点圈定 + Esc 关闭（§7）。
 */
import { nextTick, ref, watch } from "vue";

import { MODAL_VIEWPORT_MARGIN } from "@/constants";

const props = defineProps<{
  open: boolean;
  title: string;
  /** 危险动作（停止/删除）：确认按钮用 danger */
  danger?: boolean;
  confirmText?: string;
  cancelText?: string;
  loading?: boolean;
  /** 内容未就绪时禁用确认（如输入原文读取中） */
  disabled?: boolean;
  /** 弹窗宽度覆写（CSS 长度值，透传 --modal-width 变量；不覆写 width
   *  属性——min(var(--modal-width), calc(100vw − 视口边距)) 表达式保持，
   *  超视口自动钳制、居中由 .scrim 承载不破坏）。未传入时零变化。 */
  width?: string;
}>();

const emit = defineEmits<{ confirm: []; close: [] }>();

/** min() 表达式视口边距（两侧各留 ≥24px），自 constants 单一来源引入 */
const viewportMargin = `${MODAL_VIEWPORT_MARGIN}px`;

const panel = ref<HTMLElement | null>(null);
const cancelButton = ref<HTMLButtonElement | null>(null);

watch(
  () => props.open,
  async (v) => {
    if (v) {
      await nextTick();
      cancelButton.value?.focus();
    }
  },
);

function tryClose() {
  if (!props.loading) emit("close");
}

/** Tab 焦点圈定：在模态内循环（§7）。 */
function trapFocus(e: KeyboardEvent) {
  if (e.key !== "Tab" || !panel.value) return;
  const focusables = panel.value.querySelectorAll<HTMLElement>(
    "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
  );
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement;
  if (e.shiftKey && (active === first || !panel.value.contains(active))) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && active === last) {
    e.preventDefault();
    first.focus();
  }
}
</script>

<template>
  <div v-if="open" class="scrim" @click.self="tryClose" @keydown.esc="tryClose" @keydown="trapFocus">
    <div
      ref="panel"
      class="modal"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      :style="width ? { '--modal-width': width } : undefined"
    >
      <h3 class="title mono">{{ title }}</h3>
      <div class="body">
        <slot />
      </div>
      <div class="foot">
        <slot name="foot">
          <button ref="cancelButton" class="btn btn--ghost" type="button" @click="tryClose">
            {{ cancelText ?? "取消" }}
          </button>
          <button
            class="btn"
            :class="danger ? 'btn--danger' : 'btn--primary'"
            type="button"
            :data-loading="loading || undefined"
            :disabled="loading || disabled"
            @click="emit('confirm')"
          >
            {{ loading ? `${confirmText ?? "确认"}中 …` : confirmText ?? "确认" }}
          </button>
        </slot>
      </div>
      <!-- 弹窗级附件落点（如 QueueEditorModal 拖宽手柄）：必须渲染为
           .modal 直接子元素——.body 是 overflow-y 滚动容器且无定位祖先，
           绝对定位内容置其中会被裁剪、无法贴住面板右缘 -->
      <slot name="resize-handle" />
    </div>
  </div>
</template>

<style scoped>
.scrim {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background: var(--backdrop-modal); /* 纯压暗、无模糊（§1 反方向） */
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal {
  width: min(var(--modal-width), calc(100vw - v-bind(viewportMargin)));
  max-height: min(var(--modal-max-height), calc(100vh - 96px));
  display: flex;
  flex-direction: column;
  background: var(--bg-overlay);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-pop);
  /* 仅建立定位上下文（resize-handle 等附件的绝对定位参照），不改布局外观 */
  position: relative;
}
.title {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border-hair);
}
.body {
  padding: var(--space-4) var(--space-5);
  overflow-y: auto;
  min-height: 0;
}
.foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-5) var(--space-4);
  border-top: 1px solid var(--border-hair);
}
</style>
