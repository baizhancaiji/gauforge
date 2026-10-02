<script setup lang="ts">
/**
 * 04 执行中（m0-frontend-design §4.4 通道卡；m1-plan C5 真实化）
 * 页面按「并行上限」渲染等量槽位：在跑任务按通道序填槽为通道卡
 * （CH nnn），空槽为虚线占位框（槽位号 + 横线 + 空闲）。
 * 卡内大号等宽读数由 SSE execution.monitor/progress 驱动，UI 以 1Hz
 * 节流刷新（仪器刷新率语义）；running 态卡描边磷光呼吸；停滞时卡脚
 * 琥珀灯行（翻转即现/隐，只提示不终止）；停止走 danger 二次确认
 * （POST /executions/{id}/stop，归因手动停止）。
 * 8s→3s REST 基线轮询兜底（SSE 死窗口外的卡补齐 + 对账撤卡：REST 运行
 * 列表之外的一律移除，事件丢失场景下幽灵卡 ≤3s 自愈）。
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { client } from "@/api/client";
import ConfirmModal from "@/components/ConfirmModal.vue";
import EmptyState from "@/components/EmptyState.vue";
import StateChip from "@/components/StateChip.vue";
import { useEventsStore, type LiveExecution } from "@/stores/events";
import { fmtDateTime, fmtDuration, fmtMemory, fmtPercent } from "@/utils/format";

interface CardView {
  exec: LiveExecution;
  stall: { last_progress_ts: string | null; threshold_minutes: number | null } | null;
}

const events = useEventsStore();

/** 1Hz 节流快照（§4.4：SSE 原始事件先进 store，UI 每秒取一次，跳变即更新）。 */
const snap = ref<CardView[]>([]);

function refreshSnap() {
  snap.value = Array.from(events.executions.values()).map((exec) => ({
    exec: {
      ...exec,
      monitor: exec.monitor ? { ...exec.monitor } : undefined,
      progress: exec.progress ? { ...exec.progress } : undefined,
    },
    stall: events.stalled.get(exec.id) ?? null,
  }));
}

/** 停滞时长（分钟，自 last_progress_ts 起算）。 */
function stallMinutes(stall: CardView["stall"]): string {
  if (stall?.last_progress_ts) {
    const t = new Date(stall.last_progress_ts).getTime();
    if (!Number.isNaN(t)) return `${Math.max(0, Math.round((Date.now() - t) / 60000))}m`;
  }
  return "";
}

function elapsed(exec: LiveExecution): number | null {
  if (exec.monitor?.elapsed_s != null) return exec.monitor.elapsed_s;
  if (exec.started_at) {
    const s = new Date(exec.started_at).getTime();
    if (!Number.isNaN(s)) return Math.max(0, (Date.now() - s) / 1000);
  }
  return null;
}

/** SCF 读数「x-y」：x=第几轮 SCF（scf_round），y=轮内圈数（scf_cycle）。
 * 旧载荷缺 scf_round 时退单圈数值，两者皆缺显示占位符。 */
function scfDisplay(exec: LiveExecution): string {
  const p = exec.progress;
  if (p?.scf_round != null && p?.scf_cycle != null) {
    return `${p.scf_round}-${p.scf_cycle}`;
  }
  return p?.scf_cycle != null ? String(p.scf_cycle) : "—";
}

let pollId: number | null = null;
let tickId: number | null = null;

async function pollRunning() {
  try {
    const { data } = await client.GET("/executions", {
      params: { query: { state: "running" } },
    });
    const rows = data ?? [];
    rows.forEach((e) => events.push(e as unknown as LiveExecution));
    // 基线对账：仅成功响应时撤除列表之外的卡（服务不可达窗口保持现状，
    // 连接恢复后基线回流）
    events.pruneExecutions(new Set(rows.map((e) => Number(e.id))));
  } catch {
    /* 服务不可达（重启窗口）：保持现状，连接恢复后基线回流 */
  }
  refreshSnap();
}

onMounted(async () => {
  await pollRunning();
  // 轻量基线回流：SSE 只在死窗口外广播运行态，周期轮询补齐"30s 间隙中被
  // upsert 建出但缺真实文件名/基线的卡"（monitor/progress 首个事件已含读数），
  // 并对账撤除已终态/丢失事件的幽灵卡（3s 自愈，见 pollRunning）。
  pollId = window.setInterval(pollRunning, 3000);
  // UI 1Hz 节流刷新（§4.4 读数节流）。
  tickId = window.setInterval(refreshSnap, 1000);
});

onBeforeUnmount(() => {
  if (pollId != null) window.clearInterval(pollId);
  if (tickId != null) window.clearInterval(tickId);
});

// 并行上限 = 运行级设置 parallel_window（pending 快照 window_size 字段）；
// 在跑数与可用数已在其旁读出，不再重复用英文代号表达。
const windowSize = computed(() => events.pending?.window_size ?? 0);
// 当前可用并行槽位 = 上限 − 在跑数（下限 0）。
const available = computed(() => Math.max(0, windowSize.value - snap.value.length));
// 在跑卡按执行 id 升序稳定占槽（CH 编号序），其余槽位渲染为空闲占位框。
const sortedCards = computed(() => [...snap.value].sort((a, b) => a.exec.id - b.exec.id));
const placeholderCount = computed(() => Math.max(0, windowSize.value - sortedCards.value.length));

// 断连窗口（SSE 非 open）：读数降档并标注延迟，避免陈值误读（§4.4）。
const stale = computed(() => events.connection !== "open");

// ---------- 手动停止（二次确认 → cancel → 归因 manually_stopped） ----------
const stopping = ref<LiveExecution | null>(null);
const stopLoading = ref(false);
const stopError = ref<string | null>(null);

function openStop(exec: LiveExecution) {
  stopError.value = null; // 清掉上一次失败的残留提示
  stopping.value = exec;
}

async function confirmStop() {
  const exec = stopping.value;
  if (!exec) return;
  stopLoading.value = true;
  stopError.value = null;
  const { error } = await client.POST("/executions/{id}/stop", {
    params: { path: { id: exec.id } },
  });
  stopLoading.value = false;
  if (error) {
    const body = error as unknown as { error?: { message?: string } };
    stopError.value = body.error?.message ?? "停止失败";
    return;
  }
  stopping.value = null; // 终态卡移除由 history.appended 事件驱动
}
</script>

<template>
  <div>
    <div class="run-meta mono">
      <span class="meta-item">并行上限 {{ windowSize || "—" }}</span>
      <span class="meta-item">在跑 {{ snap.length }} / 可用 {{ available }}</span>
      <span v-if="stale" class="meta-item stale-note mono" role="status">
        连接中断 · 读数延迟
      </span>
    </div>

    <!-- 快照未达的首帧兜底（正常运行时窗口数已知，不出现整页空态） -->
    <div v-if="!windowSize && !snap.length" class="empty-wrap">
      <EmptyState glyph="▦" text="读取并行上限 …" />
    </div>

    <div v-else class="grid">
      <article
        v-for="card in sortedCards"
        :key="card.exec.id"
        class="card"
        :class="{ 'card--running': card.exec.monitor || card.exec.progress?.opt_step != null || card.exec.progress?.scf_round != null }"
      >
        <header class="head">
          <span class="ch mono">CH {{ String(card.exec.id).padStart(3, "0") }}</span>
          <StateChip state="running" loud />
        </header>

        <p class="file mono" :title="card.exec.filename">{{ card.exec.filename }}</p>
        <!-- 出处分两行排布：上行「队列/提交」左对齐、「启动」右对齐；
             下行「已运行」独立左对齐（无圆点分隔，文案纪律） -->
        <p class="meta mono">
          <span class="meta-row">
            <span class="meta-l">
              <span v-if="card.exec.queue_id" class="q">队列 {{ card.exec.queue_id }}</span>
              <span>提交 {{ fmtDateTime(card.exec.submitted_at) }}</span>
            </span>
            <span>启动 {{ fmtDateTime(card.exec.started_at) }}</span>
          </span>
          <span class="meta-row">已运行 {{ fmtDuration(elapsed(card.exec)) }}</span>
        </p>

        <div class="readouts" :class="{ 'readouts--stale': stale }" aria-live="off">
          <div class="ro">
            <div class="n mono">{{ fmtPercent(card.exec.monitor?.cpu_percent) }}</div>
            <div class="l mono zh">CPU 占用</div>
          </div>
          <div class="ro">
            <div class="n mono">{{ fmtMemory(card.exec.monitor?.mem_rss_mb) }}</div>
            <div class="l mono zh">内存 RSS</div>
          </div>
          <div class="ro ro--sub">
            <div class="n mono">{{ card.exec.progress?.opt_step ?? "—" }}</div>
            <div class="l mono">OPT STEP</div>
          </div>
          <div class="ro ro--sub">
            <div class="n mono">{{ scfDisplay(card.exec) }}</div>
            <div class="l mono">SCF RUN-CYCLE</div>
          </div>
        </div>

        <footer class="foot">
          <!-- 停滞琥珀灯行（翻转即现/隐；只提示不终止，红线） -->
          <span v-if="card.stall" class="stall mono">
            <i class="stall-dot" aria-hidden="true"></i>
            停滞告警 {{ stallMinutes(card.stall) }}
          </span>
          <span v-else class="quiet mono">{{ card.exec.progress?.last_line ?? "" }}</span>
          <button class="btn btn--danger stop" type="button" @click="openStop(card.exec)">
            停止
          </button>
        </footer>
      </article>

      <!-- 空闲占位槽（§4.4）：虚线框，居中槽位号，横线分隔，下注「空闲」 -->
      <div v-for="i in placeholderCount" :key="`slot-${i}`" class="slot">
        <span class="slot-no mono">{{ sortedCards.length + i }}</span>
        <span class="slot-line" aria-hidden="true"></span>
        <span class="slot-zh">空闲</span>
      </div>
    </div>

    <!-- 停止二次确认（§4.6 危险确认模态） -->
    <ConfirmModal
      :open="stopping != null"
      title="停止执行"
      danger
      confirm-text="停止"
      :loading="stopLoading"
      @confirm="confirmStop"
      @close="stopping = null"
    >
      <p class="confirm-line">
        将停止执行
        <span class="mono strong">CH {{ String(stopping?.id ?? "").padStart(3, "0") }} · {{ stopping?.filename }}</span>
        并取消对应 HQ 任务，归因「手动停止」后进历史
      </p>
      <p v-if="stopError" class="confirm-error mono" role="alert">{{ stopError }}</p>
    </ConfirmModal>
  </div>
</template>

<style scoped>
.run-meta {
  display: flex;
  gap: var(--space-6);
  margin-bottom: var(--space-4);
  font-size: var(--text-sm); /* 文案含中文（在跑/可用）：混排纪律 1 */
  color: var(--text-faint);
}
.empty-wrap {
  margin-top: var(--space-4);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--channel-card-width), 1fr));
  gap: var(--gap-card);
}
/* 空闲占位槽（§4.4）：与通道卡同网格轨，虚线框 + 居中槽位号 + 横线 + 空闲 */
.slot {
  border: 1px dashed var(--border-strong);
  border-radius: var(--r-md);
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
}
.slot-no {
  font-size: var(--text-lg);
  font-variant-numeric: tabular-nums;
  color: var(--text-faint);
  line-height: 1.1;
}
.slot-line {
  width: 72px;
  height: 1px;
  background: var(--border-strong);
}
.slot-zh {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.card {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
}
/* running 态卡描边磷光呼吸（§4.4；reduced-motion 全局关闭） */
.card--running {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  animation: cardpulse var(--dur-breathe) ease-in-out infinite;
}
@keyframes cardpulse {
  0%,
  100% {
    box-shadow: var(--glow-running);
  }
  50% {
    box-shadow:
      0 0 0 1px color-mix(in srgb, var(--accent) 20%, transparent),
      0 0 6px color-mix(in srgb, var(--accent) 5%, transparent);
  }
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ch {
  font-size: var(--text-xs);
  letter-spacing: var(--ls-wide);
  color: var(--text-faint);
}
.file {
  font-size: var(--text-md);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  font-size: var(--text-sm);
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}
.meta-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-3);
}
.meta-row + .meta-row {
  margin-top: var(--space-1);
}
.meta-l {
  display: flex;
  gap: var(--space-2);
  min-width: 0;
}
.readouts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-5);
  transition: opacity var(--dur-view) var(--ease-std);
}
/* 断连窗口读数降档（陈值不误读为实时；重连 open 后恢复） */
.readouts--stale {
  opacity: 0.45;
}
.stale-note {
  color: var(--warn);
}
.ro .n {
  font-size: var(--text-readout);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  line-height: 1.1;
}
.ro--sub .n {
  font-size: var(--text-lg);
}
.ro .l {
  /* 纯拉丁读数标签档（OPT STEP/SCF CYCLE） */
  font-size: var(--text-2xs);
  letter-spacing: var(--ls-wide);
  color: var(--text-faint);
  margin-top: 3px;
}
/* 承载中文的读数标签（CPU 占用/内存 RSS）：混排纪律 1 升档去字距 */
.ro .l.zh {
  font-size: var(--text-sm);
  letter-spacing: 0;
}
.foot {
  border-top: 1px solid var(--border-hair);
  padding-top: var(--space-3);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  min-height: 32px;
}
.stall {
  font-size: var(--text-sm);
  color: var(--warn);
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.stall-dot {
  width: var(--dot-size);
  height: var(--dot-size);
  border-radius: 50%;
  background: var(--warn);
  animation: stallbreathe 1.6s ease-in-out infinite;
}
@keyframes stallbreathe {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}
.quiet {
  font-size: var(--text-2xs); /* g16 输出末行回显（机器文本，非界面文案） */
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.stop {
  height: 26px;
  padding: 0 var(--space-3);
  font-size: var(--text-sm); /* 文案含中文（停止） */
  flex: none;
}
.confirm-line {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.confirm-line .strong {
  color: var(--text-primary);
}
.confirm-error {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--danger);
}
</style>
