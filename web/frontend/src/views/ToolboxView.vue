<script setup lang="ts">
/**
 * 工具箱视图（3.8.0 工具箱 C9，toolbox-plan §2.4/§2.5/§4.8）：
 * ① freqmem 内存估算校验表单——四参数手输（原子数/基函数数/壳层/角动量）
 *    + 可选核数（缺省 1）+ 可选对照 %mem；「从历史带入」选择器（仅 g16
 *    succeeded 条目）经 prefill 预填三参数与资源值（来源徽标标注声明/
 *    默认）；结果卡含每线程需求 MW/GB 换算与「对照总量 ≥ 每线程需求 ×
 *    核数」总量口径的充足/不足结论与差额（算术在后端单点，前端只呈现）。
 * ② 溶剂速查表——solname 184 条全量（懒加载缓存），搜索框名称/别名子串
 *    过滤（大小写不敏感）+ 两列表格 + 点击复制名称。
 */
import { computed, ref } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";

// ---------- freqmem 校验 ----------
const numAtoms = ref<number | null>(null);
const numBasis = ref<number | null>(null);
const shell = ref<"r" | "u">("r");
const basisType = ref<"p" | "d" | "f" | "g" | "h" | "i">("d");
const nproc = ref<number | null>(null);
const compareMem = ref<number | null>(null);

const checking = ref(false);
const result = ref<components["schemas"]["FreqmemCheckResponse"] | null>(null);
const checkError = ref<string | null>(null);

const BASIS_OPTIONS = [
  { value: "p", label: "p" },
  { value: "d", label: "d" },
  { value: "f", label: "f" },
  { value: "g", label: "g" },
  { value: "h", label: "h" },
  { value: "i", label: "i" },
] as const;

function errText(e: unknown, fallback: string): string {
  const body = e as { error?: { code?: string; message?: string;
    details?: { reason?: string; error_lines?: string[] } } };
  const code = body?.error?.code;
  if (code === "VALIDATION_FAILED") {
    if (body?.error?.details?.error_lines?.length) {
      return `freqmem 拒绝了该参数组合 — ${body.error.details.error_lines[0]}`;
    }
    return body?.error?.message ?? "参数校验失败";
  }
  if (code === "G16_TOOL_UNAVAILABLE") return "freqmem 不可用 — 请检查 g16_root 设置";
  if (code === "G16_TOOL_FAILED") return "freqmem 执行失败（启动失败或超时）";
  return body?.error?.message ?? fallback;
}

async function runCheck() {
  if (!numAtoms.value || !numBasis.value) {
    checkError.value = "请先填写原子数与基函数数";
    return;
  }
  checking.value = true;
  checkError.value = null;
  result.value = null;
  const body: components["schemas"]["FreqmemCheckRequest"] = {
    num_atoms: numAtoms.value,
    num_basis: numBasis.value,
    shell: shell.value,
    basis_type: basisType.value,
  };
  if (nproc.value != null) body.nproc = nproc.value;
  if (compareMem.value != null) body.compare_mem_gb = compareMem.value;
  const { data, error } = await client.POST("/toolbox/freqmem", { body });
  checking.value = false;
  if (error || !data) {
    checkError.value = errText(error, "校验失败");
    return;
  }
  result.value = data;
}

// ---------- 历史带入（prefill） ----------
interface PrefillEntry { id: number; filename: string }
const historyEntries = ref<PrefillEntry[]>([]);
const loadingHistory = ref(false);
const historyLoaded = ref(false);
const selectedExec = ref<number | null>(null);
const prefilling = ref(false);
const prefillNote = ref<string | null>(null);

async function loadHistory() {
  loadingHistory.value = true;
  const { data } = await client.GET("/history", {
    params: { query: { state: "succeeded", page_size: 200 } },
  });
  loadingHistory.value = false;
  historyLoaded.value = true;
  // 仅 g16 任务（crest 等无对应分析数据，不入列）
  historyEntries.value = (data?.items ?? [])
    .filter((it) => it.kind === "g16")
    .map((it) => ({ id: it.id, filename: it.filename }));
}

async function prefill() {
  if (selectedExec.value == null) return;
  prefilling.value = true;
  prefillNote.value = null;
  const { data, error } = await client.GET("/toolbox/freqmem-prefill", {
    params: { query: { execution_id: selectedExec.value } },
  });
  prefilling.value = false;
  if (error || !data) {
    const body = error as unknown as { error?: { message?: string;
      details?: { state?: string } } };
    prefillNote.value = body?.error?.details?.state
      ? "该条目未正常运行，无分析数据可带入"
      : body?.error?.message ?? "预填失败";
    return;
  }
  numAtoms.value = data.num_atoms;
  numBasis.value = data.num_basis;
  shell.value = data.shell;
  compareMem.value = data.suggested_compare_mem_gb;
  nproc.value = data.suggested_nproc;
  prefillNote.value =
    `已带入 #${selectedExec.value}（内存来源：${data.suggested_mem_source === "declared" ? "任务声明" : "默认值"}；核数来源：${data.suggested_nproc_source === "declared" ? "任务声明" : "默认值"}）`;
}

// ---------- 溶剂速查 ----------
interface Solvent { id: number; name: string; aliases: string[] }
const solvents = ref<Solvent[]>([]);
const solventsLoading = ref(false);
const solventsError = ref<string | null>(null);
const solventQuery = ref("");
const copied = ref<string | null>(null);
const copyFailed = ref(false);

async function loadSolvents() {
  if (solvents.value.length || solventsLoading.value) return;
  solventsLoading.value = true;
  solventsError.value = null;
  const { data, error } = await client.GET("/toolbox/solvents");
  solventsLoading.value = false;
  if (error || !data) {
    const body = error as unknown as { error?: { code?: string } };
    solventsError.value = body?.error?.code === "G16_TOOL_UNAVAILABLE"
      ? "solname 不可用 — 请检查 g16_root 设置"
      : "溶剂数据加载失败";
    return;
  }
  solvents.value = data.solvents as Solvent[];
}

const filteredSolvents = computed(() => {
  const q = solventQuery.value.trim().toLowerCase();
  if (!q) return solvents.value;
  return solvents.value.filter(
    (s) => s.name.toLowerCase().includes(q)
      || s.aliases.some((a) => a.toLowerCase().includes(q)),
  );
});

async function copyName(s: Solvent) {
  copied.value = null;
  copyFailed.value = false;
  try {
    await navigator.clipboard.writeText(s.name);
    copied.value = s.name;
  } catch {
    // 剪贴板授权不可用（权限拒绝等）→ 选中单元格文本走 execCommand 兜底
    const sel = window.getSelection();
    const cell = document.querySelector(`[data-solvent-id="${s.id}"]`);
    if (sel && cell) {
      const range = document.createRange();
      range.selectNodeContents(cell);
      sel.removeAllRanges();
      sel.addRange(range);
      copyFailed.value = !document.execCommand("copy");
      sel.removeAllRanges();
    } else {
      copyFailed.value = true;
    }
  }
  setTimeout(() => { copied.value = null; copyFailed.value = false; }, 1500);
}
</script>

<template>
  <main class="content">
    <div class="tb">
      <!-- ① freqmem 校验 -->
      <section class="card">
        <header class="tb-head">
          <h2 class="tb-title">freq 任务内存估算</h2>
          <span class="tb-sub mono">freqmem — 每线程需求与 %mem 对照</span>
        </header>
        <div class="fm-prefill">
          <template v-if="!historyLoaded">
            <button
              class="btn btn--secondary"
              type="button"
              :disabled="loadingHistory"
              @click="loadHistory"
            >
              {{ loadingHistory ? "读取中 …" : "从历史带入" }}
            </button>
          </template>
          <template v-else>
            <select
              v-model.number="selectedExec"
              class="fm-select"
              aria-label="选择历史条目"
              @change="prefill"
            >
              <option :value="null" disabled>选择 succeeded 条目 …</option>
              <option v-for="e in historyEntries" :key="e.id" :value="e.id">
                #{{ String(e.id).padStart(3, "0") }} — {{ e.filename }}
              </option>
            </select>
          </template>
          <span v-if="prefillNote" class="fm-prefill-note mono">{{ prefillNote }}</span>
        </div>
        <div class="fm-grid">
          <label class="fm-field">
            <span class="fm-label">原子数</span>
            <input v-model.number="numAtoms" class="fm-input mono" type="number" min="1">
          </label>
          <label class="fm-field">
            <span class="fm-label">基函数数</span>
            <input v-model.number="numBasis" class="fm-input mono" type="number" min="1">
          </label>
          <label class="fm-field">
            <span class="fm-label">壳层</span>
            <select v-model="shell" class="fm-select">
              <option value="r">闭壳层 r</option>
              <option value="u">开壳层 u</option>
            </select>
          </label>
          <label class="fm-field">
            <span class="fm-label">角动量层级</span>
            <select v-model="basisType" class="fm-select">
              <option v-for="b in BASIS_OPTIONS" :key="b.value" :value="b.value">
                {{ b.label }}
              </option>
            </select>
          </label>
          <label class="fm-field">
            <span class="fm-label">核数（可选）</span>
            <input v-model.number="nproc" class="fm-input mono" type="number" min="1" placeholder="1">
          </label>
          <label class="fm-field">
            <span class="fm-label">对照 %mem GB（可选）</span>
            <input v-model.number="compareMem" class="fm-input mono" type="number" min="0" placeholder="如 8">
          </label>
        </div>
        <div class="fm-actions">
          <button
            class="btn btn--primary"
            type="button"
            :disabled="checking"
            @click="runCheck"
          >
            {{ checking ? "估算中 …" : "估算内存需求" }}
          </button>
        </div>
        <p v-if="checkError" class="fm-note mono note--bad" role="alert">{{ checkError }}</p>
        <div v-if="result" class="fm-result">
          <p class="fm-line mono">
            每线程需求：<strong>{{ result.minimum_mw }}</strong> MW
            ≈ <strong>{{ result.minimum_gb.toFixed(2) }}</strong> GB
          </p>
          <template v-if="result.verdict">
            <p
              class="fm-verdict mono"
              :class="result.verdict.sufficient ? 'verdict--ok' : 'verdict--bad'"
            >
              {{ result.verdict.sufficient ? "充足" : "不足" }} —
              声明 {{ result.verdict.declared_mem_gb }}GB ≥ 每线程需求 ×
              {{ result.verdict.nproc }} 核（{{ (result.minimum_gb * result.verdict.nproc).toFixed(2) }}GB）
              <template v-if="result.verdict.sufficient">
                ，富余 {{ result.verdict.delta_gb.toFixed(2) }}GB
              </template>
              <template v-else>
                ，缺口 {{ result.verdict.delta_gb.toFixed(2) }}GB
              </template>
            </p>
            <p v-if="result.verdict.nproc > 1" class="fm-hint mono">
              对照为总量口径：%mem 声明须覆盖全部核数的每线程需求合计
            </p>
          </template>
        </div>
      </section>

      <!-- ② 溶剂速查 -->
      <section class="card">
        <header class="tb-head">
          <h2 class="tb-title">SCRF 溶剂速查</h2>
          <span class="tb-sub mono">solname — 点击名称复制</span>
        </header>
        <p v-if="solventsError" class="fm-note mono note--bad" role="alert">
          {{ solventsError }}
          <button class="btn btn--ghost" type="button" @click="loadSolvents">重试</button>
        </p>
        <template v-else-if="solvents.length">
          <input
            v-model="solventQuery"
            class="fm-input fm-search mono"
            type="search"
            placeholder="搜索名称 / 别名 …"
            aria-label="搜索溶剂"
          >
          <p class="fm-hint mono">{{ filteredSolvents.length }} / {{ solvents.length }} 条</p>
          <div class="sv-table-wrap">
            <table class="sv-table">
              <thead>
                <tr>
                  <th class="mono">名称</th>
                  <th class="mono">别名 / 缩写</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="s in filteredSolvents"
                  :key="s.id"
                  class="sv-row"
                  :title="`点击复制 ${s.name}`"
                  @click="copyName(s)"
                >
                  <td class="mono sv-name" :data-solvent-id="s.id">{{ s.name }}</td>
                  <td class="mono sv-alias">{{ s.aliases.length ? s.aliases.join("、") : "—" }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="copied" class="fm-note mono note--ok" role="status">已复制 {{ copied }}</p>
          <p v-else-if="copyFailed" class="fm-note mono note--bad" role="alert">
            复制失败 — 已选中文本，请按 Ctrl+C 手动复制
          </p>
        </template>
        <template v-else>
          <button
            class="btn btn--secondary"
            type="button"
            :disabled="solventsLoading"
            @click="loadSolvents"
          >
            {{ solventsLoading ? "加载中 …" : "加载溶剂数据" }}
          </button>
        </template>
      </section>
    </div>
  </main>
</template>

<style scoped>
.tb {
  display: flex;
  flex-direction: column;
  gap: var(--gap-card);
  max-width: var(--content-max);
}
.card {
  background: var(--bg-raised);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: var(--space-4);
}
.tb-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}
.tb-title {
  font-size: var(--text-lg);
  color: var(--text-primary);
}
.tb-sub {
  font-size: var(--text-2xs);
  color: var(--text-faint);
  letter-spacing: var(--ls-micro);
}
.fm-prefill {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.fm-select,
.fm-input {
  height: var(--control-height);
  background: var(--bg-overlay);
  color: var(--text-primary);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  padding: 0 var(--space-2);
  font-size: var(--text-sm);
}
.fm-prefill-note {
  font-size: var(--text-2xs);
  color: var(--text-secondary);
}
.fm-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3) var(--space-4);
  margin-top: var(--space-3);
}
.fm-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.fm-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.fm-input { width: 100%; }
.fm-actions {
  margin-top: var(--space-4);
}
.fm-note {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
}
.note--bad { color: var(--danger); }
.note--ok { color: var(--state-succeeded); }
.fm-result {
  margin-top: var(--space-3);
  border-top: 1px solid var(--border-hair);
  padding-top: var(--space-3);
}
.fm-line {
  font-size: var(--text-md);
  color: var(--text-primary);
}
.fm-verdict {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
}
.verdict--ok { color: var(--state-succeeded); }
.verdict--bad { color: var(--warn); }
.fm-hint {
  margin-top: var(--space-1);
  font-size: var(--text-2xs);
  color: var(--text-faint);
}
.fm-search {
  width: 100%;
  margin-top: var(--space-3);
}
.sv-table-wrap {
  margin-top: var(--space-2);
  max-height: var(--peek-max-height);
  overflow: auto;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
}
.sv-table {
  width: 100%;
  border-collapse: collapse;
}
.sv-table th {
  position: sticky;
  top: 0;
  background: var(--bg-overlay);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  text-align: left;
  padding: var(--space-2);
  letter-spacing: var(--ls-micro);
}
.sv-row {
  cursor: pointer;
}
.sv-row:hover {
  background: var(--row-hover);
}
.sv-table td {
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-sm);
  border-top: 1px solid var(--border-hair);
}
.sv-name {
  color: var(--text-primary);
}
.sv-alias {
  color: var(--text-secondary);
}
</style>
