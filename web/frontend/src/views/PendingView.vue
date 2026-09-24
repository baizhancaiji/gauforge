<script setup lang="ts">
/**
 * 03 待执行（m0-frontend-design §5 · 席位型）
 * 页首容量仪表（在途席位 OCCUPIED x/limit 分段 LED）；席位纵向列表，
 * 锁定位（已被并行窗口触及、实体执行在途）加左侧 2px 磷光条 + 「在途」标记，
 * 其后为等待区。WINDOW（并行槽位）语义归执行中页，本页不复用。
 * 数据源：SSE pending.snapshot（事件驱动）；首帧回落 REST GET /pending。
 */
import { computed, reactive, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import EmptyState from "@/components/EmptyState.vue";
import StateChip from "@/components/StateChip.vue";
import { useEventsStore } from "@/stores/events";

type PendingResponse = components["schemas"]["PendingResponse"];
type PendingSeat = components["schemas"]["PendingSeat"];

const events = useEventsStore();
const local = ref<PendingResponse | null>(null);
const expanded = reactive(<Record<number, boolean>>{});

const pending = computed(() => events.pending ?? local.value);
const seats = computed(() => pending.value?.seats ?? []);

async function load() {
  const { data } = await client.GET("/pending");
  if (data) local.value = data;
}
// SSE 快照一旦到达即覆盖 local（local 仅作首帧回落）。
watch(() => events.pending, (v) => {
  if (v) local.value = null;
});
load();

function toggle(seatId: number) {
  expanded[seatId] = !expanded[seatId];
}
</script>

<template>
  <div v-if="!pending" class="loading mono">读取待执行队列 …</div>

  <template v-else>
    <!-- 在途席位容量仪表（§4.5）：内嵌读数槽（inset 凹陷底），与下方席位卡分层；
         WINDOW=并行槽位数归 exec 页 -->
    <div class="gauge mono" aria-label="在途容量">
      <span class="g-label">OCCUPIED {{ pending.capacity.occupied }}/{{ pending.capacity.limit }}</span>
      <span class="cells" aria-hidden="true">
        <i
          v-for="i in pending.capacity.limit"
          :key="i"
          class="cell"
          :class="{ 'cell--on': i <= pending.capacity.occupied }"
        ></i>
      </span>
    </div>

    <!-- 仪表区与席位区分隔（面板刻线） -->
    <div class="panel-divider" role="presentation"></div>

    <section class="seats">
      <p v-if="!seats.length" class="empty-msg mono">席位空置 — 提交任务后在此排队</p>

      <div
        v-for="s in seats"
        :key="s.seat_id"
        class="seat"
        :class="{ 'seat--locked': s.locked }"
      >
        <span class="seat-no mono">S{{ String(s.seat_id).padStart(2, "0") }}</span>
        <span class="kind mono" :class="`kind--${s.kind}`">{{ s.kind === "queue" ? "QUEUE" : "TASK" }}</span>

        <div class="seat-body">
          <div class="seat-line" @click="s.kind === 'queue' && toggle(s.seat_id)">
            <span v-if="s.kind === 'queue'" class="mono seat-name">#{{ s.queue_id }}</span>
            <span v-else class="mono seat-name">{{ s.members[0]?.filename ?? "—" }}</span>
            <span v-if="s.locked" class="mono win-tag">在途</span>
          </div>

          <!-- 队列席位可展开成员概览（§4.5） -->
          <div v-if="s.kind === 'queue' && expanded[s.seat_id]" class="sub">
            <div v-for="m in s.members" :key="m.task_id" class="sub-row">
              <span class="mono m-id">#{{ m.task_id }}</span>
              <span class="mono m-file">{{ m.filename }}</span>
              <StateChip :state="m.state" />
            </div>
          </div>
          <span v-if="!s.locked && !expanded[s.seat_id]" class="mono standby">等待派发</span>
        </div>
      </div>
    </section>
  </template>
</template>

<style scoped>
.loading {
  color: var(--text-faint);
  font-size: var(--text-sm);
  padding: var(--space-6);
}
/* 内嵌读数槽：inset 凹陷底 + 小圆角，与席位卡（raised 立起）拉开层级 */
.gauge {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-inset);
  font-size: var(--text-sm);
}
/* 仪表区 / 席位区分隔线（面板刻线） */
.panel-divider {
  height: 1px;
  background: var(--border-hair);
  margin: var(--space-4) 0;
}
.g-label {
  color: var(--text-secondary);
}
.cells {
  display: flex;
  gap: var(--space-1);
}
.cell {
  width: 18px;
  height: 10px;
  border-radius: 2px;
  background: var(--border-hair);
}
.cell--on {
  background: var(--accent);
}
.window {
  color: var(--text-primary);
  font-weight: 600;
}
.seats {
  display: grid;
  gap: var(--space-3);
}
.empty-msg {
  color: var(--text-faint);
  font-size: var(--text-sm);
  padding: var(--space-6);
  text-align: center;
}
.seat {
  display: grid;
  grid-template-columns: 44px 64px 1fr;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
  background: var(--bg-raised);
  border-left: 2px solid transparent;
}
/* 窗口边界可视化（§4.5） */
.seat--locked {
  border-left: 2px solid var(--accent);
}
.seat-no {
  color: var(--text-faint);
  font-size: var(--text-sm);
}
.kind {
  font-size: 10px;
  letter-spacing: var(--ls-micro);
  text-align: center;
  padding: 2px 0;
  border-radius: var(--r-sm);
}
.kind--task {
  color: var(--state-staged);
  border: 1px solid color-mix(in srgb, var(--state-staged) 40%, transparent);
}
.kind--queue {
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent);
}
.seat-body {
  min-width: 0;
}
.seat-line {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.seat-name {
  color: var(--text-primary);
  font-weight: 500;
}
.win-tag {
  font-size: 10px;
  color: var(--accent);
  letter-spacing: var(--ls-micro);
}
.standby {
  font-size: var(--text-xs);
  color: var(--text-faint);
}
.sub {
  margin-top: var(--space-2);
  border-top: 1px solid var(--border-hair);
  padding-top: var(--space-2);
  display: grid;
  gap: var(--space-1);
}
.sub-row {
  display: grid;
  grid-template-columns: 48px 1fr auto;
  gap: var(--space-2);
  align-items: center;
  font-size: var(--text-xs);
}
.m-id {
  color: var(--text-faint);
}
.m-file {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>