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

/** 队列状态 → 中文措辞（契约 state 枚举；m0-frontend-design §4.1 队列页属性列
 *  2026-09-27 人为指定统一中文，四态中文名同 §4.1）。原枚举保留为内部信号
 *  （chip 类名 chip--<state>）。 */
export const queueStateLabel: Record<string, string> = {
  unsubmitted: "未提交",
  submitted: "已提交",
  executing: "执行中",
  completed: "已完成",
};

/** 任务状态 → 中文措辞（契约 state 枚举；队列页展开区成员行显示用）。
 *  staged 措辞与待执行页既有覆盖一致（等待）。 */
export const taskStateLabel: Record<string, string> = {
  staged: "等待",
  running: "在跑",
  succeeded: "成功",
  failed: "失败",
  skipped: "跳过",
  archived: "已归档",
};

/** 队列结束原因 → 中文措辞（契约 finish_reason 枚举）。manually_stopped 与
 *  causeLabel 手动停止同措辞；原枚举保留为内部信号（单元格 data-finish-reason）。 */
export const finishReasonLabel: Record<string, string> = {
  success: "成功",
  abort_on_failure: "失败中止",
  finished_with_failures: "带失败完成",
  manually_stopped: "手动停止",
};
