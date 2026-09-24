<script setup lang="ts">
/**
 * 06 设置（m0-frontend-design §5 · 表单型，lim-width 880px）
 * 启动级只读区在上，运行级分组表单在下；每项带生效语义徽标；
 * 数据驱动渲染（读 GET /settings 元数据），保存调 PUT（全有或全无，422 逐项报错）。
 */
import { computed, onMounted, ref } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";

type SettingsResponse = components["schemas"]["SettingsResponse"];
type SettingItem = components["schemas"]["SettingItem"];
type EffectKind = components["schemas"]["EffectKind"];

const settings = ref<SettingsResponse | null>(null);
const form = ref<Record<string, string>>({});
const saving = ref(false);
const saved = ref<{ ok: boolean; msg: string } | null>(null);
const errors = ref<Record<string, string>>({});

const effectLabel: Record<EffectKind, string> = {
  immediate: "即时",
  immediate_retroactive: "即时且追溯",
  new_submissions: "新任务生效",
  on_restart: "重启生效",
};

const runtime = computed(() => settings.value?.runtime ?? []);
const startup = computed(() => settings.value?.startup ?? []);
const pendingRestart = computed(() =>
  runtime.value.filter((s) => s.effect === "on_restart").map((s) => s.key),
);

function initForm(s: SettingItem) {
  form.value[s.key] = String(s.value ?? "");
}

onMounted(async () => {
  const { data } = await client.GET("/settings");
  if (data) {
    settings.value = data;
    data.runtime.forEach(initForm);
  }
});

function valueFor(s: SettingItem): number | string | boolean {
  const v = form.value[s.key] ?? "";
  if (s.value_type === "integer" || s.value_type === "number") return Number(v);
  if (s.value_type === "boolean") return v === "true";
  return v;
}

async function save() {
  saving.value = true;
  saved.value = null;
  errors.value = {};
  const body: Record<string, unknown> = {};
  runtime.value.forEach((s) => {
    body[s.key] = valueFor(s);
  });
  const { data, error } = await client.PUT("/settings", { body: { values: body } });
  saving.value = false;
  if (error) {
    saved.value = { ok: false, msg: (error as { error: { message: string } }).error?.message ?? "保存失败" };
    const details = (error as { error?: { details?: { errors?: { key: string; reason: string }[] } } }).error?.details;
    if (details?.errors) {
      details.errors.forEach((d) => (errors.value[d.key] = d.reason));
    }
    return;
  }
  if (data) {
    settings.value = data;
    data.runtime.forEach(initForm);
  }
  saved.value = { ok: true, msg: "设置已保存" };
}
</script>

<template>
  <div class="settings">
    <div
      v-if="settings"
      :key="settings ? 'form' : 'loading'"
      class="s-wrap"
    >
      <!-- 启动级只读 -->
      <section class="group">
        <h2 class="group-title mono">启动级参数</h2>
        <div class="reads">
          <dl v-for="s in startup" :key="s.key" class="read">
            <dt class="mono">
              <span class="lock" aria-hidden="true">🔒</span>
              {{ s.key }}
            </dt>
            <dd class="mono val">{{ s.value }}<span class="env mono">{{ s.env_var }}</span></dd>
            <dd class="note mono">{{ s.description }}</dd>
          </dl>
        </div>
      </section>

      <!-- 运行级表单 -->
      <section class="group">
        <h2 class="group-title mono">运行级参数</h2>
        <div class="form-grid">
          <div v-for="s in runtime" :key="s.key" class="field" :class="{ 'has-err': errors[s.key] }">
            <label class="mono" :for="s.key">{{ s.key }}</label>
            <input
              :id="s.key"
              :type="s.value_type === 'integer' || s.value_type === 'number' ? 'number' : 'text'"
              v-model="form[s.key]"
              :step="s.value_type === 'number' ? 'any' : '1'"
            />
            <p class="hint mono">
              {{ s.description }}
              <span class="eff mono">{{ effectLabel[s.effect] }}</span>
            </p>
            <p v-if="errors[s.key]" class="err mono">值越界或非法：{{ errors[s.key] }}</p>
          </div>
        </div>
      </section>

      <div class="savebar">
        <button class="btn-primary mono" type="button" :disabled="saving" @click="save">
          {{ saving ? "保存中 …" : "保存" }}
        </button>
        <span v-if="saved" class="saved-mono" :class="saved.ok ? 'ok' : 'bad'">
          {{ saved.msg }}
        </span>
      </div>

      <p v-if="pendingRestart.length" class="restart mono">
        以下项保存后需重启生效：{{ pendingRestart.join("、") }}
      </p>
    </div>
    <p v-else class="loading mono">读取设置 …</p>
  </div>
</template>

<style scoped>
.settings {
  max-width: 880px;
}
.s-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}
.group {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-lg);
  background: var(--bg-raised);
  padding: var(--space-5);
}
.group-title {
  font-size: var(--text-sm);
  font-weight: 600;
  letter-spacing: var(--ls-micro);
  color: var(--text-faint);
  margin-bottom: var(--space-4);
}
.reads {
  display: grid;
  gap: var(--space-4);
}
.read dt {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.lock {
  font-size: 10px;
  filter: grayscale(1);
}
.read .val {
  font-size: var(--text-sm);
  color: var(--text-primary);
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-top: 2px;
}
.read .env {
  font-size: var(--text-xs);
  color: var(--text-faint);
}
.read .note {
  font-size: var(--text-xs);
  color: var(--text-faint);
  margin-top: 2px;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.field label {
  font-size: var(--text-sm);
  color: var(--text-primary);
}
.field input {
  height: 34px;
}
.hint {
  font-size: var(--text-xs);
  color: var(--text-faint);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.eff {
  padding: 1px 6px;
  border-radius: var(--r-sm);
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
}
.field.has-err input {
  border-color: var(--danger);
}
.err {
  font-size: var(--text-xs);
  color: var(--danger);
}
.savebar {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
.btn-primary {
  height: 32px;
  padding: 0 var(--space-5);
  background: var(--accent);
  color: var(--accent-ink);
  border-radius: var(--r-md);
  font-size: var(--text-sm);
  font-weight: 500;
  transition: background-color 120ms ease;
}
.btn-primary:hover:not(:disabled) {
  background: var(--accent-dim);
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.saved-mono {
  font-size: var(--text-xs);
}
.saved-mono.ok {
  color: var(--state-succeeded);
}
.saved-mono.bad {
  color: var(--danger);
}
.restart {
  font-size: var(--text-xs);
  color: var(--warn);
}
.loading {
  color: var(--text-faint);
  font-size: var(--text-sm);
}
@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>