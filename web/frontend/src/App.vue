<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

import ThemeToggle from "@/components/ThemeToggle.vue";

const route = useRoute();

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

// 状态灯排（§3）M0 接 mock 流（C4）；先静态占位。
const lamps = ref({ running: 0, queued: 0, alarm: 0 });
const hasAlarm = ref(false);
</script>

<template>
  <div class="app-frame">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-dot" aria-hidden="true"></span>
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
          <transition name="view" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </main>
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
.brand-dot {
  width: 6px;
  height: 6px;
  border-radius: 1px;
  background: var(--accent);
}
.brand-name {
  font-weight: 600;
  letter-spacing: 0.02em;
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
  transition: background-color 120ms ease, color 120ms ease;
}
.nav-item:hover {
  background: var(--row-hover);
}
.nav-item--active {
  color: var(--text-primary);
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
  width: 7px;
  height: 7px;
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
  font-size: var(--text-xl);
  font-weight: 500;
  line-height: 1.3;
}
.page-no {
  font-size: var(--text-xs);
  color: var(--text-faint);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-5);
}
.lamps {
  display: flex;
  gap: var(--space-4);
}
.lamp {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  transition: opacity 120ms ease;
}
.lamp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.lamp--running .lamp-dot {
  background: var(--state-running);
  animation: breathe 2.4s ease-in-out infinite;
}
.lamp--queued .lamp-dot {
  background: var(--state-staged);
}
.lamp--alarm .lamp-dot {
  background: var(--state-skipped);
}
.lamp--dim {
  opacity: 0.4;
}
@keyframes breathe {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}
</style>