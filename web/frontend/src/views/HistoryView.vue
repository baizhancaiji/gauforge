<script setup lang="ts">
/**
 * 05 历史 / 归档（m0-frontend-design §5 · 表格型全宽；m1-plan C6 真实化）
 * 全宽表格（复选框/ID/任务/状态徽标/归因/提交/结束/耗时/资源/队列归属）
 * + 顶部状态筛选；表格多选与候选页同一交互套件（useMultiSelect：复选框、
 * Shift 锚点范围、Ctrl/Cmd 单选、Ctrl+A/Esc/方向键），勾选经工具条批量
 * 导出 .out（POST /history/export → ZIP blob 下载，跨页勾选整体参与）；
 * 状态徽标与筛选下拉中文显示（taskStateLabel 单一来源，与队列页同纪律，
 * 2026-09-27 验收修正）；
 * 行点击（普通点击）→ 详情抽屉：终态冻结全字段以单行键值行呈现（dt 左/值右，
 * 2026-09-29 紧凑化，抽屉宽 --drawer-width 520px）+ 输入查看 / 输出预览与
 * 分析板块共占展示区（按钮开合互斥：分析默认收起，展开时点输入/输出则
 * 分析收起，反之亦然；展示区拉伸贴抽屉下缘，上游超高保底 300px 依赖抽屉
 * 滚动）+ 归档 + failed/skipped 重新排队与退回候选（409 提示）+ 清理入口
 * （统计回显）。批量导出走工具条（单条导出入口已移除）。
 * 归档管理视图承载 archived=true（独立路由 /archive，决策点 10），仅保留查看动作。
 */
import { computed, nextTick, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { client, exportOutputs, getText } from "@/api/client";
import type { components } from "@/api/contract";
import AnalysisPanel from "@/components/analysis/AnalysisPanel.vue";
import ConfirmModal from "@/components/ConfirmModal.vue";
import EmptyState from "@/components/EmptyState.vue";
import StateChip from "@/components/StateChip.vue";
import StoragePanel from "@/components/analysis/StoragePanel.vue";
import TablePager from "@/components/TablePager.vue";
import { useMultiSelect } from "@/composables/useMultiSelect";
import { useSortPref } from "@/composables/useSortPref";
import { useEventsStore } from "@/stores/events";
import { fmtDateTime, fmtDeclaredRes, fmtDuration, fmtHash, fmtMemory, fmtPercent } from "@/utils/format";
import { causeLabel, taskStateLabel } from "@/utils/labels";

type HistoryEntry = components["schemas"]["HistoryEntry"];

const route = useRoute();
const events = useEventsStore();

/** 归档模式（/archive 独立路由）：只读视图 + 输入/输出查看。 */
const archived = computed(() => route.meta.archived === true);

const list = ref<HistoryEntry[]>([]);
const total = ref(0);
/** 分页状态（m0-frontend-design §4.3 列表底栏）：筛选/排序变更回第 1 页，
 *  SSE 增量与路由往返保持在当前页；pageSize 取后端信封回落值。 */
const page = ref(1);
const pageSize = ref(0);
const loading = ref(false);
const everLoaded = ref(false);
const filter = ref<"all" | "succeeded" | "failed" | "skipped">("all");
/** 排序（openapi HistorySort）：默认提交倒序（上线前行为）。选择经视图
 *  偏好域持久化（历史页键 history.sort / 归档页键 archive.sort 分立各自
 *  记忆；同组件跨路由复用实例，键切换时重拉），重启/更新/断联不回默认。 */
const sortPrefKey = computed(() => (archived.value ? "archive.sort" : "history.sort"));
const sort = useSortPref(
  sortPrefKey, "submitted_desc",
  ["submitted_desc", "finished_desc", "finished_asc", "filename_asc", "filename_desc"]);
const selected = ref<HistoryEntry | null>(null);
const textView = ref<{ kind: "input" | "output"; content: string; error: string | null } | null>(null);
/** 分析板块开合（A-1：默认收起，与预览互斥，同占展示区）。 */
const anaOpen = ref(false);
const textViewEl = ref<HTMLElement | null>(null);
const actionNote = ref<{ ok: boolean; msg: string } | null>(null);

async function load() {
  loading.value = true;
  const { data } = await client.GET("/history", {
    params: {
      query: {
        ...(filter.value === "all" ? {} : { state: filter.value }),
        archived: archived.value,
        sort: sort.value,
        page: page.value,
        // page_size 省略 → 后端回落设置值（列表分页大小，即时生效）
      },
    },
  });
  loading.value = false;
  everLoaded.value = true;
  if (data) {
    total.value = data.total ?? 0;
    pageSize.value = data.page_size ?? 50;
    // 页码越界（归档/清理后总页数收缩）→ 钳到末页并重取一次
    const tp = Math.max(1, Math.ceil(total.value / Math.max(1, pageSize.value)));
    if (page.value > tp) {
      page.value = tp;
      return load();
    }
    list.value = (data.items as HistoryEntry[]) ?? [];
  }
}

// ---------- 空间占用面板（M3.7 C8）：拉取式，列表加载与清理后同步刷新 ----------
const usage = ref<components["schemas"]["StorageUsage"] | null>(null);

async function loadUsage() {
  if (archived.value) return; // 归档视图不重复占用统计（历史页清理区承载）
  const { data } = await client.GET("/storage/usage");
  usage.value = data ?? null;
}

/** 筛选/排序变更：回到第 1 页再取。 */
function resetPage() {
  page.value = 1;
  load();
}

function goPage(p: number) {
  page.value = p;
  load();
}

// history.appended（终态落库）→ 重拉当前页；路由切换（历史↔归档）回第 1 页重载。
watch(() => events.dirty.history, () => {
  load();
  loadUsage(); // 占用统计随终态落库/清理刷新（拉取式，无新增 SSE 事件）
});
watch(
  () => route.fullPath,
  () => {
    everLoaded.value = false;
    selected.value = null;
    page.value = 1;
    load();
    loadUsage(); // 归档 ↔ 历史切换同样拉新占用（历史页加载时机，§4.14 ③）
  },
);
load();
loadUsage();

async function open(e: HistoryEntry) {
  selected.value = e;
  textView.value = null;
  anaOpen.value = false;
  actionNote.value = null;
  const { data } = await client.GET("/history/{id}", { params: { path: { id: e.id } } });
  if (data) selected.value = data;
}

const activeId = computed(() => selected.value?.id ?? null);
const canRequeue = computed(
  () => selected.value?.state === "failed" || selected.value?.state === "skipped",
);

// ---------- 表格多选（与候选页同套件：useMultiSelect 锚点+焦点驱动） ----------
/** 滚动容器 ref：键盘事件宿主（tabindex=0）与行元素序来源（与列表响应序
 *  对齐，供导航滚动定位）。 */
const tableScroll = ref<HTMLElement | null>(null);
const {
  checkedIds,
  anchorIndex,
  focusedIndex,
  clearAll,
  resetIndices,
  click: checkAt,
  pointAt,
  toggle: toggleId,
  selectRange,
  selectAll,
  onKeydown: onListKeydown,
} = useMultiSelect({
  ids: () => list.value.map((h) => h.id),
  rows: () =>
    tableScroll.value
      ? Array.from(tableScroll.value.querySelectorAll<HTMLElement>("tbody tr"))
      : null,
});
// 列表整体重载（翻页/重取）→ 页内索引失效：重置锚点/焦点（勾选跨页保留）
watch(list, resetIndices);

const allChecked = computed(
  () =>
    list.value.length > 0 && list.value.every((h) => checkedIds.value.has(h.id)),
);

/** 表头全选/清空 */
function toggleAll() {
  if (allChecked.value) clearAll();
  else selectAll();
}

/** 行点击（修饰交互全在行上，参照资源管理器范式）：普通点击 → 详情抽屉
 *  （排错入口）+ 锚点/焦点同步衔接 Shift 扩展；Shift+行点击——从锚点行
 *  到目标行范围勾选（普通 Shift 替换式、Ctrl+Shift 追加式，锚点不动）；
 *  Ctrl/Cmd+行点击——切换单项勾选并重置锚点。修饰点击不开抽屉，
 *  多选导出不被打断。 */
function onRowClick(h: HistoryEntry, index: number, e: MouseEvent) {
  if (e.shiftKey && anchorIndex.value !== -1) {
    selectRange(anchorIndex.value, index, e.ctrlKey || e.metaKey);
    focusedIndex.value = index;
    return;
  }
  if (e.ctrlKey || e.metaKey) {
    toggleId(h.id);
    anchorIndex.value = index;
    focusedIndex.value = index;
    return;
  }
  open(h);
  pointAt(index);
}

/** 行复选框点击（统一接 Shift/Ctrl 修饰）。不 preventDefault——Chromium 的
 *  checkbox 取消激活回滚发生在 Vue 渲染写入之后，会覆盖 :checked 的同步
 *  （候选页同款修正：counter 已更新而复选框不亮）；放行原生翻转后按
 *  checkedIds 语义同步修正被点击项 DOM，随后容器聚焦承接键盘导航。 */
function onRowCheck(index: number, e: MouseEvent) {
  checkAt(index, e);
  const box = e.target as HTMLInputElement;
  const id = list.value[index]?.id;
  if (box && id != null) box.checked = checkedIds.value.has(id);
  tableScroll.value?.focus();
}

// ---------- 勾选批量导出（POST /history/export → ZIP blob 落盘） ----------
const exporting = ref(false);
const exportNote = ref<string | null>(null);

async function exportSelected() {
  // 跨页勾选集合整体参与（useMultiSelect 勾选跨页保留），按 id 升序打包
  const ids = [...checkedIds.value].map(Number).sort((a, b) => a - b);
  if (!ids.length) return;
  exporting.value = true;
  exportNote.value = null;
  const { data, error } = await exportOutputs(ids);
  exporting.value = false;
  if (error || !data) {
    const body = error as unknown as { error?: { message?: string } };
    exportNote.value = body?.error?.message ?? "导出失败";
    return;
  }
  // binary 契约经 parseAs blob 取包；文件名带本地时刻避免重复导出互相覆盖
  const url = URL.createObjectURL(data as unknown as Blob);
  const a = document.createElement("a");
  const t = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  a.download =
    `gauforge-outputs-${t.getFullYear()}${p(t.getMonth() + 1)}${p(t.getDate())}` +
    `-${p(t.getHours())}${p(t.getMinutes())}${p(t.getSeconds())}.zip`;
  a.href = url;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------- 输入查看 / 输出预览（展示区拉伸贴底，内部滚动） ----------
async function viewText(kind: "input" | "output") {
  const e = selected.value;
  if (!e) return;
  anaOpen.value = false; // 与分析板块互斥：开一边关另一边
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
  } else {
    textView.value = { kind, content: (res.data as unknown as string) ?? "", error: null };
  }
  // 上游字段超高时展示区在视口外——渲染后滚入视野
  await nextTick();
  textViewEl.value?.scrollIntoView({ block: "end" });
}

/** 分析板块开合（与预览互斥）：展开时收起预览。 */
function toggleAna() {
  anaOpen.value = !anaOpen.value;
  if (anaOpen.value) textView.value = null;
}

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
  if (data) {
    // 提交核验规范化注记（§2.5 三路径之一：仅据响应 normalized 字段展示）
    actionNote.value = {
      ok: true,
      msg: data.normalized
        ? `已入待执行队列 S${data.seat_id} — 输入已自动规范化（换行/空行）`
        : `已入待执行队列 S${data.seat_id}`,
    };
  }
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
    cleanupNote.value = `清理完成 — 检查 ${data.checked} 项 — 移除 chk ${data.removed_chk} — rwf ${data.removed_rwf}`;
  }
  loadUsage(); // 手动清理后统计即时反映（§2.6）
}
</script>

<template>
  <div class="history">
    <div class="controls">
      <label v-if="!archived" class="mono filter">
        <span>状态筛选</span>
        <select v-model="filter" @change="resetPage">
          <option value="all">全部</option>
          <option value="succeeded">成功</option>
          <option value="failed">失败</option>
          <option value="skipped">跳过</option>
        </select>
      </label>
      <label class="mono filter">
        <span>排序</span>
        <select v-model="sort" @change="resetPage">
          <option value="submitted_desc">提交时间 / 新→旧</option>
          <option value="finished_desc">完成时间 / 新→旧</option>
          <option value="finished_asc">完成时间 / 旧→新</option>
          <option value="filename_asc">文件名 / A→Z</option>
          <option value="filename_desc">文件名 / Z→A</option>
        </select>
      </label>

      <!-- 勾选批量导出（与候选页多选同套件）：跨页勾选整体参与 -->
      <span class="tb-divider" aria-hidden="true"></span>
      <span v-if="checkedIds.size" class="picked-count mono">已选 {{ checkedIds.size }}</span>
      <button
        class="btn btn--secondary"
        type="button"
        :disabled="!checkedIds.size || exporting"
        @click="exportSelected"
      >
        {{ exporting ? "导出中 …" : "导出 .out" }}
      </button>
      <span v-if="exportNote" class="export-note mono" role="alert">{{ exportNote }}</span>

      <span class="spacer"></span>
      <RouterLink v-if="!archived" class="btn btn--secondary" to="/archive">归档管理</RouterLink>
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
      <!-- 占用面板（M3.7 C8）：常驻读数 + 超阈琥珀警示 + 可展开明细 -->
      <StoragePanel v-if="!archived" :usage="usage" />
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

    <section v-else class="table-card">
      <!-- 多选交互宿主容器（与候选页同款）：tabindex 承接键盘导航
           （Ctrl+A/Esc/方向键），Shift 按下的 mousedown 阻止默认行为
           防范围点击拖出文本选区 -->
      <div
        ref="tableScroll"
        class="table-scroll"
        tabindex="0"
        @keydown="onListKeydown"
        @mousedown.shift.prevent
      >
        <table class="table">
          <thead>
            <tr>
              <th class="chk-col">
                <input
                  class="ck"
                  type="checkbox"
                  :checked="allChecked"
                  aria-label="全选历史条目"
                  @change="toggleAll"
                />
              </th>
              <th class="mono">ID</th>
              <th class="mono">任务</th>
              <th class="mono">状态</th>
              <th class="mono">归因</th>
              <th class="mono">提交</th>
              <th class="mono">结束</th>
              <th class="mono">耗时</th>
              <th class="mono">资源</th>
              <th class="mono">出处</th>
            </tr>
          </thead>
          <tbody class="stagger">
            <tr
              v-for="(h, i) in list"
              :key="h.id"
              :class="{
                'row--active': activeId === h.id,
                'row--checked': checkedIds.has(h.id),
                'row--focused': focusedIndex === i,
              }"
              @click="onRowClick(h, i, $event)"
            >
              <td class="chk-col" @click.stop>
                <input
                  class="ck"
                  type="checkbox"
                  :checked="checkedIds.has(h.id)"
                  :aria-label="`选择 ${h.filename}`"
                  @click="onRowCheck(i, $event)"
                />
              </td>
              <td class="mono dim">{{ String(h.id).padStart(3, "0") }}</td>
              <td class="mono file" :title="h.filename">{{ h.filename }}</td>
              <!-- 状态列中文显示（taskStateLabel 单一来源，与队列页同纪律，2026-09-27） -->
              <td>
                <StateChip :state="h.state" :label="taskStateLabel[h.state] ?? h.state" />
              </td>
              <td class="mono dim">{{ h.cause ? causeLabel[h.cause] : "—" }}</td>
              <td class="mono dim">{{ fmtDateTime(h.submitted_at) }}</td>
              <td class="mono dim">{{ fmtDateTime(h.finished_at) }}</td>
              <td class="mono">{{ fmtDuration(h.wall_time_s) }}</td>
              <td class="mono dim">{{ fmtDeclaredRes(h.resources) }}</td>
              <td class="mono dim">{{ h.queue_id ?? "直提" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="scanline" aria-hidden="true" v-if="loading"></div>
      <!-- 列表底栏（§4.3 标准套件）：计数右对齐 + 分页控件居中（单页时控件隐藏） -->
      <TablePager
        v-if="list.length"
        :total="total"
        :page="page"
        :page-size="pageSize"
        @change="goPage"
      />
    </section>

    <!-- 详情抽屉（行点击；终态冻结字段全量） -->
    <div v-if="selected" class="scrim" @click.self="selected = null">
      <aside class="drawer">
        <header class="d-head">
          <span class="d-title mono">
            {{ String(selected.id).padStart(3, "0") }} — {{ selected.filename }}
          </span>
          <StateChip :state="selected.state" :label="taskStateLabel[selected.state] ?? selected.state" />
        </header>

        <dl class="cell">
          <dt class="mono">状态 / 归因</dt>
          <dd>{{ selected.cause ? causeLabel[selected.cause] : "正常结束" }}</dd>
        </dl>
        <dl class="cell">
          <dt class="mono">提交 / 启动 / 结束</dt>
          <dd class="mono">
            {{ fmtDateTime(selected.submitted_at) }} /
            {{ fmtDateTime(selected.started_at) }} /
            {{ fmtDateTime(selected.finished_at) }}
          </dd>
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
            CPU {{ selected.resources.nproc.value }}（{{ selected.resources.nproc.defaulted ? "默认补齐" : "声明" }}）
            / MEM {{ selected.resources.mem_gb.value }} GB（{{ selected.resources.mem_gb.defaulted ? "默认补齐" : "声明" }}）
          </dd>
        </dl>
        <dl class="cell">
          <dt class="mono">HQ 任务 / 出处</dt>
          <dd class="mono">{{ selected.hq_job_id ?? "—" }} / {{ selected.queue_id ?? "直接提交" }}</dd>
        </dl>
        <dl v-if="selected.monitor_summary" class="cell">
          <dt class="mono">监控峰值</dt>
          <dd class="mono">
            CPU {{ fmtPercent(selected.monitor_summary.cpu_peak_percent) }} / MEM
            {{ fmtMemory(selected.monitor_summary.mem_peak_mb) }} / 停滞
            {{ selected.monitor_summary.stall_alerts ?? 0 }} 次 / 累计
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

        <p v-if="actionNote" class="note mono" :class="actionNote.ok ? 'note--ok' : 'note--bad'">
          {{ actionNote.msg }}
        </p>

        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="viewText('input')">输入</button>
          <button class="btn btn--secondary" type="button" @click="viewText('output')">输出</button>
          <button
            class="btn btn--secondary ana-toggle"
            :class="{ 'ana-toggle--on': anaOpen }"
            type="button"
            :aria-expanded="anaOpen"
            @click="toggleAna"
          >
            分析
          </button>
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

        <!-- 展示区（输入/输出预览与分析互斥，同占动作行以下剩余高度：
             上游字段放得下时拉伸贴抽屉下缘，放不下保底 300px 依赖抽屉滚动） -->
        <div v-if="anaOpen" class="sub-region">
          <!-- 分析区（M3.1：内嵌历史详情，不单列页面；异常条目由组件内置置灰态；
               惰性挂载——首次展开才发起概览请求） -->
          <AnalysisPanel :key="selected.id" :execution-id="selected.id" :entry-state="selected.state" />
        </div>
        <div v-else-if="textView" ref="textViewEl" class="text-view">
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
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.controls {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-shrink: 0;
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
.cleanup-note {
  font-size: var(--text-sm);
  color: var(--state-succeeded);
}
/* 列表卡：flex 列，滚动包裹层吃剩余高度、局部滚动（§3 视口纪律） */
.table-card {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--bg-raised);
}
.table-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
/* ---------- 表格套件（与候选页同款：真表格 + 粘性表头 + 复选框列） ---------- */
.table {
  width: 100%;
  /* 行级 min-width 触发横向滚动（收窄窗口不挤压列；复选框列后 760+32） */
  min-width: 800px;
  /* 边框模型必须 separate（间距 0）：collapse 的单元格绘制由表层级合并处理，
     粘性表头滚动时行内容会穿透（候选页列表局部滚动改造显形，同款修复） */
  border-collapse: separate;
  border-spacing: 0;
  font-size: var(--text-sm);
}
th {
  text-align: left;
  /* 表头样式类承载中文（混排纪律 1）：升 --text-sm、去字距 */
  font-size: var(--text-sm);
  font-weight: 500;
  text-transform: uppercase;
  color: var(--text-faint);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-raised);
  position: sticky;
  top: 0;
  /* z-index 建自身层叠上下文（与 separate 边框模型配套，同候选页）；
     局部层 1 远低于全局层级档，不入 z 令牌 */
  z-index: 1;
  border-bottom: 1px solid var(--border-hair);
}
td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-hair);
  cursor: pointer;
  vertical-align: middle;
  white-space: nowrap;
}
tbody tr:last-child td {
  border-bottom: none;
}
tbody tr {
  transition: background-color var(--dur-fast) var(--ease-std);
}
tbody tr:hover {
  background: var(--row-hover);
}
/* 勾选行（useMultiSelect 勾选集合）：范围内每行呈选中态底色，hover 轻微
   加深保留反馈 */
tbody tr.row--checked,
tbody tr.row--checked:hover {
  background: color-mix(in srgb, var(--accent) 7%, transparent);
}
/* 选中行（抽屉打开）：inset 2px accent 条 */
.row--active {
  background: color-mix(in srgb, var(--accent) 7%, transparent);
  box-shadow: inset 2px 0 0 var(--accent);
}
/* 键盘导航焦点行：inset 发丝描边区别于抽屉选中左条，叠加时两形态并存 */
.row--focused {
  box-shadow: inset 0 0 0 1px var(--accent);
}
.row--active.row--focused {
  box-shadow: inset 2px 0 0 var(--accent), inset 0 0 0 1px var(--accent);
}
/* 复选框列（§4.6 checkbox 规格，样式类 .ck 全局定义） */
.chk-col {
  width: 32px;
  text-align: center;
}
/* 工具条批量导出组（与筛选区以竖分割线分主从） */
.tb-divider {
  width: 1px;
  height: 20px;
  background: var(--border-strong);
  flex: none;
}
.picked-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.export-note {
  font-size: var(--text-sm);
  color: var(--danger);
}
.file {
  color: var(--text-primary);
  font-weight: 500;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dim {
  color: var(--text-faint);
}
/* 刷新两态：底部 1px 磷光扫描线（§4.3）——处于滚动区外、列表卡底部常驻可视 */
.scanline {
  height: 1px;
  flex-shrink: 0;
  background: var(--accent);
  /* 引用 base.css 共用 scanline（--ease-std），不重复定义 keyframes */
  animation: scanline var(--dur-scan) var(--ease-std) infinite;
}
.skel {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--bg-raised);
}
.sk-row {
  height: var(--row-height);
  border-bottom: 1px solid var(--border-hair);
  background: var(--bg-inset);
  animation: row-in var(--dur-enter) var(--ease-std) both;
}
.sk-row:nth-child(2) {
  animation-delay: var(--stagger-step);
}
.sk-row:nth-child(3) {
  animation-delay: calc(var(--stagger-step) * 2);
}
.sk-row:nth-child(4) {
  animation-delay: calc(var(--stagger-step) * 3);
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
  width: var(--drawer-width);
  height: 100%;
  background: var(--bg-overlay);
  border-left: 1px solid var(--border-hair);
  padding: var(--space-5);
  overflow: auto;
  display: flex;
  flex-direction: column;
  animation: slide var(--dur-slide) var(--ease-std);
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
/* 字段行（2026-09-29 紧凑化）：一行一字段，dt 左 / 值右对齐；
   行距由自身 padding 承担（抽屉不设 gap），首个字段行与表头分隔线相邻去重 */
.cell {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  border-top: 1px solid var(--border-hair);
  padding: var(--space-2) 0;
}
.cell:first-of-type {
  border-top: none;
}
.cell dt {
  flex: none;
  font-size: var(--text-sm); /* 承载中文（状态 / 归因 等） */
  color: var(--text-faint);
}
.cell dd {
  flex: 1;
  min-width: 0;
  margin: 0;
  text-align: right;
  overflow-wrap: anywhere; /* 超长值（chk 位置等）换行不出格 */
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.note {
  margin: var(--space-2) 0 0;
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
  margin-top: var(--space-3);
}
/* 分析开合按钮展开态：accent 描边（同 .preset--on 语义） */
.ana-toggle--on {
  color: var(--accent);
  border-color: var(--accent-dim);
}
/* 展示区（预览/分析互斥共用）：拉伸吃动作行以下剩余高度贴抽屉下缘，
   上游内容超高时保底 300px 依赖抽屉滚动 */
.sub-region,
.text-view {
  flex: 1 1 auto;
  min-height: 300px;
  display: flex;
  flex-direction: column;
  margin-top: var(--space-3);
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
/* 预览体拉伸内部滚动（去限高：展示区本体已限底） */
.tv-body {
  margin: 0;
  padding: var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.confirm-line {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
</style>
