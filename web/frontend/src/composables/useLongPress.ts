/**
 * useLongPress — 长按手势组合式（危险操作强化确认）。
 *
 * 逻辑范式：pointerdown（仅主键）启动 RAF 进度回调与到点定时器；
 * pointerup/pointerleave/pointercancel 任一打断即取消并把进度归零；
 * 到点触发 onLongPress，并在捕获阶段拦截紧随其后的 click（防二次提交）；
 * contextmenu 一并阻止（触屏长按系统菜单）。绑定随元素 ref 生灭，
 * 卸载时全量解绑并清理定时器。
 */
import { onBeforeUnmount, watch, type Ref } from "vue";

export interface LongPressOptions {
  /** 长按时长（ms），到点即触发。 */
  duration: number;
  /** 到点触发回调。 */
  onLongPress: () => void;
  /** 进度回调（0~1；取消归零、到点置 1）。 */
  onProgress?: (p: number) => void;
}

export function useLongPress(
  el: Ref<HTMLElement | null>,
  opts: LongPressOptions,
) {
  let timerId: number | null = null;
  let rafId = 0;
  let startTime = 0;
  let triggered = false;

  function cleanup() {
    if (timerId !== null) {
      clearTimeout(timerId);
      timerId = null;
    }
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
  }

  function tick() {
    const p = Math.min((performance.now() - startTime) / opts.duration, 1);
    opts.onProgress?.(p);
    if (p < 1) rafId = requestAnimationFrame(tick);
  }

  function onDown(e: PointerEvent) {
    if (e.button !== 0) return;
    triggered = false;
    startTime = performance.now();
    tick();
    timerId = window.setTimeout(() => {
      cleanup();
      triggered = true;
      opts.onProgress?.(1);
      opts.onLongPress();
    }, opts.duration);
  }

  function onCancel() {
    cleanup();
    opts.onProgress?.(0);
  }

  function prevent(e: Event) {
    e.preventDefault();
  }

  function onClickCapture(e: MouseEvent) {
    if (triggered) {
      e.stopPropagation();
      e.preventDefault();
      triggered = false;
    }
  }

  function bind(target: HTMLElement) {
    target.addEventListener("pointerdown", onDown);
    target.addEventListener("pointerup", onCancel);
    target.addEventListener("pointerleave", onCancel);
    target.addEventListener("pointercancel", onCancel);
    target.addEventListener("contextmenu", prevent);
    target.addEventListener("click", onClickCapture, true);
  }

  function unbind(target: HTMLElement) {
    target.removeEventListener("pointerdown", onDown);
    target.removeEventListener("pointerup", onCancel);
    target.removeEventListener("pointerleave", onCancel);
    target.removeEventListener("pointercancel", onCancel);
    target.removeEventListener("contextmenu", prevent);
    target.removeEventListener("click", onClickCapture, true);
  }

  watch(el, (next, prev) => {
    if (prev) unbind(prev);
    cleanup();
    if (next) bind(next);
  });

  onBeforeUnmount(() => {
    if (el.value) unbind(el.value);
    cleanup();
  });

  return { cancel: onCancel };
}
