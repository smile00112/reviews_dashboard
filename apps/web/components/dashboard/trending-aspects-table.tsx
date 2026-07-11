import type { TrendingAspect } from "@/lib/types";
import { Panel } from "./panel";

function SentimentBar({ s }: { s: { pos: number; neu: number; neg: number } }) {
  const total = s.pos + s.neu + s.neg || 1;
  const w = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className="inline-flex h-2 w-[100px] overflow-hidden rounded bg-surface-3">
      <div className="h-full bg-good" style={{ width: w(s.pos) }} />
      <div className="h-full bg-text-faint" style={{ width: w(s.neu) }} />
      <div className="h-full bg-bad" style={{ width: w(s.neg) }} />
    </div>
  );
}

export function TrendingAspectsTable({ aspects }: { aspects: TrendingAspect[] }) {
  return (
    <Panel
      title="🔥 Аспекты с ростом негатива"
      meta="Что чаще всего вызывает жалобы · последние 7 дней vs предыдущие"
    >
      {aspects.length === 0 ? (
        <div className="py-10 text-center text-text-faint">Нет данных за период</div>
      ) : (
        <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-text-faint">
              <th className="border-b border-border px-3 py-2.5 text-left">Аспект</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Упом.</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Δ за неделю</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Тональность</th>
            </tr>
          </thead>
          <tbody>
            {aspects.map((a) => (
              <tr key={a.category} className="hover:bg-surface-2">
                <td className="border-b border-border px-3 py-3.5 font-semibold capitalize">{a.category}</td>
                <td className="border-b border-border px-3 py-3.5">{a.mentions}</td>
                <td className="border-b border-border px-3 py-3.5 font-mono text-[11px]">
                  {a.change_percent === null ? (
                    <span className="text-text-faint">новый</span>
                  ) : (
                    <span className={a.change_percent > 0 ? "text-bad" : "text-good"}>
                      {a.change_percent > 0 ? "▲ +" : "▼ "}
                      {a.change_percent}%
                    </span>
                  )}
                </td>
                <td className="border-b border-border px-3 py-3.5">
                  <SentimentBar s={a.sentiment} />
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
    </Panel>
  );
}
