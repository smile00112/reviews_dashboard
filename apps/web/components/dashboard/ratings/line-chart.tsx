/**
 * Minimal hand-rolled multi-series SVG line chart.
 *
 * Shared by the rating-trend and response-speed panels (feature 014). No chart
 * library — same constraint the overview donuts were built under.
 *
 * `null` points are treated as gaps: the path breaks rather than dropping to
 * zero, which would invent a data point that does not exist.
 */

export interface LineSeries {
  label: string;
  color: string;
  points: (number | null)[];
  /** Dashed stroke — used for p95 and the SLA target line. */
  dashed?: boolean;
  width?: number;
}

const W = 720;
const H = 260;
const PAD_L = 44;
const PAD_R = 12;
const PAD_T = 12;
const PAD_B = 28;

/** Nice-ish tick values across [min, max]. */
function ticks(min: number, max: number, count = 4): number[] {
  if (max === min) return [min];
  const step = (max - min) / count;
  return Array.from({ length: count + 1 }, (_, i) => min + step * i);
}

export function LineChart({
  labels,
  series,
  formatValue = (v) => String(v),
  /** Force the y-axis to include 0 (volume-like scales). */
  zeroBased = false,
  emptyMessage = "Нет данных за выбранный период",
}: {
  labels: string[];
  series: LineSeries[];
  formatValue?: (v: number) => string;
  zeroBased?: boolean;
  emptyMessage?: string;
}) {
  const values = series.flatMap((s) => s.points.filter((p): p is number => p !== null));

  if (labels.length === 0 || values.length === 0) {
    return <div className="py-16 text-center text-text-faint">{emptyMessage}</div>;
  }

  let min = zeroBased ? 0 : Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    // A flat series still deserves a readable band rather than a divide-by-zero.
    min = zeroBased ? 0 : min - 0.5;
    max = max + 0.5;
  } else if (!zeroBased) {
    const pad = (max - min) * 0.15;
    min -= pad;
    max += pad;
  }

  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;
  const x = (i: number) =>
    labels.length === 1 ? PAD_L + plotW / 2 : PAD_L + (i / (labels.length - 1)) * plotW;
  const y = (v: number) => PAD_T + plotH - ((v - min) / (max - min)) * plotH;

  // Break each series into contiguous runs so gaps stay gaps.
  const pathsFor = (s: LineSeries): string[] => {
    const runs: string[] = [];
    let current: string[] = [];
    s.points.forEach((p, i) => {
      if (p === null) {
        if (current.length) runs.push(current.join(" "));
        current = [];
        return;
      }
      current.push(`${current.length ? "L" : "M"}${x(i).toFixed(1)},${y(p).toFixed(1)}`);
    });
    if (current.length) runs.push(current.join(" "));
    return runs;
  };

  // With many buckets, thin the x labels so they stay legible.
  const labelStep = Math.max(1, Math.ceil(labels.length / 12));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[260px] w-full" role="img">
      {ticks(min, max).map((t, i) => (
        <g key={i}>
          <line
            x1={PAD_L}
            x2={W - PAD_R}
            y1={y(t)}
            y2={y(t)}
            stroke="#262b38"
            strokeWidth={1}
          />
          <text
            x={PAD_L - 8}
            y={y(t) + 3}
            textAnchor="end"
            className="fill-[#5a6175] font-mono"
            fontSize={9}
          >
            {formatValue(t)}
          </text>
        </g>
      ))}

      {labels.map((label, i) =>
        i % labelStep === 0 ? (
          <text
            key={label + i}
            x={x(i)}
            y={H - 8}
            textAnchor="middle"
            className="fill-[#5a6175] font-mono"
            fontSize={9}
          >
            {label}
          </text>
        ) : null,
      )}

      {series.map((s) =>
        pathsFor(s).map((d, i) => (
          <path
            key={`${s.label}-${i}`}
            d={d}
            fill="none"
            stroke={s.color}
            strokeWidth={s.width ?? 2.5}
            strokeDasharray={s.dashed ? "5 4" : undefined}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )),
      )}

      {/* Single-point series would otherwise be invisible (a path needs two points). */}
      {series.map((s) =>
        s.points.map((p, i) =>
          p !== null &&
          (s.points[i - 1] ?? null) === null &&
          (s.points[i + 1] ?? null) === null ? (
            <circle key={`${s.label}-dot-${i}`} cx={x(i)} cy={y(p)} r={3} fill={s.color} />
          ) : null,
        ),
      )}
    </svg>
  );
}

export function ChartLegend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap gap-3.5 text-[11px] text-text-dim">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: it.color }}
          />
          {it.label}
        </span>
      ))}
    </div>
  );
}
