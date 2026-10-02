<script setup lang="ts">
/**
 * LongPressButton — 长按确认按钮（危险操作强化；有在跑执行时替代普通
 * 确认按钮）。按住达到 duration 触发 pressed；中途抬起/移出/打断即取消
 * 并归零。进度经 --p 变量由 ::after scaleX 呈现（覆盖色走 --veil-press
 * 令牌）；禁选中与长按系统菜单。
 */
import { onBeforeUnmount, ref } from "vue";

import { useLongPress } from "@/composables/useLongPress";

const props = withDefaults(
  defineProps<{
    label: string;
    /** 长按时长 ms（默认 3000，用户验收口径）。 */
    duration?: number;
    disabled?: boolean;
  }>(),
  { duration: 3000, disabled: false },
);

const emit = defineEmits<{ pressed: [] }>();

const el = ref<HTMLElement | null>(null);
const { cancel } = useLongPress(el, {
  duration: props.duration,
  onLongPress: () => emit("pressed"),
  onProgress: (p) => {
    el.value?.style.setProperty("--p", String(p));
  },
});
onBeforeUnmount(cancel);
</script>

<template>
  <button
    ref="el"
    class="btn btn--danger lp-btn"
    type="button"
    :disabled="disabled"
  >
    {{ label }}
  </button>
</template>

<style scoped>
.lp-btn {
  position: relative;
  overflow: hidden;
  /* 长按关键：禁选中、禁触屏长按菜单与点按高亮、手势自理 */
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
}
/* 进度覆盖层：--p（0~1）驱动横向铺满，左起 */
.lp-btn::after {
  content: "";
  position: absolute;
  inset: 0;
  background: var(--veil-press);
  transform: scaleX(var(--p, 0));
  transform-origin: left center;
  pointer-events: none;
}
</style>
