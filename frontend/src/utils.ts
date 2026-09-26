const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;

/** "4m", "3h", "2d" — compact, for metadata rows. */
export function timeAgo(ts: number, now = Date.now() / 1000): string {
  const diff = Math.max(0, now - ts);
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h`;
  if (diff < 30 * DAY) return `${Math.floor(diff / DAY)}d`;
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** "just now" / "4m ago" — for sentences like "updated …". */
export function ago(ts: number, now = Date.now() / 1000): string {
  const short = timeAgo(ts, now);
  return short === "just now" || /^\d+ \w+$/.test(short) ? short : `${short} ago`;
}

/** "4 minutes ago", for titles/tooltips. */
export function timeAgoLong(ts: number, now = Date.now() / 1000): string {
  const short = timeAgo(ts, now);
  if (short === "just now") return short;
  const unit = short.slice(-1);
  const n = parseInt(short, 10);
  const word = { m: "minute", h: "hour", d: "day" }[unit];
  if (!word || Number.isNaN(n)) return short;
  return `${n} ${word}${n === 1 ? "" : "s"} ago`;
}

export function fullDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function dayLabel(ts: number): string {
  const d = new Date(ts * 1000);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

/** 1,284 / 12.9K / 4.2M */
export function compact(n: number): string {
  if (n < 1000) return n.toLocaleString();
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0).replace(/\.0$/, "")}K`;
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
}

/** Today's edition, written like a version number: v26.10.02 */
export function editionVersion(date = new Date()): string {
  const yy = String(date.getFullYear()).slice(2);
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `v${yy}.${mm}.${dd}`;
}

export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export function plural(n: number, word: string, pluralWord = `${word}s`): string {
  return `${n.toLocaleString()} ${n === 1 ? word : pluralWord}`;
}

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}
