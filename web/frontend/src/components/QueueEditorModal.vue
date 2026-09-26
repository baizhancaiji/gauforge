<script lang="ts">
/** 成员行视图（创建态来自候选行；编辑态经 last_failure/pending 交叉）。
 *  置于普通 script 块：script setup 内 export 会引发模块初始化 ReferenceError
 *  （对话框 chunk 加载即崩溃，D1 走查实测；vue-tsc/vite build 均不拦截）。 */
export interface MemberRow {
  id: number;
  /** 创建态来自候选行；编辑态契约 Queue 无成员明细，缺省显示 — */
  filename?: string;
  title?: string | null;
  /** 失败归因交叉（Queue.last_failure.members，编辑/只读态） */
  state?: string;
  cause?: string | null;
}
</script>

<script setup lang="ts">
/**
 * QueueEditorModal — 队列编辑对话框（m2-plan §2.2/§2.4/§4.3 C2；创建/编辑共用）。
 * 布局（m0-frontend-design §4.6 定稿，复用 ConfirmModal 弹层基础）：顶部队列名
 * 输入（创建默认 yyyymmddhhmmss 时间戳可改；创建态不渲染队列 id 字段——id
 * 保存后由后端生成，编辑/只读态只读展示真实 id，2026-09-27 计划外人为修正
 * 去除「保存后生成」占位注记）；中部成员列表（任务 id/文件名/title，「-」
 * 移除剩 1 禁用、拖动排序 120ms --ease-std）；「自动跳过失败任务」toggle
 * 开关；底部「取消」/「保存」（primary，每视图至多一个）/「直接提交」
 * （secondary）。
 * 状态分级（m2-plan §2.2 矩阵）：unsubmitted 全量可编辑；submitted 仅成员
 * （改名/开关 409，A2 决策点 2/9——禁用并注明）；executing/completed 只读详情。
 * 「直接提交」= 保存 + submit 链式；submit 失败时队列保留 unsubmitted，展示
 * 原因引导队列页重试；提交响应 normalized=true 显「已自动规范化」中性注记。
 */
import { computed, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";
import StateChip from "@/components/StateChip.vue";
import { useDragSort } from "@/composables/useDragSort";
import { fmtTaskId } from "@/utils/format";
import { causeLabel } from "@/utils/labels";

type Queue = components["schemas"]["Queue"];

const props = defineProps<{
  open: boolean;
  mode: "create" | "edit" | "readonly";
  /** edit/readonly 模式的队列数据 */
  queue?: Queue | null;
  /** create 模式的待组成员（候选行） */
  initialMembers?: MemberRow[];
  /** create 预填队列名（留空用时间戳默认） */
  initialName?: string;
}>();

const emit = defineEmits<{ close: []; saved: [queue: Queue]; submitted: [] }>();

const readonly = computed(() => props.mode === "readonly");
/** submitted 态仅成员可改（改名/开关 409 前置禁用，A2 决策点 2/9）。 */
const memberOnly = computed(() => props.queue?.state === "submitted");
/** executing 只读详情附跨页引导（设计 §5：未执行成员移除属席位端点能力）。 */
const executingHint = computed(() => props.queue?.state === "executing");

const name = ref("");
const skipFailed = ref(false);
const members = ref<MemberRow[]>([]);
const busy = ref(false);
const error = ref<string | null>(null);
/** 成功注记（含 normalized 规范化提示；提交成功后锁定输入等待关闭） */
const note = ref<string | null>(null);
const done = ref(false);

const drag = useDragSort();
const canSort = computed(() => !readonly.value && !done.value);

watch(
  () => props.open,
  (v) => {
    if (!v) return;
    error.value = null;
    note.value = null;
    done.value = false;
    busy.value = false;
    if (props.mode === "create") {
      name.value = props.initialName ?? defaultQueueName();
      members.value = (props.initialMembers ?? []).map((m) => ({ ...m }));
      skipFailed.value = false;
    } else {
      const q = props.queue;
      name.value = q?.name ?? "";
      skipFailed.value = q?.skip_failed ?? false;
      const lf = new Map<number, { state?: string; cause?: string | null }>();
      for (const it of q?.last_failure?.members ?? []) {
        if (it.task_id != null) lf.set(it.task_id, { state: it.state, cause: it.cause });
      }
      members.value = (q?.member_ids ?? []).map((id) => ({
        id,
        filename: undefined,
        title: null,
        ...(lf.get(id) ?? {}),
      }));
    }
  },
);

function defaultQueueName(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

/** 队列 id 只读展示；创建态该字段不渲染（id 保存后由后端生成，不再显示占位注记）。 */
const qidLabel = computed(() => props.queue?.id ?? "—");

const canSave = computed(() => {
  if (!name.value.trim().length) return false;
  const n = members.value.length;
  // 成员数 2–10 仅创建时校验；编辑态只减不增、下限 1（§2.2——后端
  // PATCH 仅拒 0，canSave 误用创建期下限会禁存合法的剩 1 编辑，
  // D1 走查实测缺陷）
  return props.mode === "create" ? n >= 2 && n <= 10 : n >= 1;
});

function removeAt(i: number) {
  if (members.value.length <= 1) return; // 至少保留 1 个（下限前置禁用）
  const m = members.value[i];
  if (memberOnly.value && m?.state === "running") return; // 在跑成员移除后端 409（前置禁用）
  members.value.splice(i, 1);
}

// ---------- 拖拽排序（公共组合式；锁定/边界判定：只读态不可拖） ----------
function onDragStart(m: MemberRow, e: DragEvent) {
  if (!canSort.value) return;
  drag.start(m.id, e);
}
function onDragOver(m: MemberRow, e: DragEvent) {
  drag.over(m.id, e, canSort.value);
}
function onDrop(m: MemberRow) {
  const from = drag.dragId.value;
  const to = m.id;
  drag.end();
  if (from == null || from === to) return;
  const ids: (string | number)[] = members.value.map((x) => x.id);
  const next = drag.move(ids, from, to);
  if (!next) return;
  const byId = new Map(members.value.map((x) => [x.id, x]));
  members.value = next.map((id) => byId.get(id as number)!);
}

// ---------- 保存 / 直接提交 ----------
function errText(e: unknown, fallback: string): string {
  const body = e as unknown as { error?: { code?: string; message?: string } };
  return body.error?.message ?? fallback;
}

/** 创建或更新（内部共用，不触发关闭）；成功返回队列视图。 */
async function saveInternal(): Promise<Queue | null> {
  if (props.mode === "create") {
    const { data, error: e } = await client.POST("/queues", {
      body: {
        name: name.value.trim(),
        member_ids: members.value.map((m) => m.id),
        skip_failed: skipFailed.value,
      },
    });
    if (e) {
      error.value = errText(e, "创建被拒绝");
      return null;
    }
    return data ?? null;
  }
  const q = props.queue!;
  const body: Record<string, unknown> = {};
  if (!memberOnly.value && name.value.trim() !== q.name) {
    body.name = name.value.trim();
  }
  const ids = members.value.map((m) => m.id);
  if (JSON.stringify(ids) !== JSON.stringify(q.member_ids)) body.member_ids = ids;
  if (!memberOnly.value && skipFailed.value !== q.skip_failed) {
    body.skip_failed = skipFailed.value;
  }
  if (!Object.keys(body).length) return q; // 无变更视同成功
  const { data, error: e } = await client.PATCH("/queues/{id}", {
    params: { path: { id: q.id } },
    body: body as never,
  });
  if (e) {
    error.value = errText(e, "保存被拒绝");
    return null;
  }
  return data ?? null;
}

async function save() {
  busy.value = true;
  error.value = null;
  const q = await saveInternal();
  busy.value = false;
  if (!q) return;
  emit("saved", q);
}

async function submitNow() {
  busy.value = true;
  error.value = null;
  const q = await saveInternal();
  if (!q) {
    busy.value = false;
    return;
  }
  const { data: sub, error: e } = await client.POST("/queues/{id}/submit", {
    params: { path: { id: q.id } },
  });
  busy.value = false;
  if (e) {
    // 链式失败：队列保留为已保存（unsubmitted），引导队列页重试（m2-plan §2.2）
    const body = e as unknown as { error?: { code?: string; message?: string } };
    error.value =
      body.error?.code === "PENDING_CAPACITY_FULL"
        ? "在途席位满员 — 队列已保存（未提交），请稍后在队列页重试"
        : `提交失败 — 队列已保存（未提交）：${body.error?.message ?? "稍后在队列页重试"}`;
    return;
  }
  done.value = true;
  note.value = sub?.normalized
    ? "已保存并提交 — 输入已自动规范化（换行/空行）"
    : "已保存并提交";
  emit("submitted");
}

function tryClose() {
  if (!busy.value) emit("close");
}
</script>

<template>
  <ConfirmModal :open="open" :title="mode === 'create' ? '新建队列' : '队列编辑'" :loading="busy" @close="tryClose">
    <div class="q-body">
      <div class="q-top">
        <label class="q-field">
          <span class="q-label mono">队列名</span>
          <input
            v-model="name"
            type="text"
            :disabled="readonly || memberOnly || done"
            maxlength="64"
          />
        </label>
        <!-- 队列 id 只读展示仅编辑/只读态；创建态不渲染（id 保存后生成，无占位注记） -->
        <div v-if="mode !== 'create'" class="q-field q-id-field">
          <span class="q-label mono">队列 ID</span>
          <span class="q-id mono">{{ qidLabel }}</span>
        </div>
      </div>

      <p v-if="memberOnly && !readonly" class="q-hint mono">
        已提交队列仅可重排与移除未执行成员（改名/开关在执行语义上不追溯）
      </p>
      <p v-if="executingHint" class="q-hint mono">
        队列执行中（只读）— 成员移除请前往待执行页操作
      </p>
      <p v-if="error" class="q-error mono" role="alert">{{ error }}</p>
      <p v-if="note" class="q-note mono" role="status">{{ note }}</p>

      <p class="q-label mono">成员（{{ members.length }}）— 顺序即执行序列</p>
      <div class="q-members">
        <div
          v-for="(m, i) in members"
          :key="m.id"
          class="q-mem"
          :class="{
            'q-mem--dragging': drag.dragId.value === m.id,
            'q-mem--over': drag.overId.value === m.id && drag.dragId.value !== m.id,
          }"
          :draggable="canSort"
          @dragstart="onDragStart(m, $event)"
          @dragover.prevent="onDragOver(m, $event)"
          @dragleave="drag.leave(m.id)"
          @drop.prevent="onDrop(m)"
        >
          <span v-if="canSort" class="m-drag mono" aria-hidden="true">⋮⋮</span>
          <span class="m-id mono">{{ fmtTaskId(m.id) }}</span>
          <span class="m-file mono" :title="m.filename">{{ m.filename ?? "—" }}</span>
          <span class="m-title" :title="m.title ?? undefined">{{ m.title ?? "—" }}</span>
          <StateChip v-if="m.state" :state="m.state" />
          <span v-if="m.cause" class="m-cause mono">{{ causeLabel[m.cause] ?? m.cause }}</span>
          <button
            v-if="!readonly"
            class="btn btn--ghost m-remove"
            type="button"
            :disabled="members.length <= 1 || done || (memberOnly && m.state === 'running')"
            :title="members.length <= 1 ? '队列至少保留 1 个成员' : (memberOnly && m.state === 'running' ? '在跑成员不可移除' : undefined)"
            @click="removeAt(i)"
          >
            -
          </button>
        </div>
      </div>

      <div class="q-toggle-row">
        <span class="q-label mono">自动跳过失败任务</span>
        <button
          type="button"
          class="tgl"
          :class="{ 'tgl--on': skipFailed }"
          role="switch"
          :aria-checked="skipFailed"
          :disabled="readonly || memberOnly || done"
          @click="skipFailed = !skipFailed"
        >
          <i class="tgl-knob"></i>
        </button>
      </div>
    </div>

    <template #foot>
      <button class="btn btn--ghost" type="button" @click="tryClose">
        {{ done ? "关闭" : "取消" }}
      </button>
      <template v-if="!readonly">
        <button
          class="btn btn--secondary"
          type="button"
          :disabled="busy || done"
          @click="submitNow"
        >
          直接提交
        </button>
        <button
          class="btn btn--primary"
          type="button"
          :data-loading="busy || undefined"
          :disabled="busy || done || !canSave"
          @click="save"
        >
          {{ busy ? "保存中 …" : "保存" }}
        </button>
      </template>
    </template>
  </ConfirmModal>
</template>

<style scoped>
.q-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.q-top {
  display: flex;
  gap: var(--space-4);
  align-items: flex-end;
}
.q-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
  min-width: 0;
}
.q-id-field {
  flex: none;
  align-items: flex-start;
}
.q-label {
  font-size: var(--text-sm); /* 文案含中文（队列名/成员等）：不用微标签档、不加字距 */
  color: var(--text-faint);
}
.q-id {
  font-size: var(--text-sm);
  color: var(--text-primary);
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: 6px var(--space-2);
}
.q-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.q-error {
  font-size: var(--text-sm);
  color: var(--danger);
}
/* 信息注记（中性档 §4.6：提交响应「已自动规范化」提示） */
.q-note {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.q-members {
  display: grid;
  gap: var(--space-1);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-inset);
  padding: var(--space-2);
  max-height: 260px;
  overflow: auto;
}
.q-mem {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  font-size: var(--text-sm);
  transition: transform var(--dur-fast) var(--ease-std), border-color var(--dur-fast) var(--ease-std);
}
.q-mem--dragging {
  opacity: 0.5;
}
.q-mem--over {
  border-color: var(--border-strong);
}
.m-drag {
  color: var(--text-faint);
  cursor: grab;
  letter-spacing: -2px;
}
.m-id {
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}
.m-file {
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 150px;
}
.m-title {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 40px;
}
.m-cause {
  font-size: var(--text-sm);
  color: var(--warn);
}
.m-remove {
  height: var(--control-height-sm);
  padding: 0 var(--space-2);
}
.q-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
/* toggle 开关（§4.6 A3 定稿：36×20 轨道 + 16px 滑块，选中轨道 --accent） */
.tgl {
  position: relative;
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  padding: 0;
  cursor: pointer;
  flex: none;
}
.tgl:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.tgl-knob {
  position: absolute;
  left: 2px;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--text-faint);
  transition: left var(--dur-fast) var(--ease-std), background-color var(--dur-fast) var(--ease-std);
}
.tgl--on {
  background: var(--accent);
  border-color: var(--accent);
}
.tgl--on .tgl-knob {
  left: 16px;
  background: var(--bg-raised);
}
</style>
