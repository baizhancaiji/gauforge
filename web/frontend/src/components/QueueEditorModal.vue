<script lang="ts">
/** 成员行视图（创建态来自候选行；编辑态名称经 Queue.members，归因经 last_failure 交叉）。
 *  置于普通 script 块：script setup 内 export 会引发模块初始化 ReferenceError
 *  （对话框 chunk 加载即崩溃，D1 走查实测；vue-tsc/vite build 均不拦截）。 */
export interface MemberRow {
  id: number;
  /** 创建态来自候选行；编辑态来自 Queue.members（契约自带成员明细） */
  filename?: string;
  title?: string | null;
  /** 失败归因交叉（Queue.last_failure.members，编辑/只读态） */
  state?: string;
  cause?: string | null;
}

/**
 * Link0 符号引用行解析/改写（m4-plan §4.9 C5「接续前置 chk」勾选的落盘工具）。
 * 解析规则与后端 dependencies.parse_link0_refs 同源：跳过前导空行/!注释后的
 * 连续 % 行，keyword 大小写不敏感；此处仅识别 `%oldchk=@task:<id>` 精确形态
 * （勾选只承载 %oldchk 只读形态，续用形态 `%chk=@task:id` 无前端生成入口）。
 */
export function oldChkTaskRefTargets(lines: string[]): number[] {
  const targets: number[] = [];
  let i = 0;
  while (i < lines.length && (!lines[i].trim() || lines[i].trimStart().startsWith("!"))) i++;
  while (i < lines.length && lines[i].trimStart().startsWith("%")) {
    const m = /^%oldchk\s*=\s*@task:(\d+)$/i.exec(lines[i].trim());
    if (m) targets.push(Number(m[1]));
    i++;
  }
  return targets;
}

/** 移除指向 target 的 `%oldchk=@task:<target>` 行（精确撤销勾选写入）。 */
export function removeOldChkTaskRef(lines: string[], target: number): string[] {
  return lines.filter(
    (l) => !new RegExp(`^%oldchk\\s*=\\s*@task:${target}$`, "i").exec(l.trim()),
  );
}
</script>

<script setup lang="ts">
/**
 * QueueEditorModal — 队列编辑对话框（m2-plan §2.2/§2.4/§4.3 C2；创建/编辑共用）。
 * 布局（m0-frontend-design §4.6 定稿，复用 ConfirmModal 弹层基础）：顶部队列名
 * 输入（创建默认 yyyymmddhhmmss 时间戳可改；创建态不渲染队列 id 字段——id
 * 保存后由后端生成，编辑/只读态只读展示真实 id，2026-09-27 计划外人为修正
 * 去除「保存后生成」占位注记）；中部成员列表（任务 id/文件名/title，「-」
 * 移除剩 1 禁用、拖动排序走 usePointerSort 指针跟手动效 --dur-drag）；「自动
 * 跳过失败任务」toggle
 * 开关；底部「取消」/「保存」（primary，每视图至多一个）/「直接提交」
 * （secondary）。
 * 状态分级（m2-plan §2.2 矩阵）：unsubmitted 全量可编辑；submitted 仅成员
 * （改名/开关 409，A2 决策点 2/9——禁用并注明）；executing/completed 只读详情。
 * 「直接提交」= 保存 + submit 链式；submit 失败时队列保留 unsubmitted，展示
 * 原因引导队列页重试；提交响应 normalized=true 显「已自动规范化」中性注记。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import ConfirmModal from "@/components/ConfirmModal.vue";
import StateChip from "@/components/StateChip.vue";
import { usePointerSort } from "@/composables/usePointerSort";
import { MODAL_WIDTH_MIN, MODAL_VIEWPORT_MARGIN } from "@/constants";
import { fmtTaskId } from "@/utils/format";
import { causeLabel } from "@/utils/labels";

type Queue = components["schemas"]["Queue"];

const props = defineProps<{
  open: boolean;
  mode: "create" | "edit" | "readonly";
  /** edit/readonly 模式的队列数据 */
  queue?: Queue | null;
  /** create 模式的待组成员（候选行） */
  initialMembers?: MemberRow[];
  /** create 预填队列名（留空用时间戳默认） */
  initialName?: string;
}>();

const emit = defineEmits<{ close: []; saved: [queue: Queue]; submitted: [] }>();

const readonly = computed(() => props.mode === "readonly");
/** submitted 态仅成员可改（改名/开关 409 前置禁用，A2 决策点 2/9）。 */
const memberOnly = computed(() => props.queue?.state === "submitted");
/** executing 只读详情附跨页引导（设计 §5：未执行成员移除属席位端点能力）。 */
const executingHint = computed(() => props.queue?.state === "executing");

const name = ref("");
const skipFailed = ref(false);
const members = ref<MemberRow[]>([]);
const busy = ref(false);
const error = ref<string | null>(null);
/** 成功注记（含 normalized 规范化提示；提交成功后锁定输入等待关闭） */
const note = ref<string | null>(null);
const done = ref(false);
/** B8 G12：队列提交响应的非阻断 warnings（逐条附 task_id，琥珀档展示） */
const submitWarnings = ref<components["schemas"]["Warning"][]>([]);

// ---------- 依赖勾选（m4-plan §4.9 C5「接续前置 chk」） ----------
/** per-member 勾选状态：打开对话框时拉取成员预览初始化。
 *  original=写盘前基线（DAG 校验失败回滚用）；initTarget=打开时已含的
 *  %oldchk=@task:<前驱> 引用目标（按加载时顺序判定，重排不重算——
 *  重排不改既有 id 引用，仅勾选动作过的成员按保存时位置写入）；
 *  dirty=本会话勾选动作标记（uncheck→重排→recheck 等序列以动作为准，
 *  不以「checked 与初值相等」判定——否则重排后复勾会跳过持久化，
 *  UI title 显示新前驱而文件引用残留旧前驱）。 */
interface LinkState {
  original: string[];
  baseline: string[];
  initTarget: number | null;
  checked: boolean;
  dirty: boolean;
  /** 预览不可达（如输入解析失败）：不渲染可用勾选（禁用+提示） */
  available: boolean;
  /** B9 G13 裁决⑤：成员输入的核验警告预显（任务级归属，打开时现算自
   *  preview.warnings；available=false 时为空，改显占位提示） */
  warnings: components["schemas"]["Warning"][];
}
const linkStates = ref<Map<number, LinkState>>(new Map());
const linksReady = ref(false);
/** DAG 校验错误逐成员映射（taskId → 提示文案；行加红描边 + 错误清单区） */
const depErrors = ref<Map<number, string>>(new Map());

const linkEditable = computed(() => !readonly.value && !memberOnly.value && !done.value);

/** 成员行勾选框 title：接续当前序列前置成员（保存时按位置生成引用）；
 *  预览不可达（available=false）时明确提示不可用原因。 */
function linkTitle(i: number): string {
  const m = members.value[i];
  const st = m ? linkStates.value.get(m.id) : undefined;
  if (linksReady.value && st && !st.available) {
    return "成员输入预览不可用（解析失败或形态锁定）— 接续勾选不可用";
  }
  const prev = members.value[i - 1];
  return prev
    ? `接续前置成员 ${fmtTaskId(prev.id)} 的 chk（写入 %oldchk=@task:${prev.id}，只读接续）`
    : "接续前置 chk";
}

const linkState = (i: number) => {
  const m = members.value[i];
  return m ? linkStates.value.get(m.id) : undefined;
};

/** 前驱是否为 crest 任务不可行——crest 不入队（B6 校验），勾选无需特判；
 *  单成员队列无前驱：首行不渲染勾选框。
 *  B9 G13 裁决⑤：同一并行取数路径扩展消费 warnings——创建态与编辑态
 *  （含仅成员可改的 submitted 态）打开时逐成员预显核验警告（复用既有
 *  preview 请求，不新增第二条请求路径）；只读/已提交完成态不预显。 */
async function loadLinkStates() {
  linkStates.value = new Map();
  depErrors.value = new Map();
  linksReady.value = false;
  if (readonly.value || done.value) {
    linksReady.value = true;
    return;
  }
  const ids = members.value.map((m) => m.id);
  const previews = await Promise.all(
    ids.map((id) =>
      client
        .GET("/candidates/{id}/preview", { params: { path: { id } } })
        .then(({ data }) =>
          data
            ? { lines: data.blocks.link0.lines, warnings: data.warnings ?? [] }
            : null,
        )
        .catch(() => null),
    ),
  );
  const map = new Map<number, LinkState>();
  ids.forEach((id, i) => {
    const pv = previews[i];
    const lines = pv?.lines ?? null;
    const prevId = i > 0 ? ids[i - 1] : null;
    const init = prevId != null && (lines ?? []).some((l) =>
      new RegExp(`^%oldchk\\s*=\\s*@task:${prevId}$`, "i").exec(l.trim()),
    );
    map.set(id, {
      original: [...(lines ?? [])],
      baseline: [...(lines ?? [])],
      initTarget: init && prevId != null ? prevId : null,
      checked: init,
      dirty: false,
      available: lines != null,
      warnings: pv?.warnings ?? [],
    });
  });
  linkStates.value = map;
  linksReady.value = true;
  // 警告区改变行高：渲染完成后重测画布（前缀和定位依赖实测行高）
  await nextTick();
  sort.measure();
}

function toggleLink(i: number) {
  const m = members.value[i];
  const st = m ? linkStates.value.get(m.id) : undefined;
  if (!st?.available) return;
  st.checked = !st.checked;
  st.dirty = true; // 勾选动作标记：保存按动作判定，非「与初值相等」
  depErrors.value.delete(m.id); // 勾选变更即解除该行旧错误标注
}

/** 勾选动作过的成员写入 Link0 引用行（先于建队——DAG 校验读输入文件，
 *  m4-plan §4.9 C5 落盘时序）。写入按保存时位置取前驱（重排后复勾落新
 *  前驱、纯重排不动既有引用）；内容与基线一致则不产生写请求。
 *  失败抛错由调用方汇总；成功则同步 baseline。 */
async function persistLinkChanges(): Promise<void> {
  const ids = members.value.map((m) => m.id);
  for (let i = 0; i < members.value.length; i++) {
    const m = members.value[i];
    const st = m ? linkStates.value.get(m.id) : undefined;
    if (!st?.available || !st.dirty) continue;
    const prevId = i > 0 ? ids[i - 1] : null;
    let lines = [...st.baseline];
    if (st.initTarget != null) lines = removeOldChkTaskRef(lines, st.initTarget);
    if (st.checked && prevId != null) lines.push(`%oldchk=@task:${prevId}`);
    if (JSON.stringify(lines) === JSON.stringify(st.baseline)) continue;
    const { error: e } = await client.PUT("/candidates/{id}/blocks/{section}", {
      params: { path: { id: m.id, section: "link0" } },
      body: { lines },
    });
    if (e) {
      const body = e as unknown as { error?: { message?: string } };
      throw new Error(
        `成员 ${fmtTaskId(m.id)} 依赖行写入失败：${body.error?.message ?? "未知错误"}`,
      );
    }
    st.baseline = lines;
  }
}

/** DAG 校验失败回滚：恢复本批次写盘成员的 Link0 原文（零残留副作用）。 */
async function rollbackLinkChanges(): Promise<void> {
  for (const [id, st] of linkStates.value) {
    if (!st.available) continue;
    if (JSON.stringify(st.baseline) === JSON.stringify(st.original)) continue;
    await client.PUT("/candidates/{id}/blocks/{section}", {
      params: { path: { id, section: "link0" } },
      body: { lines: st.original },
    });
    st.baseline = [...st.original];
  }
}

/** DAG 校验 422 → 逐成员内联提示（details.task_id / details.cycle /
 *  details.task_ids 映射到成员行；无法对应者落顶部 error）。 */
function mapDepError(code: string | undefined, message: string, details: Record<string, unknown> | undefined): boolean {
  let mapped = false;
  const put = (tid: number, msg: string) => {
    if (members.value.some((m) => m.id === tid)) {
      depErrors.value.set(tid, msg);
      mapped = true;
    }
  };
  if (code === "DEPENDENCY_CYCLE" && Array.isArray(details?.cycle)) {
    for (const tid of details.cycle as number[]) put(tid, message);
  } else if (code === "INVALID_MEMBERS" && Array.isArray(details?.task_ids)) {
    for (const tid of details.task_ids as number[]) put(tid, message);
  } else if (typeof details?.task_id === "number") {
    put(details.task_id, message);
  }
  return mapped;
}

const canSort = computed(() => !readonly.value && !done.value);

// ---------- 弹窗宽度调节（§2.5）：右缘拖拽/键盘步进，localStorage 持久化 ----------
// 宽度属设备视口相关的本地视图偏好（不上 ui-prefs：其键为枚举白名单、
// 连续像素值不在该域模型内），持久化通道与 g16web-theme 同前缀约定。
const WIDTH_KEY = "g16web-queue-editor-width";
const WIDTH_STEP = 16; // 键盘 ←/→ 步长
// 宽度下限与视口边距自 @/constants 单一来源引入（与 ConfirmModal
// min() 表达式同源，消除 560/48 字面量跨文件漂移，3.5.0 审查修复）

function loadWidth(): number {
  const raw = localStorage.getItem(WIDTH_KEY);
  const v = raw == null ? NaN : Number(raw);
  return Number.isFinite(v) && v >= MODAL_WIDTH_MIN ? v : MODAL_WIDTH_MIN;
}

const panelWidth = ref<number>(loadWidth());
const viewportW = ref<number>(window.innerWidth);
/** 实际渲染宽度 = min(内部值, 视口宽 − MODAL_VIEWPORT_MARGIN)：由
 *  ConfirmModal 的 min() 表达式钳制，此处同式计算供 aria-valuenow 与渲染一致。 */
const renderedWidth = computed(() =>
  Math.min(panelWidth.value, Math.max(viewportW.value - MODAL_VIEWPORT_MARGIN, 0)),
);
/** 渲染上限（视口宽 − MODAL_VIEWPORT_MARGIN）：视口宽 < 608px 时小于
 *  aria-valuemin（MODAL_WIDTH_MIN），为如实暴露的退化区间（此时渲染宽度
 *  由 min() 钳制、拖拽不改变可见宽度）。 */
const ariaMax = computed(() => Math.max(viewportW.value - MODAL_VIEWPORT_MARGIN, 0));

function setWidth(v: number): void {
  const cap = Math.max(MODAL_WIDTH_MIN, viewportW.value - MODAL_VIEWPORT_MARGIN);
  panelWidth.value = Math.round(Math.min(Math.max(v, MODAL_WIDTH_MIN), cap));
}

function persistWidth(): void {
  localStorage.setItem(WIDTH_KEY, String(panelWidth.value));
}

function nudgeWidth(delta: number): void {
  setWidth(panelWidth.value + delta);
  persistWidth();
}

let resizeStartX = 0;
let resizeStartW = 0;

function onResizeDown(e: PointerEvent): void {
  e.preventDefault();
  resizeStartX = e.clientX;
  resizeStartW = panelWidth.value;
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  const onMove = (ev: PointerEvent): void => {
    // 居中面板两侧对称扩展：右缘拖 1px 面板宽 2px（否则拖拽与视觉增长不同步）
    setWidth(resizeStartW + (ev.clientX - resizeStartX) * 2);
  };
  const onUp = (): void => {
    persistWidth();
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
  };
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
  window.addEventListener("pointercancel", onUp);
}

function onViewportResize(): void {
  viewportW.value = window.innerWidth;
}

onMounted(() => window.addEventListener("resize", onViewportResize));
onUnmounted(() => window.removeEventListener("resize", onViewportResize));

// ---------- 拖拽排序（指针跟手画布式 usePointerSort，§4.6；只读/完成态不可拖） ----------
const listEl = ref<HTMLElement | null>(null);
const canvasEl = ref<HTMLElement | null>(null);
const sort = usePointerSort({
  count: () => members.value.length,
  enabled: () => canSort.value,
  canvas: canvasEl,
  scroller: listEl,
  /** 归位动画结束后提交重排（视觉已就位，按位重排无跳变） */
  commit: (from, to) => {
    const [moved] = members.value.splice(from, 1);
    if (moved) members.value.splice(to, 0, moved);
  },
});

watch(
  () => props.open,
  async (v) => {
    if (!v) return;
    sort.reset(); // 丢弃上次遗留的拖拽状态（关闭即取消整次编辑）
    error.value = null;
    note.value = null;
    done.value = false;
    submitWarnings.value = [];
    busy.value = false;
    if (props.mode === "create") {
      name.value = props.initialName ?? defaultQueueName();
      members.value = (props.initialMembers ?? []).map((m) => ({ ...m }));
      skipFailed.value = false;
    } else {
      const q = props.queue;
      name.value = q?.name ?? "";
      skipFailed.value = q?.skip_failed ?? false;
      const lf = new Map<number, { state?: string; cause?: string | null }>();
      for (const it of q?.last_failure?.members ?? []) {
        if (it.task_id != null) lf.set(it.task_id, { state: it.state, cause: it.cause });
      }
      const det = new Map((q?.members ?? []).map((m) => [m.task_id, m]));
      members.value = (q?.member_ids ?? []).map((id) => ({
        id,
        filename: det.get(id)?.filename,
        title: det.get(id)?.title ?? null,
        ...(lf.get(id) ?? {}),
      }));
    }
    await nextTick(); // 行渲染完成后量测行高/行距（画布高度与步距）
    sort.measure();
    void loadLinkStates(); // 依赖勾选初始化（异步拉成员预览；不阻塞首帧）
  },
);

// 成员增删后行数变化，画布总高随之重算
watch(
  () => members.value.length,
  () => {
    void nextTick(() => sort.measure());
  },
);

function defaultQueueName(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

/** 队列 id 只读展示；创建态该字段不渲染（id 保存后由后端生成，不再显示占位注记）。 */
const qidLabel = computed(() => props.queue?.id ?? "—");

const canSave = computed(() => {
  if (!name.value.trim().length) return false;
  const n = members.value.length;
  // 成员数 2–10 仅创建时校验；编辑态只减不增、下限 1（§2.2——后端
  // PATCH 仅拒 0，canSave 误用创建期下限会禁存合法的剩 1 编辑，
  // D1 走查实测缺陷）
  return props.mode === "create" ? n >= 2 && n <= 10 : n >= 1;
});

function removeAt(i: number) {
  if (members.value.length <= 1) return; // 至少保留 1 个（下限前置禁用）
  const m = members.value[i];
  if (memberOnly.value && m?.state === "running") return; // 在跑成员移除后端 409（前置禁用）
  members.value.splice(i, 1);
}

// ---------- 保存 / 直接提交 ----------
/** 创建或更新（内部共用，不触发关闭）；成功返回队列视图。
 *  依赖勾选先落盘（Link0 引用行写入成员输入），建队/_PATCH 的 DAG 校验
 *  方能读到依赖边；校验失败回滚写盘并做逐成员内联提示（m4-plan §4.9 C5）。 */
async function saveInternal(): Promise<Queue | null> {
  // ① 勾选变更写入 Link0（create/edit 皆可编辑依赖行）
  try {
    await persistLinkChanges();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "依赖行写入失败";
    return null;
  }
  const rollback = () => {
    void rollbackLinkChanges().catch(() => {
      /* 回滚尽力而为：失败时成员输入保留引用行，错误区已提示 */
    });
  };
  if (props.mode === "create") {
    const { data, error: e } = await client.POST("/queues", {
      body: {
        name: name.value.trim(),
        member_ids: members.value.map((m) => m.id),
        skip_failed: skipFailed.value,
      },
    });
    if (e) {
      const body = e as unknown as { error?: { code?: string; message?: string; details?: Record<string, unknown> } };
      // DAG 校验错误逐成员内联（§4.9 C5）；无成员映射才落顶部错误条
      if (body.error?.code && mapDepError(body.error.code, body.error.message ?? "依赖校验未通过", body.error.details)) {
        error.value = null;
      } else {
        error.value = body.error?.message ?? "创建被拒绝";
      }
      rollback();
      return null;
    }
    return data ?? null;
  }
  const q = props.queue!;
  const body: Record<string, unknown> = {};
  if (!memberOnly.value && name.value.trim() !== q.name) {
    body.name = name.value.trim();
  }
  const ids = members.value.map((m) => m.id);
  if (JSON.stringify(ids) !== JSON.stringify(q.member_ids)) body.member_ids = ids;
  if (!memberOnly.value && skipFailed.value !== q.skip_failed) {
    body.skip_failed = skipFailed.value;
  }
  if (!Object.keys(body).length) return q; // 无变更视同成功
  const { data, error: e } = await client.PATCH("/queues/{id}", {
    params: { path: { id: q.id } },
    body: body as never,
  });
  if (e) {
    const eb = e as unknown as { error?: { code?: string; message?: string; details?: Record<string, unknown> } };
    if (eb.error?.code && mapDepError(eb.error.code, eb.error.message ?? "依赖校验未通过", eb.error.details)) {
      error.value = null;
    } else {
      error.value = eb.error?.message ?? "保存被拒绝";
    }
    rollback();
    return null;
  }
  return data ?? null;
}

async function save() {
  busy.value = true;
  error.value = null;
  const q = await saveInternal();
  busy.value = false;
  if (!q) return;
  // B9 G13「再次保存即清空」：直接提交的警告为提交回执，再次保存动作
  // 即视为知悉，旧回执不跨动作滞留（弹窗重开清空已有 watch(open) 承接）
  submitWarnings.value = [];
  emit("saved", q);
}

async function submitNow() {
  busy.value = true;
  error.value = null;
  const q = await saveInternal();
  if (!q) {
    busy.value = false;
    return;
  }
  const { data: sub, error: e } = await client.POST("/queues/{id}/submit", {
    params: { path: { id: q.id } },
  });
  busy.value = false;
  if (e) {
    // 链式失败：队列保留为已保存（unsubmitted），引导队列页重试（m2-plan §2.2）
    const body = e as unknown as { error?: { code?: string; message?: string } };
    error.value =
      body.error?.code === "PENDING_CAPACITY_FULL"
        ? "在途席位满员 — 队列已保存（未提交），请稍后在队列页重试"
        : `提交失败 — 队列已保存（未提交）：${body.error?.message ?? "稍后在队列页重试"}`;
    return;
  }
  done.value = true;
  note.value = sub?.normalized
    ? "已保存并提交 — 输入已自动规范化（换行/空行）"
    : "已保存并提交";
  submitWarnings.value = sub?.warnings ?? [];
  // B9 G13 裁决⑥：提交可能规范化改写文本，打开时预显不再代表当前存储
  // 文本——done 后重拉清空成员预显，最新核验由提交回执（含 task_id）承载
  void loadLinkStates();
  emit("submitted");
}

function tryClose() {
  if (!busy.value) emit("close");
}
</script>

<template>
  <ConfirmModal
    :open="open"
    :title="mode === 'create' ? '新建队列' : '队列编辑'"
    :loading="busy"
    :width="`${panelWidth}px`"
    @close="tryClose"
  >
    <div class="q-body">
      <div class="q-top">
        <label class="q-field">
          <span class="q-label mono">队列名</span>
          <input
            v-model="name"
            type="text"
            :disabled="readonly || memberOnly || done"
            maxlength="64"
          />
        </label>
        <!-- 队列 id 只读展示仅编辑/只读态；创建态不渲染（id 保存后生成，无占位注记） -->
        <div v-if="mode !== 'create'" class="q-field q-id-field">
          <span class="q-label mono">队列 ID</span>
          <span class="q-id mono">{{ qidLabel }}</span>
        </div>
      </div>

      <p v-if="memberOnly && !readonly" class="q-hint mono">
        已提交队列仅可重排与移除未执行成员（改名/开关在执行语义上不追溯）
      </p>
      <p v-if="executingHint" class="q-hint mono">
        队列执行中（只读）— 成员移除请前往待执行页操作
      </p>
      <p v-if="error" class="q-error mono" role="alert">{{ error }}</p>
      <p v-if="note" class="q-note mono" role="status">{{ note }}</p>
      <!-- 队列提交回执警告（B8 G12 通道 / B9 G13 文案：条目
           「⚠ 任务 #task_id: L行号 message」，限高滚动防堆叠溢出） -->
      <div v-if="submitWarnings.length" class="q-warns" role="status">
        <p v-for="(w, i) in submitWarnings" :key="`qw${i}`" class="q-warn mono">
          ⚠ 任务 #{{ w.task_id ?? "?" }}: L{{ w.line }} {{ w.message }}
        </p>
      </div>

      <p class="q-label mono">成员（{{ members.length }}）— 顺序即执行序列</p>
      <!-- 滚动容器只管滚动与内边距；行定位交给画布（无内边距，坐标量测基准） -->
      <div ref="listEl" class="q-members">
        <div ref="canvasEl" class="q-canvas" :class="{ 'q-canvas--live': canSort }" :style="sort.canvasStyle.value">
          <div
            v-for="(m, i) in members"
            :key="m.id"
            class="q-mem"
            :class="{ 'q-mem--dragging': sort.dragIndex.value === i, 'q-mem--error': depErrors.has(m.id) }"
            :style="sort.styleFor(i)"
            @pointerdown="sort.onDown($event, i)"
            @pointermove="sort.onMove($event)"
            @pointerup="sort.onUp"
            @pointercancel="sort.onUp"
          >
            <div class="q-mem-main">
              <span v-if="canSort" class="m-drag mono" aria-hidden="true">⋮⋮</span>
              <span class="m-id mono">{{ fmtTaskId(m.id) }}</span>
              <span class="m-file mono" :title="m.filename">{{ m.filename ?? "—" }}</span>
              <span class="m-title" :title="m.title ?? undefined">{{ m.title ?? "—" }}</span>
              <!-- 接续前置 chk（m4-plan §4.9 C5）：勾选=对前置成员写入
                   %oldchk=@task:<id> 只读接续行（保存时落盘，建队 DAG 校验）；
                   首成员无前驱不渲染；预览不可达（编辑态成员锁定/解析失败）
                   禁用并提示——不静默：原生勾选视觉态曾掩盖持久化失效；
                   pointerdown.stop 防拖拽误触 -->
              <label
                v-if="i > 0 && linkEditable"
                class="m-link"
                :class="{ 'm-link--disabled': !linksReady || !linkState(i)?.available }"
                :title="linkTitle(i)"
                @pointerdown.stop
                @click.stop
              >
                <input
                  class="ck"
                  type="checkbox"
                  :disabled="!linksReady || busy || !linkState(i)?.available"
                  :checked="linkStates.get(m.id)?.checked ?? false"
                  @change="toggleLink(i)"
                />
                <span class="m-link-text">接续前置 chk</span>
              </label>
              <StateChip v-if="m.state" :state="m.state" />
              <span v-if="m.cause" class="m-cause mono">{{ causeLabel[m.cause] ?? m.cause }}</span>
              <button
                v-if="!readonly"
                class="btn btn--ghost m-remove"
                type="button"
                :disabled="members.length <= 1 || done || (memberOnly && m.state === 'running')"
                :title="members.length <= 1 ? '队列至少保留 1 个成员' : (memberOnly && m.state === 'running' ? '在跑成员不可移除' : undefined)"
                @click="removeAt(i)"
              >
                -
              </button>
            </div>
            <!-- B9 G13 裁决⑤：该成员自己的核验警告预显（任务级归属，
                 打开时现算自 preview.warnings，限高滚动）；预览取回失败仅
                 该成员占位提示、不阻断其余成员；done 后成员区有意清空
                 （提交回执承载最新核验），不显占位 -->
            <div
              v-if="!done && linksReady && linkState(i) && !linkState(i)?.available"
              class="q-mem-warns q-mem-warns--empty mono"
            >
              成员输入预览不可用 — 无法核验
            </div>
            <div v-else-if="linkState(i)?.warnings?.length" class="q-mem-warns" role="status">
              <p v-for="(w, j) in linkState(i)?.warnings ?? []" :key="`mw${i}-${j}`" class="q-warn mono">
                ⚠ L{{ w.line }} {{ w.message }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- DAG 校验错误逐成员清单（m4-plan §4.9 C5：内联提示——成员行红描边
           与此处逐条文案对应，行高恒定不破坏拖拽量测） -->
      <div v-if="depErrors.size" class="q-dep-errors" role="alert">
        <p v-for="[tid, msg] in depErrors" :key="tid" class="q-dep-error mono">
          <span class="m-id mono">{{ fmtTaskId(tid) }}</span> — {{ msg }}
        </p>
      </div>

      <div class="q-toggle-row">
        <span class="q-label mono">自动跳过失败任务</span>
        <button
          type="button"
          class="tgl"
          :class="{ 'tgl--on': skipFailed }"
          role="switch"
          :aria-checked="skipFailed"
          :disabled="readonly || memberOnly || done"
          @click="skipFailed = !skipFailed"
        >
          <i class="tgl-knob"></i>
        </button>
      </div>
    </div>

    <template #foot>
      <button class="btn btn--ghost" type="button" @click="tryClose">
        {{ done ? "关闭" : "取消" }}
      </button>
      <template v-if="!readonly">
        <button
          class="btn btn--secondary"
          type="button"
          :disabled="busy || done"
          @click="submitNow"
        >
          直接提交
        </button>
        <button
          class="btn btn--primary"
          type="button"
          :data-loading="busy || undefined"
          :disabled="busy || done || !canSave"
          @click="save"
        >
          {{ busy ? "保存中 …" : "保存" }}
        </button>
      </template>
    </template>
    <!-- 拖宽手柄（§2.5）：经 ConfirmModal 具名插槽渲染为 .modal 直接子元素
         （.body 是滚动容器，绝对定位置其中会被裁剪）；只读/完成态同样
         显示可操作（宽度属本地视图偏好，与队列状态无关） -->
    <template #resize-handle>
      <div
        class="q-resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整弹窗宽度"
        :aria-valuenow="renderedWidth"
        :aria-valuemin="MODAL_WIDTH_MIN"
        :aria-valuemax="ariaMax"
        tabindex="0"
        @pointerdown="onResizeDown"
        @keydown.left.prevent="nudgeWidth(-WIDTH_STEP)"
        @keydown.right.prevent="nudgeWidth(WIDTH_STEP)"
      ></div>
    </template>
  </ConfirmModal>
</template>

<style scoped>
.q-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.q-top {
  display: flex;
  gap: var(--space-4);
  align-items: flex-end;
}
.q-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
  min-width: 0;
}
.q-id-field {
  flex: none;
  align-items: flex-start;
}
.q-label {
  font-size: var(--text-sm); /* 文案含中文（队列名/成员等）：不用微标签档、不加字距 */
  color: var(--text-faint);
}
.q-id {
  font-size: var(--text-sm);
  color: var(--text-primary);
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: 6px var(--space-2);
}
.q-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.q-error {
  font-size: var(--text-sm);
  color: var(--danger);
}
/* 信息注记（中性档 §4.6：提交响应「已自动规范化」提示） */
.q-note {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
/* 提交回执警告区（B9 G13：琥珀档 + 限高滚动防堆叠溢出） */
.q-warns {
  max-height: var(--warn-list-max-height);
  overflow: auto;
  display: grid;
  gap: 2px;
}
.q-warn {
  font-size: var(--text-sm);
  color: var(--warn);
  word-break: break-word;
}
/* 滚动容器：仅滚动与内边距；行定位/间距由画布与步距量测接管（§4.6 拖拽排序） */
.q-members {
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-inset);
  padding: var(--space-2);
  max-height: 260px;
  overflow: auto;
}
/* 定位画布：position:relative 且无内边距，行 absolute + translateY 定位 */
.q-canvas {
  position: relative;
}
.q-mem {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  display: flex;
  flex-direction: column; /* 主行 + 警告预显区两行（B9 G13），前缀和量测按整行高 */
  align-items: flex-start;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  font-size: var(--text-sm);
  user-select: none;
  touch-action: none; /* 指针拖拽期间阻止触屏滚动误触 */
  transition:
    transform var(--dur-drag) var(--ease-std),
    border-color var(--dur-fast) var(--ease-std);
  will-change: transform;
}
/* 主行（成员信息 + 动作，占满整行宽） */
.q-mem-main {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  min-width: 0;
}
/* 成员核验警告预显区（B9 G13 裁决⑤）：琥珀档，限高滚动 */
.q-mem-warns {
  margin-top: var(--space-1);
  width: 100%;
  max-height: var(--warn-list-max-height);
  overflow: auto;
  display: grid;
  gap: 2px;
}
.q-mem-warns--empty {
  color: var(--text-faint);
}
.q-canvas--live .q-mem {
  cursor: grab;
}
/* 拿起态：accent 描边 + 浮起投影（令牌组合，不另设色值） */
.q-mem--dragging {
  z-index: 1;
  border-color: var(--accent);
  box-shadow: var(--shadow-pop);
}
.q-canvas--live .q-mem--dragging {
  cursor: grabbing;
}
.m-drag {
  color: var(--text-faint);
  cursor: grab;
  letter-spacing: -2px;
}
.m-id {
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}
.m-file {
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  /* 弹窗宽度可调（§2.5）：可伸缩占位替代固定 150px——基准为内容宽、
   * 与 .m-title 按 flex 比例分配行内剩余宽度；min-width: 0 防溢出撑破，
   * 单行省略兜底保留，拖宽后长任务名显示宽度随弹窗增长 */
  flex: 1 1 auto;
  min-width: 0;
}
.m-title {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 40px;
}
.m-cause {
  font-size: var(--text-sm);
  color: var(--warn);
}
/* 接续前置 chk 勾选（C5）：内联紧凑、阻断行拖拽（pointerdown.stop） */
.m-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  cursor: pointer;
  white-space: nowrap;
  flex: none;
}
.m-link--disabled {
  opacity: 0.5;
  cursor: wait;
}
.m-link-text {
  font-size: var(--text-xs); /* 文案含中文：下限档从属选项（候选页 .qf 同口径） */
  color: var(--text-secondary);
}
/* DAG 校验错误行（C5）：红描边标注涉错成员（不改行高，画布量测不受影响） */
.q-mem--error {
  border-color: var(--danger);
}
.q-dep-errors {
  border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
  border-radius: var(--r-md);
  background: var(--bg-raised);
  padding: var(--space-2) var(--space-3);
  display: grid;
  gap: var(--space-1);
}
.q-dep-error {
  font-size: var(--text-sm);
  color: var(--danger);
}
.q-dep-error .m-id {
  color: var(--danger);
}
.m-remove {
  height: var(--control-height-sm);
  padding: 0 var(--space-2);
}
.q-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
/* toggle 开关（§4.6 A3 定稿：36×20 轨道 + 16px 滑块，选中轨道 --accent） */
.tgl {
  position: relative;
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  padding: 0;
  cursor: pointer;
  flex: none;
}
.tgl:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.tgl-knob {
  position: absolute;
  left: 2px;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--text-faint);
  transition: left var(--dur-fast) var(--ease-std), background-color var(--dur-fast) var(--ease-std);
}
.tgl--on {
  background: var(--accent);
  border-color: var(--accent);
}
.tgl--on .tgl-knob {
  left: 16px;
  background: var(--bg-raised);
}

/* 拖宽手柄（§2.5）：右缘 8px 热区贴面板外缘 4px（ConfirmModal .modal
 * 已建定位上下文），透明常态 + hover/焦点显右侧指示线；焦点态由全局
 * :focus-visible 轮廓承载。宽度值为组件级像素写法（既有先例 .m-file） */
.q-resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  right: -4px;
  width: 8px;
  border: none;
  padding: 0;
  background: transparent;
  border-right: 2px solid transparent;
  border-radius: var(--r-lg);
  cursor: col-resize;
  touch-action: none;
}
.q-resize-handle:hover,
.q-resize-handle:focus-visible {
  border-right-color: var(--border-strong);
}
</style>
