<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import ThemeToggle from "@/components/ThemeToggle.vue";
import { client } from "@/api/client";
import { useEventsStore } from "@/stores/events";

const route = useRoute();
const router = useRouter();
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

// 侧栏 HQ 连接状态行（§5；hq.status 事件 + 快照 hq 字段驱动，M1 真实化）。
const hqText = computed(() => {
  switch (events.hq.state) {
    case "up":
      return "HQ 已连接";
    case "down":
      return "HQ 未连接";
    case "off":
      return "HQ 未启用";
    default:
      return "HQ 连接中";
  }
});

// 侧栏版本行（§3.1）：health 下发带 v 形态直接渲染，前端不加前缀；
// 启动拉取一次，断线重连/服务重启后重拉校对（随强刷机制自然对齐）。
const version = ref("");
async function pullVersion() {
  const { data } = await client.GET("/system/health");
  if (data) {
    version.value = data.version;
    events.markAppVersion(data.version); // 版本基线（强刷轮询判定 version 变化）
  }
}
watch(
  () => events.connection,
  (conn, prev) => {
    if (conn === "open" && prev === "reconnecting") pullVersion();
  },
);

// 更新可用圆点（D5）：available 点亮，done/up_to_date 熄灭，其余相默认灭。
const updateDotOn = computed(() => events.updatePhase === "available");

onMounted(() => {
  pullVersion();
  events.start();
});
</script>

<template>
  <div class="app-frame">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-dot" :data-conn="events.connection" aria-hidden="true"></span>
        <span class="brand-name">
          <span class="brand-line mono">Gaussian 16</span>
          <span class="brand-line mono">管理工作台</span>
        </span>
      </div>

      <!-- 版本行（§3.1）：品牌两行下方，点击（热区含圆点）跳设置页更新卡；
           无导航项形态，hover/focus 微反馈为唯一交互暗示 -->
      <button
        class="version-row"
        type="button"
        :title="version"
        @click="router.push('/settings')"
      >
        <span class="update-dot" :class="{ 'update-dot--on': updateDotOn }" aria-hidden="true"></span>
        <span class="version-text mono">{{ version }}</span>
      </button>

      <nav class="nav">
        <RouterLink
          v-for="item in nav"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          active-class="nav-item--active"
        >
          <span class="nav-main">
            <span class="nav-page mono">{{ item.page }}</span>
            <span class="nav-label">{{ item.label }}</span>
          </span>
          <span class="nav-en">{{ item.en }}</span>
        </RouterLink>
      </nav>

      <div class="hq-status">
        <span class="hq-led" :data-state="events.hq.state" aria-hidden="true"></span>
        <span class="mono hq-text">{{ hqText }}</span>
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
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-2) var(--space-4);
}
/* 磷光青 8px 方块电源灯（§3）：服务在线常亮、断线 danger 闪烁（接 SSE 连接态） */
.brand-dot {
  width: 8px;
  height: 8px;
  margin-top: 6px; /* 与首行「Gaussian 16」视觉居中对齐 */
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
  animation: pulse var(--dur-scan) ease-in-out infinite;
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
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  font-weight: 600;
  color: var(--text-primary);
}

/* 版本行（§3.1）：mono 弱化色装饰从简；点击跳设置页，去按钮化样式 */
.version-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 var(--space-2) var(--space-3);
  padding: 2px var(--space-2);
  padding-left: 16px; /* 与 brand-name 左缘对齐（brand-dot 8px + gap 8px） */
  background: none;
  border: none;
  border-radius: var(--r-sm);
  cursor: pointer;
  color: var(--text-faint);
  transition:
    color var(--dur-fast) var(--ease-std),
    background-color var(--dur-fast) var(--ease-std);
}
.version-row:hover {
  color: var(--text-secondary);
  background: var(--row-hover);
}
.version-row:focus-visible {
  outline: 1px solid var(--accent);
  outline-offset: 1px;
}
.version-text {
  font-size: var(--text-xs); /* 版本号纯拉丁（v 前缀形态），微标签档 */
  overflow: hidden; /* 源码形态 git describe 长串单行截断，title 补全 */
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* D5 accent 圆点：available 点亮、熄灭为中性灰；--dot-size 圆形与
   brand-dot（8px 方形）以位置尺寸区分，不新增颜色语义 */
.update-dot {
  width: var(--dot-size);
  height: var(--dot-size);
  border-radius: 50%;
  background: var(--state-idle);
  transition: background-color var(--dur-fast) var(--ease-std);
}
.update-dot--on {
  background: var(--accent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--accent) 70%, transparent);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  border-top: 1px solid var(--border-hair); /* 导航区与版本行视觉分离（§3.1） */
  padding-top: var(--space-3);
}
/* 导航项（§3，2026-09-27 人为指定调整）：中英上下两行，命中区 --nav-item-height */
.nav-item {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-height: var(--nav-item-height);
  padding: var(--space-1) var(--space-2);
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
.nav-main {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  min-width: 0;
}
.nav-label {
  font-size: var(--text-lg); /* 14px → 18px（2026-09-27 人为指定）：主导航可读性 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nav-en {
  font-size: var(--text-2xs);
  color: var(--text-faint);
  letter-spacing: var(--ls-wide);
}

.hq-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0; /* §3 视口纪律：常驻侧栏底部，不随内容滚出 */
  padding: var(--space-3) var(--space-2) 0;
  border-top: 1px solid var(--border-hair);
  color: var(--text-faint);
}
.hq-led {
  width: var(--dot-size);
  height: var(--dot-size);
  border-radius: 50%;
  background: var(--state-idle);
}
/* 连接三态（hq.status）：up=accent 常亮辉光、down=danger 闪烁、
   off/快照未达=淡化 idle（引擎未启用/演示模式） */
.hq-led[data-state="up"] {
  background: var(--accent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--accent) 70%, transparent);
}
.hq-led[data-state="down"] {
  background: var(--danger);
  animation: pulse var(--dur-scan) ease-in-out infinite;
}
.hq-text {
  font-size: var(--text-sm); /* 文案含中文（已连接/未连接/未启用） */
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
  transition: opacity var(--dur-fast) var(--ease-std);
}
.lamp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.lamp--running .lamp-dot {
  background: var(--state-running);
  box-shadow: 0 0 8px color-mix(in srgb, var(--state-running) 70%, transparent);
  animation: breathe var(--dur-breathe) ease-in-out infinite;
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
    transform var(--dur-toast) var(--ease-glide),
    opacity var(--dur-toast) var(--ease-glide);
}
.toast-leave-active {
  transition:
    transform var(--dur-slide) var(--ease-std),
    opacity var(--dur-slide) var(--ease-std);
}
.toast-enter-from,
.toast-leave-to {
  transform: translateX(28px);
  opacity: 0;
}
</style>