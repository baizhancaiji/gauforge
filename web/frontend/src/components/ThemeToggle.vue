<script setup lang="ts">
import { onMounted, ref } from "vue";

// 明暗主题切换（§3/Q2）：默认暗色，localStorage 记忆。
const root = document.documentElement;
const isLight = ref(localStorage.getItem("g16web-theme") === "light");

function apply() {
  root.dataset.theme = isLight.value ? "light" : "dark";
  localStorage.setItem("g16web-theme", isLight.value ? "light" : "dark");
}
function toggle() {
  isLight.value = !isLight.value;
  apply();
}
onMounted(apply);
</script>

<template>
  <button class="theme-toggle mono" type="button" @click="toggle">
    <span>{{ isLight ? "◑ 暗色" : "◐ 亮色" }}</span>
  </button>
</template>

<style scoped>
.theme-toggle {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  height: 28px;
  padding: 0 var(--space-3);
  background: none;
  transition: border-color 120ms ease, color 120ms ease;
}
.theme-toggle:hover {
  border-color: var(--accent);
  color: var(--text-primary);
}
</style>