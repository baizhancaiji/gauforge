<script setup lang="ts">
/**
 * 导出 cube 区块（3.8.0 工具箱 C8，toolbox-plan §2.2/§4.8；3.8.0 修订批
 * R3/R4/R5）：工具箱导出域——fchk → cube 供外部专业分析软件（PyMOL /
 * VMD / Chemcraft），与 OrbitalsPanel 预览面板并列、互不侵入（预览不改造）。
 *
 * 类型复选（修订批 R3：六项复选按钮组 + 全选切换；恰选 1 类走单 kind
 * 端点直下 .cube，≥2 类走批量端点收单个 ZIP）；MO 轨道号行随 MO 勾选
 * 显隐（多选含 MO 时单一轨道号作用于该类，越界以提交后提示回显）；α/β
 * 仅开壳层（闭壳层 / 不可判定均明示，服务端 fail-closed）。异常终止任务
 * 缺数据段时生成前按 kind 明示不可生成原因（修订批 R4：422
 * kind_errors[] 逐 kind 罗列 / 单端点 data_missing；502 呈现 failing
 * kind 与工具输出摘录）。下载命名全英文档位（修订批 R5：coarse/
 * medium/fine；多类型包名类型段规范序、全选 all），落盘名与服务端
 * Content-Disposition 同公式。
 */
import { computed, ref } from "vue";

import { client, generateCubeBatch } from "@/api/client";
import type { components } from "@/api/contract";

const props = defineProps<{
  executionId: number;
  entryState: string;
  filename: string;
}>();

type Kind = "MO" | "Potential" | "Density" | "Spin" | "Alpha" | "Beta";
type Grade = -2 | -3 | -4;

// 规范序（与服务端 KINDS 一致——包名类型段排列同源）
const KINDS: { key: Kind; label: string }[] = [
  { key: "MO", label: "分子轨道 MO" },
  { key: "Potential", label: "静电势" },
  { key: "Density", label: "电子密度" },
  { key: "Spin", label: "自旋密度" },
  { key: "Alpha", label: "α 密度（开壳层）" },
  { key: "Beta", label: "β 密度（开壳层）" },
];
const GRADES: { value: Grade; label: string }[] = [
  { value: -2, label: "粗" },
  { value: -3, label: "中" },
  { value: -4, label: "细" },
];
const GRADE_EN: Record<number, string> = {
  [-2]: "coarse",
  [-3]: "medium",
  [-4]: "fine",
};

const selected = ref<Set<Kind>>(new Set(["Density"]));
const orbital = ref(1);
const grade = ref<Grade>(-3);
const busy = ref(false);
const note = ref<{ kind: "bad" | "warn" | "ok"; text: string } | null>(null);

const stem = computed(() => {
  const n = props.filename;
  return n.includes(".") ? n.slice(0, n.lastIndexOf(".")) : n;
});

const allSelected = computed(() => selected.value.size === KINDS.length);
const multiFine = computed(() => selected.value.size >= 2 && grade.value === -4);

function kindLabel(k: string): string {
  return KINDS.find((x) => x.key === k)?.label ?? k;
}

function toggleKind(k: Kind) {
  const next = new Set(selected.value);
  if (next.has(k)) {
    next.delete(k);
  } else {
    next.add(k);
  }
  selected.value = next;
}

/** 全选切换（六项全勾 / 全清）。 */
function toggleAll() {
  selected.value = allSelected.value
    ? new Set<Kind>()
    : new Set(KINDS.map((k) => k.key));
}

function gradeToken(): string {
  return GRADE_EN[grade.value] ?? String(grade.value);
}

/** 类型段（§2.5）：规范序罗列、六类全选 all、不含 MO 轨道号。 */
function typeseg(list: Kind[]): string {
  const ordered = KINDS.map((k) => k.key).filter((k) => list.includes(k));
  return ordered.length === KINDS.length ? "all" : ordered.join("-");
}

function cubeName(k: Kind): string {
  const moPart = k === "MO" ? `-${orbital.value}` : "";
  return `${stem.value}-${k}${moPart}-${gradeToken()}.cube`;
}

function zipName(list: Kind[]): string {
  return `${stem.value}-${typeseg(list)}-${gradeToken()}.zip`;
}

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.download = name;
  a.href = url;
  a.click();
  URL.revokeObjectURL(url);
}

/** kind + reason(+section) → 中文文案映射（§2.4 映射表右列定稿）。 */
function reasonText(kind: string, reason: string, section?: string): string {
  if (reason === "closed_shell") {
    return "α/β 密度要求开壳层体系 — 当前条目为闭壳层，已拒绝生成";
  }
  if (reason === "shell_unknown") {
    return "无法判定开壳层 — 已拒绝生成 α/β 密度（数据不足）";
  }
  if (reason === "data_missing") {
    if (section?.includes("MO")) {
      return "fchk 缺少 MO 系数数据 — 无法生成轨道 cube";
    }
    if (section === "Spin SCF Density" && (kind === "Alpha" || kind === "Beta")) {
      return "fchk 缺少总密度或自旋密度数据 — 已拒绝生成，避免产出错误密度";
    }
    if (section === "Spin SCF Density") {
      return "fchk 缺少自旋密度数据 — 无法生成";
    }
    if (section === "Total SCF Density") {
      return "fchk 缺少密度数据 — 异常结束任务的 chk 通常不含密度数据，无法生成";
    }
    return "fchk 缺少必需数据段 — 无法生成";
  }
  return reason;
}

interface ErrBody {
  error?: {
    code?: string;
    message?: string;
    details?: {
      reason?: string;
      section?: string;
      kind?: string;
      stderr_tail?: string;
      errors?: { field?: string; max?: number }[];
      kind_errors?: { kind: string; reason: string; section?: string }[];
    };
  };
}

function errText(e: unknown, fallback: string): string {
  const body = e as ErrBody;
  const code = body?.error?.code;
  const details = body?.error?.details;
  if (code === "VALIDATION_FAILED") {
    // 按 details 键名分流：kind_errors[] 逐 kind 罗列（前置校验）、
    // errors[] 字段词形（文法）、两键皆缺沿 message 兜底透显
    if (details?.kind_errors?.length) {
      return details.kind_errors
        .map((x) => `${kindLabel(x.kind)} — ${reasonText(x.kind, x.reason, x.section)}`)
        .join("\n");
    }
    const orbitalErr = details?.errors?.find((x) => x.field === "orbital");
    if (orbitalErr?.max != null) {
      return `MO 轨道号越界 — 本体系可寻址范围至 ${orbitalErr.max}`;
    }
    if (details?.reason === "closed_shell") {
      return reasonText("", "closed_shell");
    }
    if (details?.reason === "shell_unknown") {
      return reasonText("", "shell_unknown");
    }
    if (details?.reason === "data_missing") {
      return reasonText(details?.kind ?? "", "data_missing", details?.section);
    }
    if (details?.reason === "mo_upper_unknown") {
      return "无法确定轨道上界 — 条目数据不完整，无法生成 MO cube";
    }
    return body?.error?.message ?? "参数校验失败";
  }
  if (code === "CUBE_GENERATION_FAILED") {
    if (details?.reason === "fchk_missing") {
      return "fchk 缺失 — 请先执行 chk 转换后再生成 cube";
    }
    const label = details?.kind ? kindLabel(details.kind) : "";
    const head = label
      ? `${label}生成失败（cubegen 非零退出或超时）`
      : "cube 生成失败（cubegen 非零退出或超时）";
    const tail = details?.stderr_tail
      ? `— 工具输出摘录：${String(details.stderr_tail).slice(-200)}`
      : "";
    return `${head}${tail ? ` ${tail}` : ""}`;
  }
  if (code === "CUBE_EXECUTABLE_MISSING") {
    return "cubegen 不可用 — 请检查设置中的 G16 安装目录";
  }
  if (code === "ANALYSIS_UNAVAILABLE") return "未运行条目无执行产物";
  if (code === "NOT_FOUND") return "执行条目或产物不存在";
  return body?.error?.message ?? fallback;
}

async function generate() {
  const picked = KINDS.map((k) => k.key).filter((k) => selected.value.has(k));
  if (!picked.length) return;
  busy.value = true;
  note.value = null;
  const hasMo = picked.includes("MO");
  if (picked.length === 1) {
    // 恰选 1 类：走既有单 kind 端点直下 .cube（现行为零变更）
    const kind = picked[0];
    const body: components["schemas"]["CubeRequest"] =
      kind === "MO"
        ? { kind, orbital: orbital.value, npts: grade.value }
        : { kind, npts: grade.value };
    const { data: created, error: genErr } = await client.POST(
      "/history/{id}/analysis/cube",
      { params: { path: { id: props.executionId } }, body },
    );
    if (genErr || !created) {
      busy.value = false;
      note.value = { kind: "bad", text: errText(genErr, "生成失败") };
      return;
    }
    const { data: blob, error: dlErr } = await client.GET(
      "/history/{id}/analysis/cube/{cube_id}",
      {
        params: { path: { id: props.executionId, cube_id: created.cube_id } },
        parseAs: "blob",
      },
    );
    busy.value = false;
    if (dlErr || !blob) {
      note.value = { kind: "bad", text: "cube 下载失败" };
      return;
    }
    saveBlob(blob as unknown as Blob, cubeName(kind));
    note.value = { kind: "ok", text: `已下载 ${cubeName(kind)}` };
    return;
  }
  // 选中 ≥2 类：批量端点收单个 ZIP（逐类串行生成、幂等命中复用）
  const body: components["schemas"]["CubeBatchRequest"] = {
    kinds: picked,
    ...(hasMo ? { orbital: orbital.value } : {}),
    npts: grade.value,
  };
  const { data: blob, error: genErr } = await generateCubeBatch(
    props.executionId,
    body,
  );
  busy.value = false;
  if (genErr || !blob) {
    note.value = { kind: "bad", text: errText(genErr, "生成失败") };
    return;
  }
  const name = zipName(picked);
  saveBlob(blob as unknown as Blob, name);
  note.value = { kind: "ok", text: `已下载 ${name}` };
}
</script>

<template>
  <section
    v-if="entryState === 'succeeded' || entryState === 'failed' || entryState === 'skipped'"
    class="cubeexp"
  >
    <header class="ce-head">
      <span class="ce-title">导出 cube</span>
      <span class="ce-sub mono">供 PyMOL / VMD / Chemcraft 等外部软件</span>
    </header>
    <div class="ce-row">
      <span class="ce-label">类型</span>
      <div class="ce-kinds" role="group" aria-label="cube 类型（可多选）">
        <button
          v-for="k in KINDS"
          :key="k.key"
          type="button"
          class="ce-kind mono"
          :class="{ 'ce-kind--on': selected.has(k.key) }"
          :aria-pressed="selected.has(k.key)"
          @click="toggleKind(k.key)"
        >
          {{ k.label }}
        </button>
      </div>
      <button
        type="button"
        class="ce-all"
        :aria-pressed="allSelected"
        @click="toggleAll"
      >
        全选
      </button>
    </div>
    <div v-if="selected.has('MO')" class="ce-row">
      <label class="ce-label" for="cube-orbital">轨道号</label>
      <input
        id="cube-orbital"
        v-model.number="orbital"
        class="ce-input mono"
        type="number"
        min="1"
        step="1"
      >
      <span class="ce-hint mono">多选时作用于 MO 一类；越界以提交后提示回显</span>
    </div>
    <div class="ce-row">
      <span class="ce-label">网格档位</span>
      <div class="ce-grades" role="radiogroup" aria-label="网格档位">
        <button
          v-for="g in GRADES"
          :key="g.value"
          type="button"
          class="ce-grade mono"
          :class="{ 'ce-grade--on': grade === g.value }"
          :aria-pressed="grade === g.value"
          @click="grade = g.value"
        >
          {{ g.label }}
        </button>
      </div>
      <span v-if="multiFine" class="ce-hint ce-hint--warn mono">多类型 × 细档 — 体积叠加（每类数十 MB 量级）</span>
      <span v-else-if="grade === -4" class="ce-hint ce-hint--warn mono">细档体积大（数十 MB 量级）</span>
    </div>
    <div class="ce-actions">
      <button
        class="btn btn--primary"
        type="button"
        :disabled="busy || selected.size === 0"
        @click="generate"
      >
        {{ busy
          ? (selected.size > 1 ? `生成中（${selected.size} 类）…` : "生成中 …")
          : "生成并下载" }}
      </button>
    </div>
    <p v-if="note" class="ce-note mono" :class="`note--${note.kind}`" role="alert">
      {{ note.text }}
    </p>
  </section>
</template>

<style scoped>
.cubeexp {
  margin-top: var(--space-3);
  border-top: 1px solid var(--border-strong);
  padding-top: var(--space-3);
}
.ce-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}
.ce-title {
  font-size: var(--text-sm);
  color: var(--text-primary);
}
.ce-sub {
  font-size: var(--text-2xs);
  color: var(--text-faint);
  letter-spacing: var(--ls-micro);
}
.ce-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.ce-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  min-width: 4em;
}
.ce-kinds {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
.ce-kind {
  height: var(--control-height);
  padding: 0 var(--space-3);
  background: var(--bg-overlay);
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  font-size: var(--text-sm);
  cursor: pointer;
}
.ce-kind--on {
  color: var(--accent-ink);
  background: var(--accent);
  border-color: var(--accent);
}
.ce-all {
  height: var(--control-height);
  padding: 0 var(--space-3);
  background: var(--bg-overlay);
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  font-size: var(--text-sm);
  cursor: pointer;
}
.ce-input {
  height: var(--control-height);
  background: var(--bg-overlay);
  color: var(--text-primary);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  padding: 0 var(--space-2);
  font-size: var(--text-sm);
  width: 6em;
}
.ce-hint {
  font-size: var(--text-2xs);
  color: var(--text-faint);
}
.ce-hint--warn { color: var(--warn); }
.ce-grades {
  display: flex;
  gap: var(--space-1);
}
.ce-grade {
  height: var(--control-height);
  padding: 0 var(--space-3);
  background: var(--bg-overlay);
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  font-size: var(--text-sm);
  cursor: pointer;
}
.ce-grade--on {
  color: var(--accent-ink);
  background: var(--accent);
  border-color: var(--accent);
}
.ce-actions {
  margin-top: var(--space-3);
}
.ce-note {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  white-space: pre-line; /* kind_errors[] 逐 kind 逐行罗列 */
}
.note--bad { color: var(--danger); }
.note--warn { color: var(--warn); }
.note--ok { color: var(--state-succeeded); }
</style>
