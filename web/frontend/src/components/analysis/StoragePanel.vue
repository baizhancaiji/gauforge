<script setup lang="ts">
/**
 * 历史页清理区占用面板（m3-plan §2.6/§4.14 C8）：常驻总占用读数 + 超阈
 * 琥珀警示条（「需要行动的警告」纪律允许面）+ 前 N 大占用明细可展开 +
 * 引导既有清理入口。纯拉取式（历史页加载与 history.appended 后由父组件
 * 触发 reload），无定时器、绝不自动清理（M3.7 裁决）。
 * 阈值在设置页 disk_usage_warn_gb 可配（0=禁用告警），响应 over 字段
 * 即判定结果，前端不重复实现阈值逻辑。
 */
import { computed, ref } from "vue";

import type { components } from "@/api/contract";
import { fmtBytes, fmtTaskId } from "@/utils/format";

type StorageUsage = components["schemas"]["StorageUsage"];

const props = defineProps<{ usage: StorageUsage | null }>();

const expanded = ref(false);

const overText = computed(() => {
  const u = props.usage;
  if (!u?.over) return "";
  const gb = u.threshold_bytes / 1024 ** 3;
  return `总占用已超阈值 ${gb > 0 ? gb.toFixed(0) : "—"} GB — 请手动清理`;
});
</script>

<template>
  <div v-if="usage" class="st">
    <button
      class="st-toggle mono"
      :class="{ 'st-toggle--over': usage.over }"
      type="button"
      :title="usage.over ? overText : '空间占用明细'"
      @click="expanded = !expanded"
    >
      占用 {{ fmtBytes(usage.total_bytes) }}{{ usage.over ? " ⚠" : "" }}
    </button>
    <span v-if="usage.over" class="st-warn mono" role="alert">{{ overText }}</span>

    <div v-if="expanded" class="st-detail">
      <table class="st-table mono">
        <thead>
          <tr>
            <th>执行</th>
            <th>任务</th>
            <th>占用</th>
            <th>可清理</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!usage.entries.length">
            <td colspan="4" class="st-empty">无执行目录明细</td>
          </tr>
          <tr v-for="e in usage.entries" :key="e.execution_id">
            <td>{{ fmtTaskId(e.execution_id) }}</td>
            <td class="st-file" :title="e.filename">{{ e.filename }}</td>
            <td>{{ fmtBytes(e.total_bytes) }}</td>
            <td>{{ fmtBytes(e.reclaimable_bytes) }}</td>
          </tr>
        </tbody>
      </table>
      <p class="st-foot mono">
        共 {{ usage.total_entries }} 项执行目录{{ usage.truncated ? "（仅列前 50）" : "" }}
        — 口径：工作区根整树（含数据库等非执行文件）；可清理量为超保留期的
        chk/rwf，手动清理后此处即时反映
      </p>
    </div>
  </div>
</template>

<style scoped>
.st {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  position: relative;
}
.st-toggle {
  appearance: none;
  background: none;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: 2px var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}
.st-toggle:hover {
  color: var(--text-primary);
}
/* 超阈：琥珀读数（需要行动的警告，--warn 纪律允许面） */
.st-toggle--over {
  color: var(--warn);
  border-color: var(--warn);
}
.st-warn {
  font-size: var(--text-xs);
  color: var(--warn);
  white-space: nowrap;
}
/* 明细为下拉浮层：不占工具条 flex 流（展开把筛选/导出挤成竖排的教训） */
.st-detail {
  position: absolute;
  right: 0;
  top: calc(100% + var(--space-1));
  z-index: var(--z-dropdown);
  width: 420px;
  max-width: 90vw;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-overlay);
  box-shadow: var(--shadow-pop);
  padding: var(--space-2) var(--space-3);
}
.st-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: var(--text-xs);
}
.st-table th {
  text-align: right;
  font-weight: 500;
  color: var(--text-faint);
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-hair);
}
.st-table td {
  text-align: right;
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-hair);
  color: var(--text-secondary);
}
.st-table th:first-child,
.st-table td:first-child {
  text-align: left;
}
.st-table td:nth-child(2) {
  text-align: left;
}
.st-file {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.st-empty {
  text-align: center;
  color: var(--text-faint);
}
.st-foot {
  margin: var(--space-2) 0 0;
  font-size: var(--text-xs);
  color: var(--text-faint);
}
</style>
