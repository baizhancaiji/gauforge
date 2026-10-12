<script setup lang="ts">
/**
 * ResumeDialog — 断点续跑对话框（m4-plan §4.9 C6 / §2.2 两段式第一段渲染）。
 * 打开即调 preview（无副作用恒 200；探针同步执行 formchk 秒级、120s 兜底，
 * 等待期显示「探针进行中」）；载荷渲染三分支：
 * - eligible：探针结果 + route 类型 + 注入清单（Link0 追加/route 改写/追加）
 *   + input_diff 统一 diff 文本；freq 回落原样重跑（injections 空）琥珀明示；
 * - ineligible：原因五态中文（无资产/chk 损坏/探针超时/类型不明/链内引用），
 *   确认禁用仅可关闭（零副作用）。
 * 确认调 POST /history/{id}/resume（幂等重探）：ineligible 422
 * RESUME_NOT_ELIGIBLE、满员 409 PENDING_CAPACITY_FULL 均在弹窗内提示；
 * 成功由父组件提示「已创建续跑任务 #NNN（源自 #MMM）」并刷新列表。
 */
import { computed, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";

type HistoryEntry = components["schemas"]["HistoryEntry"];
type ResumePreviewResponse = components["schemas"]["ResumePreviewResponse"];

const props = defineProps<{ open: boolean; entry: HistoryEntry | null }>();
const emit = defineEmits<{ close: []; confirmed: [task_id: number, origin: number] }>();

const loading = ref(false);
const preview = ref<ResumePreviewResponse | null>(null);
const busy = ref(false);
const error = ref<string | null>(null);

watch(
  () => props.open,
  (v) => {
    if (!v) return;
    preview.value = null;
    error.value = null;
    busy.value = false;
    void loadPreview();
  },
);

async function loadPreview() {
  const e = props.entry;
  if (!e) return;
  loading.value = true;
  error.value = null;
  const { data, error: err } = await client.POST("/history/{id}/resume/preview", {
    params: { path: { id: e.id } },
  });
  loading.value = false;
  if (err) {
    // 预览失败不静默（原缺陷：error 被解构丢弃，弹窗只剩 origin 行）
    const body = err as unknown as { error?: { message?: string } };
    error.value = `探针预览获取失败 — ${body.error?.message ?? "请关闭后重试"}`;
    preview.value = null;
    return;
  }
  preview.value = data ?? null;
}

/** ineligible 原因五态中文（契约 ResumePreviewResponse.reason 枚举）。 */
const REASON_LABEL: Record<string, string> = {
  no_resume_asset: "无续跑资产 — 无保全 chk，且无可溯源的成功执行 chk",
  chk_corrupted: "chk 损坏 — formchk 有效性探针未通过",
  probe_timeout: "探针超时 — formchk 未在时限内完成",
  unknown_kind: "任务类型不明 — 输入 route 缺失或不可解析",
  chained_ref: "链内引用 — 输入含 @task: 队列符号引用，不可脱离队列独立续跑（请在队列中回退编辑后重新提交）",
  archived: "归档条目不可续跑 — 如需操作请先取消归档",
};

/** route 任务类型中文（preview.task_kind）。 */
const KIND_LABEL: Record<string, string> = {
  opt: "几何优化",
  scf: "单点能",
  freq: "频率分析",
};

/** 注入条目摘要（ResumeInjection 三型；载体徽标已标 LINK0/ROUTE，文案不重复）。 */
function injectionText(t: components["schemas"]["ResumeInjection"]): string {
  if (t.type === "link0_append") return `追加 ${(t.link0_lines ?? []).join(" ")}`;
  if (t.type === "route_rewrite") return `改写为 ${(t.route_lines ?? []).join(" ")}`;
  return `追加 ${(t.route_lines ?? []).join(" ")}`;
}

const eligible = computed(() => preview.value?.eligible === true);
const freqFallback = computed(
  () => eligible.value && preview.value?.task_kind === "freq",
);

async function confirmResume() {
  const e = props.entry;
  if (!e) return;
  busy.value = true;
  error.value = null;
  const { data, error: err } = await client.POST("/history/{id}/resume", {
    params: { path: { id: e.id } },
  });
  busy.value = false;
  if (err) {
    const body = err as unknown as { error?: { code?: string; message?: string } };
    error.value =
      body.error?.code === "RESUME_NOT_ELIGIBLE"
        ? "续跑资产已失效 — 确认时复探未通过（chk 可能已被清理），请重新发起"
        : body.error?.code === "PENDING_CAPACITY_FULL"
          ? "在途席位满员 — 请先移除席位或调高上限后重试"
          : (body.error?.message ?? "续跑失败");
    return;
  }
  if (data) emit("confirmed", data.task_id, e.id);
}
</script>

<template>
  <ConfirmModal
    :open="open"
    title="从断点续跑"
    confirm-text="确认续跑"
    :loading="busy"
    :disabled="!eligible"
    @confirm="confirmResume"
    @close="!busy && emit('close')"
  >
    <div class="r-body">
      <p class="r-origin mono">
        对执行 <span class="strong">#{{ entry ? String(entry.id).padStart(3, "0") : "—" }}</span>
        （{{ entry?.filename }}）发起断点续跑 — 确认后新建任务并入待执行队列
      </p>

      <!-- 探针进行中（preview 同步执行 formchk，等待期占位） -->
      <p v-if="loading" class="r-probing mono" role="status">探针进行中 …（formchk 有效性检测）</p>

      <template v-else-if="preview">
        <!-- ineligible：原因五态（确认禁用，零副作用） -->
        <p v-if="!eligible" class="r-ineligible mono" role="alert">
          ✕ {{ REASON_LABEL[preview.reason ?? ""] ?? preview.reason }}
        </p>

        <template v-else>
          <p class="r-ok mono">✓ chk 有效性探针通过 — 任务类型：{{ KIND_LABEL[preview.task_kind ?? ""] ?? preview.task_kind }}</p>

          <!-- freq 回落原样重跑明示（无注入，§2.2 注入矩阵第三行） -->
          <p v-if="freqFallback" class="r-freq mono">
            ⚠ freq 任务无中断续跑语义 — 将按原样重跑（新建任务并保留「续跑自」关联）
          </p>

          <!-- 注入清单（§2.2 注入矩阵） -->
          <div v-if="preview.injections?.length" class="r-injections">
            <p class="r-cap mono">注入改动</p>
            <p v-for="(t, i) in preview.injections" :key="i" class="r-inj mono">
              <span class="inj-type">{{ t.type === "link0_append" ? "Link0" : "ROUTE" }}</span>
              {{ injectionText(t) }}
            </p>
          </div>

          <!-- 输入 diff（统一 diff 文本，注入前后全文） -->
          <div v-if="preview.input_diff" class="r-diff">
            <p class="r-cap mono">输入 diff</p>
            <pre class="diff-body mono">{{ preview.input_diff }}</pre>
          </div>
        </template>
      </template>

      <p v-if="error" class="r-error mono" role="alert">{{ error }}</p>
    </div>
  </ConfirmModal>
</template>

<style scoped>
.r-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.r-origin {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.r-origin .strong {
  color: var(--text-primary);
}
.r-probing {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.r-ineligible {
  font-size: var(--text-sm);
  color: var(--danger);
}
.r-ok {
  font-size: var(--text-sm);
  color: var(--state-succeeded);
}
.r-freq {
  font-size: var(--text-sm);
  color: var(--warn);
}
.r-cap {
  font-size: var(--text-sm); /* 文案含中文（注入改动/输入 diff） */
  text-transform: uppercase;
  color: var(--text-faint);
  margin-bottom: var(--space-1);
}
.r-injections {
  display: flex;
  flex-direction: column;
}
.r-inj {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-inset);
}
.inj-type {
  color: var(--accent);
  margin-right: var(--space-2);
  font-size: var(--text-xs);
  letter-spacing: var(--ls-wide);
}
.r-diff {
  display: flex;
  flex-direction: column;
}
.diff-body {
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
.r-error {
  font-size: var(--text-sm);
  color: var(--danger);
}
</style>
