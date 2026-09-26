/**
 * useDragSort — 拖拽排序公共组合式（m2-plan §2.4/A3：队列编辑对话框与待执行页
 * 拖拽共用一套实现与锁定/边界判定语义）。仅管理拖源/落点状态与移动计算，
 * 持久化由宿主完成（待执行页 PUT /pending/order 全量原子；队列编辑对话框
 * 本地重排后随保存提交）。位移动效 120ms --ease-std 由宿主样式承载。
 */
import { ref } from "vue";

export type DragId = string | number;

export function useDragSort() {
  const dragId = ref<DragId | null>(null);
  const overId = ref<DragId | null>(null);

  function start(id: DragId, e: DragEvent) {
    dragId.value = id;
    e.dataTransfer?.setData("text/plain", String(id));
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
  }

  function over(id: DragId, e: DragEvent, enabled = true) {
    if (dragId.value == null || !enabled) return;
    overId.value = id;
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
  }

  function leave(id: DragId) {
    if (overId.value === id) overId.value = null;
  }

  /** 计算 from 移动到 to 位置后的新序（原地移动语义，与待执行页一致）；
   *  非法移动（源/落点不在序内或原地）返回 null。 */
  function move(
    ids: DragId[],
    from: DragId,
    to: DragId,
  ): DragId[] | null {
    const src = ids.indexOf(from);
    const dst = ids.indexOf(to);
    if (src < 0 || dst < 0 || src === dst) return null;
    const next = [...ids];
    next.splice(dst, 0, ...next.splice(src, 1));
    return next;
  }

  function end() {
    dragId.value = null;
    overId.value = null;
  }

  return { dragId, overId, start, over, leave, move, end };
}
