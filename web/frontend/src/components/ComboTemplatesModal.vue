<script setup lang="ts">
/**
 * ComboTemplatesModal — 组合流精修模板配置弹窗（插波 3.2.0，m4-combo-deploy-plan §3.4）。
 * 外壳 ConfirmModal（QueueEditorModal 同款：默认插槽 + #foot）。
 * 顶部一排 5 个矩形方案框（.preset--on 选中范式放大：显式数字 1–5 + 配置名 +
 * 默认徽标），点击选中（accent 描边）展开下方编辑区，打开自动选中方案 1。
 * 编辑区：配置名 / route textarea（单行约束 @input 剥离换行）/ link0 三编辑框
 * （%nprocshared inputmode=numeric、%mem inputmode=decimal、%cpu 默认置灰——
 * 勾选 %nprocshared 旁「指定CPU核心」复选框启用）/「设为默认」复选框（radio
 * 语义：默认不可取消、仅可改选）。三者均以文本形态提交，值级校验归后端单点；
 * 输入不做实时改写，保存由后端归一化回显（notice：temp_applied 已补齐 /
 * normalized 已归一化 / spelling_warnings 词典外 token 清单）。
 * 保存 422：errors 全量显著展示（字段级红描边 + 顶部错误清单）；
 * reason=keyword_not_in_dict 时出「忽略拼写警告并保存」豁免按钮——豁免记忆
 * 作用域 = 弹窗打开期间 × 全局 token 集（跨方案共享、关闭弹窗即清空、保存
 * 失败不清、成功后本会话保持、重开重新校验；§3.4）。
 * 未点保存：本地改动丢弃，切方案/关闭均回已保存值。
 */
import { computed, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";

type ComboTemplate = components["schemas"]["ComboTemplate"];
type ComboNotice = components["schemas"]["ComboTemplateMutationResult"]["notice"];
type TemplateError = { field: string; line: number; reason: string; message: string };

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();

const loading = ref(false);
const loadError = ref(false); // 打开时 GET 失败：错误态呈现，保存不可用
const busy = ref(false);
const templates = ref<ComboTemplate[]>([]);
const initialRoute = ref("");
const selectedId = ref<number>(1);

// 编辑区（文本形态原样保存，清空即「恢复初始值/未配置」语义，由后端裁决）
const name = ref("");
const route = ref("");
const nproc = ref("");
const memGb = ref("");
const cpu = ref("");
const useCpu = ref(false); // 「指定CPU核心」：%cpu 编辑框启用开关
const isDefault = ref(false); // 「设为默认」（radio 语义）

const errors = ref<TemplateError[]>([]);
const warnings = ref<string[]>([]); // notice.spelling_warnings（词典外 token 原文）
const notice = ref<ComboNotice | null>(null); // 最近一次成功保存的 notice
const exemptTokens = ref<Set<string>>(new Set()); // 豁免记忆（弹窗打开期间 × 全局）

const selected = computed(
  () => templates.value.find((t) => t.template_id === selectedId.value) ?? null,
);
/** 字段级红描边映射（后端 errors[].field：route/nproc/mem_gb/cpu/link0）。 */
const fieldErrors = computed(() => new Set(errors.value.map((e) => e.field)));
const hasKeywordErrors = computed(() =>
  errors.value.some((e) => e.reason === "keyword_not_in_dict"),
);

/** 422 errors 中 keyword_not_in_dict 条目的 token（message「词典外关键词：{t}」）。 */
function oovTokensFromErrors(errs: TemplateError[]): string[] {
  return errs
    .filter((e) => e.reason === "keyword_not_in_dict")
    .map((e) => e.message.replace(/^词典外关键词：/, ""))
    .filter(Boolean);
}

function fillForm(t: ComboTemplate) {
  name.value = t.name;
  route.value = t.route;
  nproc.value = t.nproc ?? "";
  memGb.value = t.mem_gb ?? "";
  cpu.value = t.cpu ?? "";
  useCpu.value = t.cpu != null;
  isDefault.value = t.is_default;
}

/** 切方案：丢弃未保存的本地改动，回该方案已保存值。 */
function selectScheme(id: number) {
  selectedId.value = id;
  errors.value = [];
  warnings.value = [];
  notice.value = null;
  const t = templates.value.find((x) => x.template_id === id);
  if (t) fillForm(t);
}

watch(
  () => props.open,
  async (v) => {
    if (!v) return;
    loading.value = true;
    loadError.value = false;
    errors.value = [];
    warnings.value = [];
    notice.value = null;
    exemptTokens.value = new Set(); // 关闭即清空豁免记忆（重开重新校验）
    const { data } = await client.GET("/combo-templates");
    loading.value = false;
    if (!data) {
      loadError.value = true;
      return;
    }
    templates.value = data.templates;
    initialRoute.value = data.initial.route;
    selectScheme(templates.value[0]?.template_id ?? 1); // 打开自动选中方案 1
  },
);

/** route 单行约束：@input 剥离换行符（粘贴多行亦不可构造，§3.4）。 */
function stripNewlines() {
  if (/\r?\n/.test(route.value)) {
    route.value = route.value.replace(/\r?\n/g, " ");
  }
}

/** 「设为默认」radio 语义：默认方案不可取消，仅可改选（A4）。
 *  原生 checkbox 点击已把 DOM 取反，须显式回写勾选态防视觉与状态脱节。 */
function toggleDefault(e: Event) {
  (e.target as HTMLInputElement).checked = true;
  isDefault.value = true;
}

/** 「指定CPU核心」：取消勾选即清空 %cpu（未配置语义）。 */
function toggleUseCpu() {
  useCpu.value = !useCpu.value;
  if (!useCpu.value) cpu.value = "";
}

async function save(ignoreSpelling: boolean) {
  busy.value = true;
  errors.value = [];
  notice.value = null;
  warnings.value = [];
  const templateId = selectedId.value;
  const { data, error: e } = await client.PUT("/combo-templates/{templateId}", {
    params: { path: { templateId } },
    body: {
      name: name.value,
      route: route.value,
      nproc: nproc.value.trim() || null,
      mem_gb: memGb.value.trim() || null,
      cpu: useCpu.value && cpu.value.trim() ? cpu.value.trim() : null,
      is_default: isDefault.value,
      ignore_spelling: ignoreSpelling,
    },
  });
  busy.value = false;
  if (e) {
    const errs =
      (e as unknown as { error?: { details?: { errors?: TemplateError[] } } })
        .error?.details?.errors ?? [];
    errors.value = errs; // 全量一次展示（一次全报，不逐个）
    return;
  }
  if (data) {
    notice.value = data.notice;
    warnings.value = data.notice.spelling_warnings ?? [];
    // 重拉收敛：is_default 迁移（radio 同事务清其余行）与归一化回显
    const { data: fresh } = await client.GET("/combo-templates");
    if (fresh) {
      templates.value = fresh.templates;
      initialRoute.value = fresh.initial.route;
      const t = fresh.templates.find((x) => x.template_id === templateId);
      if (t) fillForm(t);
    }
  }
}

/** 「保存」：两段式按 token 粒度豁免（§3.3 豁免集＝该批该 reason 的 token 集）——
 *  先不带豁免直存；422 的词典外 token 全部已在会话豁免集时才自动携
 *  ignore_spelling 重试（已豁免 token 跨方案共享免再拦），新 token 仍须
 *  显式点「忽略拼写警告并保存」。 */
async function saveNormal() {
  await save(false);
  if (
    errors.value.length &&
    hasKeywordErrors.value &&
    oovTokensFromErrors(errors.value).every((t) => exemptTokens.value.has(t))
  ) {
    await save(true);
  }
}

/** 「忽略拼写警告并保存」：本批词典外 token 记入豁免集后重试（仅当次落库，
 *  豁免态不落库——重开弹窗重新校验）。 */
function saveWithExemption() {
  for (const t of oovTokensFromErrors(errors.value)) exemptTokens.value.add(t);
  void save(true);
}

const routeInitialHint = computed(() => `清空恢复初始值：${initialRoute.value}`);
</script>

<template>
  <ConfirmModal
    :open="open"
    title="组合流精修模板配置"
    :disabled="loading"
    :loading="busy"
    @close="!busy && emit('close')"
  >
    <div class="ct-body">
      <!-- 顶部一排 5 个矩形方案框（均匀排布，显式数字 1–5 + 配置名 + 默认徽标） -->
      <div class="ct-presets">
        <button
          v-for="t in templates"
          :key="t.template_id"
          type="button"
          class="ct-preset"
          :class="{ 'ct-preset--on': t.template_id === selectedId }"
          @click="selectScheme(t.template_id)"
        >
          <span class="ct-preset-top">
            <span class="ct-num mono">{{ t.template_id }}</span>
            <span v-if="t.is_default" class="ct-badge">默认</span>
          </span>
          <span class="ct-name">{{ t.name }}</span>
        </button>
      </div>

      <!-- 顶部错误清单（422 全量一次报；message 自足中文，reason 枚举
           不透出——仅用于豁免逻辑判定） -->
      <div v-if="errors.length" class="ct-errors" role="alert">
        <p v-for="(err, i) in errors" :key="i" class="ct-error mono">
          {{ err.message }}
        </p>
      </div>

      <!-- 保存成功注记：temp 补齐 / 归一化 / 词典外 token 警告清单 -->
      <div v-if="notice" class="ct-notices" role="status">
        <p v-if="notice.temp_applied" class="ct-note mono">已补齐温度 temperature=298.15</p>
        <p v-if="notice.normalized" class="ct-note mono">已归一化（全小写入库）</p>
        <p v-if="warnings.length" class="ct-warn mono">
          词典外关键词（已放行）：{{ warnings.join("、") }}
        </p>
      </div>

      <!-- 编辑区（选中方案展开） -->
      <div v-if="selected" class="ct-edit">
        <div class="ct-row">
          <label class="ct-field">
            <span class="ct-label mono">配置名（清空恢复「配置{{ selectedId }}」）</span>
            <input v-model="name" type="text" />
          </label>
          <label class="ct-check">
            <input class="ck" type="checkbox" :checked="isDefault" @change="toggleDefault" />
            <span>设为默认</span>
          </label>
        </div>

        <label class="ct-field">
          <span class="ct-label mono" :title="routeInitialHint">
            精修 route（单行、# 开头；清空恢复初始值）
          </span>
          <textarea
            v-model="route"
            rows="2"
            class="mono"
            :class="{ 'ct-invalid': fieldErrors.has('route') }"
            @input="stripNewlines"
          ></textarea>
        </label>

        <div class="ct-row ct-row--link0">
          <div class="ct-field">
            <span class="ct-label mono">%nprocshared</span>
            <input
              v-model="nproc"
              type="text"
              inputmode="numeric"
              placeholder="正整数，如 4"
              :class="{ 'ct-invalid': fieldErrors.has('nproc') }"
            />
            <label class="ct-check ct-check--inline">
              <input class="ck" type="checkbox" :checked="useCpu" @change="toggleUseCpu" />
              <span>指定CPU核心</span>
            </label>
          </div>
          <label class="ct-field">
            <span class="ct-label mono">%mem（GB 数值）</span>
            <input
              v-model="memGb"
              type="text"
              inputmode="decimal"
              :class="{ 'ct-invalid': fieldErrors.has('mem_gb') }"
            />
          </label>
          <label class="ct-field">
            <span class="ct-label mono">%cpu（处理器列表）</span>
            <input
              v-model="cpu"
              type="text"
              :disabled="!useCpu"
              placeholder="0-5 或 0,2,4"
              :class="{ 'ct-invalid': fieldErrors.has('cpu') || fieldErrors.has('link0') }"
            />
          </label>
        </div>
      </div>
      <p v-else-if="loadError" class="ct-error mono">模板读取失败，请关闭后重试</p>
      <p v-else class="ct-loading mono">读取模板 …</p>
    </div>

    <template #foot>
      <button class="btn btn--ghost" type="button" :disabled="busy" @click="emit('close')">
        关闭
      </button>
      <button
        v-if="hasKeywordErrors"
        class="btn btn--secondary"
        type="button"
        :disabled="busy"
        title="豁免仅本次弹窗内生效：跨方案共享，关闭后重新校验"
        @click="saveWithExemption"
      >
        忽略拼写警告并保存
      </button>
      <button
        class="btn btn--primary"
        type="button"
        :data-loading="busy || undefined"
        :disabled="busy || loading || loadError"
        @click="saveNormal"
      >
        {{ busy ? "保存中 …" : "保存" }}
      </button>
    </template>
  </ConfirmModal>
</template>

<style scoped>
.ct-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.ct-presets {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--space-2);
}
/* .preset/.preset--on 选中范式放大（§3.4）：矩形框 + accent 描边选中态。
 * 上下两行布局（数字+徽标 / 配置名）：单行挤不下「配置n+默认」三段 */
.ct-preset {
  appearance: none;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  cursor: pointer;
  min-width: 0;
}
.ct-preset-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-1);
}
.ct-preset--on {
  border-color: var(--accent);
  background: var(--bg-raised);
}
.ct-preset--on .ct-num {
  color: var(--accent);
}
.ct-num {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}
.ct-name {
  font-size: var(--text-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  text-align: left;
}
/* 默认徽标：中性 plain 档（§4.6，不使用状态色） */
.ct-badge {
  font-size: var(--text-xs);
  padding: 0 var(--space-1);
  border-radius: var(--r-sm);
  color: var(--accent);
  border: 1px solid var(--accent-dim);
  flex: none;
}
.ct-errors {
  border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  padding: var(--space-2) var(--space-3);
  display: grid;
  gap: var(--space-1);
}
.ct-error {
  font-size: var(--text-sm);
  color: var(--danger);
}
.ct-notices {
  display: grid;
  gap: var(--space-1);
}
.ct-note {
  font-size: var(--text-sm);
  color: var(--state-succeeded);
}
.ct-warn {
  font-size: var(--text-sm);
  color: var(--warn);
}
.ct-edit {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.ct-row {
  display: flex;
  gap: var(--space-4);
  align-items: flex-end;
}
.ct-row--link0 {
  align-items: flex-start;
}
.ct-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
  min-width: 0;
}
.ct-label {
  font-size: var(--text-sm); /* 文案含中文：不用微标签档、不加字距 */
  color: var(--text-faint);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap; /* 标签行可换行：内联复选框不溢出邻列 */
}
.ct-check {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  cursor: pointer;
  white-space: nowrap;
  flex: none;
}
.ct-check--inline {
  align-self: flex-start;
  padding: 0;
  margin-top: -2px;
}
.ct-check span {
  font-size: var(--text-sm); /* 文案含中文 */
  color: var(--text-secondary);
}
.ct-loading {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
textarea {
  resize: vertical;
  white-space: pre;
}
input:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.ct-invalid {
  border-color: var(--danger);
}
</style>
