<script setup lang="ts">
/**
 * ComboFlowDialog — 组合流一键提交对话框（m4-plan §4.9 C7 / §2.3）。
 * 入口：候选列表页候选行「组合流」（载荷预选该候选 id）。
 * 参数：crest 核数（默认运行级 link0_default_nproc）/ top N∈[2,10] /
 * 精修模板 route（可选 Link0 行——坐标由 top-N 构象替换注入，非通用编辑器）。
 * 提交 POST /workflows/conformer-refinement，前置检查序 503/409/422 逐一
 * 映射文案（可执行缺失/席位满员整体拒绝零副作用/来源候选形态/越界）；
 * 成功 emit submitted（响应含 workflow_id/crest_task_id/seat_id），由父级
 * 打开进度面板定位。
 */
import { ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";
import { fmtTaskId } from "@/utils/format";

type Candidate = components["schemas"]["Candidate"];
type ConformerRefinementResponse = components["schemas"]["ConformerRefinementResponse"];

/** 默认精修模板 route（A5 定稿组合流内置模板；用户可改）。 */
const DEFAULT_ROUTE = "#p B3LYP/6-31G(d) Opt Freq";

const props = defineProps<{ open: boolean; candidate: Candidate | null }>();
const emit = defineEmits<{ close: []; submitted: [resp: ConformerRefinementResponse] }>();

const nproc = ref<number>(2);
const topN = ref<number>(2);
const route = ref(DEFAULT_ROUTE);
const link0 = ref("");
const busy = ref(false);
const error = ref<string | null>(null);

watch(
  () => props.open,
  async (v) => {
    if (!v) return;
    error.value = null;
    busy.value = false;
    route.value = DEFAULT_ROUTE;
    link0.value = "";
    topN.value = 2;
    nprocInvalid.value = false;
    routeInvalid.value = false;
    // crest 核数默认取运行级 link0_default_nproc（§2.3 组合流资源声明）
    const { data } = await client.GET("/settings");
    const nprocDefault = data?.runtime.find((s) => s.key === "link0_default_nproc")?.value;
    nproc.value = typeof nprocDefault === "number" ? nprocDefault : 2;
  },
);

/** top_n∈[2,10] / nproc 正整数 / route 非空——前端兜底（后端 422 同判）。 */
const topNInvalid = ref(false);
const nprocInvalid = ref(false);
const routeInvalid = ref(false);

async function submit() {
  const c = props.candidate;
  if (!c) return;
  const nprocBad = !Number.isInteger(nproc.value) || nproc.value < 1;
  const routeBad = !route.value.trim();
  nprocInvalid.value = nprocBad;
  routeInvalid.value = routeBad;
  if (topN.value < 2 || topN.value > 10) {
    topNInvalid.value = true;
    return;
  }
  topNInvalid.value = false;
  if (nprocBad || routeBad) return;
  busy.value = true;
  error.value = null;
  const link0Lines = link0.value
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const { data, error: e } = await client.POST("/workflows/conformer-refinement", {
    body: {
      candidate_id: c.id,
      crest: { nproc: nproc.value, top_n: topN.value },
      template: {
        route: route.value.trim(),
        ...(link0Lines.length ? { link0: link0Lines } : {}),
      },
    },
  });
  busy.value = false;
  if (e) {
    const body = e as unknown as { error?: { code?: string; message?: string } };
    error.value =
      body.error?.code === "CREST_EXECUTABLE_MISSING"
        ? "crest 可执行不可用 — 请检查运行级设置 crest_root 后重试"
        : body.error?.code === "PENDING_CAPACITY_FULL"
          ? "在途席位满员 — 组合流未受理（零副作用），请先移除席位或调高上限"
          : body.error?.code === "WORKFLOW_STATE_INVALID"
            ? "来源候选已不在候选形态 — 请重新选择候选"
            : (body.error?.message ?? "组合流提交失败");
    return;
  }
  if (data) emit("submitted", data);
}
</script>

<template>
  <ConfirmModal
    :open="open"
    title="组合流 — 构象搜索 + 精修"
    confirm-text="一键提交"
    :loading="busy"
    @confirm="submit"
    @close="!busy && emit('close')"
  >
    <div class="cf-body">
      <p class="cf-origin mono">
        来源候选 <span class="strong">#{{ candidate ? fmtTaskId(candidate.id) : "—" }}</span>
        （{{ candidate?.filename }}）— crest 构象搜索完成后自动生成 top-N 精修队列并提交
      </p>

      <div class="cf-row">
        <label class="cf-field">
          <span class="cf-label mono">crest 核数</span>
          <input v-model.number="nproc" type="number" min="1" max="64" :class="{ 'cf-invalid': nprocInvalid }" />
        </label>
        <label class="cf-field">
          <span class="cf-label mono">精修构象数 Top N（2–10）</span>
          <input
            v-model.number="topN"
            type="number"
            min="2"
            max="10"
            :class="{ 'cf-invalid': topNInvalid }"
          />
        </label>
      </div>
      <p v-if="topNInvalid" class="cf-error mono" role="alert">Top N 须在 2–10 范围内</p>
      <p v-else-if="nprocInvalid" class="cf-error mono" role="alert">crest 核数须为正整数</p>

      <label class="cf-field">
        <span class="cf-label mono">精修模板 route</span>
        <textarea v-model="route" rows="2" class="mono" :class="{ 'cf-invalid': routeInvalid }"></textarea>
      </label>
      <p v-if="routeInvalid" class="cf-error mono" role="alert">精修模板 route 必填</p>
      <label class="cf-field">
        <span class="cf-label mono">精修模板 Link0（可选，每行一条；缺省按运行级补齐）</span>
        <textarea v-model="link0" rows="2" class="mono" placeholder="%NProcShared=4"></textarea>
      </label>

      <p v-if="error" class="cf-error mono" role="alert">{{ error }}</p>
    </div>
  </ConfirmModal>
</template>

<style scoped>
.cf-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.cf-origin {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.cf-origin .strong {
  color: var(--text-primary);
}
.cf-row {
  display: flex;
  gap: var(--space-4);
}
.cf-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
  min-width: 0;
}
.cf-label {
  font-size: var(--text-sm); /* 文案含中文：不用微标签档、不加字距 */
  color: var(--text-faint);
}
input,
textarea {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: var(--space-1) var(--space-2);
  background: var(--bg-inset);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
}
textarea {
  resize: vertical;
  white-space: pre;
}
.cf-invalid {
  border-color: var(--danger);
}
.cf-error {
  font-size: var(--text-sm);
  color: var(--danger);
}
</style>
