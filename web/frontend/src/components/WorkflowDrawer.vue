<script setup lang="ts">
/**
 * WorkflowDrawer — 组合流进度面板（m4-plan §4.9 C7；右侧抽屉）。
 * 数据源：GET /workflows?limit=20 列表（单点同形响应——页面刷新后找回
 * 组合流的恢复路径）；crest 终态与精修成员终态经既有 history.appended
 * 事件（dirty.history）驱动重拉，能量表随成员完成增量刷新。
 * 展示：workflow 状态徽标（四态中文）+ refine_queue_pending 满员提示
 * （「精修队列已生成、未自动提交，可在队列页手动提交」）+ 能量表
 * （EnergyTable，相对值列零点随完成进度重算）。
 */
import { ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import EnergyTable from "@/components/EnergyTable.vue";
import EmptyState from "@/components/EmptyState.vue";
import { fmtDateTime } from "@/utils/format";
import { useEventsStore } from "@/stores/events";

type Workflow = components["schemas"]["Workflow"];

const events = useEventsStore();

const open = ref(false);
const list = ref<Workflow[]>([]);
const loading = ref(false);
const expanded = ref<Record<string, boolean>>({});
/** 定位打开（提交成功后父级传入 workflow_id，展开该项）。 */
const focusId = ref<string | null>(null);

const STATE_LABEL: Record<string, { label: string; chip: string }> = {
  crest_running: { label: "构象搜索中", chip: "running" },
  refining: { label: "精修中", chip: "running" },
  completed: { label: "已完成", chip: "succeeded" },
  failed: { label: "已失败", chip: "failed" },
};

async function load() {
  loading.value = true;
  const { data } = await client.GET("/workflows", {
    params: { query: { limit: 20 } },
  });
  loading.value = false;
  list.value = data?.workflows ?? [];
  if (focusId.value && list.value.some((w) => w.workflow_id === focusId.value)) {
    expanded.value[focusId.value] = true;
    focusId.value = null;
  }
}

/** 组合流推进的增量刷新：crest 终态与精修成员终态均走 history.appended。 */
watch(
  () => events.dirty.history,
  () => {
    if (open.value) load();
  },
);

function show(focus?: string) {
  focusId.value = focus ?? null;
  open.value = true;
  load();
}
function hide() {
  open.value = false;
}
defineExpose({ show, hide });
</script>

<template>
  <div v-if="open" class="scrim" @click.self="hide">
    <aside class="drawer">
      <header class="d-head">
        <span class="d-title mono">组合流进度</span>
        <button class="btn btn--ghost" type="button" @click="hide">×</button>
      </header>

      <div v-if="!list.length && !loading" class="empty-wrap">
        <EmptyState glyph="◫" text="暂无组合流 — 在候选页对候选发起「组合流」后显示于此" />
      </div>

      <div v-for="w in list" :key="w.workflow_id" class="wf">
        <button
          class="wf-head"
          type="button"
          :aria-expanded="!!expanded[w.workflow_id]"
          @click="expanded[w.workflow_id] = !expanded[w.workflow_id]"
        >
          <span class="wf-id mono">{{ w.workflow_id }}</span>
          <span
            class="wf-state mono"
            :class="`wf-state--${w.state}`"
          >{{ STATE_LABEL[w.state]?.label ?? w.state }}</span>
          <span class="wf-upd mono dim">{{ fmtDateTime(w.updated_at) }}</span>
          <span class="wf-caret mono" aria-hidden="true">{{ expanded[w.workflow_id] ? "▾" : "▸" }}</span>
        </button>

        <div v-if="expanded[w.workflow_id]" class="wf-body">
          <p class="wf-meta mono dim">
            来源候选 #{{ w.source_candidate_id }}
            <template v-if="w.crest_execution_id != null">、crest 执行 #{{ w.crest_execution_id }}</template>
            <template v-if="w.refine_queue_id">、精修队列 {{ w.refine_queue_id }}</template>
          </p>
          <!-- 满员未自动提交提示（refine_queue_pending 布尔，§2.3 非状态枚举） -->
          <p v-if="w.refine_queue_pending" class="wf-pending mono" role="status">
            ⚠ 精修队列已生成、席位满员未自动提交 — 可在队列页手动提交
          </p>
          <EnergyTable :rows="w.energy_summary.rows" />
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.scrim {
  position: fixed;
  inset: 0;
  z-index: var(--z-dropdown);
  background: var(--backdrop-dim);
  display: flex;
  justify-content: flex-end;
}
.drawer {
  width: var(--drawer-width);
  height: 100%;
  background: var(--bg-overlay);
  border-left: 1px solid var(--border-hair);
  padding: var(--space-5);
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  animation: slide var(--dur-slide) var(--ease-std);
}
@keyframes slide {
  from {
    transform: translateX(100%);
  }
  to {
    transform: none;
  }
}
.d-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-hair);
}
.d-title {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
}
.empty-wrap {
  margin-top: var(--space-4);
}
.wf {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  overflow: hidden;
}
.wf-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
}
.wf-head:hover {
  background: var(--row-hover);
}
.wf-id {
  font-weight: 600;
  color: var(--accent);
}
.wf-state {
  font-size: var(--text-sm);
}
.wf-state--crest_running,
.wf-state--refining {
  color: var(--state-running);
}
.wf-state--completed {
  color: var(--state-succeeded);
}
.wf-state--failed {
  color: var(--state-failed);
}
.wf-upd {
  margin-left: auto;
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.wf-caret {
  color: var(--text-faint);
}
.wf-body {
  border-top: 1px solid var(--border-hair);
  background: var(--bg-inset);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.wf-meta {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.dim {
  color: var(--text-faint);
}
.wf-pending {
  font-size: var(--text-sm);
  color: var(--warn);
}
</style>
