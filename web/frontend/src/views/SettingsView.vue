<script setup lang="ts">
/**
 * 06 设置（m0-frontend-design §5 · 表单型限宽 880px；m1-plan C7 真实化）
 * 启动级只读区（锁定 + 值 mono）在上，运行级分组表单在下；
 * 每项带中性生效语义徽标（§4.6：即时/即时且追溯/新任务生效/重启生效，plain 档）；
 * 保存后按实际变更提示（on_restart 项琥珀提示条，中文名经 key→description
 * 映射）；席位上限调小弹「将自队尾挤出」确认（挤出语义：只挤窗口未触及
 * 席位、在跑不追溯）。参数名/env 名不展示（A-11：面向用户只留必要解释）。
 */
import { computed, onMounted, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";
import UpdateCard from "@/components/UpdateCard.vue";
import { useEventsStore } from "@/stores/events";

type SettingsResponse = components["schemas"]["SettingsResponse"];
type SettingItem = components["schemas"]["SettingItem"];
type EffectKind = components["schemas"]["EffectKind"];

const settings = ref<SettingsResponse | null>(null);
const form = ref<Record<string, string>>({});
/** 载入时的原始值（判断实际变更项）。 */
const original = ref<Record<string, string>>({});
const saving = ref(false);
const saved = ref<{ ok: boolean; msg: string } | null>(null);
const errors = ref<Record<string, string>>({});
/** 实际变更且 on_restart 的 key（保存后琥珀提示条）。 */
const restartKeys = ref<string[]>([]);
const shrink = ref<{ from: number; to: number } | null>(null);

const events = useEventsStore();

/**
 * 实际可挤席位数（m1-acceptance §1.3 文案精度修复）：与后端
 * apply_capacity_limit 同口径——超限幅度与未锁定（窗口未触及）席位数
 * 取小，锁定席位在跑不追溯（可临时超限）。自 pending 快照实时取数
 * （SSE 随席位变化推送），确认前席位变动时计数跟随更新。
 */
const squeezeCount = computed(() => {
  if (!shrink.value) return 0;
  const seats = events.pending?.seats ?? [];
  const unlocked = seats.filter((s) => !s.locked).length;
  return Math.min(Math.max(0, seats.length - shrink.value.to), unlocked);
});

const effectLabel: Record<EffectKind, string> = {
  immediate: "即时",
  immediate_retroactive: "即时且追溯",
  new_submissions: "新任务生效",
  on_restart: "重启生效",
};

const runtime = computed(() => settings.value?.runtime ?? []);
const startup = computed(() => settings.value?.startup ?? []);
const seatLimitItem = computed(() =>
  runtime.value.find((s) => s.key === "pending_seat_limit"),
);

function rangeText(s: SettingItem): string {
  if (!s.range) return "";
  if (s.range.enum?.length) return s.range.enum.join(" / ");
  const min = s.range.min ?? "—";
  const max = s.range.max ?? "—";
  return `${min}–${max}`;
}

/** 枚举值域（string 型参数载体，如 update_check_interval 四档）→ 下拉渲染。 */
function enumOf(s: SettingItem): string[] {
  return s.range?.enum ?? [];
}

function initForm(items: SettingItem[]) {
  for (const s of items) {
    form.value[s.key] = String(s.value ?? "");
    original.value[s.key] = String(s.value ?? "");
  }
}

onMounted(async () => {
  const { data } = await client.GET("/settings");
  if (data) {
    settings.value = data;
    initForm(data.runtime);
  }
});

// settings.updated（多标签页同步，sse.md §2）：无未保存修改时静默重拉；
// 有编辑中的输入则不动表单（保存时以表单为准，成功后由响应收敛）。
watch(() => events.dirty.settings, async () => {
  const { data } = await client.GET("/settings");
  if (!data) return;
  settings.value = data;
  const untouched = Object.keys(form.value).every(
    (k) => form.value[k] === original.value[k],
  );
  if (untouched) initForm(data.runtime);
});

function valueFor(s: SettingItem): number | string | boolean {
  const v = form.value[s.key] ?? "";
  if (s.value_type === "integer" || s.value_type === "number") return Number(v);
  if (s.value_type === "boolean") return v === "true";
  return v;
}

async function requestSave() {
  saved.value = null;
  errors.value = {};
  restartKeys.value = [];

  // 席位上限调小 → 挤出确认（C7：将自队尾挤出，在跑不追溯）。
  const limitItem = seatLimitItem.value;
  if (limitItem && form.value[limitItem.key] !== original.value[limitItem.key]) {
    const from = Number(original.value[limitItem.key]);
    const to = Number(form.value[limitItem.key]);
    if (Number.isFinite(to) && to < from) {
      shrink.value = { from, to };
      return;
    }
  }
  await doSave();
}

async function doSave() {
  shrink.value = null;
  saving.value = true;
  const body: Record<string, unknown> = {};
  runtime.value.forEach((s) => {
    body[s.key] = valueFor(s);
  });
  const { data, error } = await client.PUT("/settings", { body: { values: body } });
  saving.value = false;
  if (error) {
    const detail = (
      error as unknown as {
        error?: { message?: string; details?: { errors?: { key: string; reason: string }[] } };
      }
    ).error;
    if (detail?.details?.errors?.length) {
      saved.value = { ok: false, msg: "保存失败" };
      detail.details.errors.forEach((d) => (errors.value[d.key] = d.reason));
    } else {
      saved.value = { ok: false, msg: detail?.message ?? "保存失败" };
    }
    return;
  }
  if (data) {
    settings.value = data;
    initForm(data.runtime);
  }
  // 实际变更且 on_restart 的项（保存前对比原始值）→ 重启提示条。
  restartKeys.value = runtime.value
    .filter((s) => s.effect === "on_restart" && form.value[s.key] !== original.value[s.key])
    .map((s) => s.key);
  saved.value = { ok: true, msg: "设置已保存" };
}

/** 重启提示条显示中文参数名（key→description 映射，A-11）。 */
const restartLabels = computed(() =>
  restartKeys.value.map(
    (k) => runtime.value.find((s) => s.key === k)?.description ?? k,
  ));
</script>

<template>
  <div class="settings">
    <div v-if="settings" class="s-wrap">
      <!-- 更新卡（§3.2）：置顶，无标题，左内容右按钮 -->
      <UpdateCard />

      <!-- 启动级只读（锁定 + 值 mono；§3.7 两项水平一行两列） -->
      <section class="group">
        <h2 class="group-title mono">启动级参数</h2>
        <div class="reads">
          <dl v-for="s in startup" :key="s.key" class="read">
            <dt>
              <span class="lock" aria-hidden="true">▪</span>
              {{ s.description }}
            </dt>
            <dd class="mono val">{{ s.value }}</dd>
          </dl>
        </div>
      </section>

      <!-- 运行级表单 -->
      <section class="group">
        <h2 class="group-title mono">运行级参数</h2>
        <div class="form-grid">
          <div v-for="s in runtime" :key="s.key" class="field" :class="{ 'has-err': errors[s.key] }">
            <label :for="s.key">{{ s.description }}</label>
            <select
              v-if="enumOf(s).length"
              :id="s.key"
              v-model="form[s.key]"
            >
              <option v-for="opt in enumOf(s)" :key="opt" :value="opt">{{ opt }}</option>
            </select>
            <input
              v-else
              :id="s.key"
              :type="s.value_type === 'integer' || s.value_type === 'number' ? 'number' : 'text'"
              v-model="form[s.key]"
              :step="s.value_type === 'number' ? 'any' : '1'"
            />
            <p class="hint">
              <span v-if="rangeText(s)" class="range">{{ enumOf(s).length ? "取值" : "范围" }} {{ rangeText(s) }}</span>
              <!-- 生效语义：中性 plain 徽标（§4.6）并入 hint 行（1080p 一屏预算） -->
              <span class="eff mono">{{ effectLabel[s.effect] }}</span>
            </p>
            <p v-if="errors[s.key]" class="err mono">值越界或非法：{{ errors[s.key] }}</p>
          </div>
        </div>
      </section>

      <div class="savebar">
        <button
          class="btn btn--primary"
          type="button"
          :data-loading="saving || undefined"
          :disabled="saving"
          @click="requestSave"
        >
          {{ saving ? "保存中 …" : "保存设置" }}
        </button>
        <span v-if="saved" class="saved mono" :class="saved.ok ? 'ok' : 'bad'">
          {{ saved.msg }}
        </span>
        <!-- 重启提示条（琥珀纪律：保存条重启提示；仅实际变更项，显中文参数名） -->
        <span v-if="restartKeys.length" class="restart mono">
          ⚠ 以下修改需重启 g16web 后生效：{{ restartLabels.join("、") }}
        </span>
      </div>
    </div>
    <p v-else class="loading mono">读取设置 …</p>

    <!-- 席位上限调小 → 挤出确认（C7） -->
    <ConfirmModal
      :open="shrink != null"
      title="确认收缩席位上限"
      confirm-text="确认收缩"
      :loading="saving"
      @confirm="doSave"
      @close="shrink = null"
    >
      <p class="confirm-line">
        在途席位上限由 <span class="mono strong">{{ shrink?.from }}</span> 调整为
        <span class="mono strong">{{ shrink?.to }}</span>
        <template v-if="squeezeCount > 0">
          — 将自队尾挤出 <span class="mono strong">{{ squeezeCount }}</span>
          个席位（窗口触及席位除外，在跑不追溯），被挤出的任务将退回候选列表
        </template>
        <template v-else>
          — 当前在途席位未超新上限，暂不挤出席位（此后超出时自队尾挤出，窗口触及席位除外，在跑不追溯）
        </template>
      </p>
    </ConfirmModal>
  </div>
</template>

<style scoped>
.settings {
  max-width: 880px;
}
.s-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-3); /* 1080p 一屏预算（§3.7）：更新卡 + 两卡 + 保存条收敛 */
}
.group {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  padding: var(--space-4);
}
.group-title {
  font-size: var(--text-sm);
  font-weight: 500; /* 文案含中文，不加字距 */
  color: var(--text-faint);
  margin-bottom: var(--space-2);
}
/* 启动级只读：两项水平一行两列（§3.7） */
.reads {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}
.read dt {
  font-size: var(--text-sm); /* 释义含中文（混排纪律 1），不用微标签档 */
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.lock {
  font-size: var(--text-2xs); /* 锁定刻度符号（▪） */
  color: var(--text-faint);
}
.read .val {
  font-size: var(--text-sm);
  color: var(--text-primary);
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-top: 2px;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
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
.field input,
.field select {
  height: var(--control-height);
}
.hint {
  font-size: var(--text-sm);
  line-height: 1.25; /* 1080p 一屏预算：11 项两列 hint 行高收敛 */
  color: var(--text-secondary);
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.hint .range {
  color: var(--text-faint);
}
/* 生效语义徽标：中性 plain 档（§4.6，不使用状态色）；hint 行内联（省高） */
.eff {
  font-size: var(--text-sm); /* 生效语义含中文 */
  padding: 0 var(--space-2);
  border-radius: var(--r-sm);
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--text-secondary) 10%, transparent);
}
.field.has-err input {
  border-color: var(--danger);
}
.err {
  font-size: var(--text-sm);
  color: var(--danger);
}
.savebar {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-wrap: wrap;
}
.saved {
  font-size: var(--text-sm);
}
.saved.ok {
  color: var(--state-succeeded);
}
.saved.bad {
  color: var(--danger);
}
.restart {
  font-size: var(--text-sm);
  color: var(--warn);
}
.loading {
  color: var(--text-faint);
  font-size: var(--text-sm);
}
.confirm-line {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.confirm-line .strong {
  color: var(--text-primary);
}
</style>
