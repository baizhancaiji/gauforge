<script setup lang="ts">
/**
 * 05 历史（m0-frontend-design §5 · 表格型全宽）
 * 顶部状态筛选；行点击 → 右侧详情抽屉（终态冻结字段全量 + 查看输入/输出 + 归档）。
 * 归档条目不列于此（归档页 M1 独立路由，决策点 10）。
 */
import { computed, ref } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import EmptyState from "@/components/EmptyState.vue";
import StateChip from "@/components/StateChip.vue";
import { fmtDateTime, fmtDuration, fmtHash, fmtMemory, fmtPercent } from "@/utils/format";

type HistoryEntry = components["schemas"]["HistoryEntry"];

const list = ref<HistoryEntry[]>([]);
const total = ref(0);
const loading = ref(false);
const filter = ref<"all" | "succeeded" | "failed" | "skipped">("all");
const selected = ref<HistoryEntry | null>(null);
const textView = ref<{ kind: "input" | "output"; content: string; loading: boolean } | null>(null);

const causeLabel: Record<string, string> = {
  manually_stopped: "手动停止",
  program_error: "程序错误",
  external_interrupt: "外部中断",
  predecessor_failed: "前驱失败",
  queue_manually_stopped: "队列停止",
};

async function load() {
  loading.value = true;
  const { data } = await client.GET("/history", {
    params: {
      query: {
        ...(filter.value === "all" ? {} : { state: filter.value }),
        archived: false,
        page: 1,
        page_size: 100,
      },
    },
  });
  loading.value = false;
  if (data) {
    list.value = (data.items as HistoryEntry[]) ?? [];
    total.value = data.total ?? 0;
  }
}
load();

async function open(e: HistoryEntry) {
  selected.value = e;
  const { data } = await client.GET("/history/{id}", { params: { path: { id: e.id } } });
  if (data) selected.value = data;
}

const activeId = computed(() => selected.value?.id ?? null);

async function viewText(kind: "input" | "output") {
  const e = selected.value;
  if (!e) return;
  // M0：正文占位；M1 接 GET /history/{id}/input|output。
  textView.value = { kind, content: "", loading: true };
}

async function archive(e: HistoryEntry) {
  await client.POST("/history/{id}/archive", { params: { path: { id: e.id } } });
  e.archived = true;
}
</script>

<template>
  <div class="history">
    <div class="controls">
      <label class="mono filter">
        <span>状态筛选</span>
        <select v-model="filter" @change="load">
          <option value="all">全部</option>
          <option value="succeeded">SUCCEEDED</option>
          <option value="failed">FAILED</option>
          <option value="skipped">SKIPPED</option>
        </select>
      </label>
      <span class="mono count">共 {{ total }}</span>
    </div>

    <div v-if="!list.length && !loading" class="empty-wrap">
      <EmptyState glyph="▯" text="暂无历史记录 — 任务结束后显示于此" />
    </div>

    <section v-else class="table" :class="{ 'is-loading': loading }">
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
        <span class="mono file">{{ h.filename }}</span>
        <span><StateChip :state="h.state" :label="h.archived ? 'ARCHIVED' : undefined" /></span>
        <span class="mono dim">{{ h.cause ? causeLabel[h.cause] : "—" }}</span>
        <span class="mono dim">{{ fmtDateTime(h.submitted_at) }}</span>
        <span class="mono dim">{{ fmtDateTime(h.finished_at) }}</span>
        <span class="mono">{{ fmtDuration(h.wall_time_s) }}</span>
        <span class="mono dim">
          {{ h.resources.nproc.value }}C{{ h.resources.nproc.defaulted ? "*" : "" }} / {{ h.resources.mem_gb.value }}G{{ h.resources.mem_gb.defaulted ? "*" : "" }}
        </span>
        <span class="mono dim">{{ h.queue_id ?? "直提" }}</span>
      </div>
    </section>

    <!-- 详情抽屉（行点击） -->
    <div v-if="selected" class="scrim" @click.self="selected = null">
      <aside class="drawer mono">
        <header class="d-head">
          <span class="d-title">
            {{ String(selected.id).padStart(3, "0") }} — {{ selected.filename }}
          </span>
          <StateChip :state="selected.state" />
        </header>

        <dl class="cell">
          <dt>状态 / 归因</dt>
          <dd>{{ selected.cause ? causeLabel[selected.cause] : "正常结束" }}</dd>
        </dl>
        <dl class="cell">
          <dt>提交 / 启动 / 结束</dt>
          <dd>{{ fmtDateTime(selected.submitted_at) }}</dd>
          <dd>{{ fmtDateTime(selected.started_at) }}</dd>
          <dd>{{ fmtDateTime(selected.finished_at) }}</dd>
        </dl>
        <dl class="cell">
          <dt>耗时</dt>
          <dd>{{ fmtDuration(selected.wall_time_s) }}</dd>
        </dl>
        <dl class="cell">
          <dt>输入哈希</dt>
          <dd>{{ fmtHash(selected.input_hash) }}</dd>
        </dl>
        <dl class="cell">
          <dt>资源</dt>
          <dd>CPU {{ selected.resources.nproc.value }}（{{ selected.resources.nproc.defaulted ? "默认" : "声明" }}）</dd>
          <dd>MEM {{ selected.resources.mem_gb.value }} GB（{{ selected.resources.mem_gb.defaulted ? "默认" : "声明" }}）</dd>
        </dl>
        <dl v-if="selected.monitor_summary" class="cell">
          <dt>监控峰值</dt>
          <dd>CPU {{ fmtPercent(selected.monitor_summary.cpu_peak_percent) }} / MEM {{ fmtMemory(selected.monitor_summary.mem_peak_mb) }}</dd>
          <dd>停滞告警 {{ selected.monitor_summary.stall_alerts ?? 0 }} 次</dd>
        </dl>
        <dl class="cell">
          <dt>chk 保全</dt>
          <dd>{{ selected.chk_snapshot.protected ? "已保全" : "未保全" }}{{ selected.chk_snapshot.location ? " — " + selected.chk_snapshot.location : "" }}</dd>
        </dl>
        <dl class="cell">
          <dt>结果引用（M3 占位）</dt>
          <dd>{{ selected.result_ref ?? "—" }}</dd>
        </dl>

        <div class="actions">
          <button class="btn sm" type="button" @click="viewText('input')">输入</button>
          <button class="btn sm" type="button" @click="viewText('output')">输出</button>
          <button
            class="btn sm danger"
            type="button"
            :disabled="selected.archived"
            @click="archive(selected)"
          >
            {{ selected.archived ? "已归档" : "归档" }}
          </button>
          <button class="btn sm ghost" type="button" @click="selected = null">关闭</button>
        </div>

        <div v-if="textView" class="text-view mono">
          <header class="tv-head">
            <span>{{ textView.kind === "input" ? "输入原文" : "输出预览" }}</span>
            <button class="btn sm ghost" type="button" @click="textView = null">×</button>
          </header>
          <pre class="tv-body">{{ textView.loading ? "读取中 …" : "（M0 mock 暂不填充正文）" }}</pre>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.history {
  position: relative;
}
.controls {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}
.filter {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-faint);
}
.count {
  font-size: var(--text-xs);
  color: var(--text-faint);
}
.table {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
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
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-faint);
}
.row {
  border-bottom: 1px solid var(--border-hair);
  cursor: pointer;
  min-height: 44px;
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
.is-loading {
  opacity: 0.4;
}
.empty-wrap {
  margin-top: var(--space-4);
}
/* ---------- 详情抽屉 ---------- */
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
  animation: slide 160ms ease-out;
}
@keyframes slide {
  from {
    transform: translateX(28px);
    opacity: 0;
  }
  to {
    transform: none;
    opacity: 1;
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
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}
.cell {
  margin: 0;
  border-top: 1px solid var(--border-hair);
  padding-top: var(--space-3);
}
.cell dt {
  font-size: var(--text-xs);
  letter-spacing: 0.06em;
  color: var(--text-faint);
  margin-bottom: var(--space-1);
}
.cell dd {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.btn {
  font-size: var(--text-xs);
  border: 1px solid var(--border-strong);
  color: var(--text-secondary);
  border-radius: var(--r-md);
  padding: 6px 12px;
  height: 30px;
  transition: border-color 120ms ease, color 120ms ease;
}
.btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--text-primary);
}
.btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.btn.danger {
  border-color: color-mix(in srgb, var(--danger) 50%, transparent);
  color: var(--danger);
}
.btn.danger:hover:not(:disabled) {
  border-color: var(--danger);
}
.btn.ghost {
  border-color: transparent;
  color: var(--text-faint);
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
  font-size: var(--text-xs);
  color: var(--text-faint);
}
.tv-body {
  margin: 0;
  padding: var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  white-space: pre-wrap;
  max-height: 240px;
  overflow: auto;
}
</style>