<script setup lang="ts">
/**
 * ConfirmModal — 二次确认模态（m0-frontend-design §4.6）：
 * --bg-overlay + backdrop 纯压暗（无模糊）+ --r-lg + --shadow-pop；
 * 标题 mono 500；危险确认按钮用 danger 类。焦点圈定 + Esc 关闭（§7）。
 */
import { nextTick, ref, watch } from "vue";

const props = defineProps<{
  open: boolean;
  title: string;
  /** 危险动作（停止/删除）：确认按钮用 danger */
  danger?: boolean;
  confirmText?: string;
  cancelText?: string;
  loading?: boolean;
}>();

const emit = defineEmits<{ confirm: []; close: [] }>();

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
    <div ref="panel" class="modal" role="dialog" aria-modal="true" :aria-label="title">
      <h3 class="title mono">{{ title }}</h3>
      <div class="body">
        <slot />
      </div>
      <div class="foot">
        <button ref="cancelButton" class="btn btn--ghost" type="button" @click="tryClose">
          {{ cancelText ?? "取消" }}
        </button>
        <button
          class="btn"
          :class="danger ? 'btn--danger' : 'btn--primary'"
          type="button"
          :data-loading="loading || undefined"
          :disabled="loading"
          @click="emit('confirm')"
        >
          {{ loading ? `${confirmText ?? "确认"}中 …` : confirmText ?? "确认" }}
        </button>
      </div>
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
  width: min(560px, calc(100vw - 48px));
  max-height: min(640px, calc(100vh - 96px));
  display: flex;
  flex-direction: column;
  background: var(--bg-overlay);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-pop);
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
