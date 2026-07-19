import type { KpiStrip } from "@/lib/types";

const na = "—";

/** Минуты → "Xч Yм" при ≥60 мин, иначе "Yм". Для подписи p95. */
function fmtDuration(min: number): string {
  if (min < 60) return `${min}м`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h}ч ${m}м` : `${h}ч`;
}

/** Дельта период-к-периоду: стрелка, знак, значение, единица. */
function fmtDelta(v: number | null, unit: string): { text: string; dir: "up" | "down" | "flat" } | null {
  if (v === null || v === undefined) return null;
  const dir = v > 0 ? "up" : v < 0 ? "down" : "flat";
  const arrow = v > 0 ? "▲" : v < 0 ? "▼" : "•";
  return { text: `${arrow} ${v > 0 ? "+" : ""}${v}${unit}`, dir };
}

const toneClass = { up: "text-good", down: "text-bad", flat: "text-text-faint" } as const;
// Для «ср. времени ответа» рост — плохо: цвета инвертированы.
const invertedTone = { up: "text-bad", down: "text-good", flat: "text-text-faint" } as const;

function Mini({
  label,
  value,
  unit,
  sub,
  subClass = "text-text-faint",
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  subClass?: string;
}) {
  return (
    <div className="rounded-[10px] border border-border bg-surface p-4 transition-colors hover:border-text-faint">
      <div className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-wide text-text-faint">{label}</div>
      <div className="mb-1 font-display text-2xl font-medium leading-none tracking-tight">
        {value}
        {unit && <span className="font-sans text-[13px] font-medium text-text-dim"> {unit}</span>}
      </div>
      {sub && <div className={`font-mono text-[11px] ${subClass}`}>{sub}</div>}
    </div>
  );
}

export function KpiStripRow({ strip }: { strip: KpiStrip }) {
  const avgDelta = fmtDelta(strip.response_avg_min_delta, " мин");
  const slaDelta = fmtDelta(strip.sla_percent_delta, " п.п.");
  const posDelta = fmtDelta(strip.positivity_percent_delta, " п.п.");
  const repDelta = fmtDelta(strip.reputation_index_delta, " п.п.");

  return (
    <div className="mb-7 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
      <Mini
        label="Ср. время ответа"
        value={strip.response_avg_min !== null ? String(strip.response_avg_min) : na}
        unit={strip.response_avg_min !== null ? "мин" : undefined}
        sub={avgDelta?.text}
        subClass={avgDelta ? invertedTone[avgDelta.dir] : undefined}
      />
      <Mini
        label="Медиана ответа"
        value={strip.response_median_min !== null ? String(strip.response_median_min) : na}
        unit={strip.response_median_min !== null ? "мин" : undefined}
        sub={strip.response_p95_min !== null ? `p95: ${fmtDuration(strip.response_p95_min)}` : undefined}
      />
      <Mini
        label="В SLA"
        value={strip.sla_percent !== null ? String(strip.sla_percent) : na}
        unit={strip.sla_percent !== null ? "%" : undefined}
        sub={slaDelta?.text}
        subClass={slaDelta ? toneClass[slaDelta.dir] : undefined}
      />
      <Mini
        label="Позитивность"
        value={String(strip.positivity_percent)}
        unit="%"
        sub={posDelta?.text}
        subClass={posDelta ? toneClass[posDelta.dir] : undefined}
      />
      <Mini
        label="Индекс репутации"
        value={strip.reputation_index !== null ? String(strip.reputation_index) : na}
        unit={strip.reputation_index !== null ? "%" : undefined}
        sub={repDelta?.text}
        subClass={repDelta ? toneClass[repDelta.dir] : undefined}
      />
    </div>
  );
}
