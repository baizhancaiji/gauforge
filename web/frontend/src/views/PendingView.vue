<script setup lang="ts">
/**
 * 03 待执行（m0-frontend-design §5 · 席位型；m1-plan C4 真实化）
 * 页首容量仪表（OCCUPIED 分段 LED，超限段琥珀示警）；席位纵向列表，
 * 窗口触及席位（locked）加左侧 2px 磷光条 + 「在途」标记，不可作拖源/落点
 * 亦不可移除；其后为等待区（分隔注记），支持拖拽重排（PUT /pending/order
 * 全量原子，锁定席位保持原下标即放行）与整席/席位内未执行成员移除（二次
 * 确认）。数据源：SSE pending.snapshot 驱动 events store；首帧回落 REST。
 * 席位重排动效（A-12，2026-10-02）：迁移 usePointerSort 指针跟手画布式
 * （与队列编辑框一致）——变高行前缀和定位（子表展开行高可变）、逐行门控
 * （锁定席位不可作拖源/落点）；与队列页队列框同一动效纪律。
 * 队列席位成员重排（2026-10-04）：展开子表抽为 PendingSeatMembers 组件，
 * 成员拖拽复用既有 usePointerSort（与席位行同一动效纪律，子组件行
 * pointerdown 阻断冒泡防误触席位拖拽）；门控按 m2 分级矩阵定稿——
 * 执行中席位不可拖、仅 staged 成员可作拖源/落点，提交 PATCH
 * /queues/{id} member_ids 全量有序原子。
 * 席位展开切换修复（2026-10-04）：等待席位可拖——onDown 的
 * setPointerCapture + preventDefault 使后续 click 不再派发，点击行无法
 * 展开子表（锁定席位反而可展开）；切换改由 .seat 行 pointerup 统一判定
 * （按压起于 .seat-line 且未发生实质拖动才切换），.seat-line 的 click
 * 绑定移除，等待/在途席位行为一致且不误触子表与行内按钮。
 */
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";
import EmptyState from "@/components/EmptyState.vue";
import PendingSeatMembers from "@/components/PendingSeatMembers.vue";
import StateChip from "@/components/StateChip.vue";
import { fmtDateTime, fmtTaskId } from "@/utils/format";
import { useEventsStore } from "@/stores/events";
import { usePointerSort } from "@/composables/usePointerSort";

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

// ---------- 席位重排（指针跟手画布式 usePointerSort，A-12 迁移） ----------
// PUT /pending/order 全量原子；提交 order 保证锁定席位下标不变，越界本地
// 拒绝并提示。逐行门控：锁定席位不可作拖源（enabledAt），落点解析跳过
// 锁定槽位取最近可落槽。等待区注记非行元素（rowSelector 过滤），按前缀和
// 绝对定位在锁定区与等待区间隙。
const rootEl = ref<HTMLElement | null>(null);
const canvasEl = ref<HTMLElement | null>(null);
const scrollerEl = ref<HTMLElement | null>(null);
const orderError = ref<string | null>(null);

/** 首个未锁定席位下标（无锁定时 -1）：等待区注记锚点。 */
const firstUnlocked = computed(() => {
  if (!anyLocked.value) return -1;
  return seats.value.findIndex((s) => !s.locked);
});

const canDrag = (s: PendingSeat) => !s.locked;

/** 提交链路（与迁移前一致）：本地锁定不变式校验 → PUT /pending/order →
 *  applySnapshot。校验失败不发请求（拖拽行由视觉归位弹回）。 */
async function reorder(from: number, to: number) {
  const before = seats.value.map((x) => x.seat_id);
  const ids = [...before];
  const [movedId] = ids.splice(from, 1);
  if (movedId == null) return;
  ids.splice(to, 0, movedId);
  // 后端语义（锁定席位保持原下标即放行，c6a0906e3）：本地先校验，越界不发请求
  const movedLocked = seats.value.some(
    (x) => x.locked && ids.indexOf(x.seat_id) !== before.indexOf(x.seat_id),
  );
  if (movedLocked) {
    orderError.value = "重排越界 — 锁定席位必须保持原位";
    return;
  }
  const { data, error } = await client.PUT("/pending/order", {
    body: { seat_order: ids as number[] },
  });
  if (error) {
    orderError.value = "重排被拒绝 — 锁定席位必须保持原位";
    return;
  }
  if (data) applySnapshot(data);
}

const sort = usePointerSort({
  count: () => seats.value.length,
  enabled: () => seats.value.length > 1,
  enabledAt: (i) => canDrag(seats.value[i] as PendingSeat),
  canvas: canvasEl,
  scroller: scrollerEl,
  rowSelector: ".seat", // 等待区注记非行元素，不进行高量测
  commit: (from, to) => void reorder(from, to),
});

onMounted(() => {
  // 滚动容器为页面内容列（触边自动滚屏的判定基准），就近查找不硬编码层级
  scrollerEl.value = rootEl.value?.closest(".content") ?? null;
  void nextTick(() => sort.measure());
});

// 席位集变化（SSE 快照/重排提交）与子表展开收起 → 行高重测（前缀和定位）
watch(seats, () => void nextTick(() => sort.measure()));
watch(expanded, () => void nextTick(() => sort.measure()));

/** 席位展开切换（pointerup 统一判定）：捕获期间 pointerup 被重定向到
 *  .seat 行、target 无法回查按下位置，故在按下时记录本次按压档案；组件级
 *  单按压记录——子表成员行 pointerdown 带 .stop 不经过此处，且 pointerup
 *  时 seat_id/pointerId 不符即忽略，子表内点击不会误触席位展开。 */
let press: { onLine: boolean; seatId: number; pointerId: number } | null = null;

function onSeatDown(e: PointerEvent, s: PendingSeat, i: number) {
  const t = e.target as HTMLElement | null;
  press = {
    onLine:
      !(e.pointerType === "mouse" && e.button !== 0) && // 只认左键/非鼠标
      t != null &&
      t.closest(".seat-line") != null && // 仅主行触发，子表/注记不算
      t.closest("button") == null, // 行内按钮不劫持（与 onDown 同门控）
    seatId: s.seat_id,
    pointerId: e.pointerId,
  };
  sort.onDown(e, i);
}

/** 松手：排序器收尾（拖拽归位提交）在前；本次按压始于 .seat-line 且未
 *  发生实质拖动（moved，既有「拖后的点击不作切换」语义）才展开/收起。 */
function onSeatUp(e: PointerEvent, s: PendingSeat) {
  void sort.onUp();
  const p = press;
  press = null;
  if (!p || !p.onLine || p.seatId !== s.seat_id || e.pointerId !== p.pointerId) return;
  if (sort.moved.value) return;
  if (s.kind === "queue") toggle(s.seat_id);
}

/** 取消（滚动手势接管等）：不视作点击，丢弃按压档案并照常复位排序器。 */
function onSeatCancel() {
  press = null;
  void sort.onUp();
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

  <div v-else ref="rootEl" class="pending">
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

    <section v-if="!seats.length" class="seats">
      <div class="empty-wrap">
        <EmptyState glyph="▯" text="席位空置 — 在候选页提交任务后在此排队" />
      </div>
    </section>

    <!-- 席位画布（指针跟手拖拽，A-12）：行 absolute + transform 定位，
         画布定高由组合式按逐行前缀和给出 -->
    <section
      v-else
      ref="canvasEl"
      class="seats seats--canvas"
      :class="{ 'seats--live': seats.length > 1 }"
      :style="sort.canvasStyle.value"
    >
      <div
        v-for="(s, i) in seats"
        :key="s.seat_id"
        class="seat"
        :class="{
          'seat--locked': s.locked,
          'seat--dragging': sort.dragIndex.value === i,
        }"
        :style="sort.styleFor(i)"
        @pointerdown="onSeatDown($event, s, i)"
        @pointermove="sort.onMove($event)"
        @pointerup="onSeatUp($event, s)"
        @pointercancel="onSeatCancel"
      >
        <span class="seat-no mono">S{{ String(s.seat_id).padStart(2, "0") }}</span>

        <div class="seat-body">
          <!-- 窗口边界注记（§4.5 样板 divider-note）：并入等待区首行——
               画布行距 8px 放不下独立注记行（居中必与上下卡片重叠），
               行内渲染使高度自然计入前缀和 -->
          <div
            v-if="i === firstUnlocked"
            class="divider-note mono"
          >▼ 等待区 · 窗口未触及，可重排 / 移除</div>
          <!-- 展开/收起由 .seat 行的 pointerup 统一判定（见 script 说明） -->
          <div class="seat-line">
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
            <!-- locked（在途）席位不渲染状态 chip：与「在途」标记语义重复 -->
            <span v-if="s.kind === 'task' && s.members[0] && !s.locked" class="state-slot">
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

          <!-- 队列席位展开成员子表（PendingSeatMembers）：明细 + 未执行
               成员移除 + 拖拽重排（usePointerSort，每席位独立排序器） -->
          <PendingSeatMembers
            v-if="s.kind === 'queue' && expanded[s.seat_id]"
            :seat="s"
            @remove="(tid) => (removing = { seat: s, task_id: tid })"
            @changed="load"
            @error="(msg) => (orderError = msg)"
          />
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
/* 席位画布（指针跟手拖拽，A-12）：relative + grid gap（供行距量测），
   行 absolute + transform 定位，画布定高由组合式前缀和给出 */
.seats {
  position: relative;
  display: grid;
  gap: var(--space-2);
}
.seats--live .seat:not(.seat--locked) {
  cursor: grab;
}
.empty-wrap {
  padding: var(--space-4);
}
.divider-note {
  margin: 0 0 var(--space-2);
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
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: grid;
  grid-template-columns: 44px 1fr auto;
  gap: var(--space-4);
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  transition: border-color var(--dur-fast) var(--ease-std);
}
.seat:hover {
  border-color: var(--border-strong);
}
/* 窗口边界可视化（§4.5）：磷光条 + 泛光 + 「在途」标记 */
.seat--locked {
  border-left: 2px solid var(--accent);
  box-shadow: var(--glow-running);
}
/* 拿起态：accent 描边 + 浮起投影（与队列编辑框同款，令牌组合） */
.seat--dragging {
  z-index: 1;
  border-color: var(--accent);
  box-shadow: var(--shadow-pop);
}
.seats--live .seat--dragging {
  cursor: grabbing;
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
  padding: 1px var(--space-2);
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
/* 展开箭头与队列页同款：弹性居中保证绕字形中心原地旋转（§5 02 队列页修复） */
.expand {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-lg);
  line-height: 1;
  color: var(--text-faint);
  transition: transform var(--dur-view) var(--ease-std);
}
.expand.open {
  transform: rotate(90deg);
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
