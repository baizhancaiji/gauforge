<script setup lang="ts">
/** 通用空态（m0-frontend-design §4.6）：极简刻度符号 + mono 短句，无插画。 */
defineProps<{ glyph?: string; text: string }>();
</script>

<template>
  <div class="empty">
    <div class="frame">
      <span class="glyph mono" aria-hidden="true">{{ glyph ?? "▮" }}</span>
      <p class="text mono">{{ text }}</p>
    </div>
  </div>
</template>

<style scoped>
.empty {
  display: grid;
  place-items: center;
  min-height: 320px;
}
.frame {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8) var(--space-10);
  border: 1px dashed var(--border-hair);
  border-radius: var(--r-lg);
}
.glyph {
  font-size: var(--text-xl);
  color: var(--text-faint);
}
.text {
  font-size: var(--text-sm);
  color: var(--text-faint);
}
</style>