import type { TrendBlock } from "@/lib/types";
import { Panel } from "../panel";
import { ChartLegend } from "./line-chart";
import { formatMonth } from "./rating-trend-chart";

const W = 720;
const H = 260;
const PAD_L = 44;
const PAD_R = 12;
const PAD_T = 12;
const PAD_B = 28;

/**
 * Stacked review-volume bars per month (feature 014).
 *
 * Review counts across platforms are additive, so stacking is honest here —
 * unlike the rating trend, where stacking averages would be meaningless.
 * A `null` point means "no snapshot that month" and contributes nothing to the
 * stack rather than counting as 0.
 */
export function VolumeTrendChart({ block }: { block: TrendBlock }) {
  const totals = block.labels.map((_, i) =>
    block.series.reduce((sum, s) => sum + (s.points[i] ?? 0), 0),
  );
  const max = Math.max(1, ...totals);

  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;
  const n = block.labels.length;
  const slot = n ? plotW / n : plotW;
  const barW = Math.min(38, slot * 0.6);
  const labelStep = Math.max(1, Math.ceil(n / 12));

  const hasData = n > 0 && totals.some((t) => t > 0);

  return (
    <Panel
      title="Количество отзывов по площадкам"
      meta="Накопительная диаграмма · по месяцам"
      action={
        <ChartLegend items={block.series.map((s) => ({ label: s.label, color: s.color }))} />
      }
    >
      {!hasData ? (
        <div className="py-16 text-center text-text-faint">
          История отзывов ещё накапливается
        </div>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="h-[260px] w-full" role="img">
          {Array.from({ length: 5 }, (_, i) => {
            const v = (max / 4) * i;
            const y = PAD_T + plotH - (v / max) * plotH;
            return (
              <g key={i}>
                <line x1={PAD_L} x2={W - PAD_R} y1={y} y2={y} stroke="#262b38" strokeWidth={1} />
                <text
                  x={PAD_L - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-[#5a6175] font-mono"
                  fontSize={9}
                >
                  {Math.round(v).toLocaleString("ru-RU")}
                </text>
              </g>
            );
          })}

          {block.labels.map((label, i) => {
            const cx = PAD_L + slot * i + slot / 2;
            let cursor = PAD_T + plotH;
            return (
              <g key={label}>
                {block.series.map((s) => {
                  const v = s.points[i] ?? 0;
                  if (v <= 0) return null;
                  const h = (v / max) * plotH;
                  cursor -= h;
                  return (
                    <rect
                      key={s.platform}
                      x={cx - barW / 2}
                      y={cursor}
                      width={barW}
                      height={h}
                      fill={s.color}
                      rx={2}
                    />
                  );
                })}
                {i % labelStep === 0 && (
                  <text
                    x={cx}
                    y={H - 8}
                    textAnchor="middle"
                    className="fill-[#5a6175] font-mono"
                    fontSize={9}
                  >
                    {formatMonth(label)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
    </Panel>
  );
}
