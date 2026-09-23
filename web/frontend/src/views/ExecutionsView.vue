<script setup lang="ts">
/**
 * 04 执行中（m0-frontend-design §4.3 通道卡）
 * 每在跑任务一张编号通道卡（CH nn），大号等宽读数由 SSE
 * execution.monitor/progress/stalled 驱动跳变；running 态卡描边磷光呼吸。
 * 数据源：events store 实时 map（SSE 键控 execution_id）；首帧回落 GET /executions。
 */
import { computed, onBeforeUnmount, onMounted } from "vue";

import { client } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
import StateChip from "@/components/StateChip.vue";
import { useEventsStore, type LiveExecution } from "@/stores/events";
import { fmtClock, fmtDuration, fmtMemory, fmtPercent } from "@/utils/format";

const events = useEventsStore();

const stalledIds = computed(() => events.stalled);
const cards = computed(() => Array.from(events.executions.entries()));

function elapsed(exec: LiveExecution): number | null {
  if (exec.monitor?.elapsed_s != null) return exec.monitor.elapsed_s;
  if (exec.started_at) {
    const s = new Date(exec.started_at).getTime();
    if (!Number.isNaN(s)) return Math.max(0, (Date.now() - s) / 1000);
  }
  return null;
}

let pollId: number | null = null;

async function pollRunning() {
  const { data } = await client.GET("/executions", { params: { query: { state: "running" } } });
  (data ?? []).forEach((e) => events.push(e as unknown as LiveExecution));
}

onMounted(async () => {
  await pollRunning();
  // 轻量基线回流：SSE 只在死窗口外广播运行态，周期轮询补齐"30s 间隙中被
  // upsert 建出但缺真实文件名/基线的卡"（monitor/progress 首个事件已含读数）。
  pollId = window.setInterval(pollRunning, 8000);
});

onBeforeUnmount(() => {
  if (pollId != null) window.clearInterval(pollId);
});

// WINDOW = 当前并行执行数（window_size，来自 pending 快照）；不是排队数。
const windowSize = computed(() => events.pending?.window_size ?? 0);
// 当前可用并行槽位 = 窗口 − 在跑数（下限 0）。
const available = computed(() => Math.max(0, windowSize.value - cards.value.length));
</script>

<template>
  <div>
    <div class="run-meta mono">
      <span class="meta-item">WINDOW {{ windowSize || "—" }}</span>
      <span class="meta-item">在跑 {{ cards.length }} / 可用 {{ available }}</span>
    </div>

    <div v-if="!cards.length" class="empty-wrap">
      <EmptyState glyph="▦" :text="`暂无在跑任务 — 窗口 ${windowSize || 0} 空闲`" />
    </div>

    <div v-else class="grid">
      <article
        v-for="[eid, exec] in cards"
        :key="eid"
        class="card"
        :class="{ 'card--running': exec.monitor || exec.progress?.opt_step != null }"
      >
        <header class="head">
          <span class="ch mono">CH {{ String(exec.id).padStart(3, "0") }}</span>
          <StateChip state="running" />
        </header>

        <p class="file mono">{{ exec.filename }}</p>
        <p class="meta mono" v-if="exec.queue_id">队列 {{ exec.queue_id }}</p>

        <div class="times mono">
          <span>提交 {{ fmtClock(exec.submitted_at) }}</span>
          <span>启动 {{ fmtClock(exec.started_at) }}</span>
          <span>已运行 {{ fmtDuration(elapsed(exec)) }}</span>
        </div>

        <div v-if="stalledIds.has(exec.id)" class="stall mono">
          停滞已过阈值
        </div>

        <div class="readouts">
          <div class="rg">
            <span class="rg-label mono">CPU</span>
            <span class="rg-val mono">{{ fmtPercent(exec.monitor?.cpu_percent) }}</span>
          </div>
          <div class="rg">
            <span class="rg-label mono">MEM</span>
            <span class="rg-val mono">{{ fmtMemory(exec.monitor?.mem_rss_mb) }}</span>
          </div>
          <div class="rg rg--sub">
            <span class="rg-label mono">OPT STEP</span>
            <span class="rg-val mono">{{ exec.progress?.opt_step ?? "—" }}</span>
          </div>
          <div class="rg rg--sub">
            <span class="rg-label mono">SCF CYCLE</span>
            <span class="rg-val mono">{{ exec.progress?.scf_cycle ?? "—" }}</span>
          </div>
        </div>

        <p v-if="exec.progress?.last_line" class="tail mono">{{ exec.progress.last_line }}</p>
      </article>
    </div>
  </div>
</template>

<style scoped>
.run-meta {
  display: flex;
  gap: var(--space-6);
  margin-bottom: var(--space-4);
  font-size: var(--text-xs);
  color: var(--text-faint);
}
.empty-wrap {
  margin-top: var(--space-4);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--channel-card-width), 1fr));
  gap: var(--space-5);
}
.card {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
  background: var(--bg-raised);
  box-shadow: var(--inset-highlight);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
}
/* running 态卡描边磷光呼吸（§4.4；reduced-motion 全局关闭） */
.card--running {
  box-shadow: var(--inset-highlight), var(--glow-running);
  animation: breathe 2.4s ease-in-out infinite;
}
@keyframes breathe {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.72;
  }
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ch {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.file {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  font-size: var(--text-xs);
  color: var(--text-faint);
}
.times {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  border-top: 1px solid var(--border-hair);
  padding-top: var(--space-3);
}
.stall {
  font-size: var(--text-xs);
  color: var(--warn);
}
.readouts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  border-top: 1px solid var(--border-hair);
  padding-top: var(--space-3);
}
.rg {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rg--sub .rg-val {
  font-size: var(--text-lg);
}
.rg-label {
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--text-faint);
}
.rg-val {
  font-size: var(--text-readout);
  line-height: 1;
  color: var(--text-primary);
}
.tail {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  border-top: 1px solid var(--border-hair);
  padding-top: var(--space-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>