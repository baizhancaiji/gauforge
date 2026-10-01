/**
 * 格式化工具（m0-frontend-design §2.2：数字/时间/资源列一律 mono + tabular）。
 * 中文语义：单位与数字间加空格（512 MB、3h 12m）。
 */

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO 时间 → "HH:MM:SS"（同一会话内取本地时刻，足够读取）。 */
export function fmtClock(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** ISO 时间 → "MM-DD HH:MM"（跨日列表用）。 */
export function fmtDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 秒数 → "3h 12m" / "45s" / "2m 05s"。 */
export function fmtDuration(s?: number | null): string {
  if (s == null || Number.isNaN(s)) return "—";
  const sec = Math.max(0, Math.floor(s));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const rs = sec % 60;
  if (h > 0) return `${h}h ${pad(m)}m`;
  if (m > 0) return `${m}m ${pad(rs)}s`;
  return `${sec}s`;
}

/** CPU 读数 → "386%"。 */
export function fmtPercent(n?: number | null): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(0)}%`;
}

/** 内存读数 MB → "512 MB" / "1.20 GB"。 */
export function fmtMemory(mb?: number | null): string {
  if (mb == null || Number.isNaN(mb)) return "—";
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${Math.round(mb)} MB`;
}

/** 字节读数 → "12.3 GB" / "512 MB"（占用面板 M3.7；GB 一位小数）。 */
export function fmtBytes(b?: number | null): string {
  if (b == null || Number.isNaN(b)) return "—";
  if (b >= 1024 ** 3) return `${(b / 1024 ** 3).toFixed(1)} GB`;
  if (b >= 1024 ** 2) return `${(b / 1024 ** 2).toFixed(0)} MB`;
  return `${(b / 1024).toFixed(0)} KB`;
}

/** 哈希 → 前 12 位缩写。 */
export function fmtHash(h?: string | null): string {
  if (!h) return "—";
  const body = h.startsWith("sha256:") ? h.slice("sha256:".length) : h;
  return body.length > 12 ? `${body.slice(0, 12)}…` : body;
}

/**
 * 任务/候选 id → "034"（三位零填充是显示下宽，不是上限：
 * padStart 只补齐不截断，id ≥ 1000 自然加宽为 "1000"）。
 * 全站任务 id 统一用此形式（候选/待执行/队列成员概览），勿再写 `#34`。
 */
export function fmtTaskId(n?: number | null): string {
  return n == null ? "—" : String(n).padStart(3, "0");
}

/** Link0 声明资源 → "4C* / 8G*"（* = 运行级缺省补齐；缺省 "—"）。 */
export function fmtDeclaredRes(
  r?: {
    nproc: { value: number; defaulted: boolean };
    mem_gb: { value: number; defaulted: boolean };
  } | null,
): string {
  if (!r?.nproc || !r?.mem_gb) return "—";
  return `${r.nproc.value}C${r.nproc.defaulted ? "*" : ""} / ${r.mem_gb.value}G${r.mem_gb.defaulted ? "*" : ""}`;
}