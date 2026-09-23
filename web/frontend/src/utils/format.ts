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

/** 哈希 → 前 12 位缩写。 */
export function fmtHash(h?: string | null): string {
  if (!h) return "—";
  const body = h.startsWith("sha256:") ? h.slice("sha256:".length) : h;
  return body.length > 12 ? `${body.slice(0, 12)}…` : body;
}