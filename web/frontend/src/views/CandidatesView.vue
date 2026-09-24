<script setup lang="ts">
/**
 * 01 候选任务（m0-frontend-design §5 · 表格型双栏）
 * 左 55% 列表（id/文件名/title/来源徽标/失败附注） + 右侧粘性分块预览卡。
 */
import { ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import EmptyState from "@/components/EmptyState.vue";
import { useEventsStore } from "@/stores/events";
import { fmtDateTime } from "@/utils/format";

type Candidate = components["schemas"]["Candidate"];
type InputPreview = components["schemas"]["InputPreview"];

const events = useEventsStore();

const list = ref<Candidate[]>([]);
const total = ref(0);
const loading = ref(false);
const selected = ref<Candidate | null>(null);
const preview = ref<InputPreview | null>(null);
const previewLoading = ref(false);

async function load() {
  loading.value = true;
  const { data } = await client.GET("/candidates", { params: { query: {} } });
  loading.value = false;
  if (data) {
    list.value = (data.items as Candidate[]) ?? [];
    total.value = data.total ?? 0;
  }
}

async function loadPreview(c: Candidate) {
  selected.value = c;
  previewLoading.value = true;
  const { data } = await client.GET("/candidates/{id}/preview", {
    params: { path: { id: c.id } },
  });
  previewLoading.value = false;
  preview.value = data ?? null;
}

// 契约 §3.5⑥：候选通知事件 → 重拉当前页。
watch(() => events.dirty.candidates, load);
load();

const originLabel: Record<string, string> = {
  imported: "IMPORTED",
  returned_unrun: "RETURN UNRUN",
  returned_failed: "RETURN FAILED",
  returned_succeeded: "RETURN OK",
};
</script>

<template>
  <div class="candidates">
    <section class="list" :class="{ 'is-loading': loading }">
      <div v-if="!list.length && !loading" class="empty-wrap">
        <EmptyState glyph="▯" text="暂无候选任务 — 导入 .gjf 文件后显示于此" />
      </div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>文件名</th>
            <th>标题</th>
            <th>来源</th>
            <th>创建</th>
            <th class="right">动作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in list"
            :key="c.id"
            :class="{ 'row--active': selected?.id === c.id }"
            @click="loadPreview(c)"
          >
            <td class="mono">{{ String(c.id).padStart(3, "0") }}</td>
            <td class="mono filename">{{ c.filename }}</td>
            <td class="title">{{ c.title ?? "—" }}</td>
            <td>
              <span
                class="origin mono"
                :class="`origin--${c.origin}`"
              >{{ originLabel[c.origin] ?? c.origin }}</span>
              <span
                v-if="c.failure_note"
                class="failure mono"
                title="c.failure_note"
              >因 {{ c.failure_note }}</span>
            </td>
            <td class="mono dim">{{ fmtDateTime(c.created_at) }}</td>
            <td class="right">
              <button class="ghost mono" type="button" @click.stop="loadPreview(c)">
                预览
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="scanline" aria-hidden="true" v-if="loading"></div>
      <div class="foot mono" v-if="list.length">
        {{ list.length }} 项 — 共 {{ total }}
      </div>
    </section>

    <section class="preview">
      <template v-if="previewLoading">
        <div class="preview-blank mono">读取预览 …</div>
      </template>
      <template v-else-if="preview">
        <header class="p-head">
          <span class="p-name mono">{{ preview.filename }}</span>
          <span v-if="preview.parse_errors?.length" class="p-err mono">
            {{ preview.parse_errors.length }} 处解析失败
          </span>
        </header>

        <dl class="block">
          <dt class="mono">TITLE</dt>
          <dd class="mono">{{ preview.blocks.title ?? "—" }}</dd>
        </dl>

        <div class="block">
          <p class="mono label">LINK0</p>
          <pre class="mono code">{{ preview.blocks.link0.lines.join("\n") || "（无声明）" }}</pre>
          <p v-if="preview.blocks.link0.missing.length" class="missing mono">
            缺 {{ preview.blocks.link0.missing.join("、") }}（提交将按默认补齐）
          </p>
        </div>

        <dl class="block">
          <dt class="mono label">ROUTE</dt>
          <dd class="mono route">{{ preview.blocks.route || "—" }}</dd>
        </dl>

        <dl class="block">
          <dt class="mono label">CHARGE / MULT</dt>
          <dd class="mono">{{ preview.blocks.charge_mult || "—" }}</dd>
        </dl>

        <div class="block">
          <p class="mono label">MOLECULE</p>
          <div class="mol mono">
            <span>{{ preview.blocks.molecule.atom_count }} 原子</span>
            <span class="formula">{{ preview.blocks.molecule.formula }}</span>
          </div>
          <p
            v-if="preview.blocks.molecule.variables_present || preview.blocks.molecule.constants_present"
            class="dim mono"
          >
            含变量/常数区
          </p>
        </div>

        <div class="block">
          <p class="mono label">ADDITIONAL SECTIONS</p>
          <p v-if="!preview.blocks.additional_sections.length" class="dim mono">
            无附加输入节
          </p>
          <ol v-else class="addi mono">
            <li v-for="(sec, i) in preview.blocks.additional_sections" :key="i">
              <span class="sec-idx">{{ i + 1 }}</span>
              <pre class="code">{{ sec.lines.join("\n") }}</pre>
            </li>
          </ol>
        </div>
      </template>
      <template v-else>
        <div class="p-empty">
          <span class="pe-glyph mono" aria-hidden="true">◱</span>
          <p class="pe-text mono">选择左侧任务查看分块预览</p>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.candidates {
  display: grid;
  grid-template-columns: 1fr 1.05fr;
  gap: var(--space-5);
  align-items: start;
}
.list {
  position: relative;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
  overflow: hidden;
  background: var(--bg-raised);
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}
th {
  text-align: left;
  font-size: var(--text-xs);
  font-weight: 500;
  letter-spacing: var(--ls-micro);
  text-transform: uppercase;
  color: var(--text-faint);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-raised);
  position: sticky;
  top: 0;
  border-bottom: 1px solid var(--border-hair);
}
td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-hair);
  cursor: pointer;
  vertical-align: middle;
}
tbody tr:last-child td {
  border-bottom: none;
}
tbody tr:hover {
  background: var(--row-hover);
}
.row--active {
  background: var(--row-hover);
}
.filename {
  color: var(--text-primary);
  font-weight: 500;
}
.title {
  color: var(--text-secondary);
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dim {
  color: var(--text-faint);
}
.right {
  text-align: right;
}
.origin {
  font-size: 10px;
  letter-spacing: var(--ls-micro);
  padding: 1px 6px;
  border-radius: var(--r-sm);
  border: 1px solid var(--border-strong);
  color: var(--text-secondary);
}
.origin--returned_failed {
  color: var(--warn);
  border-color: color-mix(in srgb, var(--warn) 40%, transparent);
}
.origin--returned_succeeded {
  color: var(--state-succeeded);
  border-color: color-mix(in srgb, var(--state-succeeded) 40%, transparent);
}
.origin--returned_unrun {
  color: var(--state-staged);
  border-color: color-mix(in srgb, var(--state-staged) 40%, transparent);
}
.failure {
  display: block;
  margin-top: 2px;
  font-size: 10px;
  color: var(--warn);
}
.ghost {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  padding: 4px 8px;
  border-radius: var(--r-md);
  transition: background-color 120ms ease, color 120ms ease;
}
.ghost:hover {
  background: var(--row-hover);
  color: var(--text-primary);
}
.is-loading {
  opacity: 0.4;
}
.scanline {
  height: 1px;
  background: var(--accent);
  animation: scan 1.2s ease-in-out infinite;
  margin-top: -1px;
}
@keyframes scan {
  0% {
    opacity: 0.5;
    transform: translateX(-100%);
  }
  50%,
  100% {
    opacity: 0.5;
    transform: translateX(100%);
  }
}
.foot {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-faint);
  border-top: 1px solid var(--border-hair);
}
.empty-wrap {
  padding: var(--space-4);
}
/* ---------- 预览卡 ---------- */
.preview {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
  background: var(--bg-raised);
  padding: var(--space-5);
  position: sticky;
  top: var(--space-2);
  max-height: calc(100vh - 120px);
  overflow: auto;
}
.p-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.p-name {
  font-weight: 600;
  color: var(--text-primary);
}
.p-err {
  font-size: var(--text-xs);
  color: var(--danger);
}
.block {
  padding: var(--space-3) 0;
  border-top: 1px solid var(--border-hair);
}
.block:first-of-type {
  border-top: none;
}
.label {
  font-size: var(--text-xs);
  color: var(--text-faint);
  letter-spacing: var(--ls-micro);
  margin-bottom: var(--space-1);
}
.code {
  font-size: var(--text-xs);
  color: var(--text-primary);
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: var(--space-2) var(--space-3);
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
.route {
  font-size: var(--text-sm);
  color: var(--text-primary);
}
.missing {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--warn);
}
.mol {
  display: flex;
  gap: var(--space-4);
  align-items: baseline;
  color: var(--text-primary);
}
.formula {
  font-size: var(--text-lg);
  color: var(--accent);
}
.addi {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--space-2);
}
.addi li {
  display: grid;
  grid-template-columns: 20px 1fr;
  gap: var(--space-2);
  align-items: start;
}
.sec-idx {
  color: var(--text-faint);
  font-size: var(--text-xs);
}
.preview-blank {
  color: var(--text-faint);
  font-size: var(--text-sm);
}
/* §4.6 空态：居中发丝虚线框 + 刻度符号 + mono 短句（不占满、不插画） */
.p-empty {
  min-height: 280px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  border: 1px dashed var(--border-strong);
  border-radius: var(--r-lg);
}
.pe-glyph {
  font-size: 24px;
  line-height: 1;
  color: var(--accent-dim);
  opacity: 0.7;
}
.pe-text {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
/* < 1024px：双栏收为纵向栈（§4.7 移动端显式塌缩） */
@media (max-width: 1023px) {
  .candidates {
    grid-template-columns: 1fr;
  }
  .preview {
    position: static;
    max-height: none;
  }
}
</style>