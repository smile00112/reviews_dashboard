"use client";

export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

const R = 50;
const CIRC = 2 * Math.PI * R;

/** Hand-rolled SVG donut (no charting dependency). */
export function Donut({ segments, centerLabel }: { segments: DonutSegment[]; centerLabel?: string }) {
  const total = segments.reduce((s, seg) => s + seg.value, 0);
  let offset = 0;
  return (
    <div className="relative flex h-[200px] items-center justify-center">
      <svg viewBox="0 0 120 120" className="h-[180px] w-[180px] -rotate-90">
        <circle cx="60" cy="60" r={R} fill="none" stroke="#262b38" strokeWidth="18" />
        {total > 0 &&
          segments.map((seg) => {
            const len = (seg.value / total) * CIRC;
            const dash = <circle
              key={seg.label}
              cx="60"
              cy="60"
              r={R}
              fill="none"
              stroke={seg.color}
              strokeWidth="18"
              strokeDasharray={`${len} ${CIRC - len}`}
              strokeDashoffset={-offset}
            />;
            offset += len;
            return dash;
          })}
      </svg>
      {centerLabel && (
        <div className="absolute font-display text-xl font-medium text-text">{centerLabel}</div>
      )}
    </div>
  );
}

export function DonutLegend({ items }: { items: { label: string; value: number; color: string }[] }) {
  return (
    <div className="mt-3.5 flex flex-col gap-2 text-[12.5px] text-text-dim">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: it.color }} />
          {it.label}
          <b className="ml-auto font-semibold text-text">{it.value.toLocaleString("ru-RU")}</b>
        </div>
      ))}
    </div>
  );
}
