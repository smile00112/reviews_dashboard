"use client";

import { useState } from "react";
import type { TrendBlock } from "@/lib/types";
import { Panel } from "../panel";
import { ChartLegend } from "./line-chart";
import { formatTrendLabel, granularityMeta } from "./trend-labels";

const W = 720;
const H = 260;
const PAD_L = 44;
const PAD_R = 12;
const PAD_T = 12;
const PAD_B = 28;
const TOOLTIP_W = 148;

/**
 * Stacked review-volume bars per bucket (feature 014, granularity added later).
 *
 * Review counts across platforms are additive, so stacking is honest here —
 * unlike the rating trend, where stacking averages would be meaningless.
 * A `null` point means "no snapshot in that bucket" and contributes nothing to
 * the stack rather than counting as 0.
 */
export function VolumeTrendChart({ block }: { block: TrendBlock }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

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
      meta={`Накопительная диаграмма · ${granularityMeta(block.granularity)}`}
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
            const hovered = hoverIndex === i;
            return (
              <g key={label}>
                {hovered && (
                  <rect
                    x={PAD_L + slot * i}
                    y={PAD_T}
                    width={slot}
                    height={plotH}
                    fill="#ffffff"
                    opacity={0.04}
                  />
                )}
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
                      opacity={hovered ? 1 : 0.9}
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
                    {formatTrendLabel(label, block.granularity)}
                  </text>
                )}
                {/* Hit target spans the full plot height, not just the bar — short
                    bars would otherwise be hard to hover precisely. */}
                <rect
                  x={PAD_L + slot * i}
                  y={PAD_T}
                  width={slot}
                  height={plotH}
                  fill="transparent"
                  tabIndex={0}
                  onMouseEnter={() => setHoverIndex(i)}
                  onMouseLeave={() => setHoverIndex(null)}
                  onFocus={() => setHoverIndex(i)}
                  onBlur={() => setHoverIndex(null)}
                />
              </g>
            );
          })}

          {hoverIndex !== null && (
            <VolumeTooltip
              label={formatTrendLabel(block.labels[hoverIndex], block.granularity)}
              series={block.series}
              index={hoverIndex}
              total={totals[hoverIndex]}
              cx={PAD_L + slot * hoverIndex + slot / 2}
            />
          )}
        </svg>
      )}
    </Panel>
  );
}

function VolumeTooltip({
  label,
  series,
  index,
  total,
  cx,
}: {
  label: string;
  series: TrendBlock["series"];
  index: number;
  total: number;
  cx: number;
}) {
  const rows = series.filter((s) => (s.points[index] ?? 0) > 0);
  const height = 30 + rows.length * 16 + 8;
  const x = Math.min(Math.max(cx - TOOLTIP_W / 2, PAD_L), W - PAD_R - TOOLTIP_W);
  const y = PAD_T + 4;

  return (
    <foreignObject x={x} y={y} width={TOOLTIP_W} height={height} style={{ pointerEvents: "none" }}>
      <div className="rounded-lg border border-border bg-surface-2 px-2.5 py-2 text-[10px] shadow-lg">
        <div className="mb-1 font-mono text-[9px] text-text-faint">{label}</div>
        {rows.map((s) => (
          <div key={s.platform} className="flex items-center justify-between gap-2 py-0.5">
            <span className="flex items-center gap-1.5 text-text-dim">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
            <span className="font-mono text-text">
              {(s.points[index] ?? 0).toLocaleString("ru-RU")}
            </span>
          </div>
        ))}
        <div className="mt-1 flex items-center justify-between gap-2 border-t border-border pt-1 font-mono text-text">
          <span className="text-text-faint">Всего</span>
          <span>{total.toLocaleString("ru-RU")}</span>
        </div>
      </div>
    </foreignObject>
  );
}
