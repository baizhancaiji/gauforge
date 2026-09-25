/**
 * SSE 消费 store（m0-plan §3.4–3.7 / m0-frontend-design §4.4）：
 * - 原生 fetch + ReadableStream，不走 EventSource，以便完全掌控重连退避与
 *   Last-Event-ID 透传（契约 §3.5：1s→2s→5s→10s 封顶，收到任意事件即复位）。
 * - 状态类事件（pending.snapshot / system.snapshot / task.status / execution.*）
 *   直接驱动本 store 反应态（灯排读数、执行中读数、待执行席位）。
 * - 通知类事件（candidates.changed / queues.changed）仅递增脏计数，页面 watch 后重拉 REST。
 * - history.appended（succeeded/failed）触发 Toast；skipped 不通知（设计 §4.6）。
 */
import { defineStore } from "pinia";
import { computed, reactive, ref } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";

type Execution = components["schemas"]["Execution"];
type HistoryEntry = components["schemas"]["HistoryEntry"];
type PendingResponse = components["schemas"]["PendingResponse"];

export interface LiveExecution {
  id: number;
  task_id: number;
  filename: string;
  queue_id?: string | null;
  state?: string;
  submitted_at?: string;
  started_at?: string;
  monitor?: Execution["monitor"];
  progress?: Execution["progress"];
}

export interface Toast {
  id: number;
  title: string;
  /** 通知状态词颜色（succeeded/failed） */
  state: string;
}

const BACKOFF = [1000, 2000, 5000, 10000];

export const useEventsStore = defineStore("events", () => {
  const connection = ref<"connecting" | "open" | "reconnecting" | "closed">("closed");
  const lastSeq = ref<number>(0);

  // 灯排（§3/§4.1）：派生 computed——直接从 executions/pending/stalled 计算，
  // 任何路径塞卡/撤卡/心跳都自动同步，不再依赖手改 reactive + syncLamps()。
  const lamps = computed(() => ({
    running: executions.size,
    queued: pending.value?.seats.length ?? 0,
    alarm: stalled.size,
  }));

  // 执行中实时读数（按 execution_id 键控，契约 §3.1）。
  const executions = reactive(new Map<number, LiveExecution>());

  // 待执行席位全量（pending.snapshot 快照式覆盖）。
  const pending = ref<PendingResponse | null>(null);

  // Toast 队列（右上滑入、自动消）。
  const toasts = ref<Toast[]>([]);

  // 通知类事件的脏计数——列表页 watch 后重拉 REST 当前页（契约 §3.5⑥）。
  const dirty = reactive({ candidates: 0, queues: 0, history: 0 });

  /**
   * 停滞告警表（execution_id → 详情）。键存在即告警中（点亮告警灯、
   * 通道卡琥珀行），载荷为事件明细（last_progress_ts/threshold_minutes）。
   * 原 Set+Map 双结构总需成对增删，捆扎为单一 Map 消除漂移面。
   */
  const stalled = reactive(
    new Map<number, { last_progress_ts: string | null; threshold_minutes: number | null }>(),
  );

  /** 已知 eid → filename（REST/snapshot 注入时记录），供未知监测事件补齐卡名。 */
  const knownNames = new Map<number, string>();

  /** 队列名缓存（Toast 队列成员通知取「所属队列名」，设计 §4.6）。 */
  let queueNames: Map<string, string> | null = null;
  function refreshQueueNames() {
    // 走契约 client（§4.4 全部 REST 经生成类型；拉取失败回退 id 展示，下次再试）
    client
      .GET("/queues")
      .then(({ data }) => {
        if (data) queueNames = new Map(data.map((q) => [q.id, q.name]));
      })
      .catch(() => {
        /* 拉取失败：Toast 回退 id 展示，下次再试 */
      });
  }

  let controller: AbortController | null = null;
  let closedByUs = false;
  let attempt = 0;
  let toastSeq = 0;

  function push(live: LiveExecution | HistoryEntry) {
    const e = live as LiveExecution;
    if (e.filename) knownNames.set(e.id, e.filename);
    // 合并语义：REST 基线轮询只补齐身份字段，不得整体覆盖卡片——
    // 否则会抹掉 SSE 写入的 monitor/progress 实时读数（GUI 走查实测）。
    const prev = executions.get(e.id);
    executions.set(e.id, {
      id: e.id,
      task_id: e.task_id,
      filename: e.filename || prev?.filename || knownNames.get(e.id) || "—",
      queue_id: e.queue_id ?? prev?.queue_id ?? null,
      state: e.state,
      submitted_at: e.submitted_at,
      started_at: e.started_at,
      monitor: e.monitor ?? prev?.monitor,
      progress: e.progress ?? prev?.progress,
    });
  }

  /** 监测事件落在未知执行上时（30s 剧本交叠间隙）用已知卡名补齐。 */
  function upsert(eid: number) {
    if (!executions.has(eid)) {
      executions.set(eid, { id: eid, task_id: eid, filename: knownNames.get(eid) || "—" });
    }
  }

  function pushToast(title: string, state: string) {
    toasts.value.push({ id: ++toastSeq, title, state });
    setTimeout(() => dismissToast(toastSeq), 5000);
  }

  function dismissToast(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }

  function handle(event: string, data: unknown) {
    const d = data as Record<string, unknown>;
    switch (event) {
      case "system.snapshot":
        if (d.pending) pending.value = d.pending as PendingResponse;
        if (Array.isArray(d.executions_running)) {
          // 重建基线：先清空旧态，避免重连后残留已结束执行的僵尸卡。
          executions.clear();
          stalled.clear();
          (d.executions_running as HistoryEntry[]).forEach(push);
        }
        break;
      case "pending.snapshot":
        pending.value = d as unknown as PendingResponse;
        break;
      case "execution.progress": {
        const eid = Number(d.execution_id);
        upsert(eid); // 30s 间隙后执行才出现：先建卡再合并监测读数
        const e = executions.get(eid);
        if (e)
          e.progress = {
            opt_step: Number(d.opt_step),
            scf_cycle: Number(d.scf_cycle),
            converged: Boolean(d.converged),
            last_line: String(d.last_line ?? ""),
          };
        break;
      }
      case "execution.monitor": {
        const eid = Number(d.execution_id);
        upsert(eid);
        const e = executions.get(eid);
        if (e)
          e.monitor = {
            cpu_percent: Number(d.cpu_percent),
            mem_rss_mb: Number(d.mem_rss_mb),
            elapsed_s: Number(d.elapsed_s),
          };
        break;
      }
      case "execution.stalled": {
        const id = Number(d.execution_id);
        if (d.stalled) {
          stalled.set(id, {
            last_progress_ts: (d.last_progress_ts as string) ?? null,
            threshold_minutes: (d.threshold_minutes as number) ?? null,
          });
        } else {
          stalled.delete(id);
        }
        break;
      }
      case "task.status":
        if (d.to === "running") {
          if (d.execution_id != null) push({ id: Number(d.execution_id), task_id: Number(d.task_id), filename: "", queue_id: (d.queue_id as string) ?? null });
        }
        break;
      case "history.appended": {
        const st = d.state as string;
        // 执行到达终态：从运行视图移除（与后端 executions 列表一致），通知除 skipped。
        const eid = Number(d.execution_id);
        executions.delete(eid);
        stalled.delete(eid);
        dirty.history++; // 历史页按需重拉当前页
        if (st === "succeeded" || st === "failed") {
          // 名称规则（设计 §4.6）：单任务取任务名（M0 mock 的 title 与文件名
          // 同源，knownNames 即其载体）、队列成员取所属队列名；超 15 字符截断。
          const qid = d.queue_id as string | undefined;
          if (qid && !queueNames) refreshQueueNames();
          const raw = qid
            ? queueNames?.get(qid) ?? `队列 ${qid}`
            : knownNames.get(eid) ?? `任务 ${d.task_id ?? ""}`;
          const name = raw.length > 15 ? `${raw.slice(0, 15)}…` : raw;
          pushToast(name, st);
        }
        break;
      }
      case "candidates.changed":
        dirty.candidates++;
        break;
      case "queues.changed":
        queueNames = null; // 队列集变化：名称缓存失效，下次 Toast 前重拉
        dirty.queues++;
        break;
      case "queue.status":
        // 队列状态实时流转（submitted/executing/completed）：置脏驱动队列页重拉。
        dirty.queues++;
        break;
      default:
        break; // heartbeat / 其余事件按需在后续 M1 展开
    }
  }

  async function connect() {
    closedByUs = false;
    connection.value = lastSeq.value ? "reconnecting" : "connecting";
    if (!queueNames) refreshQueueNames(); // 连接前预热队列名缓存（Toast 用）
    controller = new AbortController();
    try {
      // 例外：SSE 流式响应不走契约 client——openapi-fetch 不支持流式读取，
      // 需原生 fetch + ReadableStream 掌控重连与 Last-Event-ID（文件头说明）。
      const res = await fetch("/api/v1/events", {
        headers: {
          Accept: "text/event-stream",
          "Last-Event-ID": String(lastSeq.value || 0),
        },
        signal: controller.signal,
      });
      if (!res.ok || !res.body) throw new Error(`sse http ${res.status}`);
      connection.value = "open";
      attempt = 0;

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let evName = "";
      let evId: number | null = null;
      const dataLines: string[] = [];

      const dispatch = () => {
        if (dataLines.length) {
          try {
            handle(evName, JSON.parse(dataLines.join("\n")));
          } catch {
            /* 单事件序列化失败：跳过，不影响流（契约 §3.6） */
          }
          if (evId != null) lastSeq.value = evId;
        }
        evName = "";
        evId = null;
        dataLines.length = 0;
      };

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (let line of lines) {
          // SSE 规范行尾可为 CRLF：剥尾部 \r，否则事件分隔空行识别为
          // "\r" 而非 ""，全部事件将被静默吞掉（GUI 走查实测）。
          if (line.endsWith("\r")) line = line.slice(0, -1);
          if (line === "") {
            dispatch();
            continue;
          }
          if (line.startsWith(":")) continue; // 注释帧
          if (line.startsWith("event:")) evName = line.slice(6).trim();
          else if (line.startsWith("id:")) evId = parseInt(line.slice(3).trim(), 10) || null;
          else if (line.startsWith("retry:")) attempt = 0; // 服务端建议重试间隔，接收即复位
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
        }
      }
    } catch {
      /* 断线/中止 */
    } finally {
      if (!closedByUs && controller?.signal && !controller.signal.aborted) {
        connection.value = "reconnecting";
        const delay = BACKOFF[Math.min(attempt, BACKOFF.length - 1)];
        attempt++;
        setTimeout(() => connect(), delay);
      }
    }
  }

  async function start() {
    if (connection.value !== "closed" && controller) return;
    await connect();
  }

  function stop() {
    closedByUs = true;
    controller?.abort();
    controller = null;
    connection.value = "closed";
  }

  return {
    connection,
    lastSeq,
    lamps,
    executions,
    pending,
    toasts,
    dirty,
    stalled,
    push,
    dismissToast,
    start,
    stop,
  };
});