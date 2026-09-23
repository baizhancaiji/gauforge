<template>
  <div class="page empty-state">
    <span class="empty-glyph mono">▥</span>
    <p class="empty-text">暂无待执行席位</p>
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  gap: var(--space-3);
  border: 1px dashed var(--border-hair);
  border-radius: var(--r-lg);
  text-align: center;
}
.empty-glyph {
  font-size: var(--text-xl);
  color: var(--text-faint);
}
.empty-text {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-faint);
}
</style>