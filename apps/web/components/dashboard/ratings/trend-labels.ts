import type { TrendGranularity } from "@/lib/types";

const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

/** `2026-03` -> `мар 26` */
function formatMonthKey(key: string): string {
  const [year, month] = key.split("-");
  const idx = Number(month) - 1;
  if (!MONTHS[idx]) return key;
  return `${MONTHS[idx]} ${year.slice(2)}`;
}

/** `2026-W29` -> `нед. 29` */
function formatWeekKey(key: string): string {
  const week = key.split("-W")[1];
  return week ? `нед. ${Number(week)}` : key;
}

/** `2026-07-23` -> `23 июл` */
function formatDayKey(key: string): string {
  const [, month, day] = key.split("-");
  const idx = Number(month) - 1;
  if (!MONTHS[idx] || !day) return key;
  return `${Number(day)} ${MONTHS[idx]}`;
}

/** Bucket key -> short axis/tooltip label, dispatched on the block's granularity. */
export function formatTrendLabel(key: string, granularity: TrendGranularity = "month"): string {
  if (granularity === "day") return formatDayKey(key);
  if (granularity === "week") return formatWeekKey(key);
  return formatMonthKey(key);
}

/** Panel `meta` suffix describing the bucket width, e.g. "по неделям". */
export function granularityMeta(granularity: TrendGranularity = "month"): string {
  if (granularity === "day") return "по дням";
  if (granularity === "week") return "по неделям";
  return "по месяцам";
}
