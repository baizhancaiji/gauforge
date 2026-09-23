<template>
  <div class="page">
    <!-- C3 将按设计规范 §5 填充候选列表 + 预览卡 -->
    <div class="empty-state">
      <span class="empty-glyph mono">⌗</span>
      <p class="empty-text">暂无候选任务 · 导入 .gjf 文件后显示于此</p>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  border: 1px dashed var(--border-hair);
  border-radius: var(--r-lg);
  padding: var(--space-12) var(--space-10);
  max-width: 420px;
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