<script setup lang="ts">
/**
 * 更新卡（version-update-spec §3.2，v2.1 更新域）：设置页顶部，卡内不渲染标题。
 * - 八态显示状态机随 phase 切换：实时流转由 SSE update.phase/update.progress
 *   驱动（events store），GET /update/status 仅页面进入时恢复现场，不触发重查；
 * - 「检查更新」「立即更新」同行右对齐；按钮可用性矩阵按 §3.5 置灰附文案
 *   （running 在场 / 源码形态 / 流程进行中）；
 * - 下载中显示进度条（左新版本号、右实时速度，KB/s→MB/s 换档）；
 * - 代理通道三选一读写 .update-proxy（与 update.sh 共用配置，保存即时生效）。
 */
import { computed, onMounted, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import { useEventsStore } from "@/stores/events";

type UpdateStatus = components["schemas"]["UpdateStatus"];

const events = useEventsStore();

const status = ref<UpdateStatus | null>(null);
const checking = ref(false);
const applying = ref(false);
const proxySaving = ref(false);
const proxyError = ref("");
/** 409 守卫拒绝等无广播场景的本地文案（phase 翻转即清，恢复服务端真值）。 */
const localMessage = ref<string | null>(null);

// 显示状态源：快照灌 store 后随 SSE 事件流走（多标签页广播联动）。
const phase = computed(() => events.updatePhase);
const inFlight = computed(() =>
  ["downloading", "installing", "restarting"].includes(phase.value),
);
const supported = computed(() => status.value?.supported ?? true);
const progress = computed(() => events.updateProgress);
const targetVersion = computed(
  () => events.updateVersion ?? status.value?.latest_version ?? null,
);

// 立即更新置灰矩阵：源码形态 / running 在场 / 流程进行中（§3.5 文案随置灰附显）
const blockedReason = computed(() => {
  if (!supported.value) return "当前为源码运行模式，请通过 git 更新";
  if (events.lamps.running > 0) return "为保证运行稳定性，任务执行期间禁止更新";
  return "";
});
const applyDisabled = computed(
  () => inFlight.value || blockedReason.value !== "" || checking.value,
);

// 显示状态机（§3.2 表逐行）：installing/restarting 静默等待同一文案
// （后端这两相不携带 message，显示态由前端固定）；轮询 120s 超时如实提示
// （§3.4 回登文案，交还用户手动处置）。
const MSG_RESTARTING = "服务重启中 …";
const MSG_RESTART_TIMEOUT = "服务重启超时，请手动重启后刷新";
const head = computed(() => {
  if (events.updateTimeout) return MSG_RESTART_TIMEOUT;
  if (phase.value === "installing" || phase.value === "restarting")
    return MSG_RESTARTING;
  return localMessage.value ?? events.updateMessage ?? "";
});
// available 文案尾六字替换为「更新说明」链接（文案仍以后端下发为准，防双写漂移）
const RELEASE_NOTE = "查看更新说明";
const availableHead = computed(() => {
  const m = head.value;
  return m.endsWith(RELEASE_NOTE) ? m.slice(0, -RELEASE_NOTE.length) : m;
});
const releaseUrl = computed(
  () =>
    `https://github.com/baizhancaiji/gauforge/releases/tag/${targetVersion.value ?? ""}`,
);

function speedText(bps: number): string {
  if (bps >= 1024 * 1024) return `${(bps / 1024 / 1024).toFixed(1)} MB/s`;
  if (bps >= 1024) return `${(bps / 1024).toFixed(1)} KB/s`;
  return `${Math.round(bps)} B/s`;
}

// 后端统一错误结构 {error: {code, message, details}}（openapi-fetch error 侧）
function errMsg(e: unknown): string {
  return (e as { error?: { message?: string } }).error?.message ?? "操作失败";
}

async function check() {
  localMessage.value = null;
  checking.value = true;
  const { data, error } = await client.POST("/update/check");
  checking.value = false;
  if (error) {
    // 探测失败（502）：后端已翻 failed 相并广播；本地文案兜底 SSE 缺席场景
    localMessage.value = errMsg(error);
    return;
  }
  if (data) events.applyUpdateSnapshot(data);
}

async function apply() {
  localMessage.value = null;
  applying.value = true;
  const { data, error } = await client.POST("/update/apply");
  applying.value = false;
  if (error) {
    // 守卫 409 后端状态机不翻转、无广播；预检 502 有广播——本地文案统一兜底
    localMessage.value = errMsg(error);
    return;
  }
  if (data) events.applyUpdateSnapshot(data);
}

// phase 翻转即清本地文案（SSE 已送达服务端真值）
watch(phase, () => (localMessage.value = null));

// ---- 代理通道三选一（null=直连 ↔ 空文件；默认代理=固定 URL 串，均无尾换行） ----
const DEFAULT_PROXY = "https://v4.gh-proxy.org";
type ProxyMode = "direct" | "default" | "custom";
const proxyMode = ref<ProxyMode>("direct");
const customProxy = ref("");

function syncProxyMode(proxy: string | null | undefined) {
  proxyMode.value =
    proxy == null || proxy === ""
      ? "direct"
      : proxy === DEFAULT_PROXY
        ? "default"
        : "custom";
  if (proxyMode.value === "custom") customProxy.value = proxy ?? "";
}

async function saveProxy(value: string | null) {
  proxySaving.value = true;
  const { data, error } = await client.PUT("/update/proxy", {
    body: { proxy: value },
  });
  proxySaving.value = false;
  if (error) {
    proxyError.value = errMsg(error);
    return;
  }
  if (data) {
    status.value = data;
    syncProxyMode(data.proxy); // 以后端落盘回显为准（直连 ↔ 空内容文件）
  }
}

function onModeChange() {
  proxyError.value = "";
  if (proxyMode.value === "direct") saveProxy(null);
  else if (proxyMode.value === "default") saveProxy(DEFAULT_PROXY);
  // custom：等 URL 输入后经「应用」保存（回车等效）
}

function validUrl(u: string): boolean {
  try {
    const p = new URL(u);
    return p.protocol === "http:" || p.protocol === "https:";
  } catch {
    return false;
  }
}

function applyCustom() {
  const u = customProxy.value.trim();
  if (!validUrl(u)) {
    proxyError.value = "代理 URL 非法，须为 http(s):// 开头的完整地址";
    return;
  }
  saveProxy(u);
}

onMounted(async () => {
  const { data } = await client.GET("/update/status");
  if (!data) return;
  status.value = data;
  events.applyUpdateSnapshot(data); // 页面重进恢复现场（含侧栏圆点），不重查
  syncProxyMode(data.proxy);
});
</script>

<template>
  <section class="update-card">
    <div class="uc-content">
      <!-- 下载中：进度条（左新版本号 / 右实时速度） -->
      <p v-if="phase === 'downloading'" class="progress-row">
        <span class="mono ver">{{ progress?.version || targetVersion || "…" }}</span>
        <span class="progress-track">
          <span
            class="progress-bar"
            :style="{ width: `${progress?.percent ?? 0}%` }"
          ></span>
        </span>
        <span class="mono speed">{{ speedText(progress?.speed_bps ?? 0) }}</span>
      </p>
      <!-- 有更新：文案尾六字替换为「更新说明」链接（新标签页） -->
      <p v-else-if="phase === 'available'" class="uc-line">
        {{ availableHead }}<a class="note-link" :href="releaseUrl" target="_blank" rel="noopener">{{ RELEASE_NOTE }}</a>
      </p>
      <p v-else class="uc-line">{{ head }}</p>

      <!-- 置灰附文案（按钮可用性矩阵） -->
      <p v-if="blockedReason" class="blocked mono">{{ blockedReason }}</p>

      <!-- 代理通道三选一（卡内，保存即时生效） -->
      <div class="uc-proxy">
        <span class="proxy-label mono">代理通道</span>
        <label><input type="radio" value="direct" v-model="proxyMode" :disabled="proxySaving" @change="onModeChange" />直连</label>
        <label><input type="radio" value="default" v-model="proxyMode" :disabled="proxySaving" @change="onModeChange" />默认代理</label>
        <label><input type="radio" value="custom" v-model="proxyMode" :disabled="proxySaving" @change="onModeChange" />自定义</label>
        <template v-if="proxyMode === 'custom'">
          <input
            v-model="customProxy"
            class="proxy-input mono"
            placeholder="https://"
            @keydown.enter="applyCustom"
          />
          <button class="btn btn--ghost" type="button" :disabled="proxySaving" @click="applyCustom">应用</button>
        </template>
        <span v-if="proxyError" class="proxy-err">{{ proxyError }}</span>
      </div>
    </div>

    <div class="uc-actions">
      <button
        class="btn btn--secondary"
        type="button"
        :disabled="checking || inFlight"
        @click="check"
      >
        {{ checking ? "检查中 …" : "检查更新" }}
      </button>
      <button
        class="btn btn--primary"
        type="button"
        :disabled="applyDisabled"
        @click="apply"
      >
        {{ applying ? "提交中 …" : "立即更新" }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.update-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  padding: var(--space-3) var(--space-4);
}
.uc-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
  flex: 1;
}
.uc-line {
  font-size: var(--text-sm);
  color: var(--text-primary);
}
.note-link {
  color: var(--accent);
}
.note-link:hover {
  text-decoration: underline;
}
.blocked {
  font-size: var(--text-sm);
  color: var(--warn);
}

/* 进度条（§3.2）：左新版本号、右实时速度 */
.progress-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.progress-row .ver {
  font-size: var(--text-sm);
  color: var(--text-primary);
  flex-shrink: 0;
}
.progress-track {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--bg-inset);
  overflow: hidden;
}
.progress-bar {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--accent);
  transition: width 240ms var(--ease-std);
}
.progress-row .speed {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  min-width: 64px;
  text-align: right;
  flex-shrink: 0;
}

/* 代理通道三选一 */
.uc-proxy {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.proxy-label {
  font-size: var(--text-sm); /* 「代理通道」含中文（混排纪律 1），微标签档禁用 */
  color: var(--text-faint);
}
.uc-proxy label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  cursor: pointer;
}
.uc-proxy input[type="radio"] {
  accent-color: var(--accent);
}
.proxy-input {
  width: 220px;
  height: var(--control-height-sm);
  /* 覆写全局 6px 垂直 padding：24px 定高下内容盒仅剩 ≈10px，中文行盒 12px 被裁 */
  padding: 0 var(--space-2);
}
.proxy-err {
  font-size: var(--text-sm);
  color: var(--danger);
}

.uc-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}
</style>
