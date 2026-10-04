<script setup lang="ts">
/**
 * 待执行队列席位成员子表（2026-10-04 自 PendingView 抽出）：
 * 成员明细（序号/任务id/文件名/标题/资源/状态）+ 未执行成员移除 +
 * 成员拖拽重排——复用既有 usePointerSort 指针跟手组件（与席位行/队列
 * 编辑框同一动效纪律），每席位展开即一个组件实例、各持一份排序器。
 *
 * 嵌套拖拽边界：本组件行 pointerdown 阻断冒泡（.stop），外层席位拖拽
 * 不被误触；重排门控按 m2 分级矩阵定稿——执行中席位（locked）整体不可
 * 拖，仅 staged 成员可作拖源/落点（正在执行/已完成成员为既定历史），
 * 落点解析由 usePointerSort 跳过不可落槽位。提交走 PATCH /queues/{id}
 * member_ids 全量有序原子（契约 #15）。
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";

import { client } from "@/api/client";
import StateChip from "@/components/StateChip.vue";
import type { components } from "@/api/contract";
import { fmtDeclaredRes, fmtTaskId } from "@/utils/format";
import { usePointerSort } from "@/composables/usePointerSort";

type PendingSeat = components["schemas"]["PendingSeat"];

const props = defineProps<{ seat: PendingSeat }>();
const emit = defineEmits<{
  remove: [task_id: number];
  changed: [];
  error: [message: string];
}>();

const members = computed(() => props.seat.members ?? []);
const stagedCount = computed(
  () => members.value.filter((m) => m.state === "staged").length,
);

const subEl = ref<HTMLElement | null>(null);
const scrollerEl = ref<HTMLElement | null>(null);

const dragEnabled = () => !props.seat.locked && stagedCount.value > 1;
const canDragAt = (i: number) => members.value[i]?.state === "staged";

async function reorder(from: number, to: number) {
  const ids = members.value.map((m) => m.task_id);
  const [movedId] = ids.splice(from, 1);
  if (movedId == null) return;
  ids.splice(to, 0, movedId);
  const { error } = await client.PATCH("/queues/{id}", {
    params: { path: { id: props.seat.queue_id ?? "" } },
    body: { member_ids: ids as number[] },
  });
  if (error) {
    const body = error as unknown as { error?: { code?: string; message?: string } };
    emit(
      "error",
      body.error?.code === "QUEUE_STATE_CONFLICT"
        ? "队列已在执行，成员顺序不可调整"
        : (body.error?.message ?? "重排被拒绝"),
    );
    return;
  }
  emit("changed"); // SSE pending.snapshot 随后同值到达，此处兜底即时刷新
}

const sort = usePointerSort({
  count: () => members.value.length,
  enabled: dragEnabled,
  enabledAt: canDragAt,
  canvas: subEl,
  scroller: scrollerEl,
  rowSelector: ".m-row", // 表头行在画布外（非拖拽行），不参与量测
  commit: (from, to) => void reorder(from, to),
});

onMounted(() => {
  scrollerEl.value = subEl.value?.closest(".content") ?? null;
  void nextTick(() => sort.measure());
});

// SSE 快照成员集变化（重排/移除/状态推进）→ 行高重测（前缀和定位）
watch(members, () => void nextTick(() => sort.measure()));
</script>

<template>
  <div class="sub">
    <div class="sub-row sub-head mono" aria-hidden="true">
      <span>#</span>
      <span>ID</span>
      <span>文件名</span>
      <span>标题</span>
      <span>资源</span>
      <span>状态</span>
      <span></span>
    </div>
    <!-- 成员画布（指针跟手拖拽）：行 absolute + transform 定位，画布定高
         由组合式按逐行前缀和给出；pointerdown 阻断冒泡防误触席位拖拽 -->
    <div
      ref="subEl"
      class="sub-canvas"
      :class="{ 'sub-canvas--live': dragEnabled() }"
      :style="sort.canvasStyle.value"
    >
      <div
        v-for="(m, mi) in members"
        :key="m.task_id"
        class="sub-row m-row"
        :class="{ 'm-row--dragging': sort.dragIndex.value === mi }"
        :style="sort.styleFor(mi)"
        @pointerdown.stop="sort.onDown($event, mi)"
        @pointermove="sort.onMove($event)"
        @pointerup="sort.onUp"
        @pointercancel="sort.onUp"
      >
        <span class="mono m-idx">{{ (m.position ?? mi) + 1 }}</span>
        <span class="mono m-id">{{ fmtTaskId(m.task_id) }}</span>
        <span class="mono m-file" :title="m.filename">{{ m.filename }}</span>
        <span class="m-title" :title="m.title ?? undefined">{{ m.title ?? "—" }}</span>
        <span class="mono m-res">{{ fmtDeclaredRes(m.resources) }}</span>
        <StateChip
          :state="m.state"
          :label="m.state === 'staged' ? '等待' : undefined"
        />
        <button
          v-if="m.state === 'staged'"
          class="btn btn--ghost m-remove"
          type="button"
          @click="emit('remove', m.task_id)"
        >
          移除
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sub {
  margin-top: var(--space-2);
  border-top: 1px solid var(--border-hair);
  padding-top: var(--space-2);
}
/* 成员画布：relative + grid gap（供行距量测），行 absolute + transform
   定位，画布定高由组合式前缀和给出（同席位画布手法） */
.sub-canvas {
  position: relative;
  display: grid;
  gap: var(--space-1);
}
.sub-canvas--live .m-row:not(.m-row--dragging) {
  cursor: grab;
}
.sub-canvas--live .m-row--dragging {
  cursor: grabbing;
}
.sub-row {
  display: grid;
  /* 序号/id 列 minmax 收窄但不截断：id ≥ 1000 时自然加宽（034 为显示下宽）；
     状态/操作列定宽——表头与数据行是两个独立 grid，auto 轨随内容宽漂移会错位 */
  grid-template-columns:
    20px minmax(36px, auto) minmax(0, 1.2fr) minmax(0, 1fr) 108px 72px 64px;
  gap: var(--space-3);
  align-items: center;
  font-size: var(--text-sm);
}
.sub-head {
  color: var(--text-faint);
  font-size: var(--text-xs); /* 表头含中文（文件名等）：不加字距 */
  margin-bottom: var(--space-2);
}
.m-row {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  /* 盒恒定（边框/内边距常态持有，拖拽态只换色）——拖拽态改盒会让行高
     偏离量测前缀和（队列编辑框 .q-mem 同款纪律） */
  border: 1px solid var(--border-hair);
  border-radius: var(--r-sm);
  background: var(--bg-raised);
  padding: var(--space-1) var(--space-2);
  user-select: none;
  touch-action: none; /* 指针拖拽期间阻止触屏滚动误触 */
  transition:
    transform var(--dur-drag) var(--ease-std),
    border-color var(--dur-fast) var(--ease-std);
  will-change: transform;
}
/* 拿起态：accent 描边 + 浮起投影（与席位行/队列编辑框同款令牌组合） */
.m-row--dragging {
  z-index: 1;
  border-color: var(--accent);
  box-shadow: var(--shadow-pop);
}
.m-idx {
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.m-id {
  color: var(--text-faint);
  font-size: var(--text-xs);
  font-variant-numeric: tabular-nums;
}
.m-file {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-title {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-res {
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}
.m-remove {
  height: var(--control-height-sm);
  font-size: var(--text-sm); /* 文案含中文（移除） */
}
</style>
