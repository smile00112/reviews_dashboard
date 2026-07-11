import type { KpiStrip } from "@/lib/types";

function Mini({
  label,
  value,
  unit,
  sub,
  subTone = "muted",
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  subTone?: "up" | "down" | "muted";
}) {
  const tone = subTone === "up" ? "text-good" : subTone === "down" ? "text-bad" : "text-text-faint";
  return (
    <div className="rounded-[10px] border border-border bg-surface p-4 transition-colors hover:border-text-faint">
      <div className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-wide text-text-faint">{label}</div>
      <div className="mb-1 font-display text-2xl font-medium leading-none tracking-tight">
        {value}
        {unit && <span className="font-sans text-[13px] font-medium text-text-dim"> {unit}</span>}
      </div>
      {sub && <div className={`font-mono text-[11px] ${tone}`}>{sub}</div>}
    </div>
  );
}

export function KpiStripRow({ strip }: { strip: KpiStrip }) {
  const na = "—";
  return (
    <div className="mb-7 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
      <Mini
        label="Ср. время ответа"
        value={strip.response_avg_min !== null ? String(strip.response_avg_min) : na}
        unit={strip.response_avg_min !== null ? "мин" : undefined}
        sub={strip.response_approximate ? "приблизительно" : undefined}
      />
      <Mini
        label="Медиана ответа"
        value={strip.response_median_min !== null ? String(strip.response_median_min) : na}
        unit={strip.response_median_min !== null ? "мин" : undefined}
        sub={strip.response_p95_min !== null ? `p95: ${strip.response_p95_min} мин` : undefined}
      />
      <Mini
        label="В SLA"
        value={strip.sla_percent !== null ? String(strip.sla_percent) : na}
        unit={strip.sla_percent !== null ? "%" : undefined}
      />
      <Mini label="Позитивность" value={String(strip.positivity_percent)} unit="%" subTone="up" />
      <Mini
        label="Индекс репутации"
        value={strip.reputation_index !== null ? String(strip.reputation_index) : na}
        unit={strip.reputation_index !== null ? "%" : undefined}
      />
    </div>
  );
}
