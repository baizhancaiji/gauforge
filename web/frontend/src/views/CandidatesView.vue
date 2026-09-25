<script setup lang="ts">
/**
 * 01 候选任务（m0-frontend-design §5 · 表格型双栏；m1-plan C1 真实化）
 * 左列列表（id/文件名/title/来源徽标——失败退回附琥珀归因注记）+ 导入交互
 * （文件多选/文件夹 webkitdirectory、422 逐文件失败清单、重复导入提示）
 * + 剔除（二次确认）。列表按自然序展示（与后端 naturalsort 同规则）。
 */
import { computed, ref, watch } from "vue";

import { client, getText } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";
import EmptyState from "@/components/EmptyState.vue";
import StateChip from "@/components/StateChip.vue";
import { useEventsStore } from "@/stores/events";
import { fmtDateTime } from "@/utils/format";
import { naturalCompare } from "@/utils/naturalsort";

type Candidate = components["schemas"]["Candidate"];
type InputPreview = components["schemas"]["InputPreview"];

const events = useEventsStore();

const list = ref<Candidate[]>([]);
const total = ref(0);
const loading = ref(false);
/** 首载骨架行（§4.3 加载两态）：首帧渲染骨架，此后刷新仅底部扫描线。 */
const everLoaded = ref(false);
const selected = ref<Candidate | null>(null);
const preview = ref<InputPreview | null>(null);
const previewLoading = ref(false);

/** 自然序展示（M1.1：不区分大小写、字母先于数字；并列保持 id 序）。 */
const sorted = computed(() =>
  [...list.value].sort((a, b) => naturalCompare(a.filename, b.filename)),
);

async function load() {
  loading.value = true;
  const { data } = await client.GET("/candidates", { params: { query: {} } });
  loading.value = false;
  everLoaded.value = true;
  if (data) {
    list.value = (data.items as Candidate[]) ?? [];
    total.value = data.total ?? 0;
  }
}

async function loadPreview(c: Candidate) {
  selected.value = c;
  previewLoading.value = true;
  const { data } = await client.GET("/candidates/{id}/preview", {
    params: { path: { id: c.id } },
  });
  previewLoading.value = false;
  preview.value = data ?? null;
}

// 契约 §3.5⑥：候选通知事件 → 重拉当前页。
watch(() => events.dirty.candidates, load);
load();

// ---------- 导入（M1.1） ----------
const importing = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const dirInput = ref<HTMLInputElement | null>(null);
const importNote = ref<string | null>(null);
const filterNote = ref<string | null>(null);
const importErrors = ref<{ filename: string; message: string }[]>([]);

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

function pickFiles() {
  importNote.value = null;
  filterNote.value = null;
  importErrors.value = [];
  fileInput.value?.click();
}
function pickFolder() {
  importNote.value = null;
  filterNote.value = null;
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
  importErrors.value = [];
  const fd = new FormData();
  fd.append("mode", mode);
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
    const dups = data.files
      .filter((f) => (f as { duplicate?: boolean }).duplicate)
      .map((f) => f.filename ?? "");
    importNote.value = dups.length
      ? `已导入 ${data.files.length} 份（${dups.length} 份与既有候选同名同内容，已另行建目）`
      : `已导入 ${data.files.length} 份`;
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

async function openSubmit(c: Candidate) {
  submitting.value = c;
  submitInput.value = "";
  submitMissing.value = [];
  submitError.value = null;
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
  return parts.length ? `${head} 未声明 · 提交时将按默认值补齐（${parts.join("、")}）` : `${head} 未声明 · 提交时将按默认值补齐`;
});

async function confirmSubmit() {
  const c = submitting.value;
  if (!c) return;
  submitBusy.value = true;
  submitError.value = null;
  const { error } = await client.POST("/candidates/{id}/submit", {
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
  if (selected.value?.id === c.id) {
    selected.value = null;
    preview.value = null;
  }
  load();
}

// 来源徽标（样本语义：安静档状态色 + 中文措辞）；失败退回附琥珀归因注记。
const originView: Record<string, { color: string; label: string }> = {
  imported: { color: "staged", label: "导入" },
  returned_unrun: { color: "skipped", label: "未运行退回" },
  returned_failed: { color: "failed", label: "失败退回" },
  returned_succeeded: { color: "succeeded", label: "成功退回" },
};
const causeLabel: Record<string, string> = {
  manually_stopped: "手动停止",
  program_error: "程序错误",
  external_interrupt: "外部中断",
  predecessor_failed: "前驱失败",
  queue_manually_stopped: "队列停止",
};
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

      <span v-if="importNote" class="note-ok mono">{{ importNote }}</span>
      <span v-if="filterNote" class="note-warn mono" role="status">{{ filterNote }}</span>
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
          <table class="table">
            <thead>
              <tr>
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
                v-for="c in sorted"
                :key="c.id"
                :class="{ 'row--active': selected?.id === c.id }"
                @click="loadPreview(c)"
              >
                <td class="mono">{{ String(c.id).padStart(3, "0") }}</td>
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
                  <button class="btn btn--ghost" type="button" @click.stop="loadPreview(c)">
                    预览
                  </button>
                  <button class="btn btn--ghost remove" type="button" @click.stop="removing = c">
                    移除
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="scanline" aria-hidden="true" v-if="loading"></div>
        </template>
        <div class="foot mono" v-if="list.length">
          {{ list.length }} 项 — 共 {{ total }}
        </div>
      </section>

      <section class="preview">
        <template v-if="previewLoading">
          <div class="preview-blank mono">读取预览 …</div>
        </template>
        <template v-else-if="preview">
          <header class="p-head">
            <span class="p-name mono">{{ preview.filename }}</span>
            <StateChip
              :state="originView[selected?.origin ?? 'imported']?.color ?? 'staged'"
              :label="`ID ${preview.candidate_id}`"
            />
          </header>

          <!-- 解析失败节容错条（C2：预览尽力而为，逐节标注不阻断） -->
          <div v-if="preview.parse_errors?.length" class="p-errors" role="alert">
            <div v-for="(pe, i) in preview.parse_errors" :key="i" class="pe-row mono">
              <span class="pe-sec">{{ pe.section }}</span>
              <span class="pe-line">第 {{ pe.line }} 行</span>
              <span class="pe-msg">{{ pe.message }}</span>
            </div>
          </div>

          <div class="block">
            <div class="lab mono">TITLE</div>
            <div class="val mono">{{ preview.blocks.title ?? "—" }}</div>
          </div>

          <div class="block">
            <div class="lab mono">LINK 0</div>
            <div v-if="preview.blocks.link0.lines.length" class="val mono">
              <span v-for="(ln, i) in preview.blocks.link0.lines" :key="i" class="l0-line">
                <span v-if="ln.includes('=')" class="dim">{{ ln.slice(0, ln.indexOf("=") + 1) }}</span
                >{{ ln.slice(ln.indexOf("=") + 1) }}
              </span>
            </div>
            <div v-else class="val mono dim">（无声明）</div>
            <!-- Link0 缺失琥珀注记（§5：M1 提交警告的伏笔；missing 为不带 % 的指令名） -->
            <div v-if="preview.blocks.link0.missing.length" class="note mono">
              ⚠ {{ preview.blocks.link0.missing.map((m) => `%${m}`).join("、") }} 未声明 · 提交时将按默认值补齐
            </div>
          </div>

          <div class="block">
            <div class="lab mono">ROUTE</div>
            <div class="val mono">{{ preview.blocks.route || "—" }}</div>
          </div>

          <div class="block">
            <div class="lab mono">CHARGE · MULT</div>
            <div class="val mono">{{ preview.blocks.charge_mult || "—" }}</div>
          </div>

          <div class="block">
            <div class="lab mono">MOLECULE</div>
            <div class="readout">
              <div class="r">
                <div class="n mono">{{ preview.blocks.molecule.atom_count }}</div>
                <div class="l mono">ATOMS</div>
              </div>
              <div class="r">
                <div class="n mono">{{ preview.blocks.molecule.formula }}</div>
                <div class="l mono">FORMULA</div>
              </div>
              <div class="r">
                <div class="n mono">{{ preview.blocks.molecule.variables_present ? "有" : "—" }}</div>
                <div class="l mono">VARS</div>
              </div>
              <div class="r">
                <div class="n mono">{{ preview.blocks.molecule.constants_present ? "有" : "—" }}</div>
                <div class="l mono">CONSTS</div>
              </div>
            </div>
          </div>

          <div class="block">
            <div class="lab mono">ADDITIONAL · {{ preview.blocks.additional_sections.length }}</div>
            <div v-if="!preview.blocks.additional_sections.length" class="val mono dim">
              无附加输入节
            </div>
            <div v-else class="addi">
              <div v-for="(sec, i) in preview.blocks.additional_sections" :key="i" class="addi-item">
                <span class="sec-idx mono">{{ i + 1 }}</span>
                <pre class="code mono">{{ sec.lines.join("\n") }}</pre>
              </div>
            </div>
          </div>
        </template>
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

        <div class="input-cap mono">完整输入（纯文本 · 含坐标）</div>
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
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.note-ok {
  font-size: var(--text-xs);
  color: var(--state-succeeded);
}
.note-warn {
  font-size: var(--text-sm);
  color: var(--warn);
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
  font-size: var(--text-xs);
  color: var(--danger);
}
.ie-row {
  display: flex;
  gap: var(--space-4);
  font-size: var(--text-xs);
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
  font-size: var(--text-xs);
  color: var(--warn);
}
.submit-ok {
  font-size: var(--text-xs);
  color: var(--text-faint);
}
.submit-error {
  font-size: var(--text-xs);
  color: var(--danger);
}
.input-cap {
  font-size: var(--text-sm); /* 文案含中文：混排纪律下限，不用微标签档 */
  letter-spacing: var(--ls-wide);
  text-transform: uppercase;
  color: var(--text-faint);
}
/* 完整输入限高滚动（M1.3：纯文本完整预览，含坐标） */
.input-text {
  margin: 0;
  max-height: 300px;
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
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: var(--gap-card);
  align-items: start;
}
.list {
  position: relative;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--bg-raised);
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}
th {
  text-align: left;
  font-size: var(--text-xs);
  font-weight: 500;
  letter-spacing: var(--ls-micro);
  text-transform: uppercase;
  color: var(--text-faint);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-raised);
  position: sticky;
  top: 0;
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
  transition: background-color 120ms var(--ease-std);
}
tbody tr:hover {
  background: var(--row-hover);
}
/* 选中行：inset 2px accent 条（§4.3 样板） */
.row--active {
  background: color-mix(in srgb, var(--accent) 7%, transparent);
  box-shadow: inset 2px 0 0 var(--accent);
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
  font-size: var(--text-xs);
  color: var(--warn);
}
.btn.remove {
  color: var(--danger);
}
.btn.remove:hover {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 10%, transparent);
}
/* 刷新两态：底部 1px 磷光扫描线（§4.3） */
.scanline {
  height: 1px;
  background: var(--accent);
  animation: scanline 1.2s var(--ease-std) infinite;
  margin-top: -1px;
}
.skel {
  display: grid;
}
.sk-row {
  height: 40px;
  border-bottom: 1px solid var(--border-hair);
  background: var(--bg-inset);
  animation: row-in 220ms var(--ease-std) both;
}
.skel .sk-row:nth-child(2) {
  animation-delay: 18ms;
}
.skel .sk-row:nth-child(3) {
  animation-delay: 36ms;
}
.skel .sk-row:nth-child(4) {
  animation-delay: 54ms;
}
.foot {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-faint);
  border-top: 1px solid var(--border-hair);
}
.empty-wrap {
  padding: var(--space-4);
}
/* ---------- 预览卡（C2：分块卡，右侧 380px 粘性，§5/样板） ---------- */
.preview {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  position: sticky;
  top: var(--space-2);
  max-height: calc(100vh - 120px);
  overflow: auto;
}
.p-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-hair);
}
.p-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 解析失败节容错条（--danger：异常信号；预览尽力而为不阻断） */
.p-errors {
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--border-hair);
  display: grid;
  gap: 2px;
}
.pe-row {
  display: flex;
  gap: var(--space-3);
  font-size: var(--text-xs);
  color: var(--danger);
}
.pe-sec {
  min-width: 64px;
  color: var(--text-primary);
}
.pe-line {
  min-width: 64px;
}
.pe-msg {
  color: var(--danger);
}
.block {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-hair);
}
.block:last-child {
  border-bottom: none;
}
.lab {
  font-size: var(--text-2xs);
  letter-spacing: var(--ls-wide);
  text-transform: uppercase;
  color: var(--text-faint);
  margin-bottom: var(--space-1);
}
.val {
  font-size: var(--text-sm);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.val .dim,
.dim {
  color: var(--text-secondary);
}
/* Link0 逐行：指令名弱化（样板语义 %Chk= dim + 值亮） */
.l0-line {
  display: block;
}
.note {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--warn);
}
/* 分子四格读数（样板 readout：ATOMS/FORMULA/VARS/CONSTS） */
.readout {
  display: flex;
  gap: var(--space-6);
}
.readout .r .n {
  font-size: var(--text-lg);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
.readout .r .l {
  font-size: var(--text-2xs);
  letter-spacing: var(--ls-wide);
  color: var(--text-faint);
}
.addi {
  display: grid;
  gap: var(--space-2);
}
.addi-item {
  display: grid;
  grid-template-columns: 20px 1fr;
  gap: var(--space-2);
  align-items: start;
}
.sec-idx {
  color: var(--text-faint);
  font-size: var(--text-xs);
}
.code {
  font-size: var(--text-xs);
  color: var(--text-primary);
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: var(--space-2) var(--space-3);
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
.preview-blank {
  padding: var(--space-5);
  color: var(--text-faint);
  font-size: var(--text-sm);
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
