<script setup lang="ts">
/**
 * 01 候选任务（m0-frontend-design §5 · 表格型双栏；m1-plan C1 真实化）
 * 左列列表（id/文件名/title/来源徽标——失败退回附琥珀归因注记）+ 导入交互
 * （文件多选/文件夹 webkitdirectory、422 逐文件失败清单、重复导入提示）
 * + 剔除（二次确认）。列表由后端按「回退候选置顶 + 创建时间倒序（批内 id
 * 逆序）」排序后返回（openapi /candidates），前端按响应序渲染（原页内排序
 * 双实现已删）。
 * 右侧预览卡由 BlockEditor 承载（M2 C1：只读/编辑双态、分块自动保存、
 * 拼写警告与 CRLF 中性注记），本页仅负责行选中与提交动作。
 */
import { computed, ref, watch } from "vue";

import { client, getText } from "@/api/client";
import type { components } from "@/api/contract";
import BlockEditor from "@/components/BlockEditor.vue";
import ConfirmModal from "@/components/ConfirmModal.vue";
import EmptyState from "@/components/EmptyState.vue";
import QueueEditorModal, { type MemberRow } from "@/components/QueueEditorModal.vue";
import StateChip from "@/components/StateChip.vue";
import TablePager from "@/components/TablePager.vue";
import { useMultiSelect } from "@/composables/useMultiSelect";
import { useEventsStore } from "@/stores/events";
import { fmtDateTime, fmtTaskId } from "@/utils/format";
import { causeLabel } from "@/utils/labels";

type Candidate = components["schemas"]["Candidate"];
type Queue = components["schemas"]["Queue"];

const events = useEventsStore();

const list = ref<Candidate[]>([]);
const total = ref(0);
/** 分页状态（m0-frontend-design §4.3 列表底栏）：page 当前页（1 起），
 *  pageSize 取后端信封回落值（设置项 page_size，全局统一）。 */
const page = ref(1);
const pageSize = ref(0);
const loading = ref(false);
/** 首载骨架行（§4.3 加载两态）：首帧渲染骨架，此后刷新仅底部扫描线。 */
const everLoaded = ref(false);
const selected = ref<Candidate | null>(null);

async function load() {
  loading.value = true;
  const { data } = await client.GET("/candidates", {
    params: { query: { page: page.value } },
  });
  loading.value = false;
  everLoaded.value = true;
  if (data) {
    total.value = data.total ?? 0;
    pageSize.value = data.page_size ?? 50;
    // 页码越界（删减后总页数收缩）→ 钳到末页并重取一次
    const tp = Math.max(1, Math.ceil(total.value / Math.max(1, pageSize.value)));
    if (page.value > tp) {
      page.value = tp;
      return load();
    }
    list.value = (data.items as Candidate[]) ?? [];
  }
}

function goPage(p: number) {
  page.value = p;
  load();
}

/** 行点击：预览选中 + 锚点/焦点同步（不改变勾选，衔接键盘 Shift 扩展） */
function select(c: Candidate, index: number) {
  selected.value = c;
  pointAt(index);
}

// 契约 §3.5⑥：候选通知事件 → 重拉当前页。
watch(() => events.dirty.candidates, load);
load();

// ---------- 导入（M1.1；M2 C4 增补文件夹导入成队选项） ----------
const importing = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const dirInput = ref<HTMLInputElement | null>(null);
const importNote = ref<string | null>(null);
const filterNote = ref<string | null>(null);
const importErrors = ref<{ filename: string; message: string }[]>([]);
// C4 导入成队：勾选后文件夹导入按 queue_from_folder 上送（mode=files 不生效），
// 队列名缺省回落顶层目录名；越界拒绝成队时后端回落全部候选并明示原因。
const queueFromFolder = ref(false);
const queueName = ref("");
const fallbackNote = ref<string | null>(null);

/** B3：文件夹导入仅提交受支持输入文件（.gjf/.com，不区分大小写）。
 *  整目录直传会因杂文件触发整批 422，前端先行过滤（F-03）。 */
const SUPPORTED_EXTS = [".gjf", ".com"];

function isSupported(f: File): boolean {
  const dot = f.name.lastIndexOf(".");
  const ext = dot >= 0 ? f.name.slice(dot).toLowerCase() : "";
  return SUPPORTED_EXTS.includes(ext);
}

/** webkitRelativePath 任一段以「.」开头即视为隐藏目录内文件，跳过。 */
function inHiddenDir(f: File): boolean {
  const rel =
    (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
  return rel.split("/").some((seg) => seg.startsWith("."));
}

/** 顶层目录名（webkitRelativePath 首段）——契约 folder_name 缺省来源。 */
function folderTopName(files: File[]): string {
  const rel = (files[0] as File & { webkitRelativePath?: string })
    .webkitRelativePath;
  return rel && rel.includes("/") ? rel.split("/")[0] : "";
}

function pickFiles() {
  importNote.value = null;
  filterNote.value = null;
  fallbackNote.value = null;
  importErrors.value = [];
  fileInput.value?.click();
}
function pickFolder() {
  importNote.value = null;
  filterNote.value = null;
  fallbackNote.value = null;
  importErrors.value = [];
  dirInput.value?.click();
}

async function onImportChange(e: Event, mode: "files" | "folder") {
  const input = e.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  input.value = ""; // 允许再次选择同一批文件
  if (!files.length) return;
  let picked = files;
  if (mode === "folder") {
    picked = files.filter((f) => isSupported(f) && !inHiddenDir(f));
    if (!picked.length) {
      // 过滤后为空：提示且不发请求（避免整批 422 噪声）
      filterNote.value = "所选文件夹内无受支持的输入文件（.gjf/.com）— 未发起导入";
      return;
    }
  }
  importing.value = true;
  importNote.value = null;
  filterNote.value = null;
  fallbackNote.value = null;
  importErrors.value = [];
  const fd = new FormData();
  fd.append("mode", mode);
  if (mode === "folder" && queueFromFolder.value) {
    fd.append("queue_from_folder", "true");
    fd.append("folder_name", queueName.value.trim() || folderTopName(files));
  }
  for (const f of picked) fd.append("files", f, f.name);
  const { data, error } = await client.POST("/candidates", {
    body: fd as never,
  });
  importing.value = false;
  if (error) {
    // 整批原子（m1-plan §8 决策点 2）：任一失败 422 + details 逐文件。
    const detail = (
      error as unknown as {
        error?: { details?: { errors?: { filename: string; message: string }[] } };
      }
    ).error?.details;
    importErrors.value = detail?.errors ?? [];
    return;
  }
  if (data) {
    // duplicate 已入契约（openapi.yaml CandidateCreate.files），不再强转读取
    const dups = data.files.filter((f) => f.duplicate).map((f) => f.filename ?? "");
    let msg = dups.length
      ? `已导入 ${data.files.length} 份（${dups.length} 份与既有候选同名同内容，已另行建目）`
      : `已导入 ${data.files.length} 份`;
    if (data.queue) msg += ` — 已保存为队列「${data.queue.name ?? ""}」`;
    importNote.value = msg;
    if (data.queue_fallback_reason) {
      // 越界拒绝成队：回落全部生成候选（后端明示原因），中性信息注记展示
      fallbackNote.value = `成队未满足 — ${data.queue_fallback_reason}`;
    }
    queueFromFolder.value = false;
    queueName.value = "";
  }
  load();
}

// ---------- 行内提交（M1.3：确认框完整输入限高滚动 / Link0 黄警 / 满员 409） ----------
const submitting = ref<Candidate | null>(null);
const submitInput = ref("");
const submitMissing = ref<string[]>([]);
const submitDefaults = ref<{ nproc: number | null; mem: number | null }>({
  nproc: null,
  mem: null,
});
const submitFetching = ref(false);
const submitBusy = ref(false);
const submitError = ref<string | null>(null);
const submitActive = computed(() => submitting.value != null);
/** 提交核验规范化注记（§2.5 契约增量：仅据响应 normalized 字段展示）。 */
const submitNote = ref<string | null>(null);

async function openSubmit(c: Candidate) {
  submitting.value = c;
  submitInput.value = "";
  submitMissing.value = [];
  submitError.value = null;
  submitNote.value = null;
  submitFetching.value = true;
  const [inp, prev, set] = await Promise.all([
    // 该端点契约为 text/plain，经 getText 统一按文本取（封装动机见 api/client.ts）
    getText("/candidates/{id}/input", c.id),
    client.GET("/candidates/{id}/preview", { params: { path: { id: c.id } } }),
    client.GET("/settings"),
  ]);
  submitFetching.value = false;
  submitInput.value = inp.data ?? "";
  submitMissing.value = prev.data?.blocks.link0.missing ?? [];
  const runtime = set.data?.runtime ?? [];
  const num = (k: string) => runtime.find((s) => s.key === k)?.value;
  submitDefaults.value = {
    nproc: (num("link0_default_nproc") as number | undefined) ?? null,
    mem: (num("link0_default_mem_gb") as number | undefined) ?? null,
  };
}

/** 黄警文案：缺失项 + 设置面板缺省值（验收路径第 3 步）。
 *  后端 missing 为不带 % 前缀的指令名（如 "NProcShared"、"Mem"）。 */
const submitWarnText = computed(() => {
  const parts: string[] = [];
  if (submitMissing.value.includes("NProcShared") && submitDefaults.value.nproc != null)
    parts.push(`%NProcShared=${submitDefaults.value.nproc}`);
  if (submitMissing.value.includes("Mem") && submitDefaults.value.mem != null)
    parts.push(`%Mem=${submitDefaults.value.mem} GB`);
  const head = submitMissing.value.map((m) => `%${m}`).join("、");
  return parts.length ? `${head} 未声明 · 执行时将按默认值补齐（${parts.join("、")}）` : `${head} 未声明 · 执行时将按默认值补齐`;
});

async function confirmSubmit() {
  const c = submitting.value;
  if (!c) return;
  submitBusy.value = true;
  submitError.value = null;
  const { data, error } = await client.POST("/candidates/{id}/submit", {
    params: { path: { id: c.id } },
  });
  submitBusy.value = false;
  if (error) {
    const body = error as unknown as { error?: { code?: string; message?: string } };
    submitError.value =
      body.error?.code === "PENDING_CAPACITY_FULL"
        ? "在途席位满员 — 请在待执行页移除席位或调高上限后重试"
        : (body.error?.message ?? "提交失败");
    return;
  }
  submitting.value = null;
  // 提交核验规范化注记（中性档 §4.6；仅据响应 normalized 字段，不自行检测）
  submitNote.value = data?.normalized
    ? `已提交 ${fmtTaskId(c.id)} — 输入已自动规范化（换行/空行）`
    : null;
  load();
}

// ---------- 剔除（删除任务实体唯一入口，二次确认） ----------
const removing = ref<Candidate | null>(null);
const removeLoading = ref(false);

async function confirmRemove() {
  const c = removing.value;
  if (!c) return;
  removeLoading.value = true;
  await client.DELETE("/candidates/{id}", { params: { path: { id: c.id } } });
  removeLoading.value = false;
  removing.value = null;
  if (selected.value?.id === c.id) selected.value = null;
  load();
}

// 来源徽标（样本语义：安静档状态色 + 中文措辞）；失败退回附琥珀归因注记。
const originView: Record<string, { color: string; label: string }> = {
  imported: { color: "staged", label: "导入" },
  returned_unrun: { color: "skipped", label: "未运行退回" },
  returned_failed: { color: "failed", label: "失败退回" },
  returned_succeeded: { color: "succeeded", label: "成功退回" },
};

// ---------- 多选 + 队列组建（M2 C2，m2-plan §4.3 C2/§2.4；交互套件
// useMultiSelect：锚点+焦点驱动 Shift 范围选择 / Ctrl+Shift 追加范围 /
// 方向键导航。普通点击保持复选框 toggle 语义，修饰键增量在 Ctrl+Shift） ----------
/** 滚动容器 ref：键盘事件宿主（tabindex=0）与行元素序来源（与列表响应序
 *  对齐，供导航滚动定位）。 */
const tableScroll = ref<HTMLElement | null>(null);
const {
  checkedIds,
  focusedIndex,
  clearAll,
  resetIndices,
  click: checkAt,
  pointAt,
  selectAll,
  onKeydown: onListKeydown,
} = useMultiSelect({
  ids: () => list.value.map((c) => c.id),
  rows: () =>
    tableScroll.value
      ? Array.from(tableScroll.value.querySelectorAll<HTMLElement>("tbody tr"))
      : null,
});
// 列表整体重载（翻页/重取）→ 页内索引失效：重置锚点/焦点（勾选跨页保留）
watch(list, resetIndices);

const QUEUE_MIN = 2;
const QUEUE_MAX = 10;

const allChecked = computed(
  () => list.value.length > 0 && list.value.every((c) => checkedIds.value.has(c.id)),
);
const queueBtnDisabled = computed(
  () => checkedIds.value.size < QUEUE_MIN || checkedIds.value.size > QUEUE_MAX,
);
/** 越界禁用提示（创建校验前置）：勾选数不在 2–10 时说明原因。 */
const queueHint = computed(() => {
  const n = checkedIds.value.size;
  if (n === 0) return null;
  if (n > QUEUE_MAX) return `已选 ${n} 个 — 超出队列成员上限 ${QUEUE_MAX}`;
  if (n < QUEUE_MIN) return `已选 ${n} 个 — 组建队列至少勾选 ${QUEUE_MIN} 个任务`;
  return null;
});

/** 表头全选/清空 */
function toggleAll() {
  if (allChecked.value) clearAll();
  else selectAll();
}

/** 行复选框点击（统一接 Shift/Ctrl 修饰；preventDefault 屏蔽原生翻转——
 *  状态全由 checkedIds 渲染驱动，原生翻转遇「渲染前后值相同」会被 Vue
 *  跳过写 DOM 造成不一致）后容器聚焦承接键盘导航。 */
function onRowCheck(index: number, e: MouseEvent) {
  e.preventDefault();
  checkAt(index, e);
  tableScroll.value?.focus();
}

// 「+队列」对话框（创建态；成员行带候选完整信息）
const queueModalOpen = ref(false);
const queueInitial = ref<MemberRow[]>([]);

function openQueueModal() {
  queueInitial.value = list.value
    .filter((c) => checkedIds.value.has(c.id))
    .map((c) => ({ id: c.id, filename: c.filename, title: c.title }));
  queueModalOpen.value = true;
}

/** 保存（不提交）：关闭对话框并留在候选页（列表经 SSE 自动刷新；
 *  2026-09-27 验收修正——不再跳转队列页） */
function onQueueSaved(_q: Queue) {
  queueModalOpen.value = false;
  clearAll();
}

/** 直接提交：注记在对话框内展示，关闭后留候选页（列表经 SSE 自动刷新） */
function onQueueSubmitted() {
  clearAll();
}

function onQueueClosed() {
  queueModalOpen.value = false;
}
</script>

<template>
  <div class="candidates">
    <!-- 导入工具条：primary 每视图至多一个（§4.2） -->
    <div class="toolbar">
      <button
        class="btn btn--primary"
        type="button"
        :data-loading="importing || undefined"
        :disabled="importing"
        @click="pickFiles"
      >
        {{ importing ? "导入中 …" : "导入文件" }}
      </button>
      <!-- 主/从分组（2026-09-27 人为修正）：竖分割线分隔「导入文件」与
           「导入文件夹 + 保存为队列」从属组——成队选项仅对文件夹导入生效 -->
      <span class="tb-divider" aria-hidden="true"></span>
      <button class="btn btn--secondary" type="button" :disabled="importing" @click="pickFolder">
        导入文件夹
      </button>
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".gjf,.com"
        class="hidden-input"
        @change="onImportChange($event, 'files')"
      />
      <input
        ref="dirInput"
        type="file"
        multiple
        webkitdirectory
        class="hidden-input"
        @change="onImportChange($event, 'folder')"
      />

      <!-- 保存为队列（C4）：勾选后文件夹导入按 queue_from_folder 上送，
           队列名缺省顶层目录名（可改）；对「导入文件」不生效 -->
      <label class="qf mono">
        <input class="ck" type="checkbox" v-model="queueFromFolder" />
        <span>保存为队列</span>
      </label>
      <input
        v-if="queueFromFolder"
        v-model="queueName"
        type="text"
        class="qf-name"
        placeholder="队列名，默认用文件夹名"
        maxlength="64"
      />

      <span v-if="importNote" class="note-ok mono">{{ importNote }}</span>
      <span v-if="filterNote" class="note-warn mono" role="status">{{ filterNote }}</span>
      <!-- 成队回落原因（queue_fallback_reason，中性信息注记） -->
      <span v-if="fallbackNote" class="note-info mono" role="status">{{ fallbackNote }}</span>
      <!-- 提交核验规范化注记（中性信息档，§4.6/§2.5） -->
      <span v-if="submitNote" class="note-info mono" role="status">{{ submitNote }}</span>

      <span class="spacer"></span>
      <!-- 多选组建队列（C2）：已选 2–10 可用，越界禁用+提示（创建校验前置） -->
      <span v-if="checkedIds.size" class="note-info mono">已选 {{ checkedIds.size }}</span>
      <span v-if="queueHint" class="note-warn mono" role="status">{{ queueHint }}</span>
      <button
        class="btn btn--secondary queue-btn"
        type="button"
        :disabled="queueBtnDisabled || importing"
        @click="openQueueModal"
      >
        + 队列
      </button>
    </div>

    <!-- 导入失败清单（422 details 逐文件） -->
    <div v-if="importErrors.length" class="import-errors" role="alert">
      <p class="ie-head mono">导入失败 {{ importErrors.length }} 份 — 未产生任何候选（整批原子）</p>
      <div v-for="e in importErrors" :key="e.filename" class="ie-row mono">
        <span class="ie-file">{{ e.filename }}</span>
        <span class="ie-msg">{{ e.message }}</span>
      </div>
    </div>

    <div class="duo">
      <section class="list">
        <!-- 首载骨架（§4.3：--bg-inset 骨架行 3–5 行，一次性入场） -->
        <div v-if="!everLoaded" class="skel" aria-hidden="true">
          <div v-for="i in 4" :key="i" class="sk-row"></div>
        </div>

        <div v-else-if="!list.length" class="empty-wrap">
          <EmptyState glyph="▯" text="暂无候选任务 — 导入 .gjf 文件后显示于此" />
        </div>

        <template v-else>
          <!-- 多选交互宿主容器：tabindex 承接键盘导航（Ctrl+A/Esc/方向键），
               Shift 按下的 mousedown 阻止默认行为防范围点击拖出文本选区 -->
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
                  <th class="chk-col"><input class="ck" type="checkbox" :checked="allChecked" aria-label="全选候选任务" @change="toggleAll" /></th>
                  <th class="mono">ID</th>
                  <th class="mono">文件名</th>
                  <th class="mono">标题</th>
                  <th class="mono">来源</th>
                  <th class="mono">创建</th>
                  <th class="right mono">动作</th>
                </tr>
              </thead>
              <tbody class="stagger">
                <tr
                  v-for="(c, i) in list"
                  :key="c.id"
                  :class="{
                    'row--active': selected?.id === c.id,
                    'row--focused': focusedIndex === i,
                  }"
                  @click="select(c, i)"
                >
                  <td class="chk-col" @click.stop>
                    <input
                      class="ck"
                      type="checkbox"
                      :checked="checkedIds.has(c.id)"
                      :aria-label="`选择 ${c.filename}`"
                      @click="onRowCheck(i, $event)"
                    />
                  </td>
                  <td class="mono">{{ fmtTaskId(c.id) }}</td>
                  <td class="mono filename" :title="c.filename">{{ c.filename }}</td>
                  <td class="title" :title="c.title ?? ''">{{ c.title ?? "—" }}</td>
                  <td>
                    <StateChip
                      :state="originView[c.origin]?.color ?? 'staged'"
                      :label="originView[c.origin]?.label ?? c.origin"
                    />
                    <span v-if="c.failure_note" class="failure mono">
                      {{ causeLabel[c.failure_note] ?? c.failure_note }}
                    </span>
                  </td>
                  <td class="mono dim">{{ fmtDateTime(c.created_at) }}</td>
                  <td class="right">
                    <button class="btn btn--ghost" type="button" @click.stop="openSubmit(c)">
                      提交
                    </button>
                    <button class="btn btn--ghost" type="button" @click.stop="select(c, i)">
                      预览
                    </button>
                    <button class="btn btn--ghost remove" type="button" @click.stop="removing = c">
                      移除
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="scanline" aria-hidden="true" v-if="loading"></div>
        </template>
        <!-- 列表底栏（§4.3 标准套件）：计数右对齐 + 分页控件居中（单页时控件隐藏） -->
        <TablePager
          v-if="list.length"
          :total="total"
          :page="page"
          :page-size="pageSize"
          @change="goPage"
        />
      </section>

      <section class="preview">
        <!-- 分块预览/编辑（M2 C1：BlockEditor 承载双态与自动保存） -->
        <BlockEditor v-if="selected" :key="selected.id" :task-id="selected.id" :editable="true">
          <template #head>
            <span class="p-name mono">{{ selected.filename }}</span>
            <StateChip
              :state="originView[selected.origin]?.color ?? 'staged'"
              :label="`ID ${selected.id}`"
            />
          </template>
        </BlockEditor>
        <template v-else>
          <div class="p-empty">
            <span class="pe-glyph mono" aria-hidden="true">◱</span>
            <p class="pe-text mono">选择左侧任务查看分块预览</p>
          </div>
        </template>
      </section>
    </div>

    <!-- 行内提交确认框（§4.6 模态；完整输入限高滚动 + Link0 黄警 + 满员 409） -->
    <ConfirmModal
      :open="submitting != null"
      title="提交执行"
      confirm-text="提交"
      :loading="submitBusy"
      :disabled="submitFetching"
      @confirm="confirmSubmit"
      @close="submitting = null"
    >
      <div class="submit-body">
        <!-- Link0 缺失黄色警告（琥珀纪律：需要行动的警告；M1.3 验收路径第 3 步） -->
        <p v-if="submitMissing.length" class="submit-warn mono">
          ⚠ {{ submitWarnText }}
        </p>
        <p v-else class="submit-ok mono">Link0 声明齐全</p>

        <p v-if="submitError" class="submit-error mono" role="alert">{{ submitError }}</p>

        <!-- 读数仅「完整输入」；纯文本含坐标属实现语义，见 .input-text 样式注释 -->
        <div class="input-cap mono">完整输入</div>
        <pre class="input-text mono">{{ submitFetching ? "读取中 …" : submitInput }}</pre>
      </div>
    </ConfirmModal>

    <!-- 剔除二次确认（§4.6 危险确认模态） -->
    <ConfirmModal
      :open="removing != null"
      title="剔除候选"
      danger
      confirm-text="移除"
      :loading="removeLoading"
      @confirm="confirmRemove"
      @close="removing = null"
    >
      <p class="confirm-line">
        将删除任务
        <span class="mono strong">#{{ removing?.id }} {{ removing?.filename }}</span>
        的输入副本与记录，不可恢复
      </p>
    </ConfirmModal>

    <!-- 队列编辑对话框（C2 创建态；编辑/只读模式由队列页 C3 接入） -->
    <QueueEditorModal
      :open="queueModalOpen"
      mode="create"
      :initial-members="queueInitial"
      @saved="onQueueSaved"
      @submitted="onQueueSubmitted"
      @close="onQueueClosed"
    />
  </div>
</template>

<style scoped>
.candidates {
  display: flex;
  flex-direction: column;
  gap: var(--gap-card);
}
.hidden-input {
  display: none;
}
/* 主/从分组分割线：拉大「导入文件」与「导入文件夹」组间距（配合工具条 12px
   gap，两按钮间视觉间距 12+1+12=25px，线居中） */
.tb-divider {
  width: 1px;
  height: 20px;
  background: var(--border-strong);
  flex: none;
}
/* 保存为队列（C4）：「导入文件夹」的从属选项——贴近宿主按钮（-4px 抵消
   工具条 gap → 8px）并降字号至 --text-xs（混排纪律 1 的 12px 下限档，
   2026-09-27 人为修正指定以字号体现从属，登记为统一口径 14px 的例外） */
.qf {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: calc(var(--space-1) * -1);
  font-size: var(--text-xs); /* 文案含中文：混排纪律 1 下限档（例外登记见设计文档 §2.2） */
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}
.qf-name {
  width: 180px;
  height: var(--control-height);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: 0 var(--space-2);
}
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.spacer {
  flex: 1;
}
/* 「+ 队列」右缘对齐左列候选列表（右肩属列表不属预览区）：让出预览列宽 + 双栏间距 */
.queue-btn {
  margin-right: calc(var(--preview-width) + var(--gap-card));
}
/* 复选框列（§4.6 checkbox 规格，样式类 .ck 全局定义） */
.chk-col {
  width: 32px;
  text-align: center;
}
.note-ok {
  font-size: var(--text-sm);
  color: var(--state-succeeded);
}
.note-warn {
  font-size: var(--text-sm);
  color: var(--warn);
}
/* 信息注记（中性档，§4.6：信息性提示非「需要行动」） */
.note-info {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.import-errors {
  border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  padding: var(--space-3) var(--space-4);
  display: grid;
  gap: var(--space-1);
}
.ie-head {
  font-size: var(--text-sm);
  color: var(--danger);
}
.ie-row {
  display: flex;
  gap: var(--space-4);
  font-size: var(--text-sm);
}
.ie-file {
  color: var(--text-primary);
  min-width: 160px;
}
.ie-msg {
  color: var(--text-secondary);
}
.confirm-line {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.confirm-line .strong {
  color: var(--text-primary);
}
/* 行内提交确认框内容 */
.submit-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.submit-warn {
  font-size: var(--text-sm);
  color: var(--warn);
}
.submit-ok {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.submit-error {
  font-size: var(--text-sm);
  color: var(--danger);
}
.input-cap {
  font-size: var(--text-sm); /* 文案含中文：混排纪律 1，不用微标签档、不加字距 */
  text-transform: uppercase;
  color: var(--text-faint);
}
/* 完整输入限高滚动（M1.3：纯文本完整预览，含坐标） */
.input-text {
  margin: 0;
  max-height: var(--peek-max-height);
  overflow: auto;
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.duo {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--preview-width);
  grid-template-rows: minmax(0, 1fr);
  gap: var(--gap-card);
  flex: 1;
  min-height: 0;
}
/* 列表卡：flex 列，表格滚动包裹层吃剩余高度、局部滚动（§3 视口纪律） */
.list {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--bg-raised);
}
.table-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.table {
  width: 100%;
  /* 边框模型必须 separate（间距 0）：collapse 的单元格绘制由表层级合并处理，
     粘性表头滚动时行内容会穿透（2026-09-27 列表局部滚动改造后显形，人为验收
     指定修复）。发丝线已全在单元格 border-bottom 上，separate 下视觉不变。 */
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
  /* z-index 建自身层叠上下文（表格单元格绘制被 Chromium 特判，仅 sticky
     不提升绘制序，行内容会画在表头背景之上——与 separate 边框模型配套的
     第二半修复）；局部层 1 远低于全局层级档（--z-nav: 100），不入 z 令牌 */
  z-index: 1;
  border-bottom: 1px solid var(--border-hair);
}
td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-hair);
  cursor: pointer;
  vertical-align: middle;
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
/* 选中行：inset 2px accent 条（§4.3 样板） */
.row--active {
  background: color-mix(in srgb, var(--accent) 7%, transparent);
  box-shadow: inset 2px 0 0 var(--accent);
}
/* 键盘导航焦点行（useMultiSelect）：inset 发丝描边区别于预览选中的左条；
   与预览选中叠加时两形态并存（描边 + 左条合成双阴影） */
.row--focused {
  box-shadow: inset 0 0 0 1px var(--accent);
}
.row--active.row--focused {
  box-shadow: inset 2px 0 0 var(--accent), inset 0 0 0 1px var(--accent);
}
.filename {
  color: var(--text-primary);
  font-weight: 500;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.title {
  color: var(--text-secondary);
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dim {
  color: var(--text-faint);
}
.right {
  text-align: right;
  white-space: nowrap;
}
.failure {
  display: block;
  margin-top: 2px;
  font-size: var(--text-sm);
  color: var(--warn);
}
.btn.remove {
  color: var(--danger);
}
.btn.remove:hover {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 10%, transparent);
}
/* 刷新两态：底部 1px 磷光扫描线（§4.3）——处于滚动区外、列表卡底部常驻可视 */
.scanline {
  height: 1px;
  flex-shrink: 0;
  background: var(--accent);
  animation: scanline var(--dur-scan) var(--ease-std) infinite;
}
.skel {
  display: grid;
}
.sk-row {
  height: var(--row-height);
  border-bottom: 1px solid var(--border-hair);
  background: var(--bg-inset);
  animation: row-in var(--dur-enter) var(--ease-std) both;
}
.skel .sk-row:nth-child(2) {
  animation-delay: var(--stagger-step);
}
.skel .sk-row:nth-child(3) {
  animation-delay: calc(var(--stagger-step) * 2);
}
.skel .sk-row:nth-child(4) {
  animation-delay: calc(var(--stagger-step) * 3);
}
.empty-wrap {
  padding: var(--space-4);
}
/* ---------- 预览卡（分块卡序列由 BlockEditor 承载；双栏行高已锁定，
   预览卡随之拉伸并自管内部滚动，§3 视口纪律） ---------- */
.preview {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  min-height: 0;
  overflow: auto;
  padding: var(--space-3) var(--space-4);
}
.p-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex: 1;
  min-width: 0;
}
.p-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* §4.6 空态：居中发丝虚线框 + 刻度符号 + mono 短句 */
.p-empty {
  min-height: 280px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  border: 1px dashed var(--border-strong);
  border-radius: var(--r-md);
}
.pe-glyph {
  font-size: var(--text-xl); /* 空态刻度符号收编阶梯（原 24px 不在档位） */
  line-height: 1;
  color: var(--accent-dim);
  opacity: 0.7;
}
.pe-text {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
</style>
