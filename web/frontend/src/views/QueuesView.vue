<script setup lang="ts">
/**
 * 02 队列（m0-frontend-design §5 · 表格型，行可展开成员概览）。
 */
import { ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import EmptyState from "@/components/EmptyState.vue";
import StateChip from "@/components/StateChip.vue";
import { useEventsStore } from "@/stores/events";
import { fmtDateTime } from "@/utils/format";

type Queue = components["schemas"]["Queue"];

const events = useEventsStore();
const list = ref<Queue[]>([]);
const loading = ref(false);
const expanded = ref(<Record<string, boolean>>{});

async function load() {
  loading.value = true;
  const { data } = await client.GET("/queues");
  loading.value = false;
  list.value = data ?? [];
}
watch(() => events.dirty.queues, load);
load();

function toggle(id: string) {
  expanded.value[id] = !expanded.value[id];
}

const reasonLabel: Record<string, string> = {
  success: "SUCCESS",
  abort_on_failure: "ABORT ON FAILURE",
  finished_with_failures: "WITH FAILURES",
  manually_stopped: "MANUAL STOP",
};
</script>

<template>
  <section class="queues" :class="{ 'is-loading': loading }">
    <div v-if="!list.length && !loading" class="empty-wrap">
      <EmptyState glyph="▮" text="暂无队列 — 可从候选任务组合创建（M2）" />
    </div>
    <div v-else class="table">
      <div class="thead mono">
        <span>ID</span>
        <span>名称</span>
        <span>成员</span>
        <span>状态</span>
        <span>回退</span>
        <span>结束原因</span>
        <span class="right">已更新</span>
      </div>
      <template v-for="q in list" :key="q.id">
        <div class="row" :class="{ 'row--open': expanded[q.id] }" @click="toggle(q.id)">
          <span class="mono brand">{{ q.id }}</span>
          <span class="name">{{ q.name }}</span>
          <span class="mono count">{{ q.member_ids.length }} 个任务</span>
          <span><StateChip :state="q.state" /></span>
          <span class="mono">
            <span v-if="q.rollback_count" class="rollback">已回退 ×{{ q.rollback_count }}</span>
            <span v-else class="dim">—</span>
          </span>
          <span class="mono dim">{{ q.finish_reason ? reasonLabel[q.finish_reason] : "—" }}</span>
          <span class="mono dim right">{{ fmtDateTime(q.updated_at ?? q.created_at) }}</span>
        </div>
        <div v-if="expanded[q.id]" class="detail">
          <div class="meta mono">
            <span>创建 {{ fmtDateTime(q.created_at) }}</span>
            <span>跳过失败 {{ q.skip_failed ? "ON" : "OFF" }}</span>
            <span v-if="q.last_failure" class="warn">
              上次失败位置 {{ q.last_failure.failure_positions?.join(",") }}
            </span>
          </div>
          <p class="mono label">成员顺序（id）</p>
          <div class="members mono">
            <span v-for="m in q.member_ids" :key="m" class="mem">#{{ m }}</span>
          </div>
        </div>
      </template>
      <div class="scanline" v-if="loading" aria-hidden="true"></div>
    </div>
  </section>
</template>

<style scoped>
.queues {
  position: relative;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
  overflow: hidden;
  background: var(--bg-raised);
}
.empty-wrap {
  padding: var(--space-4);
}
.table {
  min-width: 640px;
}
.thead,
.row {
  display: grid;
  grid-template-columns: 88px 1.3fr 1fr 1fr 1fr 1.2fr 110px;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) var(--space-3);
}
.thead {
  position: sticky;
  top: 0;
  background: var(--bg-raised);
  border-bottom: 1px solid var(--border-hair);
  font-size: var(--text-xs);
  letter-spacing: var(--ls-micro);
  text-transform: uppercase;
  color: var(--text-faint);
}
.row {
  border-bottom: 1px solid var(--border-hair);
  font-size: var(--text-sm);
  cursor: pointer;
  min-height: 44px;
}
.row:hover,
.row--open {
  background: var(--row-hover);
}
.row:last-child {
  border-bottom: none;
}
.brand {
  color: var(--accent);
  font-weight: 600;
}
.name {
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.count {
  color: var(--text-secondary);
}
.rollback {
  color: var(--warn);
}
.dim {
  color: var(--text-faint);
}
.right {
  text-align: right;
}
.detail {
  border-bottom: 1px solid var(--border-hair);
  background: var(--bg-inset);
  padding: var(--space-3) var(--space-4);
  display: grid;
  gap: var(--space-2);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.warn {
  color: var(--warn);
}
.label {
  font-size: var(--text-xs);
  color: var(--text-faint);
  letter-spacing: var(--ls-micro);
}
.members {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.mem {
  font-size: var(--text-xs);
  color: var(--text-primary);
  background: var(--bg-raised);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-sm);
  padding: 2px 8px;
}
.is-loading {
  opacity: 0.4;
}
.scanline {
  height: 1px;
  background: var(--accent);
  animation: scan 1.2s ease-in-out infinite;
}
@keyframes scan {
  0% {
    opacity: 0.5;
    transform: translateX(-100%);
  }
  50%,
  100% {
    opacity: 0.5;
    transform: translateX(100%);
  }
}
/* 竖屏收紧列 */
@media (max-width: 1023px) {
  .thead,
  .row {
    grid-template-columns: 72px 1fr 1fr 90px 90px;
  }
  .thead > :nth-child(5),
  .thead > :nth-child(6),
  .row > :nth-child(5),
  .row > :nth-child(6) {
    display: none;
  }
}
</style>