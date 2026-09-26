<script setup lang="ts">
/**
 * BlockEditor — 分块编辑器（m2-plan §4.3 C1；m0-frontend-design §4.6 编辑态）。
 * 只读/编辑双态分块卡序列：
 * - 编辑按钮仅 editable 上下文渲染（候选与失败回退队列成员；新建未提交
 *   队列成员等锁定形态由宿主传 false，守卫 409 拒绝见 m2-plan §2.1）；
 * - 编辑态：可编辑节（link0/route/title/charge_mult/additional-<n>）切
 *   textarea（mono），自动保存 = 失焦或停顿 800ms 防抖二者取先（A3 定稿），
 *   逐节独立 PUT（单节原子保存语义即契约 saveBlock）；成功该卡显「已自动
 *   保存」中性注记；422 保持编辑态 + 错误注记（--danger 描边）、不落盘；
 *   无显式保存按钮、无整页级暂存/二次确认；
 * - route 拼写警告 = 琥珀注记（B1 字典近邻命中才警告，suggestion 文案）；
 * - CRLF 检出 = 中性信息注记（编辑不做转换，提交时统一规范化 §2.5）；
 * - molecule 节恒只读（原子坐标不可编辑，结构编辑交由上游 GaussView）。
 * taskId 跨形态延续：候选与回退成员共用同一端点（C3 队列页复用本组件）。
 */
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";

import { client, getText } from "@/api/client";
import type { components } from "@/api/contract";

type InputPreview = components["schemas"]["InputPreview"];
type SaveWarning = { line: number; keyword: string; kind: string; suggestion: string };

const props = defineProps<{
  taskId: number;
  /** 上下文守卫：仅候选与失败回退队列成员渲染编辑按钮（C1/C3） */
  editable?: boolean;
}>();

const preview = ref<InputPreview | null>(null);
const loading = ref(false);
const parseErrors = computed(() => preview.value?.parse_errors ?? []);
const warnings = ref<SaveWarning[]>([]);

// ---------- 编辑态 ----------
// 注意：编辑态状态必须先于 loadPreview 的 immediate watch 声明——
// immediate 回调同步执行 exitEditLocal（触达未初始化 ref 即 TDZ 崩溃，
// 预览卡恒卡「读取预览」，D1 走查实测；vue-tsc/vite build 均不拦截）。
const editing = ref(false);
/** 原文检出 CRLF（编辑不转换——提交时统一规范化，m2-plan §2.5）。 */
const crlf = ref(false);

interface EditState {
  text: string;
  dirty: boolean;
  saving: boolean;
  saved: boolean;
  error: string | null;
}
const edits = reactive(new Map<string, EditState>());

const timers = new Map<string, number>();
const saveSeq = new Map<string, number>();

async function loadPreview() {
  loading.value = true;
  exitEditLocal();
  const { data } = await client.GET("/candidates/{id}/preview", {
    params: { path: { id: props.taskId } },
  });
  loading.value = false;
  preview.value = data ?? null;
}
watch(() => props.taskId, loadPreview, { immediate: true });
onBeforeUnmount(clearTimers);

function clearTimers() {
  for (const t of timers.values()) window.clearTimeout(t);
  timers.clear();
}

function sectionText(section: string): string {
  const b = preview.value!.blocks;
  if (section === "link0") return b.link0.lines.join("\n");
  if (section === "route") return b.route;
  if (section === "title") return b.title ?? "";
  if (section === "charge_mult") return b.charge_mult;
  return (
    b.additional_sections[Number(section.split("-")[1]) - 1]?.lines.join("\n") ?? ""
  );
}

function initEdit() {
  const b = preview.value?.blocks;
  if (!b) return;
  edits.clear();
  for (const s of ["link0", "route", "title", "charge_mult"]) {
    edits.set(s, { text: sectionText(s), dirty: false, saving: false, saved: false, error: null });
  }
  b.additional_sections.forEach((_, i) => {
    const sec = `additional-${i + 1}`;
    edits.set(sec, { text: sectionText(sec), dirty: false, saving: false, saved: false, error: null });
  });
}

async function toggle() {
  if (!preview.value) return;
  if (!editing.value) {
    initEdit();
    editing.value = true;
    warnings.value = [];
    crlf.value = false;
    // CRLF 检出：读原文（跨形态端点，契约 getCandidateInput）
    const res = await getText("/candidates/{id}/input", props.taskId);
    if (editing.value && res.data && /\r/.test(res.data)) crlf.value = true;
    return;
  }
  // 退出前先落盘 dirty 节；任一保存失败保持编辑态与错误注记
  for (const [sec, st] of edits) {
    if (!st.dirty) continue;
    await saveSectionDelayed(sec);
    if (st.error) return;
  }
  exitEditLocal();
}

function exitEditLocal() {
  editing.value = false;
  edits.clear();
  warnings.value = [];
  crlf.value = false;
  clearTimers();
}

const isEd = (section: string) => editing.value && edits.has(section);
const editOf = (section: string) => edits.get(section);

/** 自动保存停顿防抖（A3 定稿：失焦或停顿时长二者取先）。 */
const AUTOSAVE_DEBOUNCE_MS = 800;

function onInput(section: string, e: Event) {
  const st = edits.get(section);
  if (!st) return;
  st.text = (e.target as HTMLTextAreaElement).value;
  st.dirty = true;
  st.saved = false;
  st.error = null;
  const t = timers.get(section);
  if (t) window.clearTimeout(t);
  timers.set(
    section,
    window.setTimeout(() => {
      timers.delete(section);
      void saveSectionDelayed(section);
    }, AUTOSAVE_DEBOUNCE_MS),
  );
}

function onBlur(section: string) {
  const t = timers.get(section);
  if (t) {
    window.clearTimeout(t);
    timers.delete(section);
  }
  void saveSectionDelayed(section);
}

async function saveSectionDelayed(section: string) {
  const st = edits.get(section);
  if (!st || !st.dirty || st.saving) return;
  const seq = (saveSeq.get(section) ?? 0) + 1;
  saveSeq.set(section, seq);
  st.saving = true;
  st.error = null;
  const { data, error } = await client.PUT("/candidates/{id}/blocks/{section}", {
    params: { path: { id: props.taskId, section } },
    body: { lines: st.text.split("\n") },
  });
  if (saveSeq.get(section) !== seq) return; // 期间又有修改：过期响应丢弃
  st.saving = false;
  if (error) {
    const body = error as unknown as {
      error?: {
        message?: string;
        details?: { errors?: { line?: number; message: string }[] };
      };
    };
    const errs = body.error?.details?.errors;
    st.error = errs?.length
      ? errs.map((e) => `第 ${e.line ?? "?"} 行 · ${e.message}`).join("；")
      : (body.error?.message ?? "保存被拒绝");
    return;
  }
  if (data) {
    preview.value = data; // 保存响应即新态（契约 mapping：不推事件）
    warnings.value = data.warnings ?? [];
    st.dirty = false;
    st.saved = true;
    st.text = sectionText(section); // 与规约后内容对齐
  }
}
</script>

<template>
  <div class="be">
    <div class="be-head">
      <slot name="head" />
      <button
        v-if="editable && preview"
        class="btn btn--secondary be-toggle"
        type="button"
        @click="toggle"
      >
        {{ editing ? "完成" : "编辑" }}
      </button>
    </div>

    <div v-if="loading" class="be-loading mono">读取预览 …</div>
    <template v-else-if="preview">
      <!-- 解析失败节容错条（预览尽力而为，逐节标注不阻断） -->
      <div v-if="parseErrors.length" class="be-errors" role="alert">
        <div v-for="(pe, i) in parseErrors" :key="i" class="pe-row mono">
          <span class="pe-sec">{{ pe.section }}</span>
          <span class="pe-line">第 {{ pe.line }} 行</span>
          <span class="pe-msg">{{ pe.message }}</span>
        </div>
      </div>

      <!-- CRLF 检出：中性信息注记（§4.6，非琥珀；编辑不转换，提交时规范化） -->
      <div v-if="editing && crlf" class="be-info mono">
        检出 CRLF 行尾 — 提交时将自动规范化为 LF
      </div>

      <!-- LINK 0 -->
      <div class="block" :class="{ 'block--editing': isEd('link0') }">
        <div class="lab mono">LINK 0</div>
        <textarea
          v-if="isEd('link0')"
          class="be-ta mono"
          :class="{ 'be-ta--error': editOf('link0')?.error }"
          :value="editOf('link0')?.text"
          rows="3"
          spellcheck="false"
          @input="onInput('link0', $event)"
          @blur="onBlur('link0')"
        ></textarea>
        <template v-else>
          <div v-if="preview.blocks.link0.lines.length" class="val mono">
            <span v-for="(ln, i) in preview.blocks.link0.lines" :key="i" class="l0-line">
              <span v-if="ln.includes('=')" class="l0-key">{{
                ln.slice(0, ln.indexOf("=") + 1)
              }}</span>{{ ln.slice(ln.indexOf("=") + 1) }}
            </span>
          </div>
          <div v-else class="val mono dim">（无声明）</div>
          <div v-if="preview.blocks.link0.missing.length" class="note mono">
            ⚠ {{ preview.blocks.link0.missing.map((m) => `%${m}`).join("、") }} 未声明 · 执行时将按默认值补齐
          </div>
        </template>
        <div v-if="editOf('link0')?.error" class="be-error mono" role="alert">
          {{ editOf('link0')?.error }}
        </div>
        <div v-if="editOf('link0')?.saved" class="be-info mono">已自动保存</div>
      </div>

      <!-- ROUTE -->
      <div class="block" :class="{ 'block--editing': isEd('route') }">
        <div class="lab mono">ROUTE</div>
        <textarea
          v-if="isEd('route')"
          class="be-ta mono"
          :class="{ 'be-ta--error': editOf('route')?.error }"
          :value="editOf('route')?.text"
          rows="2"
          spellcheck="false"
          @input="onInput('route', $event)"
          @blur="onBlur('route')"
        ></textarea>
        <div v-else class="val mono">{{ preview.blocks.route || "—" }}</div>
        <!-- 拼写警告（琥珀纪律允许清单：近邻命中才警告，非阻断不阻止自动保存） -->
        <div v-for="(w, i) in warnings" :key="i" class="be-warn mono">
          ⚠ 第 {{ w.line }} 行「{{ w.keyword }}」是否意为「{{ w.suggestion }}」？
        </div>
        <div v-if="editOf('route')?.error" class="be-error mono" role="alert">
          {{ editOf('route')?.error }}
        </div>
        <div v-if="editOf('route')?.saved" class="be-info mono">已自动保存</div>
      </div>

      <!-- TITLE -->
      <div class="block" :class="{ 'block--editing': isEd('title') }">
        <div class="lab mono">TITLE</div>
        <textarea
          v-if="isEd('title')"
          class="be-ta mono"
          :class="{ 'be-ta--error': editOf('title')?.error }"
          :value="editOf('title')?.text"
          rows="2"
          spellcheck="false"
          @input="onInput('title', $event)"
          @blur="onBlur('title')"
        ></textarea>
        <div v-else class="val mono">{{ preview.blocks.title ?? "—" }}</div>
        <div v-if="editOf('title')?.error" class="be-error mono" role="alert">
          {{ editOf('title')?.error }}
        </div>
        <div v-if="editOf('title')?.saved" class="be-info mono">已自动保存</div>
      </div>

      <!-- CHARGE · MULT -->
      <div class="block" :class="{ 'block--editing': isEd('charge_mult') }">
        <div class="lab mono">CHARGE · MULT</div>
        <textarea
          v-if="isEd('charge_mult')"
          class="be-ta mono"
          :class="{ 'be-ta--error': editOf('charge_mult')?.error }"
          :value="editOf('charge_mult')?.text"
          rows="1"
          spellcheck="false"
          @input="onInput('charge_mult', $event)"
          @blur="onBlur('charge_mult')"
        ></textarea>
        <div v-else class="val mono">{{ preview.blocks.charge_mult || "—" }}</div>
        <div v-if="editOf('charge_mult')?.error" class="be-error mono" role="alert">
          {{ editOf('charge_mult')?.error }}
        </div>
        <div v-if="editOf('charge_mult')?.saved" class="be-info mono">已自动保存</div>
      </div>

      <!-- MOLECULE（恒只读：原子坐标不可编辑） -->
      <div class="block">
        <div class="lab mono">MOLECULE</div>
        <div class="readout">
          <div class="r">
            <div class="n mono">{{ preview.blocks.molecule.atom_count }}</div>
            <div class="l mono">ATOMS</div>
          </div>
          <div class="r">
            <div class="n mono">{{ preview.blocks.molecule.formula }}</div>
            <div class="l mono">FORMULA</div>
          </div>
          <div class="r">
            <div class="n mono">{{ preview.blocks.molecule.variables_present ? "有" : "—" }}</div>
            <div class="l mono">VARS</div>
          </div>
          <div class="r">
            <div class="n mono">{{ preview.blocks.molecule.constants_present ? "有" : "—" }}</div>
            <div class="l mono">CONSTS</div>
          </div>
        </div>
      </div>

      <!-- ADDITIONAL SECTIONS -->
      <div class="block">
        <div class="lab mono">ADDITIONAL · {{ preview.blocks.additional_sections.length }}</div>
        <div v-if="!preview.blocks.additional_sections.length" class="val mono dim">
          无附加输入节
        </div>
        <div v-else class="addi">
          <div
            v-for="(sec, i) in preview.blocks.additional_sections"
            :key="i"
            class="addi-item"
            :class="{ 'block--editing': isEd(`additional-${i + 1}`) }"
          >
            <span class="sec-idx mono">{{ i + 1 }}</span>
            <textarea
              v-if="isEd(`additional-${i + 1}`)"
              class="be-ta mono"
              :class="{ 'be-ta--error': editOf(`additional-${i + 1}`)?.error }"
              :value="editOf(`additional-${i + 1}`)?.text"
              rows="3"
              spellcheck="false"
              @input="onInput(`additional-${i + 1}`, $event)"
              @blur="onBlur(`additional-${i + 1}`)"
            ></textarea>
            <pre v-else class="code mono">{{ sec.lines.join("\n") }}</pre>
            <template v-if="isEd(`additional-${i + 1}`)">
              <div class="addi-msg">
                <div v-if="editOf(`additional-${i + 1}`)?.error" class="be-error mono" role="alert">
                  {{ editOf(`additional-${i + 1}`)?.error }}
                </div>
                <div v-if="editOf(`additional-${i + 1}`)?.saved" class="be-info mono">已自动保存</div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="be-loading mono">预览不可用</div>
  </div>
</template>

<style scoped>
.be-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-hair);
  margin-bottom: var(--space-2);
}
.be-toggle {
  flex: none;
}
.be-loading {
  padding: var(--space-5);
  color: var(--text-faint);
  font-size: var(--text-sm);
}
/* 解析失败节容错条（--danger：异常信号；预览尽力而为不阻断） */
.be-errors {
  padding: var(--space-2) 0;
  margin-bottom: var(--space-2);
  border-bottom: 1px solid var(--border-hair);
  display: grid;
  gap: 2px;
}
.pe-row {
  display: flex;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--danger);
}
.pe-sec {
  min-width: 64px;
  color: var(--text-primary);
}
.pe-line {
  min-width: 64px;
}
/* 信息注记（中性档，§4.6：CRLF 提示与「已自动保存」共用） */
.be-info {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.be-errors + .be-info {
  margin-bottom: var(--space-2);
}
.block {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-hair);
}
.block:last-child {
  border-bottom: none;
}
/* 编辑中的分块卡描边转 --border-strong（A3 裁决留痕：不冒充 running 通电态） */
.block--editing {
  margin: 0 calc(-1 * var(--space-2));
  padding: var(--space-3) var(--space-2);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
}
.lab {
  font-size: var(--text-2xs);
  letter-spacing: var(--ls-wide);
  text-transform: uppercase;
  color: var(--text-faint);
  margin-bottom: var(--space-1);
}
.val {
  font-size: var(--text-sm);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.dim {
  color: var(--text-secondary);
}
/* Link0 逐行：指令名弱化（样板语义 %Chk= dim + 值亮） */
.l0-line {
  display: block;
}
.l0-key {
  color: var(--text-secondary);
}
.note {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--warn);
}
/* 编辑态 textarea（基础接管：bg-inset 底 + mono；描边 hair，错误转 danger） */
.be-ta {
  width: 100%;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: var(--space-2);
  resize: vertical;
  line-height: 1.5;
  transition: border-color var(--dur-fast) var(--ease-std);
}
.be-ta--error {
  border-color: var(--danger);
}
.be-error {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--danger);
}
/* 拼写警告（琥珀：需要行动——确认是否拼错；非阻断不阻止自动保存） */
.be-warn {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--warn);
}
.block .be-info {
  margin-top: var(--space-2);
}
/* 分子四格读数（样板 readout：ATOMS/FORMULA/VARS/CONSTS） */
.readout {
  display: flex;
  gap: var(--space-6);
}
.readout .r .n {
  font-size: var(--text-lg);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
.readout .r .l {
  font-size: var(--text-2xs);
  letter-spacing: var(--ls-wide);
  color: var(--text-faint);
}
.addi {
  display: grid;
  gap: var(--space-2);
}
.addi-item {
  display: grid;
  grid-template-columns: 20px 1fr;
  gap: var(--space-2);
  align-items: start;
}
.addi-msg {
  grid-column: 2;
}
.sec-idx {
  color: var(--text-faint);
  font-size: var(--text-xs);
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
</style>
