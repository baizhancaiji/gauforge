<script setup lang="ts">
/**
 * 03 待执行（m0-frontend-design §5 · 席位型；m1-plan C4 真实化）
 * 页首容量仪表（OCCUPIED 分段 LED，超限段琥珀示警）；席位纵向列表，
 * 窗口触及席位（locked）加左侧 2px 磷光条 + 「在途」标记，不可作拖源/落点
 * 亦不可移除；其后为等待区（分隔注记），支持拖拽重排（PUT /pending/order
 * 全量原子，锁定席位保持原下标即放行）与整席/席位内未执行成员移除（二次
 * 确认）。数据源：SSE pending.snapshot 驱动 events store；首帧回落 REST。
 */
import { computed, reactive, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";
import EmptyState from "@/components/EmptyState.vue";
import StateChip from "@/components/StateChip.vue";
import { fmtDateTime, fmtDeclaredRes, fmtTaskId } from "@/utils/format";
import { useEventsStore } from "@/stores/events";

type PendingResponse = components["schemas"]["PendingResponse"];
type PendingSeat = components["schemas"]["PendingSeat"];

const events = useEventsStore();
const local = ref<PendingResponse | null>(null);
const expanded = reactive(<Record<number, boolean>>{});

const pending = computed(() => events.pending ?? local.value);
const seats = computed(() => pending.value?.seats ?? []);
const anyLocked = computed(() => seats.value.some((s) => s.locked));

async function load() {
  const { data } = await client.GET("/pending");
  if (data) local.value = data;
}
// SSE 快照一旦到达即覆盖 local（local 仅作首帧回落）。
watch(
  () => events.pending,
  (v) => {
    if (v) local.value = null;
  },
);
load();

/** REST 动作返回的最新快照直接写入 store（SSE pending.snapshot 随后同值到达）。 */
function applySnapshot(snap: PendingResponse) {
  events.pending = snap;
  local.value = null;
}

function toggle(seatId: number) {
  expanded[seatId] = !expanded[seatId];
}

// ---------- 拖拽重排（PUT /pending/order 全量原子；锁定席位不可作拖源/落点，
// 等待区可拖；提交 order 保证锁定席位下标不变，越界本地拒绝并提示） ----------
const dragId = ref<number | null>(null);
const overId = ref<number | null>(null);
const orderError = ref<string | null>(null);

const canDrag = (s: PendingSeat) => !s.locked;

function onDragStart(s: PendingSeat, e: DragEvent) {
  dragId.value = s.seat_id;
  orderError.value = null;
  e.dataTransfer?.setData("text/plain", String(s.seat_id));
  if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
}
function onDragOver(s: PendingSeat, e: DragEvent) {
  if (dragId.value == null || !canDrag(s)) return;
  overId.value = s.seat_id;
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
}
async function onDrop(s: PendingSeat) {
  const from = dragId.value;
  dragId.value = null;
  overId.value = null;
  if (from == null || from === s.seat_id) return;
  if (s.locked) {
    orderError.value = "重排越界 — 锁定席位不可作落点";
    return;
  }
  const before = seats.value.map((x) => x.seat_id);
  const src = before.indexOf(from);
  const dst = before.indexOf(s.seat_id);
  if (src < 0 || dst < 0) return;
  const ids = [...before];
  ids.splice(dst, 0, ...ids.splice(src, 1));
  // 后端语义（锁定席位保持原下标即放行，c6a0906e3）：本地先校验，越界不发请求
  const movedLocked = seats.value.some(
    (x) => x.locked && ids.indexOf(x.seat_id) !== before.indexOf(x.seat_id),
  );
  if (movedLocked) {
    orderError.value = "重排越界 — 锁定席位必须保持原位";
    return;
  }
  const { data, error } = await client.PUT("/pending/order", {
    body: { seat_order: ids },
  });
  if (error) {
    orderError.value = "重排被拒绝 — 锁定席位必须保持原位";
    return;
  }
  if (data) applySnapshot(data);
}

// ---------- 整席移除 / 席位内成员移除（二次确认） ----------
const removing = ref<{ seat: PendingSeat; task_id?: number } | null>(null);
const removeLoading = ref(false);
const removeError = ref<string | null>(null);

const removingTitle = computed(() =>
  removing.value?.task_id != null ? "移除席位成员" : "移除席位",
);

async function confirmRemove() {
  const r = removing.value;
  if (!r) return;
  removeLoading.value = true;
  removeError.value = null;
  let error: unknown;
  if (r.task_id != null) {
    const res = await client.DELETE("/pending/seats/{seat_id}/members/{task_id}", {
      params: { path: { seat_id: r.seat.seat_id, task_id: r.task_id } },
    });
    error = res.error;
    if (res.data) applySnapshot(res.data);
  } else {
    const res = await client.DELETE("/pending/seats/{seat_id}", {
      params: { path: { seat_id: r.seat.seat_id } },
    });
    error = res.error;
  }
  removeLoading.value = false;
  if (error) {
    const body = error as unknown as { error?: { code?: string; message?: string } };
    removeError.value =
      body.error?.code === "SEAT_WINDOW_LOCKED"
        ? "席位已被并行窗口触及，不可移除"
        : (body.error?.message ?? "移除失败");
    return;
  }
  removing.value = null;
}
</script>

<template>
  <div v-if="!pending" class="loading mono">读取待执行队列 …</div>

  <div v-else class="pending">
    <!-- 在途席位容量仪表（§4.5）：内嵌读数槽；超限段琥珀示警（在跑不追溯） -->
    <div class="gauge mono" aria-label="在途容量">
      <span class="g-label">OCCUPIED 在途席位</span>
      <span class="cells" aria-hidden="true">
        <i
          v-for="i in Math.max(pending.capacity.limit, pending.capacity.occupied)"
          :key="i"
          class="cell"
          :class="{
            'cell--on': i <= pending.capacity.occupied && i <= pending.capacity.limit,
            'cell--over': i <= pending.capacity.occupied && i > pending.capacity.limit,
          }"
        ></i>
      </span>
      <span class="g-val">{{ pending.capacity.occupied }} / {{ pending.capacity.limit }}</span>
      <span v-if="pending.capacity.occupied > pending.capacity.limit" class="g-over">
        在途超出上限 {{ pending.capacity.occupied - pending.capacity.limit }} 席 — 在跑不追溯，结束后收敛
      </span>
    </div>

    <p v-if="orderError" class="op-error mono" role="alert">{{ orderError }}</p>

    <section class="seats">
      <div v-if="!seats.length" class="empty-wrap">
        <EmptyState glyph="▯" text="席位空置 — 在候选页提交任务后在此排队" />
      </div>

      <template v-for="(s, i) in seats" :key="s.seat_id">
        <!-- 窗口边界注记：首个未触及席位前（§4.5 样板 divider-note） -->
        <div
          v-if="anyLocked && !s.locked && seats[i - 1]?.locked"
          class="divider-note mono"
        >▼ 等待区 · 窗口未触及，可重排 / 移除</div>

        <div
          class="seat"
          :class="{
            'seat--locked': s.locked,
            'seat--dragging': dragId === s.seat_id,
            'seat--over': overId === s.seat_id && dragId !== s.seat_id,
          }"
          :draggable="canDrag(s)"
          @dragstart="onDragStart(s, $event)"
          @dragover.prevent="onDragOver(s, $event)"
          @dragleave="overId === s.seat_id && (overId = null)"
          @drop.prevent="onDrop(s)"
        >
          <span class="seat-no mono">S{{ String(s.seat_id).padStart(2, "0") }}</span>

          <div class="seat-body">
            <div class="seat-line" @click="s.kind === 'queue' && toggle(s.seat_id)">
              <span class="kind mono">{{ s.kind === "queue" ? "QUEUE" : "TASK" }}</span>
              <span
                class="mono seat-name"
                :title="s.kind === 'queue' ? (s.queue_id ?? undefined) : s.members[0]?.filename"
              >
                {{
                  s.kind === "queue"
                    ? (s.queue_name ?? s.queue_id)
                    : s.members[0]?.filename ?? "—"
                }}
              </span>
              <span v-if="s.kind === 'queue'" class="mono seat-meta">
                {{ s.members.length }} 个任务
              </span>
              <span class="mono seat-meta dim">{{ fmtDateTime(s.submitted_at) }}</span>
              <span v-if="s.kind === 'task' && s.members[0]" class="state-slot">
                <StateChip
                  :state="s.members[0].state"
                  :label="s.members[0].state === 'staged' ? '等待' : undefined"
                />
              </span>
              <span v-if="s.locked" class="win-tag mono">在途</span>
              <span
                v-else-if="s.kind === 'queue'"
                class="expand mono"
                :class="{ open: expanded[s.seat_id] }"
                aria-hidden="true"
              >▸</span>
            </div>

            <!-- 队列席位展开成员子表（§4.5）：序号/任务id/文件名/标题/资源/状态，
                 未执行成员可移除 -->
            <div v-if="s.kind === 'queue' && expanded[s.seat_id]" class="sub">
              <div class="sub-row sub-head mono" aria-hidden="true">
                <span>#</span>
                <span>ID</span>
                <span>文件名</span>
                <span>标题</span>
                <span>资源</span>
                <span>状态</span>
                <span></span>
              </div>
              <div v-for="(m, mi) in s.members" :key="m.task_id" class="sub-row">
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
                  @click="removing = { seat: s, task_id: m.task_id }"
                >
                  移除
                </button>
              </div>
            </div>
          </div>

          <button
            v-if="!s.locked"
            class="btn btn--ghost"
            type="button"
            @click="removing = { seat: s }"
          >
            移除席位
          </button>
        </div>
      </template>
    </section>

    <!-- 移除二次确认（危险确认模态） -->
    <ConfirmModal
      :open="removing != null"
      :title="removingTitle"
      danger
      confirm-text="移除"
      :loading="removeLoading"
      @confirm="confirmRemove"
      @close="removing = null"
    >
      <p class="confirm-line">
        <template v-if="removing?.task_id != null">
          将把任务
          <span class="mono strong">{{ fmtTaskId(removing.task_id) }} {{ removing.seat.members.find((m) => m.task_id === removing?.task_id)?.filename }}</span>
          退回候选列表
        </template>
        <template v-else-if="removing?.seat.kind === 'task'">
          将把任务
          <span class="mono strong">{{ fmtTaskId(removing.seat.task_id) }} {{ removing.seat.members[0]?.filename }}</span>
          退回候选列表
        </template>
        <template v-else>
          将把队列
          <span class="mono strong">{{ removing?.seat.queue_id }}</span>
          整席回退为未提交（成员构成不变）
        </template>
      </p>
      <p v-if="removeError" class="confirm-error mono" role="alert">{{ removeError }}</p>
    </ConfirmModal>
  </div>
</template>

<style scoped>
.loading {
  color: var(--text-faint);
  font-size: var(--text-sm);
  padding: var(--space-6);
}
.pending {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
/* 内嵌读数槽：inset 凹陷底，与席位卡（raised 立起）分层 */
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
.g-label {
  font-size: var(--text-sm); /* 文案含中文（OCCUPIED 在途席位）：不用微标签档、不加字距 */
  color: var(--text-faint);
}
.cells {
  display: flex;
  gap: 3px;
}
.cell {
  width: 26px;
  height: 8px;
  border-radius: 2px;
  background: var(--bg-overlay);
  border: 1px solid var(--border-hair);
}
.cell--on {
  background: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--accent) 50%, transparent);
}
.cell--over {
  background: var(--warn);
  border-color: var(--warn);
}
.g-val {
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.g-over {
  font-size: var(--text-sm);
  color: var(--warn);
}
.op-error {
  font-size: var(--text-sm);
  color: var(--danger);
}
.seats {
  display: grid;
  gap: var(--space-2);
}
.empty-wrap {
  padding: var(--space-4);
}
.divider-note {
  margin: var(--space-2) 0;
  font-size: var(--text-sm); /* 文案含中文（等待区注记）：不加字距 */
  color: var(--text-faint);
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.divider-note::before,
.divider-note::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--border-hair);
}
.seat {
  display: grid;
  grid-template-columns: 44px 1fr auto;
  gap: var(--space-4);
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  transition: border-color 120ms var(--ease-std);
}
.seat:hover {
  border-color: var(--border-strong);
}
/* 窗口边界可视化（§4.5）：磷光条 + 泛光 + 「在途」标记 */
.seat--locked {
  border-left: 2px solid var(--accent);
  box-shadow: var(--glow-running);
}
.seat--dragging {
  opacity: 0.5;
}
.seat--over {
  border-color: var(--accent);
}
.seat-no {
  color: var(--text-faint);
  font-size: var(--text-xs);
}
.seat-body {
  min-width: 0;
}
.seat-line {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  cursor: default;
}
.kind {
  font-size: var(--text-xs);
  letter-spacing: var(--ls-micro);
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--text-secondary) 10%, transparent);
  padding: 1px 8px;
  border-radius: var(--r-sm);
}
.seat-name {
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.seat-meta {
  flex: none;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
}
.seat-meta.dim {
  color: var(--text-faint);
}
.state-slot {
  flex: none;
}
.win-tag {
  font-size: var(--text-sm); /* 文案含中文（在途）：不加字距 */
  color: var(--accent);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.win-tag::before {
  content: "";
  width: 8px;
  height: 8px;
  border-left: 2px solid var(--accent);
  border-top: 2px solid var(--accent);
}
.expand {
  font-size: var(--text-xs);
  color: var(--text-faint);
  transition: transform 160ms var(--ease-std);
}
.expand.open {
  transform: rotate(90deg);
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
.m-file {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-remove {
  height: 24px;
  font-size: var(--text-sm); /* 文案含中文（移除） */
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
