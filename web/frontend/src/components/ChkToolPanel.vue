<script setup lang="ts">
/**
 * chk 工具区（3.8.0 工具箱 C8，toolbox-plan §2.1/§4.8；3.8.0 修订批
 * R2 按钮主次调换）：「chk 体检」→ verdict 徽标报告（在场项 ✓/✗ +
 * 版本/NAtoms 行 + 可折叠原文）；正常结束条目的 fchk 已在任务完成时
 * 自动生成——「下载 fchk」升为第一主操作（primary，缺失以 404 提示
 * 引导先转换）；「转换为 fchk 并下载」降为次操作（fchk 缺失或需重转
 * 时使用，内嵌体检闸 409 损坏态明示）。
 *
 * 对象口径（契约）：仅终态（succeeded/failed）展示入口——skipped 无执行
 * 目录（404），不渲染；归档条目同口径提供。错误态按契约区分：
 * 409 无 chk 资产（已清理/未声明/越界）/ 体检损坏拒转换（details.verdict）、
 * 503 G16 安装目录工具缺失、502 工具失败、404 fchk 缺失。
 */
import { ref } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";

type ChkReport = components["schemas"]["ChkCheckResponse"];

const props = defineProps<{
  executionId: number;
  entryState: string;
  filename: string;
}>();

type Verdict = ChkReport["verdict"];

const checking = ref(false);
const converting = ref(false);
const report = ref<ChkReport | null>(null);
const note = ref<{ kind: "bad" | "warn" | "ok"; text: string } | null>(null);
const rawOpen = ref(false);

const VERDICT_LABEL: Record<Verdict, string> = {
  ok: "chk 健康",
  corrupted: "chk 损坏 / 不完整（可提取部分结构）",
  unreadable: "chk 完全不可读（疑似截断损坏）",
};

function stem(): string {
  const n = props.filename;
  return n.includes(".") ? n.slice(0, n.lastIndexOf(".")) : n;
}

/** blob 落盘（RFC 5987 文件名由服务端给，前端以 stem 命名本地文件）。 */
function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.download = name;
  a.href = url;
  a.click();
  URL.revokeObjectURL(url);
}

function errText(e: unknown, fallback: string): string {
  const body = e as { error?: { code?: string; message?: string;
    details?: { reason?: string; verdict?: string; tool?: string } } };
  const code = body?.error?.code;
  const reason = body?.error?.details?.reason;
  if (code === "CHK_ASSET_UNAVAILABLE") {
    if (reason === "path_outside") return "chk 资产路径越界（%chk= 声明指向执行目录之外），已拒绝读取";
    if (reason === "undeclared") return "无 chk 资产 — 输入未声明 %chk，未产生检查点文件";
    if (body?.error?.details?.verdict) return `chk 损坏 / 不完整，不执行转换（体检判定：${body.error.details.verdict === "corrupted" ? "损坏可提取" : "完全不可读"}）`;
    return "无 chk 资产 — 检查点文件已被保留期清理或移除";
  }
  if (code === "G16_TOOL_UNAVAILABLE") {
    return `G16 工具 ${body?.error?.details?.tool ?? ""}不可用 — 请检查设置中的 G16 安装目录`;
  }
  if (code === "G16_TOOL_FAILED") return "G16 工具执行失败（启动失败或超时）";
  if (code === "FCHK_GENERATION_FAILED") return "formchk 转换失败（详见服务端日志；半成品已丢弃，可重试）";
  return body?.error?.message ?? fallback;
}

async function runCheck() {
  checking.value = true;
  note.value = null;
  const { data, error } = await client.POST(
    "/history/{id}/analysis/chkchk",
    { params: { path: { id: props.executionId } } },
  );
  checking.value = false;
  if (error || !data) {
    report.value = null;
    note.value = { kind: "bad", text: errText(error, "体检失败") };
    return;
  }
  report.value = data;
}

async function downloadFchk() {
  const { data, error } = await client.GET(
    "/history/{id}/analysis/fchk",
    { params: { path: { id: props.executionId } }, parseAs: "blob" },
  );
  if (error || !data) {
    const body = error as unknown as { error?: { code?: string } };
    note.value = {
      kind: "warn",
      text: body?.error?.code === "NOT_FOUND"
        ? "fchk 不存在 — 请先执行转换"
        : "fchk 下载失败",
    };
    return;
  }
  saveBlob(data as unknown as Blob, `${stem()}.fchk`);
  note.value = { kind: "ok", text: `已下载 ${stem()}.fchk` };
}

async function convert() {
  converting.value = true;
  note.value = null;
  const { data, error } = await client.POST(
    "/history/{id}/analysis/fchk",
    { params: { path: { id: props.executionId } } },
  );
  converting.value = false;
  if (error || !data) {
    note.value = { kind: "bad", text: errText(error, "转换失败") };
    return;
  }
  await downloadFchk();
}

function mark(v: boolean | null): string {
  if (v === true) return "✓";
  if (v === false) return "—";
  return "—";
}
</script>

<template>
  <section v-if="entryState === 'succeeded' || entryState === 'failed'" class="chktools">
    <header class="ct-head">
      <span class="ct-title">chk 工具</span>
      <span class="ct-sub mono">体检 / 转换 — 供外部软件分析</span>
    </header>
    <div class="ct-actions">
      <button
        class="btn btn--secondary"
        type="button"
        :disabled="checking"
        @click="runCheck"
      >
        {{ checking ? "体检中 …" : "chk 体检" }}
      </button>
      <button
        class="btn btn--primary"
        type="button"
        title="fchk 已生成时可直接下载；缺失时请先执行转换"
        @click="downloadFchk"
      >
        下载 fchk
      </button>
      <button
        class="btn btn--secondary"
        type="button"
        :disabled="converting"
        title="fchk 缺失或需重转时使用；此前已生成过则直接下载"
        @click="convert"
      >
        {{ converting ? "转换中 …" : "转换为 fchk 并下载" }}
      </button>
    </div>
    <p v-if="note" class="ct-note mono" :class="`note--${note.kind}`" role="alert">
      {{ note.text }}
    </p>
    <div v-if="report" class="ct-report">
      <p class="ct-verdict mono" :class="`verdict--${report.verdict}`">
        {{ VERDICT_LABEL[report.verdict] }}
      </p>
      <dl class="ct-grid mono">
        <div class="ct-kv">
          <dt>版本</dt><dd>{{ report.report.version ?? "—" }}</dd>
        </div>
        <div class="ct-kv">
          <dt>原子数</dt><dd>{{ report.report.natom ?? "—" }}</dd>
        </div>
        <div class="ct-kv">
          <dt>电荷 / 多重度</dt>
          <dd>{{ report.report.icharg ?? "—" }} / {{ report.report.multip ?? "—" }}</dd>
        </div>
        <div class="ct-kv">
          <dt>坐标</dt><dd>{{ mark(report.report.has_coords) }}</dd>
        </div>
        <div class="ct-kv">
          <dt>基组</dt><dd>{{ mark(report.report.has_basis) }}</dd>
        </div>
        <div class="ct-kv">
          <dt>MO 系数</dt><dd>{{ mark(report.report.has_mo) }}</dd>
        </div>
        <div class="ct-kv">
          <dt>作业正常完成</dt><dd>{{ report.report.job_ok ? "✓" : "✗" }}</dd>
        </div>
      </dl>
      <button
        class="btn btn--ghost ct-raw-toggle"
        type="button"
        @click="rawOpen = !rawOpen"
      >
        {{ rawOpen ? "收起原文" : "查看原文" }}
      </button>
      <pre v-if="rawOpen" class="ct-raw mono">{{ report.raw }}</pre>
    </div>
  </section>
</template>

<style scoped>
.chktools {
  margin-top: var(--space-3);
  border-top: 1px solid var(--border-strong);
  padding-top: var(--space-3);
}
.ct-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}
.ct-title {
  font-size: var(--text-sm);
  color: var(--text-primary);
}
.ct-sub {
  font-size: var(--text-2xs);
  color: var(--text-faint);
  letter-spacing: var(--ls-micro);
}
.ct-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.ct-note {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
}
.note--bad { color: var(--danger); }
.note--warn { color: var(--warn); }
.note--ok { color: var(--state-succeeded); }
.ct-report {
  margin-top: var(--space-2);
}
.ct-verdict {
  font-size: var(--text-sm);
}
.verdict--ok { color: var(--state-succeeded); }
.verdict--corrupted { color: var(--warn); }
.verdict--unreadable { color: var(--danger); }
.ct-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-1) var(--space-4);
  margin-top: var(--space-2);
}
.ct-kv {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: var(--text-sm);
}
.ct-kv dt { color: var(--text-secondary); }
.ct-kv dd { color: var(--text-primary); }
.ct-raw-toggle {
  margin-top: var(--space-2);
}
.ct-raw {
  margin-top: var(--space-2);
  max-height: var(--peek-max-height);
  overflow: auto;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: var(--space-2);
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
