<script setup lang="ts">
/**
 * EnergyTable — 能量表（m4-plan §4.9 C7；GET /queues/{id}/energy-summary 与
 * GET /workflows/{id}.energy_summary 同形渲染）。
 * 行：任务 / 类型徽标（g16|crest）/ 状态 / 方法 / 绝对能量（hartree·eV 双
 * 单位）/ 相对 kJ/mol / 取数来源（analysis=解析·ensemble=crest 构象表）。
 * 零点语义（§2.3）：relative_kJ_mol 以查询范围最低能量为零点，部分完成态
 * 新增更低能量行时已展示行整体改写（接受漂移）——存在未取数行时表尾标注
 * 「随完成进度重算」。
 */
import { computed } from "vue";

import type { components } from "@/api/contract";
import StateChip from "@/components/StateChip.vue";
import { fmtTaskId } from "@/utils/format";
import { taskStateLabel } from "@/utils/labels";

type Row = components["schemas"]["EnergySummaryRow"];

const props = defineProps<{ rows: Row[] }>();

/** 部分完成态（存在未取数行）→ 相对值列标注零点漂移。 */
const partial = computed(() => props.rows.some((r) => r.source === "none"));

const SOURCE_LABEL: Record<string, string> = {
  analysis: "解析",
  ensemble: "构象表",
  none: "—",
};
</script>

<template>
  <div class="et">
    <table class="et-table">
      <thead>
        <tr>
          <th class="mono">任务</th>
          <th class="mono">类型</th>
          <th class="mono">状态</th>
          <th class="mono">方法</th>
          <th class="right mono">能量（Hartree）</th>
          <th class="right mono">能量（eV）</th>
          <th class="right mono">相对（kJ/mol）</th>
          <th class="mono">来源</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="`${r.kind}-${r.task_id}`">
          <td class="mono">{{ fmtTaskId(r.task_id) }}</td>
          <td>
            <span class="kind mono" :class="{ 'kind--crest': r.kind === 'crest' }">
              {{ r.kind === "crest" ? "CREST" : "G16" }}
            </span>
          </td>
          <td>
            <StateChip :state="r.state" :label="taskStateLabel[r.state] ?? r.state" />
          </td>
          <td class="mono dim">{{ r.method ?? "—" }}</td>
          <td class="mono right num">{{ r.energy_hartree != null ? r.energy_hartree.toFixed(6) : "—" }}</td>
          <td class="mono right num">{{ r.energy_eV != null ? r.energy_eV.toFixed(4) : "—" }}</td>
          <td class="mono right num rel">
            {{ r.relative_kJ_mol != null ? r.relative_kJ_mol.toFixed(2) : "—" }}
          </td>
          <td class="mono dim">{{ SOURCE_LABEL[r.source] ?? r.source }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="partial" class="et-note mono" role="note">
      相对能量以当前最低为零点 · 随完成进度重算
    </p>
  </div>
</template>

<style scoped>
.et {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.et-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: var(--text-sm);
}
th {
  text-align: left;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-faint);
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-hair);
}
td {
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-hair);
  vertical-align: middle;
}
tbody tr:last-child td {
  border-bottom: none;
}
.right {
  text-align: right;
}
.num {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
.rel {
  color: var(--accent);
}
.dim {
  color: var(--text-faint);
}
.kind {
  font-size: var(--text-xs);
  letter-spacing: var(--ls-wide);
  color: var(--text-secondary);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-sm);
  padding: 0 var(--space-1);
}
.kind--crest {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}
.et-note {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
</style>
