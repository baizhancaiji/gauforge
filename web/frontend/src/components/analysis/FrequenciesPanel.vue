<script setup lang="ts">
/**
 * 频率与 IR 面板（m3-plan §4.11 C3）：IR 棒图（频率-强度）+ 频率表，
 * 双向联动高亮（表行点击 ↔ 棒条点击）；虚频行/棒红色（--danger）标注，
 * 计数注记随虚频数显性；强度缺失（契约 nullable）的模不画棒、表内 "—"。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import echarts from "@/charts/echarts";
import type { components } from "@/api/contract";
import { useVizTheme } from "@/composables/useVizTheme";

type FrequenciesResponse = components["schemas"]["FrequenciesResponse"];

const props = defineProps<{ data: FrequenciesResponse }>();

const tokens = useVizTheme();
const el = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;
let ro: ResizeObserver | null = null;

const rows = computed(() => props.data.frequencies);
const imagCount = computed(() => rows.value.filter((r) => r.imaginary).length);
/** 默认选中第一个虚频（有则突出警示），否则不选。 */
const selected = ref<number | null>(null);

function option() {
  const t = tokens.value;
  const drawn = rows.value.filter((r) => r.ir_intensity != null);
  return {
    textStyle: { fontFamily: t.fontSans },
    grid: { left: 8, right: 12, top: 12, bottom: 24, containLabel: true },
    tooltip: {
      trigger: "axis" as const,
      valueFormatter: (v: number) => `${v.toFixed(2)} km/mol`,
    },
    xAxis: {
      type: "value" as const,
      name: "cm⁻¹",
      nameTextStyle: { color: t.textFaint },
      axisLine: { lineStyle: { color: t.textFaint } },
      axisLabel: { color: t.textFaint },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value" as const,
      name: "km/mol",
      nameTextStyle: { color: t.textFaint },
      axisLabel: { color: t.textFaint },
      splitLine: { lineStyle: { color: t.gridLine } },
    },
    series: [
      {
        name: "IR 强度",
        type: "bar" as const,
        barWidth: 3,
        data: drawn.map((r) => ({
          value: [r.frequency_cm, r.ir_intensity],
          itemStyle: {
            color:
              r.index === selected.value
                ? t.viz[0]
                : r.imaginary
                  ? t.danger
                  : t.viz[1],
          },
        })),
        itemStyle: { color: t.viz[1] },
      },
    ],
  };
}

function rebuild() {
  if (!chart) return;
  chart.setOption(option(), { notMerge: true });
}

onMounted(() => {
  if (!el.value) return;
  chart = echarts.init(el.value);
  // 棒条点击 ↔ 表行选中（联动高亮，§4.11）；ECElementEvent.data 形状按
  // 本组件写入的数据自断言
  chart.on("click", (p) => {
    const cm = (p.data as { value?: [number, number] } | null)?.value?.[0];
    const row = rows.value.find((r) => r.frequency_cm === cm);
    if (row) selected.value = row.index;
  });
  rebuild();
  ro = new ResizeObserver(() => chart?.resize());
  ro.observe(el.value);
});

onBeforeUnmount(() => {
  ro?.disconnect();
  chart?.dispose();
  chart = null;
});

watch([rows, selected, tokens], rebuild);
watch(
  () => props.data,
  () => {
    // 数据集切换：默认锚定第一个虚频（无则清选）；置于重建 watcher 前，
    // 使同一数据变更批次内先定选中再重渲
    selected.value = rows.value.find((r) => r.imaginary)?.index ?? null;
  },
);
</script>

<template>
  <div class="fq">
    <p class="fq-count mono" :class="{ 'fq-count--warn': imagCount > 0 }">
      共 {{ rows.length }} 个频率 · 虚频 {{ imagCount }} 个
    </p>
    <div ref="el" class="fq-chart"></div>
    <div class="fq-scroll">
      <table class="fq-table mono">
        <thead>
          <tr>
            <th>#</th>
            <th>频率 cm⁻¹</th>
            <th>IR km/mol</th>
            <th>对称性</th>
            <th>约化质量</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in rows"
            :key="r.index"
            :class="{
              'fq-row--imag': r.imaginary,
              'fq-row--sel': r.index === selected,
            }"
            @click="selected = r.index"
          >
            <td>{{ r.index }}</td>
            <td>{{ r.frequency_cm.toFixed(2) }}</td>
            <td>{{ r.ir_intensity?.toFixed(2) ?? "—" }}</td>
            <td>{{ r.symmetry ?? "—" }}</td>
            <td>{{ r.reduced_mass?.toFixed(3) ?? "—" }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.fq {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.fq-count {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.fq-count--warn {
  color: var(--danger);
}
.fq-chart {
  height: 180px;
  width: 100%;
}
.fq-scroll {
  max-height: 220px;
  overflow: auto;
  border-top: 1px solid var(--border-hair);
}
.fq-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: var(--text-xs);
}
.fq-table th {
  text-align: right;
  font-weight: 500;
  color: var(--text-faint);
  padding: var(--space-1) var(--space-2);
  background: var(--bg-overlay);
  position: sticky;
  top: 0;
  z-index: 1;
  border-bottom: 1px solid var(--border-hair);
}
.fq-table td {
  text-align: right;
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-hair);
  color: var(--text-secondary);
}
.fq-table th:first-child,
.fq-table td:first-child {
  text-align: left;
}
.fq-row--imag td {
  color: var(--danger);
}
.fq-row--sel td {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}
tbody tr {
  cursor: pointer;
}
</style>
