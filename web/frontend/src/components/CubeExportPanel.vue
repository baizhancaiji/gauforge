<script setup lang="ts">
/**
 * 导出 cube 区块（3.8.0 工具箱 C8，toolbox-plan §2.2/§4.8）：工具箱
 * 导出域——fchk → cube 供外部专业分析软件（PyMOL / VMD / Chemcraft），
 * 与 OrbitalsPanel 预览面板并列、互不侵入（预览不改造）。
 *
 * kind 六选（MO / 静电势 / 密度 / 自旋 / α / β）+ 档位三选（粗 -2 /
 * 中 -3 默认 / 细 -4，禁自由数值）；MO 轨道号不在前端预显上界——提交后
 * 越界以 422 details.errors[].max 回显；α/β 仅开壳层（闭壳层 / 不可判定
 * 均按 422 message 明示，服务端 fail-closed）。错误态按契约区分：
 * 404 fchk 缺失、409 未运行条目、502 生成失败（引导先转换）、503
 * cubegen 不可用。下载文件名 <stem>-<kind>[-<n>]-<粗|中|细>.cube。
 */
import { computed, ref } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";

const props = defineProps<{
  executionId: number;
  entryState: string;
  filename: string;
}>();

type Kind = "MO" | "Potential" | "Density" | "Spin" | "Alpha" | "Beta";
type Grade = -2 | -3 | -4;

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
const GRADE_CN: Record<number, string> = { [-2]: "粗", [-3]: "中", [-4]: "细" };

const kind = ref<Kind>("Density");
const orbital = ref(1);
const grade = ref<Grade>(-3);
const busy = ref(false);
const note = ref<{ kind: "bad" | "warn" | "ok"; text: string } | null>(null);

const stem = computed(() => {
  const n = props.filename;
  return n.includes(".") ? n.slice(0, n.lastIndexOf(".")) : n;
});

function errText(e: unknown, fallback: string): string {
  const body = e as { error?: { code?: string; message?: string;
    details?: { reason?: string; errors?: { field?: string; max?: number }[] } } };
  const code = body?.error?.code;
  const reason = body?.error?.details?.reason;
  if (code === "VALIDATION_FAILED") {
    const orbitalErr = body?.error?.details?.errors?.find(
      (x) => x.field === "orbital",
    );
    if (orbitalErr?.max != null) {
      return `MO 轨道号越界 — 本体系可寻址范围至 ${orbitalErr.max}`;
    }
    if (reason === "closed_shell") {
      return "α/β 密度要求开壳层体系 — 当前条目为闭壳层，已拒绝生成";
    }
    if (reason === "shell_unknown") {
      return "无法判定开壳层 — 已拒绝生成 α/β 密度（数据不足）";
    }
    if (reason === "mo_upper_unknown") {
      return "无法确定轨道上界（分析数据与 fchk 头锚点均不可得）";
    }
    return body?.error?.message ?? "参数校验失败";
  }
  if (code === "CUBE_GENERATION_FAILED") {
    return body?.error?.details?.reason === "fchk_missing"
      ? "fchk 缺失 — 请先在上方工具区执行 chk 转换后再生成 cube"
      : "cube 生成失败（cubegen 非零退出或超时）";
  }
  if (code === "CUBE_EXECUTABLE_MISSING") {
    return "cubegen 不可用 — 请检查 g16_root 设置";
  }
  if (code === "ANALYSIS_UNAVAILABLE") return "未运行条目无执行产物";
  if (code === "NOT_FOUND") return "执行条目或产物不存在";
  return body?.error?.message ?? fallback;
}

async function generate() {
  busy.value = true;
  note.value = null;
  const body: components["schemas"]["CubeRequest"] =
    kind.value === "MO"
      ? { kind: kind.value, orbital: orbital.value, npts: grade.value }
      : { kind: kind.value, npts: grade.value };
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
  const url = URL.createObjectURL(blob as unknown as Blob);
  const a = document.createElement("a");
  const moPart = kind.value === "MO" ? `-${orbital.value}` : "";
  a.download = `${stem.value}-${kind.value}${moPart}-${GRADE_CN[grade.value]}.cube`;
  a.href = url;
  a.click();
  URL.revokeObjectURL(url);
  note.value = { kind: "ok", text: `已下载 ${a.download}` };
}
</script>

<template>
  <section v-if="entryState === 'succeeded' || entryState === 'failed'" class="cubeexp">
    <header class="ce-head">
      <span class="ce-title">导出 cube</span>
      <span class="ce-sub mono">供 PyMOL / VMD / Chemcraft 等外部软件</span>
    </header>
    <div class="ce-row">
      <label class="ce-label" for="cube-kind">类型</label>
      <select id="cube-kind" v-model="kind" class="ce-select">
        <option v-for="k in KINDS" :key="k.key" :value="k.key">{{ k.label }}</option>
      </select>
    </div>
    <div v-if="kind === 'MO'" class="ce-row">
      <label class="ce-label" for="cube-orbital">轨道号</label>
      <input
        id="cube-orbital"
        v-model.number="orbital"
        class="ce-input mono"
        type="number"
        min="1"
        step="1"
      >
      <span class="ce-hint mono">越界以提交后提示回显</span>
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
      <span v-if="grade === -4" class="ce-hint ce-hint--warn mono">细档体积大（数十 MB 量级）</span>
    </div>
    <div class="ce-actions">
      <button
        class="btn btn--primary"
        type="button"
        :disabled="busy"
        @click="generate"
      >
        {{ busy ? "生成中 …" : "生成并下载" }}
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
.ce-select,
.ce-input {
  height: var(--control-height);
  background: var(--bg-overlay);
  color: var(--text-primary);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  padding: 0 var(--space-2);
  font-size: var(--text-sm);
}
.ce-input { width: 6em; }
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
}
.note--bad { color: var(--danger); }
.note--warn { color: var(--warn); }
.note--ok { color: var(--state-succeeded); }
</style>
