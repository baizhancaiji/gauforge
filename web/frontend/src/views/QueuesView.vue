<script setup lang="ts">
/**
 * 02 队列（m0-frontend-design §5 · 表格型，行可展开成员概览；m2-plan C3 真实化）。
 * 手势分工（A3 定稿）：单击行首箭头切换展开；双击行打开编辑对话框
 * （unsubmitted 全量编辑 / submitted 仅成员 / executing、completed 只读详情）。
 * 行内动作：提交/重新提交（unsubmitted；按回退标记分级文案——失败回退队列
 * 「重新提交」、新鲜队列「提交」，roadmap §2.1 明确区分；响应 normalized=true
 * 显「已自动规范化」中性注记）、删除（二次确认；executing 不渲染——后端 409）。
 * 顶部控制行（2026-09-27 验收修正）：状态筛选（四态+全部，中文措辞）与排序
 * （默认=回退置顶·创建时间新→旧；名称 A→Z/Z→A），/queues 全量返回 → 前端
 * 过滤/排序/切片。
 * 回退标记与次数显著标识；失败成员与各自归因列表（last_failure.members 驱动，
 * submitted 队列从待执行席位交叉文件名/标题）；失败回退队列（unsubmitted 且
 * rollback_flag）的 failed/skipped 成员行提供「编辑内容」入口——展开 C1 同一套
 * BlockEditor 分块编辑（id 跨形态延续，保存端点共用）。
 */
import { computed, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import BlockEditor from "@/components/BlockEditor.vue";
import ConfirmModal from "@/components/ConfirmModal.vue";
import EmptyState from "@/components/EmptyState.vue";
import QueueEditorModal from "@/components/QueueEditorModal.vue";
import StateChip from "@/components/StateChip.vue";
import TablePager from "@/components/TablePager.vue";
import { useSortPref } from "@/composables/useSortPref";
import { useEventsStore } from "@/stores/events";
import { fmtDateTime, fmtTaskId } from "@/utils/format";
import { causeLabel, finishReasonLabel, queueStateLabel, taskStateLabel } from "@/utils/labels";

type Queue = components["schemas"]["Queue"];

interface MemberView {
  id: number;
  position: number;
  /** submitted 队列从待执行席位交叉可得；其余形态契约无来源显 — */
  filename?: string;
  title?: string | null;
  /** 失败归因交叉（Queue.last_failure.members） */
  state?: string;
  cause?: string | null;
}

const events = useEventsStore();
const list = ref<Queue[]>([]);
const loading = ref(false);
const expanded = ref(<Record<string, boolean>>{});

// ---------- 状态筛选与排序（2026-09-27 验收修正：与历史页 controls 同款；
// /queues 全量返回 → 纯前端过滤/排序，默认序=回退置顶·创建时间倒序） ----------
type QueueStateFilter = "all" | "unsubmitted" | "submitted" | "executing" | "completed";
type QueueSortKey = "default" | "name_asc" | "name_desc";

const stateFilter = ref<QueueStateFilter>("all");
// 排序规则经视图偏好域持久化（键 queues.sort），重启/更新/断联后不回默认
const sortKey = useSortPref<QueueSortKey>(
  "queues.sort", "default", ["default", "name_asc", "name_desc"]);

/** 回退队列判定（与提交动作文案 submitLabel 同口径：标记或次数任一）。 */
function isRolledBack(q: Queue): boolean {
  return q.rollback_flag || (q.rollback_count ?? 0) > 0;
}

const filtered = computed(() => {
  const rows =
    stateFilter.value === "all"
      ? list.value
      : list.value.filter((q) => q.state === stateFilter.value);
  const sorted = [...rows];
  if (sortKey.value === "name_asc") {
    sorted.sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
  } else if (sortKey.value === "name_desc") {
    sorted.sort((a, b) => b.name.localeCompare(a.name, "zh-Hans-CN"));
  } else {
    // 默认（openapi /candidates 同规则映射到队列）：回退置顶，组内创建时间
    // 倒序（created_at 恒定时区 ISO，字典序即时序），出错队列一眼可见
    sorted.sort((a, b) => {
      const g = Number(isRolledBack(b)) - Number(isRolledBack(a));
      return g !== 0 ? g : b.created_at.localeCompare(a.created_at);
    });
  }
  return sorted;
});

// 分页（m0-frontend-design §4.3 列表底栏）：/queues 全量返回 → 前端切片；
// 分页大小取设置项 page_size（全局统一，即时生效），settings.updated 跟随。
const page = ref(1);
const pageSize = ref(50);
const paged = computed(() => {
  const size = Math.max(1, pageSize.value);
  const start = (page.value - 1) * size;
  return filtered.value.slice(start, start + size);
});

/** 页码越界（删除/筛选后总页数收缩）→ 钳到末页。 */
function clampPage() {
  const tp = Math.max(1, Math.ceil(filtered.value.length / Math.max(1, pageSize.value)));
  if (page.value > tp) page.value = tp;
}

/** 筛选/排序变更：回到第 1 页（数据全量在前端，无须重取）。 */
function resetPage() {
  page.value = 1;
  clampPage();
}

async function loadPageSize() {
  const { data } = await client.GET("/settings");
  const v = data?.runtime.find((s) => s.key === "page_size")?.value;
  if (v != null) {
    pageSize.value = Number(v) || pageSize.value;
    clampPage();
  }
}
watch(() => events.dirty.settings, loadPageSize);

async function load() {
  loading.value = true;
  const { data } = await client.GET("/queues");
  loading.value = false;
  list.value = data ?? [];
  clampPage();
}
watch(() => events.dirty.queues, load);
load();
loadPageSize();

function toggle(id: string) {
  expanded.value[id] = !expanded.value[id];
}

/** 成员概览：member_ids 为主序，last_failure.members 交叉状态/归因，
 *  submitted 队列再从待执行席位交叉文件名/标题（契约内数据全用尽）。 */
function memberRows(q: Queue): MemberView[] {
  const lf = new Map<number, { state?: string; cause?: string | null }>();
  for (const it of q.last_failure?.members ?? []) {
    if (it.task_id != null) lf.set(it.task_id, { state: it.state, cause: it.cause });
  }
  const seat = events.pending?.seats.find((s) => s.queue_id === q.id);
  const byId = new Map((seat?.members ?? []).map((m) => [m.task_id, m]));
  return q.member_ids.map((id, i) => {
    const sm = byId.get(id);
    return {
      id,
      position: i,
      filename: sm?.filename,
      title: sm?.title ?? null,
      ...(lf.get(id) ?? {}),
    };
  });
}

/** 编辑入口守卫（对齐后端 _guard_editable）：仅失败回退队列的 failed/skipped 成员。 */
function isRollbackEditable(q: Queue, m: MemberView): boolean {
  return (
    q.state === "unsubmitted" &&
    q.rollback_flag &&
    (m.state === "failed" || m.state === "skipped")
  );
}

// ---------- 编辑对话框（双击行打开；按状态分级渲染模式） ----------
const editorOpen = ref(false);
const editingQueue = ref<Queue | null>(null);
const editorMode = ref<"create" | "edit" | "readonly">("edit");

function openEditor(q: Queue) {
  editingQueue.value = q;
  editorMode.value =
    q.state === "unsubmitted" || q.state === "submitted" ? "edit" : "readonly";
  editorOpen.value = true;
}

function onEditorSaved(_q: Queue) {
  editorOpen.value = false;
  editingQueue.value = null;
}

// ---------- 回退成员分块编辑（展开区 BlockEditor，id 跨形态延续） ----------
const memberEditing = ref<number | null>(null);

function toggleMemberEdit(id: number) {
  memberEditing.value = memberEditing.value === id ? null : id;
}

/** 编辑卡守卫：正在编辑的成员属于该回退队列（展开区切换/收起防悬挂）。 */
function editingMemberIn(q: Queue): boolean {
  return (
    memberEditing.value != null &&
    q.state === "unsubmitted" &&
    q.rollback_flag &&
    q.member_ids.includes(memberEditing.value)
  );
}

// ---------- 重新提交（unsubmitted；normalized 注记） ----------
const pageNote = ref<{ ok: boolean; msg: string } | null>(null);
const submittingId = ref<string | null>(null);

/** 提交动作文案（roadmap §2.1：回退队列与新鲜队列明确区分）——
 *  携带回退标记（失败回退）为「重新提交」，新鲜未提交队列为「提交」。
 *  整席移除回退按后端设计无回退标记（pending 服务文档注释），视同新鲜。 */
function submitLabel(q: Queue): string {
  if (submittingId.value === q.id) return "提交中 …";
  return q.rollback_flag || !!q.rollback_count ? "重新提交" : "提交";
}

async function resubmit(q: Queue) {
  pageNote.value = null;
  submittingId.value = q.id;
  const { data, error } = await client.POST("/queues/{id}/submit", {
    params: { path: { id: q.id } },
  });
  submittingId.value = null;
  if (error) {
    const body = error as unknown as { error?: { code?: string; message?: string } };
    pageNote.value = {
      ok: false,
      msg:
        body.error?.code === "PENDING_CAPACITY_FULL"
          ? "在途席位满员 — 请在待执行页移除席位或调高上限后重试"
          : (body.error?.message ?? "提交失败"),
    };
    return;
  }
  pageNote.value = {
    ok: true,
    msg: data?.normalized
      ? `队列 ${q.name} 已提交 — 输入已自动规范化（换行/空行）`
      : `队列 ${q.name} 已提交`,
  };
}

// ---------- 删除（二次确认；executing 不渲染——后端 409） ----------
const deleting = ref<Queue | null>(null);
const deleteLoading = ref(false);
const deleteError = ref<string | null>(null);

const deleteCopy = computed(() => {
  const q = deleting.value;
  if (!q) return "";
  if (q.state === "submitted") {
    return `队列 ${q.name} 正在待执行 — 席位将撤销，成员退回候选列表`;
  }
  if (q.state === "completed") {
    return `删除队列 ${q.name} 的记录 — 成员仅保留历史条目，不再回候选`;
  }
  return `删除队列 ${q.name} — 成员将退回候选列表`;
});

async function confirmDelete() {
  const q = deleting.value;
  if (!q) return;
  deleteLoading.value = true;
  deleteError.value = null;
  const { error } = await client.DELETE("/queues/{id}", {
    params: { path: { id: q.id } },
  });
  deleteLoading.value = false;
  if (error) {
    const body = error as unknown as { error?: { code?: string; message?: string } };
    deleteError.value = body.error?.message ?? "删除失败";
    return;
  }
  deleting.value = null;
  if (memberEditing.value != null) memberEditing.value = null;
}
</script>

<template>
  <section class="queues">
    <p
      v-if="pageNote"
      class="page-note mono"
      :class="{ 'page-note--err': !pageNote.ok }"
      role="status"
    >
      {{ pageNote.msg }}
    </p>

    <!-- 顶部控制行（2026-09-27 验收修正，与历史页 controls 同款） -->
    <div class="controls">
      <label class="mono filter">
        <span>状态筛选</span>
        <select v-model="stateFilter" @change="resetPage">
          <option value="all">全部</option>
          <option value="unsubmitted">未提交</option>
          <option value="submitted">已提交</option>
          <option value="executing">执行中</option>
          <option value="completed">已完成</option>
        </select>
      </label>
      <label class="mono filter">
        <span>排序</span>
        <select v-model="sortKey" @change="resetPage">
          <option value="default">默认 · 回退置顶·创建时间新→旧</option>
          <option value="name_asc">名称 · A→Z</option>
          <option value="name_desc">名称 · Z→A</option>
        </select>
      </label>
    </div>

    <div v-if="!list.length && !loading" class="empty-wrap">
      <EmptyState
        glyph="▮"
        text="暂无队列 — 在候选页勾选任务组建，或导入文件夹时勾选保存为队列"
      />
    </div>
    <div v-else-if="!filtered.length && !loading" class="empty-wrap">
      <EmptyState glyph="▮" text="当前筛选下暂无队列 — 切换状态或恢复全部" />
    </div>
    <div v-else class="table-area">
      <div class="thead mono">
        <span></span>
        <span>ID</span>
        <span>名称</span>
        <span>成员</span>
        <span>状态</span>
        <span>回退</span>
        <span>结束原因</span>
        <span class="right">已更新</span>
        <span class="right">动作</span>
      </div>
      <template v-for="q in paged" :key="q.id">
        <div class="row" :class="{ 'row--open': expanded[q.id] }" @dblclick="openEditor(q)">
          <span
            class="expand mono"
            :class="{ open: expanded[q.id] }"
            role="button"
            tabindex="0"
            aria-label="展开成员概览"
            @click.stop="toggle(q.id)"
            @keydown.enter.stop="toggle(q.id)"
          >▸</span>
          <span class="mono brand" :title="q.id">{{ q.id }}</span>
          <span class="name" :title="q.name">{{ q.name }}</span>
          <span class="mono count">{{ q.member_ids.length }} 个任务</span>
          <span>
            <StateChip :state="q.state" :label="queueStateLabel[q.state] ?? q.state" />
          </span>
          <span class="mono">
            <span v-if="q.rollback_count" class="rollback">已回退 ×{{ q.rollback_count }}</span>
            <span v-else class="dim">—</span>
          </span>
          <!-- 中文显示；原枚举保留在 data-finish-reason 作内部信号（§4.1） -->
          <span
            class="mono dim"
            :data-finish-reason="q.finish_reason ?? undefined"
          >{{ q.finish_reason ? finishReasonLabel[q.finish_reason] ?? q.finish_reason : "—" }}</span>
          <span class="mono dim right">{{ fmtDateTime(q.updated_at ?? q.created_at) }}</span>
          <span class="right actions">
            <button
              v-if="q.state === 'unsubmitted'"
              class="btn btn--ghost"
              type="button"
              :disabled="submittingId === q.id"
              @click.stop="resubmit(q)"
            >
              {{ submitLabel(q) }}
            </button>
            <button
              v-if="q.state !== 'executing'"
              class="btn btn--ghost q-del"
              type="button"
              @click.stop="deleting = q"
            >
              删除
            </button>
          </span>
        </div>
        <div v-if="expanded[q.id]" class="detail">
          <div class="meta mono">
            <span>创建 {{ fmtDateTime(q.created_at) }}</span>
            <span>跳过失败 {{ q.skip_failed ? "ON" : "OFF" }}</span>
            <span v-if="q.rollback_flag" class="warn">
              失败回退 — 失败/跳过成员可编辑内容后重新提交
            </span>
            <span v-if="q.state === 'executing'" class="hint">
              成员移除请前往待执行页操作
            </span>
          </div>
          <p class="mono label">成员顺序（执行序列）</p>
          <div class="member-list">
            <div v-for="m in memberRows(q)" :key="m.id" class="mem-row">
              <span class="mono m-idx">{{ m.position + 1 }}</span>
              <span class="mono m-id">{{ fmtTaskId(m.id) }}</span>
              <span class="mono m-file" :title="m.filename">{{ m.filename ?? "—" }}</span>
              <StateChip
                v-if="m.state"
                :state="m.state"
                :label="taskStateLabel[m.state] ?? m.state"
              />
              <span v-if="m.cause" class="mono m-cause">{{ causeLabel[m.cause] ?? m.cause }}</span>
              <button
                v-if="isRollbackEditable(q, m)"
                class="btn btn--ghost m-edit"
                type="button"
                @click="toggleMemberEdit(m.id)"
              >
                {{ memberEditing === m.id ? "收起编辑" : "编辑内容" }}
              </button>
            </div>
          </div>
          <!-- 失败回退成员分块编辑（C1 同一套 BlockEditor，id 跨形态延续） -->
          <BlockEditor
            v-if="memberEditing != null && editingMemberIn(q)"
            :key="memberEditing"
            :task-id="memberEditing"
            :editable="true"
          >
            <template #head>
              <span class="be-name mono">成员 {{ fmtTaskId(memberEditing) }} — 分块编辑（自动保存）</span>
            </template>
          </BlockEditor>
        </div>
      </template>
    </div>
    <div class="scanline" v-if="loading" aria-hidden="true"></div>
    <!-- 列表底栏（§4.3 标准套件）：计数右对齐 + 分页控件居中（单页时控件隐藏） -->
    <TablePager
      v-if="filtered.length"
      :total="filtered.length"
      :page="page"
      :page-size="pageSize"
      @change="(p) => (page = p)"
    />

    <!-- 队列编辑对话框（双击行；C2 组件按状态分级渲染） -->
    <QueueEditorModal
      :open="editorOpen"
      :mode="editorMode"
      :queue="editingQueue"
      @saved="onEditorSaved"
      @close="editorOpen = false"
    />

    <!-- 删除二次确认（§4.6 危险确认模态；文案按状态分级） -->
    <ConfirmModal
      :open="deleting != null"
      title="删除队列"
      danger
      confirm-text="删除"
      :loading="deleteLoading"
      @confirm="confirmDelete"
      @close="deleting = null; deleteError = null"
    >
      <p class="confirm-line">{{ deleteCopy }}</p>
      <p v-if="deleteError" class="confirm-error mono" role="alert">{{ deleteError }}</p>
    </ConfirmModal>
  </section>
</template>

<style scoped>
.queues {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
  overflow: hidden;
  background: var(--bg-raised);
}
/* 页面级注记（重新提交 normalized 中性注记 / 错误） */
.page-note {
  flex-shrink: 0;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-hair);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.page-note--err {
  color: var(--danger);
}
/* 顶部控制行（2026-09-27 验收修正，与历史页 .controls/.filter 同款）：
   卡片内顶部工具行，发丝线与表格区分隔 */
.controls {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-shrink: 0;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-hair);
}
.filter {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.empty-wrap {
  padding: var(--space-4);
}
/* 表格滚动区：吃剩余高度、局部滚动（§3 视口纪律）；行级 min-width 触发横向滚动 */
.table-area {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.thead,
.row,
.detail {
  min-width: 720px;
}
.thead,
.row {
  display: grid;
  grid-template-columns: 28px 88px 1.2fr 1fr 1fr 1fr 1.1fr 110px 150px;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) var(--space-3);
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
  font-size: var(--text-sm);
  cursor: default;
  min-height: var(--row-height); /* §4.3 行高 40px */
}
.row:hover,
.row--open {
  background: var(--row-hover);
}
.row:last-child {
  border-bottom: none;
}
/* 行首展开箭头（手势分工 A3：单击箭头切换展开，双击行开编辑对话框）。
 * 弹性居中让字形绕自身中心原地旋转（块级 baseline 排版会绕盒中心公转）；
 * 拉通行高扩大命中区（2026-09-27 人为指定放大 + 原地旋转） */
.expand {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: stretch;
  font-size: var(--text-lg);
  line-height: 1;
  color: var(--text-faint);
  cursor: pointer;
  transition: transform var(--dur-view) var(--ease-std);
  user-select: none;
}
.expand.open {
  transform: rotate(90deg);
}
.brand {
  color: var(--accent);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
.actions {
  white-space: nowrap;
}
.q-del {
  color: var(--danger);
}
.q-del:hover:not(:disabled) {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 10%, transparent);
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
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.warn {
  color: var(--warn);
}
.hint {
  color: var(--text-faint);
}
.label {
  font-size: var(--text-sm); /* 文案含中文（成员顺序） */
  color: var(--text-faint);
}
.member-list {
  display: grid;
  gap: var(--space-1);
}
.mem-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  font-size: var(--text-sm);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
}
.m-idx {
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
  min-width: 20px;
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
  min-width: 120px;
}
.m-cause {
  font-size: var(--text-sm);
  color: var(--warn);
}
.m-edit {
  height: var(--control-height-sm);
  margin-left: auto;
  font-size: var(--text-sm); /* 文案含中文（编辑内容） */
}
.be-name {
  font-size: var(--text-sm); /* 文案含中文 */
  font-weight: 500;
  color: var(--text-primary);
}
.confirm-line {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.confirm-error {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--danger);
}
.scanline {
  height: 1px;
  flex-shrink: 0;
  background: var(--accent);
  /* 引用 base.css 共用 scanline（--ease-std），不重复定义 keyframes */
  animation: scanline var(--dur-scan) var(--ease-std) infinite;
}
</style>
