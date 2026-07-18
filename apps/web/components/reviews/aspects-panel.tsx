"use client";

import type { AspectsResponse } from "@/lib/types";
import { Panel } from "@/components/dashboard/panel";

function SentimentBar({ pos, neu, neg }: { pos: number; neu: number; neg: number }) {
  const total = pos + neu + neg || 1;
  const w = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className="inline-flex h-2 w-[100px] overflow-hidden rounded bg-surface-3">
      <div className="h-full bg-good" style={{ width: w(pos) }} />
      <div className="h-full bg-text-faint" style={{ width: w(neu) }} />
      <div className="h-full bg-bad" style={{ width: w(neg) }} />
    </div>
  );
}

function Delta({ value }: { value: number | null }) {
  if (value === null) return <span className="text-text-faint">новый</span>;
  if (value === 0) return <span className="text-text-faint">— 0%</span>;
  // Growth of complaint mentions is bad, decline is good.
  return (
    <span className={value > 0 ? "text-bad" : "text-good"}>
      {value > 0 ? "▲ +" : "▼ "}
      {value}%
    </span>
  );
}

function TrendChart({ series }: { series: { date: string; count: number }[] }) {
  const max = Math.max(...series.map((p) => p.count), 1);
  const W = 460;
  const H = 80;
  const step = W / (series.length - 1 || 1);
  const points = series
    .map((p, i) => `${(i * step).toFixed(1)},${(H - (p.count / max) * (H - 6) - 3).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[90px] w-full" preserveAspectRatio="none" role="img">
      <polyline points={points} fill="none" stroke="#d4ff3a" strokeWidth="1.5" />
    </svg>
  );
}

export function AspectsPanel({
  data,
  activeAspect,
  onAspect,
}: {
  data: AspectsResponse | null;
  activeAspect: string | null;
  onAspect: (category: string | null) => void;
}) {
  return (
    <Panel title="Аспектный анализ" meta="Привязан к фильтру периода · клик по строке → фильтр ленты">
      {!data || data.aspects.length === 0 ? (
        <div className="py-10 text-center text-text-faint">Нет данных за период</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-[11px] uppercase tracking-wider text-text-faint">
                <th className="border-b border-border px-3 py-2.5 text-left">Аспект</th>
                <th className="border-b border-border px-3 py-2.5 text-left">Упом.</th>
                <th className="border-b border-border px-3 py-2.5 text-left">Δ за период</th>
                <th className="border-b border-border px-3 py-2.5 text-left">Тональность</th>
              </tr>
            </thead>
            <tbody>
              {data.aspects.map((a) => (
                <tr
                  key={a.category}
                  onClick={() => onAspect(activeAspect === a.category ? null : a.category)}
                  className={`cursor-pointer hover:bg-surface-2 ${
                    activeAspect === a.category ? "bg-surface-2" : ""
                  }`}
                  title="Кликните, чтобы отфильтровать ленту"
                >
                  <td className="border-b border-border px-3 py-3 font-semibold">{a.label}</td>
                  <td className="border-b border-border px-3 py-3">{a.mentions}</td>
                  <td className="border-b border-border px-3 py-3 font-mono text-[11px]">
                    <Delta value={a.delta_pct} />
                  </td>
                  <td className="border-b border-border px-3 py-3">
                    <SentimentBar pos={a.pos} neu={a.neu} neg={a.neg} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-3.5 flex flex-wrap gap-3.5 text-[11px] text-text-dim">
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-good align-middle" />Позитив</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-text-faint align-middle" />Нейтрально</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-bad align-middle" />Негатив</span>
      </div>
      {data?.trend && (
        <div className="mt-4 rounded-lg border border-border bg-surface-2 p-3">
          <div className="mb-1 flex items-center justify-between text-[12px]">
            <span className="font-semibold">
              Динамика «{data.aspects.find((a) => a.category === data.trend!.category)?.label ?? data.trend.category}» за 90 дней
            </span>
          </div>
          <TrendChart series={data.trend.series} />
        </div>
      )}
    </Panel>
  );
}
