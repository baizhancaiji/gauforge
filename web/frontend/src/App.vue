<script setup lang="ts">
import { computed, onMounted } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

import ThemeToggle from "@/components/ThemeToggle.vue";
import { useEventsStore } from "@/stores/events";

const route = useRoute();
const events = useEventsStore();

const nav = [
  { path: "/candidates", page: "01", label: "候选", en: "CANDIDATES" },
  { path: "/queues", page: "02", label: "队列", en: "QUEUES" },
  { path: "/pending", page: "03", label: "待执行", en: "PENDING" },
  { path: "/executions", page: "04", label: "执行中", en: "EXECUTIONS" },
  { path: "/history", page: "05", label: "历史", en: "HISTORY" },
  { path: "/settings", page: "06", label: "设置", en: "SETTINGS" },
];

const pageLabel = computed(() => route.meta.title ?? "");
const pageEn = computed(() => (route.meta.en as string) ?? "");
const pageNo = computed(() => (route.meta.page as string) ?? "");

// 状态灯排（§3/C4）：由 SSE 事件流驱动（events store 实时计数）。
const lamps = computed(() => events.lamps);
const hasAlarm = computed(() => events.lamps.alarm > 0);

onMounted(() => events.start());
</script>

<template>
  <div class="app-frame">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-dot" :data-conn="events.connection" aria-hidden="true"></span>
        <span class="brand-name mono">g16web</span>
      </div>

      <nav class="nav">
        <RouterLink
          v-for="item in nav"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          active-class="nav-item--active"
        >
          <span class="nav-page mono">{{ item.page }}</span>
          <span class="nav-label">{{ item.label }}</span>
          <span class="nav-en">{{ item.en }}</span>
        </RouterLink>
      </nav>

      <div class="hq-status">
        <span class="hq-led" aria-hidden="true"></span>
        <span class="mono hq-text">HQ 未连接</span>
      </div>
    </aside>

    <div class="main-col">
      <header class="topbar">
        <div class="topbar-title">
          <h1 class="page-title">{{ pageLabel }}</h1>
          <span class="page-no mono">{{ pageNo }} / {{ pageEn }}</span>
        </div>

        <div class="topbar-right">
          <div class="lamps" aria-label="状态灯排">
            <div class="lamp lamp--running">
              <span class="lamp-dot" aria-hidden="true"></span>
              <span class="mono">在跑 {{ lamps.running }}</span>
            </div>
            <div class="lamp lamp--queued" :class="{ 'lamp--dim': !lamps.queued }">
              <span class="lamp-dot" aria-hidden="true"></span>
              <span class="mono">排队 {{ lamps.queued }}</span>
            </div>
            <div class="lamp lamp--alarm" :class="{ 'lamp--dim': !hasAlarm }">
              <span class="lamp-dot" aria-hidden="true"></span>
              <span class="mono">告警 {{ lamps.alarm }}</span>
            </div>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main class="content">
        <RouterView v-slot="{ Component }">
          <!-- 注意：禁用 mode="out-in"。异步路由组件 + out-in 存在竞态，
               旧视图退出后新视图的 enter 偶发不触发，view-enter-from 的
               opacity:0 残留 → 主区空白，刷新才恢复。改为同帧交叉淡入淡出。 -->
          <transition name="view">
            <component :is="Component" />
          </transition>
        </RouterView>
      </main>
    </div>

    <!-- Toast 通知（§4.6：右上滑入，终态通知；skipped 不通知） -->
    <div class="toasts" aria-live="polite">
      <transition-group name="toast">
        <div
          v-for="t in events.toasts"
          :key="t.id"
          class="toast"
          :class="`toast--${t.state}`"
        >
          <span class="bar" aria-hidden="true"></span>
          <span class="msg mono">{{ t.title }}: {{ t.state }}</span>
          <button class="close mono" type="button" @click="events.dismissToast(t.id)">×</button>
        </div>
      </transition-group>
    </div>
  </div>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-2) var(--space-6);
}
/* 磷光青 8px 方块电源灯（§3）：服务在线常亮、断线 danger 闪烁（接 SSE 连接态） */
.brand-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  background: var(--accent);
  box-shadow: 0 0 10px color-mix(in srgb, var(--accent) 80%, transparent);
}
.brand-dot[data-conn="reconnecting"] {
  background: var(--warn);
  box-shadow: none;
}
.brand-dot[data-conn="closed"] {
  background: var(--danger);
  box-shadow: none;
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}
.brand-name {
  font-weight: 600;
  color: var(--text-primary);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}
.nav-item {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-2);
  border-radius: var(--r-md);
  color: var(--text-secondary);
  position: relative;
  transition:
    background-color 120ms var(--ease-std),
    color 120ms var(--ease-std);
}
.nav-item:hover {
  background: var(--row-hover);
}
.nav-item--active {
  color: var(--text-primary);
}
.nav-item--active .nav-label {
  font-weight: 500;
}
.nav-item--active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  border-radius: 1px;
  background: var(--accent);
}
.nav-page {
  color: var(--text-faint);
  font-size: var(--text-xs);
}
.nav-label {
  font-size: var(--text-sm);
}
.nav-en {
  font-size: 10px;
  color: var(--text-faint);
  letter-spacing: var(--ls-wide);
}

.hq-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-2) 0;
  border-top: 1px solid var(--border-hair);
  color: var(--text-faint);
}
.hq-led {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--state-idle);
}
.hq-text {
  font-size: var(--text-xs);
}

.topbar-title {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}
.page-title {
  font-size: var(--text-lg);
  font-weight: 500;
  line-height: 1.5;
}
.page-no {
  font-size: var(--text-xs);
  color: var(--text-faint);
  letter-spacing: var(--ls-wide);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-5);
}
.lamps {
  display: flex;
  gap: var(--space-5);
}
.lamp {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  transition: opacity 120ms var(--ease-std);
}
.lamp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.lamp--running .lamp-dot {
  background: var(--state-running);
  box-shadow: 0 0 8px color-mix(in srgb, var(--state-running) 70%, transparent);
  animation: breathe 2.4s ease-in-out infinite;
}
.lamp--queued .lamp-dot {
  background: var(--state-staged);
}
.lamp--alarm .lamp-dot {
  background: var(--warn);
}
.lamp--dim {
  opacity: 0.4;
}

/* ---- Toast（§4.6）：右上滑入 240ms --ease-glide（全站唯一使用该曲线）---- */
.toasts {
  position: fixed;
  top: 68px;
  right: var(--space-4);
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  pointer-events: none;
}
.toast {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  background: var(--bg-overlay);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-pop);
  padding: 10px 10px 10px var(--space-3);
  min-width: 240px;
  max-width: 340px;
  pointer-events: auto;
  position: relative;
  overflow: hidden;
}
.toast .bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
}
.toast--succeeded .bar {
  background: var(--state-succeeded);
}
.toast--failed .bar {
  background: var(--state-failed);
}
.toast .msg {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--text-primary);
}
.toast .close {
  color: var(--text-faint);
  font-size: var(--text-sm);
  padding: 0 2px;
}
.toast .close:hover {
  color: var(--text-primary);
}
.toast-enter-active {
  transition:
    transform 240ms var(--ease-glide),
    opacity 240ms var(--ease-glide);
}
.toast-leave-active {
  transition:
    transform 200ms var(--ease-std),
    opacity 200ms var(--ease-std);
}
.toast-enter-from,
.toast-leave-to {
  transform: translateX(28px);
  opacity: 0;
}
</style>