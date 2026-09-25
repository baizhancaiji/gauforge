/**
 * 共享标签映射（m1-review2-fix-plan F-07）：历史页与候选页的失败归因
 * 措辞单一来源，同一归因全站措辞一致（信号系统纪律）。
 */

/** 失败/跳过归因 → 中文措辞（契约 cause 枚举）。 */
export const causeLabel: Record<string, string> = {
  manually_stopped: "手动停止",
  program_error: "程序错误",
  external_interrupt: "外部中断",
  predecessor_failed: "前驱失败",
  queue_manually_stopped: "队列停止",
};
