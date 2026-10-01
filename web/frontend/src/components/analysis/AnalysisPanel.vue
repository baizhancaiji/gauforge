<script setup lang="ts">
/**
 * 分析区（m3-plan §2.4/§4.10 C2）：历史详情抽屉内嵌四 tab 分析视图，
 * 不单列路由页面（roadmap M3.1 硬约束）。两种形态同一组件：
 * - 执行模式（executionId）：概览先行，收敛/频率/轨道按 tab 激活惰性拉取
 *   （分块端点），blocks=false 的 tab 置灰并注明缺失原因；
 * - 工作区文件模式（.out 打开入口，分析区头部）：POST /analysis/workspace-out
 *   四块合一负载直接注入，不落库；轨道 tab 仅清单形态（OrbitalsPanel
 *   cubeAvailable=false：清单可浏览、cube/等值面入口置灰注明无 fchk）。
 * 异常终态（failed/skipped）不进解析管道：本执行分析区置灰 + 不可分析
 * 原因注记（409 ANALYSIS_UNAVAILABLE 语义的 UI 承载，§7.1-3），
 * 工作区文件分析入口不受其影响。
 */
import { computed, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import AnalysisOverview from "@/components/analysis/AnalysisOverview.vue";
import ConvergenceChart from "@/components/analysis/ConvergenceChart.vue";
import FrequenciesPanel from "@/components/analysis/FrequenciesPanel.vue";
import OrbitalsPanel from "@/components/analysis/OrbitalsPanel.vue";

type Result = components["schemas"]["Result"];
type ConvergenceResponse = components["schemas"]["ConvergenceResponse"];
type FrequenciesResponse = components["schemas"]["FrequenciesResponse"];
type OrbitalsResponse = components["schemas"]["OrbitalsResponse"];
type WorkspaceOutAnalysis = components["schemas"]["WorkspaceOutAnalysis"];

const props = defineProps<{ executionId: number; entryState: string }>();

type TabKey = "overview" | "convergence" | "frequencies" | "orbitals";
const TAB_LABELS: Record<TabKey, string> = {
  overview: "概览",
  convergence: "能量收敛",
  frequencies: "频率与 IR",
  orbitals: "轨道与静电势",
};

/** 当前激活 tab。声明先行：immediate watch 回调内会重置它（TDZ 教训，
 *  走查实测 ReferenceError 后数据链路全断）。 */
const activeTab = ref<TabKey>("overview");

// ---------- 本执行分析（执行模式） ----------
const overview = ref<Result | null>(null);
const overviewError = ref<string | null>(null);
const overviewLoading = ref(false);

/**
 * 分块惰性拉取状态打包：收敛/频率/轨道三块同形（data/error/loading/forId
 * 四 ref 结伴 + 同形 loader，审查裁决去重）；forId 记数据归属的执行 id，
 * 换执行时随 loadOverview 失效。
 */
function useBlock<T>(
  fetch: () => Promise<{ data?: T; error?: unknown; response?: Response }>,
) {
  const data = ref<T | null>(null);
  const error = ref<string | null>(null);
  const loading = ref(false);
  const forId = ref<number | null>(null);
  async function load() {
    loading.value = true;
    error.value = null;
    const { data: d, error: e, response } = await fetch();
    loading.value = false;
    if (e || !d) {
      error.value = errText(e, response?.status, "entry");
      return;
    }
    data.value = d;
    forId.value = props.executionId;
  }
  return { data, error, loading, forId, load };
}

const convBundle = useBlock<ConvergenceResponse>(() =>
  client.GET("/history/{id}/analysis/convergence", {
    params: { path: { id: props.executionId } },
  }),
);
const {
  data: conv,
  error: convError,
  loading: convLoading,
  forId: convFor,
  load: loadConv,
} = convBundle;
const freqBundle = useBlock<FrequenciesResponse>(() =>
  client.GET("/history/{id}/analysis/frequencies", {
    params: { path: { id: props.executionId } },
  }),
);
const {
  data: freq,
  error: freqError,
  loading: freqLoading,
  forId: freqFor,
  load: loadFreq,
} = freqBundle;
const orbBundle = useBlock<OrbitalsResponse>(() =>
  client.GET("/history/{id}/analysis/orbitals", {
    params: { path: { id: props.executionId } },
  }),
);
const {
  data: orb,
  error: orbError,
  loading: orbLoading,
  forId: orbFor,
  load: loadOrb,
} = orbBundle;

// ---------- 工作区文件分析（workspace-out，四块合一） ----------
const wsInput = ref("");
const wsLoading = ref(false);
const wsError = ref<string | null>(null);
const wsData = ref<WorkspaceOutAnalysis | null>(null);
const wsPath = ref("");

const mode = computed(() => (wsData.value ? "workspace" : "execution"));

function errText(
  error: unknown,
  status: number | undefined,
  kind: "entry" | "workspace",
): string {
  const body = error as { error?: { code?: string; message?: string } };
  const code = body?.error?.code;
  if (kind === "workspace") {
    if (code === "WORKSPACE_PATH_OUTSIDE")
      return "路径被拒绝 — 须为工作区内 .out/.log 文件（越界/空路径/后缀不符）";
    if (status === 404) return "工作区内不存在该文件";
    if (code === "ANALYSIS_PARSE_FAILED")
      return body.error?.message ?? "输出不可解析（或解析超时，上限 60s）";
    return body?.error?.message ?? "分析失败";
  }
  if (code === "ANALYSIS_UNAVAILABLE")
    return "分析数据不可用（未生成且重建失败）";
  if (code === "ANALYSIS_PARSE_FAILED") return "该数据块解析失败（数据不足）";
  return body?.error?.message ?? "读取失败";
}

/** 概览先行：blocks 驱动 tab 可见性（§2.4）。 */
async function loadOverview() {
  overview.value = null;
  overviewError.value = null;
  for (const b of [convBundle, freqBundle, orbBundle]) {
    b.data.value = null;
    b.error.value = null;
    b.forId.value = null;
  }
  if (props.entryState !== "succeeded") return; // 异常终态不进解析管道
  overviewLoading.value = true;
  const { data, error, response } = await client.GET("/history/{id}/analysis", {
    params: { path: { id: props.executionId } },
  });
  overviewLoading.value = false;
  if (error || !data) {
    overviewError.value = errText(error, response?.status, "entry");
    return;
  }
  overview.value = data;
}

watch(
  () => props.executionId,
  () => {
    wsData.value = null;
    wsPath.value = "";
    wsError.value = null;
    activeTab.value = "overview";
    void loadOverview();
  },
  { immediate: true },
);

// ---------- 工作区文件分析 ----------
async function analyzeWs() {
  const path = wsInput.value.trim();
  if (!path || wsLoading.value) return;
  wsLoading.value = true;
  wsError.value = null;
  const { data, error, response } = await client.POST("/analysis/workspace-out", {
    body: { path },
  });
  wsLoading.value = false;
  if (error || !data) {
    wsError.value = errText(error, response?.status, "workspace");
    return;
  }
  wsData.value = data;
  wsPath.value = path;
  activeTab.value = "overview";
}

function closeWs() {
  wsData.value = null;
  wsPath.value = "";
  wsError.value = null;
  activeTab.value = "overview";
}

// ---------- tab 定义与激活（blocks 驱动置灰，缺失原因 title 注明） ----------
const blocks = computed<Result["blocks"] | null>(() => {
  if (mode.value === "workspace") return wsData.value?.overview.blocks ?? null;
  return overview.value?.blocks ?? null;
});

const tabs = computed(() => {
  const b = blocks.value;
  const reason = (ok: boolean | undefined, why: string) =>
    ok ? "" : why;
  return [
    { key: "overview" as const, disabled: false, reason: "" },
    {
      key: "convergence" as const,
      disabled: !b?.convergence,
      reason: reason(b?.convergence, "无收敛数据（无 SCF 迹线或非优化任务）"),
    },
    {
      key: "frequencies" as const,
      disabled: !b?.frequencies,
      reason: reason(b?.frequencies, "无频率数据（非频率任务）"),
    },
    {
      key: "orbitals" as const,
      disabled: !b?.orbitals,
      reason: reason(b?.orbitals, "无轨道数据（输出无 MO 表 — 建议 route 加 Pop=Reg/Full）"),
    },
  ];
});

function switchTab(t: (typeof tabs.value)[number]) {
  if (t.disabled) return;
  activeTab.value = t.key;
  // 执行模式：数据 tab 首次激活时惰性拉取（缓存至换执行）
  if (mode.value === "execution") {
    if (t.key === "convergence" && !conv.value && convFor.value !== props.executionId)
      void loadConv();
    if (t.key === "frequencies" && !freq.value && freqFor.value !== props.executionId)
      void loadFreq();
    if (t.key === "orbitals" && !orb.value && orbFor.value !== props.executionId)
      void loadOrb();
  }
}
</script>

<template>
  <section class="ana">
    <header class="ana-head">
      <span class="ana-title mono">分析</span>
      <span
        v-if="mode === 'workspace' && wsData"
        class="ws-tag mono"
        :title="wsPath"
      >
        {{ wsPath }} — 只读不落库
      </span>
      <div class="ws-entry">
        <input
          v-model="wsInput"
          class="ws-input mono"
          type="text"
          placeholder="工作区 .out/.log 相对路径"
          aria-label="工作区输出文件路径"
          @keydown.enter="analyzeWs"
        />
        <button
          class="btn btn--secondary"
          type="button"
          :disabled="wsLoading || !wsInput.trim()"
          @click="analyzeWs"
        >
          {{ wsLoading ? "分析中 …" : "分析文件" }}
        </button>
        <button
          v-if="wsData"
          class="btn btn--ghost"
          type="button"
          @click="closeWs"
        >
          返回本执行
        </button>
      </div>
    </header>
    <p v-if="wsError" class="ana-note mono note--bad" role="alert">{{ wsError }}</p>

    <!-- 异常终态：本执行分析区置灰 + 不可分析原因注记（仅原文查看/导出） -->
    <div v-if="entryState !== 'succeeded' && mode === 'execution'" class="ana-off">
      <p class="mono">
        异常结束的执行不进入解析管道 — 分析不可用，仅可查看 / 导出原文
      </p>
    </div>

    <template v-else>
      <div class="ana-tabs" role="tablist">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="ana-tab mono"
          :class="{ 'ana-tab--on': activeTab === t.key, 'ana-tab--off': t.disabled }"
          role="tab"
          :aria-selected="activeTab === t.key"
          :disabled="t.disabled"
          :title="t.disabled ? t.reason : undefined"
          @click="switchTab(t)"
        >
          {{ TAB_LABELS[t.key] }}<template v-if="t.disabled"> — 缺</template>
        </button>
      </div>

      <div class="ana-body" role="tabpanel">
        <!-- 概览 -->
        <template v-if="activeTab === 'overview'">
          <p v-if="overviewLoading" class="ana-hint mono">读取中 …</p>
          <p v-else-if="overviewError" class="ana-note mono note--bad" role="alert">
            {{ overviewError }}
          </p>
          <AnalysisOverview
            v-else-if="mode === 'workspace' && wsData"
            :result="wsData.overview"
          />
          <AnalysisOverview v-else-if="overview" :result="overview" />
        </template>

        <!-- 能量收敛：三源切换 + 判据参考线（C3） -->
        <template v-else-if="activeTab === 'convergence'">
          <p v-if="convLoading" class="ana-hint mono">读取中 …</p>
          <p v-else-if="convError" class="ana-note mono note--bad" role="alert">
            {{ convError }}
          </p>
          <template v-else-if="mode === 'workspace' && wsData">
            <p v-if="wsData.convergence.downsampled" class="ana-hint mono">
              数据量超预算 — 已按步均匀抽稀（图形按抽稀后序列渲染）
            </p>
            <ConvergenceChart :data="wsData.convergence" />
          </template>
          <template v-else-if="conv">
            <p v-if="conv.downsampled" class="ana-hint mono">
              数据量超预算 — 已按步均匀抽稀（图形按抽稀后序列渲染）
            </p>
            <ConvergenceChart :data="conv" />
          </template>
        </template>

        <!-- 频率与 IR：棒图 + 表格联动（C3） -->
        <template v-else-if="activeTab === 'frequencies'">
          <p v-if="freqLoading" class="ana-hint mono">读取中 …</p>
          <p v-else-if="freqError" class="ana-note mono note--bad" role="alert">
            {{ freqError }}
          </p>
          <FrequenciesPanel
            v-else-if="mode === 'workspace' && wsData"
            :data="wsData.frequencies"
          />
          <FrequenciesPanel v-else-if="freq" :data="freq" />
        </template>

        <!-- 轨道与静电势：执行模式全功能（fchk 由 M1 formchk 产出）；
             workspace 模式仅清单形态（cubeAvailable=false，§2.4） -->
        <template v-else>
          <p v-if="orbLoading" class="ana-hint mono">读取中 …</p>
          <p v-else-if="orbError" class="ana-note mono note--bad" role="alert">
            {{ orbError }}
          </p>
          <OrbitalsPanel
            key="orbital-ws"
            v-else-if="mode === 'workspace' && wsData"
            :execution-id="executionId"
            :data="wsData.orbitals"
            :cube-available="false"
          />
          <OrbitalsPanel
            key="orbital-exec"
            v-else-if="orb"
            :execution-id="executionId"
            :data="orb"
          />
        </template>
      </div>
    </template>
  </section>
</template>

<style scoped>
.ana {
  margin-top: var(--space-4);
  border-top: 1px solid var(--border-strong);
  padding-top: var(--space-3);
}
.ana-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
}
.ana-title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  letter-spacing: var(--ls-micro);
}
.ws-tag {
  font-size: var(--text-xs);
  color: var(--accent);
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-entry {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  flex: 1 1 200px;
  min-width: 0;
}
.ws-entry .btn {
  white-space: nowrap;
}
.ws-input {
  flex: 1 1 140px;
  min-width: 100px;
  height: var(--control-height-sm);
  padding: 0 var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-primary);
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
}
.ws-input:focus {
  outline: none;
  border-color: var(--accent-dim);
}
.ws-input::placeholder {
  color: var(--text-faint);
}
.ana-note {
  margin: var(--space-2) 0 0;
  font-size: var(--text-sm);
}
.note--bad {
  color: var(--danger);
}
.ana-off {
  margin-top: var(--space-2);
  border: 1px dashed var(--border-hair);
  border-radius: var(--r-md);
  padding: var(--space-3);
  background: var(--bg-inset);
}
.ana-off p {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.ana-tabs {
  display: flex;
  gap: var(--space-1);
  margin-top: var(--space-3);
  border-bottom: 1px solid var(--border-hair);
}
.ana-tab {
  appearance: none;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-faint);
  cursor: pointer;
}
.ana-tab:hover:not(:disabled) {
  color: var(--text-secondary);
}
.ana-tab--on {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
.ana-tab--off {
  cursor: not-allowed;
  color: var(--text-faint);
  opacity: 0.55;
}
.ana-body {
  padding: var(--space-3) 0 0;
  min-height: 96px;
}
.ana-hint {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-faint);
}
</style>
