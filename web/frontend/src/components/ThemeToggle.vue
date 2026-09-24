<script setup lang="ts">
import { onMounted, ref } from "vue";

// 明暗主题切换（§3）：默认暗色，localStorage 记忆；瞬时切换、无过渡（§6）。
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
  <button class="btn btn--secondary theme-toggle mono" type="button" @click="toggle">
    <span>{{ isLight ? "◑ 暗色" : "◐ 亮色" }}</span>
  </button>
</template>

<style scoped>
.theme-toggle {
  height: 28px;
  padding: 0 var(--space-3);
  font-size: var(--text-xs);
}
</style>
