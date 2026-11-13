/**
 * 跨组件共享常量（单一来源，防字面量跨文件漂移，3.5.0 审查修复）。
 */

/** 弹窗最小宽度 = 现默认档（tokens --modal-width: 560px），默认宽度不变 */
export const MODAL_WIDTH_MIN = 560;

/** 弹窗视口边距：两侧各留 ≥24px（ConfirmModal min() 表达式消费） */
export const MODAL_VIEWPORT_MARGIN = 48;
