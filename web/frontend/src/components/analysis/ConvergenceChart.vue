<script setup lang="ts">
/**
 * 能量收敛曲线（m3-plan §4.11 C3）：三数据源切换——SCF 迹线（逐迭代判据
 * 列，log 轴）/ 几何收敛（geovalues vs geotargets，判据虚线参考线）/
 * 能量序列（各几何步末次 SCF 能量，tooltip hartree/eV 双单位）。
 * 颜色只引用设计令牌（useVizTheme）；判据列契约无名，序号命名不杜撰。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import echarts from "@/charts/echarts";
import type { components } from "@/api/contract";
import { useVizTheme } from "@/composables/useVizTheme";

type ConvergenceResponse = components["schemas"]["ConvergenceResponse"];

const props = defineProps<{ data: ConvergenceResponse }>();

type Source = "scf" | "geo" | "energy";
const SOURCES: { key: Source; label: string }[] = [
  { key: "scf", label: "SCF 迹线" },
  { key: "geo", label: "几何收敛" },
  { key: "energy", label: "能量序列" },
];
const source = ref<Source>("scf");

const tokens = useVizTheme();
const el = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;
let ro: ResizeObserver | null = null;

/** 各源是否真的有数据（空数据显示占位说明，§4.11 技术要求）。 */
const avail = computed(() => ({
  scf: props.data.scf_trace.some((s) => s.cycles.length > 0),
  geo: props.data.geo_trace.length > 0,
  energy: props.data.energy_series.length > 0,
}));

function baseAxis(xName: string, yName: string, log: boolean) {
  const t = tokens.value;
  return {
    xAxis: {
      type: "value" as const,
      name: xName,
      // 轴名中置下挂：end 定位会被画布右缘裁剪（D1 走查缺陷①）
      nameLocation: "middle" as const,
      nameGap: 25,
      nameTextStyle: { color: t.textFaint },
      axisLine: { lineStyle: { color: t.textFaint } },
      axisLabel: { color: t.textFaint },
      splitLine: { show: false },
    },
    yAxis: {
      type: log ? ("log" as const) : ("value" as const),
      name: yName,
      scale: !log, // 能量轴不强制包含 0（收敛末段微变化可见）
      nameTextStyle: { color: t.textFaint },
      axisLine: { show: false },
      axisLabel: { color: t.textFaint },
      splitLine: { lineStyle: { color: t.gridLine } },
    },
    grid: { left: 8, right: 30, top: 32, bottom: 46, containLabel: true },
    tooltip: { trigger: "axis" as const },
  };
}

/** log 轴判据图公共框架（SCF/几何两源共用）：字体栈 + 轴 + 缩放条。 */
function logCvFrame(xName: string, yName: string) {
  const t = tokens.value;
  return {
    // 根级字体栈：canvas 文本不继承 DOM，中文须显式 Web 字体（豆腐块教训）
    textStyle: { fontFamily: t.fontSans },
    ...baseAxis(xName, yName, true),
    dataZoom: [{ type: "slider", height: 14, bottom: 2 }],
  };
}

/**
 * 判据系列公共形状（SCF/几何两源共用，审查裁决去重）：按列循环取色、
 * connectNulls 保持连续；c=0 系列挂 targets 判据虚线参考线。
 */
function criteriaSeries(
  cols: { name: string; data: (number | null)[] }[],
  targets: number[],
  symbol: "none" | "circle",
) {
  const t = tokens.value;
  return cols.map((col, c) => ({
    name: col.name,
    type: "line" as const,
    data: col.data,
    symbol,
    symbolSize: symbol === "circle" ? 4 : undefined,
    connectNulls: true,
    lineStyle: { color: t.viz[c % t.viz.length], width: 1.2 },
    itemStyle: { color: t.viz[c % t.viz.length] },
    markLine:
      c === 0
        ? {
            silent: true,
            symbol: "none",
            label: { show: false },
            lineStyle: { color: t.warn, type: "dashed" as const, width: 1 },
            data: targets.map((v) => ({ yAxis: v })),
          }
        : undefined,
  }));
}

/** SCF 迹线：逐几何步的迭代判据行拉平为全局迭代序；早期判据未更新为
 *  null（契约 nullable），connectNulls 保持迹线连续。 */
function scfOption() {
  const ncol = props.data.scf_targets.length;
  // 判据列拉平：x 取数据序（即跨几何步累计迭代序，1 起）
  const cols: (number | null)[][] = Array.from({ length: ncol }, () => []);
  let i = 0;
  for (const step of props.data.scf_trace) {
    for (const row of step.cycles) {
      ++i;
      for (let c = 0; c < ncol; c++) cols[c].push(row[c] ?? null);
    }
  }
  return {
    ...logCvFrame("SCF 迭代（跨几何步累计）", "判据值（log）"),
    series: criteriaSeries(
      cols.map((values, c) => ({ name: `判据 ${c + 1}`, data: values })),
      props.data.scf_targets,
      "none",
    ),
  };
}

/** 几何收敛：四判据列 vs 各自阈值虚线（log 轴看收敛趋紧）。 */
function geoOption() {
  const ncol = props.data.geo_targets.length;
  return {
    ...logCvFrame("几何步", "判据值（log）"),
    series: criteriaSeries(
      Array.from({ length: ncol }, (_, c) => ({
        name: `判据 ${c + 1}`,
        data: props.data.geo_trace.map((g) => g.values[c] ?? null),
      })),
      props.data.geo_targets,
      "circle",
    ),
  };
}

/** 能量序列：hartree 主轴，tooltip 附 eV（契约双单位）。 */
function energyOption() {
  const t = tokens.value;
  const pts = props.data.energy_series;
  return {
    textStyle: { fontFamily: t.fontSans },
    ...baseAxis("几何步", "能量（Hartree）", false),
    tooltip: {
      trigger: "axis" as const,
      valueFormatter: (v: number) =>
        `${v.toFixed(6)} Ha（${(pts.find((p) => p.energy_hartree === v)?.energy_eV ?? NaN).toFixed(3)} eV）`,
    },
    series: [
      {
        name: "SCF 能量",
        type: "line" as const,
        data: pts.map((p) => [p.geometry_step, p.energy_hartree]),
        symbol: "circle",
        symbolSize: 4,
        lineStyle: { color: t.viz[0], width: 1.4 },
        itemStyle: { color: t.viz[0] },
      },
    ],
  };
}

function rebuild() {
  if (!chart) return;
  const a = avail.value;
  if (!a[source.value]) {
    chart.clear();
    return;
  }
  chart.setOption(
    source.value === "scf"
      ? scfOption()
      : source.value === "geo"
        ? geoOption()
        : energyOption(),
    { notMerge: true },
  );
}

onMounted(() => {
  if (!el.value) return;
  chart = echarts.init(el.value);
  rebuild();
  ro = new ResizeObserver(() => chart?.resize());
  ro.observe(el.value);
});

onBeforeUnmount(() => {
  ro?.disconnect();
  chart?.dispose();
  chart = null;
});

watch([() => props.data, source, tokens], rebuild);
</script>

<template>
  <div class="cv">
    <div class="srcs" role="radiogroup" aria-label="收敛数据源">
      <button
        v-for="s in SOURCES"
        :key="s.key"
        class="src mono"
        :class="{ 'src--on': source === s.key, 'src--empty': !avail[s.key] }"
        type="button"
        :title="avail[s.key] ? '' : '该数据源无数据（非优化任务或输出未含此类迹线）'"
        @click="source = s.key"
      >
        {{ s.label }}
      </button>
    </div>
    <div v-if="avail[source]" ref="el" class="cv-chart"></div>
    <p v-else class="cv-empty mono">
      {{ source === "geo" ? "无几何收敛数据（非优化任务或单点计算）" : "无此类迹线数据" }}
    </p>
  </div>
</template>

<style scoped>
.cv {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.srcs {
  display: flex;
  gap: var(--space-1);
}
.src {
  appearance: none;
  background: none;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: 2px var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-faint);
  cursor: pointer;
}
.src:hover:not(.src--on) {
  color: var(--text-secondary);
}
.src--on {
  color: var(--accent);
  border-color: var(--accent-dim);
}
.src--empty {
  opacity: 0.5;
}
.cv-chart {
  height: 240px;
  width: 100%;
}
.cv-empty {
  margin: var(--space-4) 0;
  font-size: var(--text-sm);
  color: var(--text-faint);
}
</style>
