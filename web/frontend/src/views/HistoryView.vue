<script setup lang="ts">
/**
 * 05 历史 / 归档（m0-frontend-design §5 · 表格型全宽；m1-plan C6 真实化）
 * 全宽表格（id/任务/状态徽标/归因/提交/结束/耗时/资源/队列归属）+ 顶部状态筛选；
 * 行点击 → 详情抽屉：终态冻结全字段 + 输入查看 / 输出预览（限高滚动）与
 * ?download=true 导出 + 归档 + failed/skipped 重新排队与退回候选（409 提示）
 * + 清理入口（统计回显）。归档视图承载 archived=true（独立路由 /archive，
 * 决策点 10），仅保留查看动作。
 */
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { client, getText } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";
import EmptyState from "@/components/EmptyState.vue";
import StateChip from "@/components/StateChip.vue";
import { useEventsStore } from "@/stores/events";
import { fmtDateTime, fmtDuration, fmtHash, fmtMemory, fmtPercent } from "@/utils/format";
import { causeLabel } from "@/utils/labels";

type HistoryEntry = components["schemas"]["HistoryEntry"];

const route = useRoute();
const events = useEventsStore();

/** 归档模式（/archive 独立路由）：只读视图 + 输入/输出查看。 */
const archived = computed(() => route.meta.archived === true);

const list = ref<HistoryEntry[]>([]);
const total = ref(0);
const loading = ref(false);
const everLoaded = ref(false);
const filter = ref<"all" | "succeeded" | "failed" | "skipped">("all");
/** 排序（openapi HistorySort）：默认提交倒序（上线前行为）。 */
const sort = ref<components["schemas"]["HistorySort"]>("submitted_desc");
const selected = ref<HistoryEntry | null>(null);
const textView = ref<{ kind: "input" | "output"; content: string; error: string | null } | null>(null);
const actionNote = ref<{ ok: boolean; msg: string } | null>(null);

async function load() {
  loading.value = true;
  const { data } = await client.GET("/history", {
    params: {
      query: {
        ...(filter.value === "all" ? {} : { state: filter.value }),
        archived: archived.value,
        sort: sort.value,
        page: 1,
        page_size: 100,
      },
    },
  });
  loading.value = false;
  everLoaded.value = true;
  if (data) {
    list.value = (data.items as HistoryEntry[]) ?? [];
    total.value = data.total ?? 0;
  }
}

// history.appended（终态落库）→ 重拉当前页；路由切换（历史↔归档）重载。
watch(() => events.dirty.history, load);
watch(
  () => route.fullPath,
  () => {
    everLoaded.value = false;
    selected.value = null;
    load();
  },
);
load();

async function open(e: HistoryEntry) {
  selected.value = e;
  textView.value = null;
  actionNote.value = null;
  const { data } = await client.GET("/history/{id}", { params: { path: { id: e.id } } });
  if (data) selected.value = data;
}

const activeId = computed(() => selected.value?.id ?? null);
const canRequeue = computed(
  () => selected.value?.state === "failed" || selected.value?.state === "skipped",
);

// ---------- 输入查看 / 输出预览与导出（?download=true） ----------
async function viewText(kind: "input" | "output") {
  const e = selected.value;
  if (!e) return;
  textView.value = { kind, content: "", error: null };
  // 两端点契约均为 text/plain，经 getText 统一按文本取（封装动机见 api/client.ts）
  const res =
    kind === "input"
      ? await getText("/history/{id}/input", e.id)
      : await getText("/history/{id}/output", e.id);
  if (res.error) {
    textView.value = {
      kind,
      content: "",
      error: kind === "output" ? "无输出文件（任务可能未产生输出）" : "无输入文件",
    };
    return;
  }
  textView.value = { kind, content: (res.data as unknown as string) ?? "", error: null };
}

const outputUrl = computed(() =>
  selected.value ? `/api/v1/history/${selected.value.id}/output?download=true` : "",
);

// ---------- 归档（冻结后唯一可变操作） ----------
const archiveLoading = ref(false);

async function archive() {
  const e = selected.value;
  if (!e) return;
  archiveLoading.value = true;
  await client.POST("/history/{id}/archive", { params: { path: { id: e.id } } });
  archiveLoading.value = false;
  selected.value = null;
  load();
}

// ---------- 重新排队 / 退回候选（failed/skipped；满员 409） ----------
const actLoading = ref(false);

async function requeue() {
  const e = selected.value;
  if (!e) return;
  actLoading.value = true;
  const { data, error } = await client.POST("/history/{id}/requeue", {
    params: { path: { id: e.id } },
  });
  actLoading.value = false;
  if (error) {
    setActionError(error);
    return;
  }
  if (data) actionNote.value = { ok: true, msg: `已入待执行队列 S${data.seat_id}` };
}

async function returnCandidate() {
  const e = selected.value;
  if (!e) return;
  actLoading.value = true;
  const { data, error } = await client.POST("/history/{id}/return-candidate", {
    params: { path: { id: e.id } },
  });
  actLoading.value = false;
  if (error) {
    setActionError(error);
    return;
  }
  if (data) actionNote.value = { ok: true, msg: `已退回候选 #${data.id}` };
}

function setActionError(error: unknown) {
  const body = error as unknown as { error?: { code?: string; message?: string } };
  actionNote.value = {
    ok: false,
    msg:
      body.error?.code === "PENDING_CAPACITY_FULL"
        ? "在途席位满员 — 请先移除席位或调高上限"
        : (body.error?.message ?? "操作失败"),
  };
}

// ---------- chk/rwf 清理（手动触发，统计回显） ----------
const cleanupOpen = ref(false);
const cleanupLoading = ref(false);
const cleanupNote = ref<string | null>(null);

async function confirmCleanup() {
  cleanupLoading.value = true;
  const { data } = await client.POST("/history/cleanup");
  cleanupLoading.value = false;
  cleanupOpen.value = false;
  if (data) {
    cleanupNote.value = `清理完成 — 检查 ${data.checked} 项 · 移除 chk ${data.removed_chk} · rwf ${data.removed_rwf}`;
  }
}
</script>

<template>
  <div class="history">
    <div class="controls">
      <label v-if="!archived" class="mono filter">
        <span>状态筛选</span>
        <select v-model="filter" @change="load">
          <option value="all">全部</option>
          <option value="succeeded">SUCCEEDED</option>
          <option value="failed">FAILED</option>
          <option value="skipped">SKIPPED</option>
        </select>
      </label>
      <label class="mono filter">
        <span>排序</span>
        <select v-model="sort" @change="load">
          <option value="submitted_desc">提交时间 · 新→旧</option>
          <option value="finished_desc">完成时间 · 新→旧</option>
          <option value="finished_asc">完成时间 · 旧→新</option>
          <option value="filename_asc">文件名 · A→Z</option>
          <option value="filename_desc">文件名 · Z→A</option>
        </select>
      </label>
      <span class="mono count">共 {{ total }}</span>

      <span class="spacer"></span>
      <RouterLink v-if="!archived" class="btn btn--secondary" to="/archive">归档视图</RouterLink>
      <RouterLink v-else class="btn btn--secondary" to="/history">返回历史</RouterLink>
      <button
        v-if="!archived"
        class="btn btn--secondary"
        type="button"
        @click="cleanupOpen = true"
      >
        清理 chk/rwf
      </button>
      <span v-if="cleanupNote" class="cleanup-note mono">{{ cleanupNote }}</span>
    </div>

    <div v-if="!everLoaded" class="skel" aria-hidden="true">
      <div v-for="i in 4" :key="i" class="sk-row"></div>
    </div>

    <div v-else-if="!list.length" class="empty-wrap">
      <EmptyState
        glyph="▯"
        :text="archived ? '暂无归档条目 — 在历史详情中归档后显示于此' : '暂无历史记录 — 任务结束后显示于此'"
      />
    </div>

    <section v-else class="table">
      <div class="thead mono">
        <span>ID</span>
        <span>任务</span>
        <span>状态</span>
        <span>归因</span>
        <span>提交</span>
        <span>结束</span>
        <span>耗时</span>
        <span>资源</span>
        <span>出处</span>
      </div>
      <div
        v-for="h in list"
        :key="h.id"
        class="row"
        :class="{ 'row--active': activeId === h.id }"
        @click="open(h)"
      >
        <span class="mono dim">{{ String(h.id).padStart(3, "0") }}</span>
        <span class="mono file" :title="h.filename">{{ h.filename }}</span>
        <span><StateChip :state="h.state" /></span>
        <span class="mono dim">{{ h.cause ? causeLabel[h.cause] : "—" }}</span>
        <span class="mono dim">{{ fmtDateTime(h.submitted_at) }}</span>
        <span class="mono dim">{{ fmtDateTime(h.finished_at) }}</span>
        <span class="mono">{{ fmtDuration(h.wall_time_s) }}</span>
        <span class="mono dim">
          {{ h.resources.nproc.value }}C{{ h.resources.nproc.defaulted ? "*" : "" }} /
          {{ h.resources.mem_gb.value }}G{{ h.resources.mem_gb.defaulted ? "*" : "" }}
        </span>
        <span class="mono dim">{{ h.queue_id ?? "直提" }}</span>
      </div>
      <div class="scanline" aria-hidden="true" v-if="loading"></div>
    </section>

    <!-- 详情抽屉（行点击；终态冻结字段全量） -->
    <div v-if="selected" class="scrim" @click.self="selected = null">
      <aside class="drawer">
        <header class="d-head">
          <span class="d-title mono">
            {{ String(selected.id).padStart(3, "0") }} — {{ selected.filename }}
          </span>
          <StateChip :state="selected.state" />
        </header>

        <dl class="cell">
          <dt class="mono">状态 / 归因</dt>
          <dd>{{ selected.cause ? causeLabel[selected.cause] : "正常结束" }}</dd>
        </dl>
        <dl class="cell">
          <dt class="mono">提交 / 启动 / 结束</dt>
          <dd class="mono">{{ fmtDateTime(selected.submitted_at) }}</dd>
          <dd class="mono">{{ fmtDateTime(selected.started_at) }}</dd>
          <dd class="mono">{{ fmtDateTime(selected.finished_at) }}</dd>
        </dl>
        <dl class="cell">
          <dt class="mono">耗时</dt>
          <dd class="mono">{{ fmtDuration(selected.wall_time_s) }}</dd>
        </dl>
        <dl class="cell">
          <dt class="mono">输入哈希</dt>
          <dd class="mono" :title="selected.input_hash ?? ''">{{ fmtHash(selected.input_hash) }}</dd>
        </dl>
        <dl class="cell">
          <dt class="mono">资源（声明/补齐）</dt>
          <dd class="mono">
            CPU {{ selected.resources.nproc.value }}
            （{{ selected.resources.nproc.defaulted ? "默认补齐" : "声明" }}）
          </dd>
          <dd class="mono">
            MEM {{ selected.resources.mem_gb.value }} GB
            （{{ selected.resources.mem_gb.defaulted ? "默认补齐" : "声明" }}）
          </dd>
        </dl>
        <dl class="cell">
          <dt class="mono">HQ 任务 / 出处</dt>
          <dd class="mono">{{ selected.hq_job_id ?? "—" }} · {{ selected.queue_id ?? "直接提交" }}</dd>
        </dl>
        <dl v-if="selected.monitor_summary" class="cell">
          <dt class="mono">监控峰值</dt>
          <dd class="mono">
            CPU {{ fmtPercent(selected.monitor_summary.cpu_peak_percent) }} / MEM
            {{ fmtMemory(selected.monitor_summary.mem_peak_mb) }}
          </dd>
          <dd class="mono">
            停滞告警 {{ selected.monitor_summary.stall_alerts ?? 0 }} 次 · 累计
            {{ fmtDuration((selected.monitor_summary.stall_total_minutes ?? 0) * 60) }}
          </dd>
        </dl>
        <dl class="cell">
          <dt class="mono">chk 保全</dt>
          <dd class="mono">
            {{ selected.chk_snapshot.protected ? "已保全（protected/）" : "未保全"
            }}{{ selected.chk_snapshot.location ? ` — ${selected.chk_snapshot.location}` : "" }}
          </dd>
        </dl>
        <dl class="cell">
          <dt class="mono">结果引用（M3 占位）</dt>
          <dd class="mono">{{ selected.result_ref ?? "—" }}</dd>
        </dl>

        <p v-if="actionNote" class="note mono" :class="actionNote.ok ? 'note--ok' : 'note--bad'">
          {{ actionNote.msg }}
        </p>

        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="viewText('input')">输入</button>
          <button class="btn btn--secondary" type="button" @click="viewText('output')">输出</button>
          <a class="btn btn--ghost" :href="outputUrl">导出 .log</a>
          <template v-if="!archived">
            <button
              v-if="canRequeue"
              class="btn btn--secondary"
              type="button"
              :disabled="actLoading"
              @click="requeue"
            >
              重新排队
            </button>
            <button
              v-if="canRequeue"
              class="btn btn--secondary"
              type="button"
              :disabled="actLoading"
              @click="returnCandidate"
            >
              退回候选
            </button>
            <button
              v-if="!selected.archived"
              class="btn btn--danger"
              type="button"
              :disabled="archiveLoading"
              @click="archive"
            >
              归档
            </button>
            <span v-else class="mono archived-tag">已归档</span>
          </template>
          <button class="btn btn--ghost" type="button" @click="selected = null">关闭</button>
        </div>

        <div v-if="textView" class="text-view">
          <header class="tv-head">
            <span class="mono">{{ textView.kind === "input" ? "输入原文" : "输出预览" }}</span>
            <button class="btn btn--ghost" type="button" @click="textView = null">×</button>
          </header>
          <pre v-if="textView.error" class="tv-body mono">{{ textView.error }}</pre>
          <pre v-else class="tv-body mono">{{ textView.content || "读取中 …" }}</pre>
        </div>
      </aside>
    </div>

    <!-- 清理确认（仅删正常结束且超保留期的 chk/rwf，永不触碰输出/输入） -->
    <ConfirmModal
      :open="cleanupOpen"
      title="清理 chk/rwf"
      danger
      confirm-text="清理"
      :loading="cleanupLoading"
      @confirm="confirmCleanup"
      @close="cleanupOpen = false"
    >
      <p class="confirm-line">
        仅删除「正常结束且超过保留期」任务的 chk/rwf 中间文件；输出与输入文件永不触碰；
        非正常终止的保全快照不受影响
      </p>
    </ConfirmModal>
  </div>
</template>

<style scoped>
.history {
  position: relative;
  min-width: 0;
}
.controls {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}
.spacer {
  flex: 1;
}
.filter {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.count {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.cleanup-note {
  font-size: var(--text-sm);
  color: var(--state-succeeded);
}
.table {
  position: relative;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--bg-raised);
  min-width: 760px;
}
.thead,
.row {
  display: grid;
  grid-template-columns: 48px 1.2fr 1fr 1fr 1fr 1fr 90px 1fr 70px;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
}
.thead {
  position: sticky;
  top: 0;
  background: var(--bg-raised);
  border-bottom: 1px solid var(--border-hair);
  /* 表头承载中文（混排纪律 1）：升 --text-sm、去字距 */
  font-size: var(--text-sm);
  text-transform: uppercase;
  color: var(--text-faint);
}
.row {
  border-bottom: 1px solid var(--border-hair);
  cursor: pointer;
  min-height: 40px; /* §4.3 行高 40px */
  transition: background-color 120ms var(--ease-std);
}
.row:last-child {
  border-bottom: none;
}
.row:hover,
.row--active {
  background: var(--row-hover);
}
.file {
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dim {
  color: var(--text-faint);
}
.scanline {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: var(--accent);
  /* 引用 base.css 共用 scanline（--ease-std），不重复定义 keyframes */
  animation: scanline 1.2s var(--ease-std) infinite;
}
.skel {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--bg-raised);
}
.sk-row {
  height: 40px;
  border-bottom: 1px solid var(--border-hair);
  background: var(--bg-inset);
  animation: row-in 220ms var(--ease-std) both;
}
.sk-row:nth-child(2) {
  animation-delay: 18ms;
}
.sk-row:nth-child(3) {
  animation-delay: 36ms;
}
.sk-row:nth-child(4) {
  animation-delay: 54ms;
}
.empty-wrap {
  margin-top: var(--space-4);
}
/* ---------- 详情抽屉（§6：右滑入 200ms --ease-std） ---------- */
.scrim {
  position: fixed;
  inset: 0;
  z-index: var(--z-dropdown);
  background: var(--backdrop-dim);
  display: flex;
  justify-content: flex-end;
}
.drawer {
  width: 380px;
  height: 100%;
  background: var(--bg-overlay);
  border-left: 1px solid var(--border-hair);
  padding: var(--space-5);
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  animation: slide 200ms var(--ease-std);
}
@keyframes slide {
  from {
    transform: translateX(100%);
  }
  to {
    transform: none;
  }
}
.d-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-hair);
}
.d-title {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
}
.cell {
  margin: 0;
  border-top: 1px solid var(--border-hair);
  padding-top: var(--space-3);
}
.cell dt {
  font-size: var(--text-sm); /* 承载中文（状态 / 归因 等） */
  color: var(--text-faint);
  margin-bottom: var(--space-1);
}
.cell dd {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.note {
  font-size: var(--text-sm);
}
.note--ok {
  color: var(--state-succeeded);
}
.note--bad {
  color: var(--danger);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.archived-tag {
  font-size: var(--text-sm);
  color: var(--state-archived);
  align-self: center;
}
.text-view {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-inset);
  overflow: hidden;
}
.tv-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-hair);
  font-size: var(--text-sm); /* 文案含中文（输入原文/输出预览） */
  color: var(--text-faint);
}
/* 输出预览限高滚动（C6） */
.tv-body {
  margin: 0;
  padding: var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow: auto;
}
.confirm-line {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
</style>
