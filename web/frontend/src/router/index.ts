import { createRouter, createWebHashHistory } from "vue-router";

// M0 六页路由（§5 页面归并四种原型）。hash 模式适配后端静态挂载任意前缀。
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", redirect: "/candidates" },
    {
      path: "/candidates",
      name: "candidates",
      component: () => import("@/views/CandidatesView.vue"),
      meta: { page: "01", title: "候选任务", en: "CANDIDATES" },
    },
    {
      path: "/queues",
      name: "queues",
      component: () => import("@/views/QueuesView.vue"),
      meta: { page: "02", title: "队列", en: "QUEUES" },
    },
    {
      path: "/pending",
      name: "pending",
      component: () => import("@/views/PendingView.vue"),
      meta: { page: "03", title: "待执行", en: "PENDING" },
    },
    {
      path: "/executions",
      name: "executions",
      component: () => import("@/views/ExecutionsView.vue"),
      meta: { page: "04", title: "执行中", en: "EXECUTIONS" },
    },
    {
      path: "/history",
      name: "history",
      component: () => import("@/views/HistoryView.vue"),
      meta: { page: "05", title: "历史", en: "HISTORY" },
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("@/views/SettingsView.vue"),
      meta: { page: "06", title: "设置", en: "SETTINGS" },
    },
  ],
});

export default router;