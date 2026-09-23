<script setup lang="ts">
/**
 * StateChip — 任务/队列状态唯一展示件（m0-frontend-design §4.1）。
 * `● STATE` mono 11px 大写、状态色文字、状态色 12% 底、3px 圆角药丸。
 * 同一状态全站颜色与措辞一致（信号系统纪律）；running 点亮点 2.4s 呼吸。
 */
import { computed } from "vue";

const props = defineProps<{
  /** 任务六态 + 队列四态 + archived（见 §4.1 状态变量映射） */
  state: string;
  /** 覆盖默认英文大写措辞（如队列 completed 显示 COMPLETED） */
  label?: string;
}>();

const running = computed(() => props.state === "running");
</script>

<template>
  <span class="chip mono" :class="`chip--${state}`" :data-running="running || undefined">
    <i class="dot" aria-hidden="true"></i>
    <span class="label">{{ label ?? state.toUpperCase() }}</span>
  </span>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 20px;
  padding: 0 8px;
  border-radius: var(--r-sm);
  font-size: var(--text-xs);
  font-weight: 500;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex: none;
}
/* 状态色文字 + 12% 底（透明度由身份变量 --text-primary 注入 currentColor 同源） */
.chip--staged    { color: var(--state-staged);    background: color-mix(in srgb, var(--state-staged) var(--chip-bg-alpha), transparent); }
.chip--running   { color: var(--state-running);   background: color-mix(in srgb, var(--state-running) var(--chip-bg-alpha), transparent); }
.chip--succeeded { color: var(--state-succeeded); background: color-mix(in srgb, var(--state-succeeded) var(--chip-bg-alpha), transparent); }
.chip--failed    { color: var(--state-failed);    background: color-mix(in srgb, var(--state-failed) var(--chip-bg-alpha), transparent); }
.chip--skipped   { color: var(--state-skipped);   background: color-mix(in srgb, var(--state-skipped) var(--chip-bg-alpha), transparent); }
.chip--unsubmitted { color: var(--state-idle);    background: color-mix(in srgb, var(--state-idle) var(--chip-bg-alpha), transparent); }
.chip--completed { color: var(--state-succeeded); background: color-mix(in srgb, var(--state-succeeded) var(--chip-bg-alpha), transparent); }
.chip--archived  { color: var(--state-archived);  background: color-mix(in srgb, var(--state-archived) var(--chip-bg-alpha), transparent); }

/* running 状态点亮点呼吸（§4.1/§6；reduced-motion 由 base.css 全局关闭） */
[data-running] .dot {
  animation: breathe 2.4s ease-in-out infinite;
}
@keyframes breathe {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
</style>