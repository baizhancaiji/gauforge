<script setup lang="ts">
/**
 * 分析概览 tab（m3-plan §4.10 C2）：Result 全集摘要——解析状态/解析器/
 * 输出程序/方法/summary 计量/可用块/degraded 明细。字段与契约 Result
 * 一一对应（gen:types 生成物），缺失值一律 "—"，不做推测性展示。
 */
import { computed } from "vue";

import type { components } from "@/api/contract";

type Result = components["schemas"]["Result"];

const props = defineProps<{ result: Result }>();

const degraded = computed(() => props.result.state === "degraded");

const optLabel = computed(() => {
  const v = props.result.summary.opt_converged;
  if (v === null) return "—";
  return v ? "已收敛" : "未收敛";
});

/** 能量双单位（契约 scf_energy_hartree 供能量表直接使用，eV 为 cclib 原生）。 */
const energyLabel = computed(() => {
  const ha = props.result.summary.scf_energy_hartree;
  const ev = props.result.summary.scf_energy_eV;
  if (ha === null || ev === null) return "—";
  return `${ha.toFixed(6)} Ha（${ev.toFixed(3)} eV）`;
});

const homosLabel = computed(() =>
  props.result.summary.homos.length
    ? props.result.summary.homos.map((h) => String(h)).join(" / ")
    : "—",
);

const blocks: { key: keyof Result["blocks"]; label: string }[] = [
  { key: "convergence", label: "能量收敛" },
  { key: "frequencies", label: "频率与 IR" },
  { key: "orbitals", label: "轨道" },
  { key: "thermochemistry", label: "热化学" },
];
</script>

<template>
  <div class="ov">
    <dl class="row">
      <dt class="mono">解析状态</dt>
      <dd>
        <span class="state mono" :class="degraded ? 'state--warn' : 'state--ok'">
          {{ degraded ? "降级解析" : "正常解析" }}
        </span>
      </dd>
    </dl>
    <dl class="row">
      <dt class="mono">解析器 / 输出程序</dt>
      <dd class="mono">
        {{ result.parser.name }} {{ result.parser.version }}
        <template v-if="result.package">
          / {{ result.package.name }} {{ result.package.version }}
        </template>
      </dd>
    </dl>
    <dl class="row">
      <dt class="mono">方法</dt>
      <dd class="mono">{{ result.method ?? "—" }}</dd>
    </dl>
    <dl class="row">
      <dt class="mono">原子 / 轨道 / 基函数</dt>
      <dd class="mono">
        {{ result.summary.natom }} / {{ result.summary.nmo }} /
        {{ result.summary.nbasis }}
      </dd>
    </dl>
    <dl class="row">
      <dt class="mono">SCF 能量</dt>
      <dd class="mono">{{ energyLabel }}</dd>
    </dl>
    <dl class="row">
      <dt class="mono">优化收敛</dt>
      <dd class="mono">{{ optLabel }}</dd>
    </dl>
    <dl class="row">
      <dt class="mono">频率数（虚频）</dt>
      <dd class="mono" :class="{ 'val--warn': (result.summary.imaginary_freq_count ?? 0) > 0 }">
        <template v-if="result.summary.freq_count === null">—</template>
        <template v-else>
          {{ result.summary.freq_count }}（{{ result.summary.imaginary_freq_count ?? 0 }}）
        </template>
      </dd>
    </dl>
    <dl class="row">
      <dt class="mono">HOMO 序号</dt>
      <dd class="mono">{{ homosLabel }}</dd>
    </dl>
    <dl class="row">
      <dt class="mono">可用数据块</dt>
      <dd class="blocks">
        <span
          v-for="b in blocks"
          :key="b.key"
          class="blk mono"
          :class="result.blocks[b.key] ? 'blk--on' : 'blk--off'"
        >
          {{ b.label }}
        </span>
      </dd>
    </dl>
    <template v-if="degraded">
      <dl v-if="result.parse_error" class="row">
        <dt class="mono">降级原因</dt>
        <dd class="mono val--warn">{{ result.parse_error }}</dd>
      </dl>
      <dl v-if="result.missing.length" class="row">
        <dt class="mono">缺失属性</dt>
        <dd class="mono val--warn">{{ result.missing.join("、") }}</dd>
      </dl>
    </template>
  </div>
</template>

<style scoped>
.ov {
  display: flex;
  flex-direction: column;
}
.row {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  border-top: 1px solid var(--border-hair);
  padding: var(--space-2) 0;
}
.row:first-child {
  border-top: none;
}
.row dt {
  flex: none;
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.row dd {
  flex: 1;
  min-width: 0;
  margin: 0;
  text-align: right;
  overflow-wrap: anywhere;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.state {
  font-size: var(--text-sm);
}
.state--ok {
  color: var(--state-succeeded);
}
.state--warn {
  color: var(--warn);
}
.val--warn {
  color: var(--warn);
}
.blocks {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-1);
}
.blk {
  font-size: var(--text-xs);
  padding: 1px var(--space-2);
  border-radius: var(--r-sm);
}
.blk--on {
  color: var(--state-succeeded);
  background: color-mix(in srgb, var(--state-succeeded) 12%, transparent);
}
.blk--off {
  color: var(--text-faint);
  background: var(--bg-inset);
}
</style>
