<script setup lang="ts">
/**
 * StateChip — 任务/队列状态唯一展示件（m0-frontend-design §4.1）。
 * `● STATE` mono 11px 大写、状态色文字。两档响度（信号响度原则 §1/§4.1）：
 * - 安静档（默认，表格/列表内）：无底色，仅 6px 状态点 + 状态色文字；
 * - 响亮档（loud：执行中页通道卡、停滞告警行、顶栏语义展示）：
 *   状态色 12% 底 + 3px 圆角药丸 + mono 500；running 点 2.4s 呼吸。
 * 同一状态全站颜色与措辞一致（信号系统纪律）。
 */
import { computed } from "vue";

const props = defineProps<{
  /** 任务六态 + 队列四态（见 §4.1 状态变量映射） */
  state: string;
  /** 覆盖默认英文大写措辞（如队列 completed 显示 COMPLETED） */
  label?: string;
  /** 响亮档：状态色 12% 底（通道卡/告警行/语义展示专用） */
  loud?: boolean;
}>();

const running = computed(() => props.state === "running");
// 同一样式类承载中文与拉丁时以中文档位为准（混排纪律 1）：
// 默认英文大写措辞用微标签档，中文覆盖措辞（等待/导入/失败退回 等）升 --text-sm 并去字距。
const CJK = /[\u4e00-\u9fff]/;
const zh = computed(() => CJK.test(props.label ?? ""));
</script>

<template>
  <span
    class="chip mono"
    :class="[`chip--${state}`, { 'chip--loud': loud, 'chip--zh': zh }]"
  >
    <i class="dot" :class="{ breathe: running }" aria-hidden="true"></i>
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
  letter-spacing: var(--ls-micro);
  white-space: nowrap;
}
.chip--zh {
  font-size: var(--text-sm);
  letter-spacing: 0;
}
.chip--loud {
  font-weight: 500;
  background: color-mix(in srgb, currentColor var(--chip-bg-alpha), transparent);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex: none;
}
/* 状态色文字（安静档直接对容器底计算对比度，响亮档对 12% 同色底） */
.chip--staged    { color: var(--state-staged); }
.chip--running   { color: var(--state-running); }
.chip--succeeded { color: var(--state-succeeded); }
.chip--failed    { color: var(--state-failed); }
.chip--skipped   { color: var(--state-skipped); }
.chip--unsubmitted { color: var(--state-idle); }
.chip--completed { color: var(--state-succeeded); }
.chip--archived  { color: var(--state-archived); }

/* running 状态点呼吸（§6；reduced-motion 由 base.css 全局关闭） */
.dot.breathe {
  animation: breathe 2.4s ease-in-out infinite;
}
</style>
