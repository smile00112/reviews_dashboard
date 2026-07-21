import Link from "next/link";
import type { WorstLocation } from "@/lib/types";
import { Panel } from "./panel";

function ratingClass(r: number | null): { pill: string; health: string } {
  if (r === null) return { pill: "text-text-faint", health: "bg-text-faint" };
  if (r < 4.0) return { pill: "text-bad", health: "bg-bad" };
  if (r < 4.3) return { pill: "text-warn", health: "bg-warn" };
  return { pill: "text-good", health: "bg-good" };
}

export function WorstLocationsTable({ rows }: { rows: WorstLocation[] }) {
  return (
    <Panel
      title="🔻 Топ-10 худших точек"
      meta="Требуют управленческой реакции · клик — карточка точки"
      action={
        <Link href="/organizations" className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-[13px] hover:bg-surface-3">
          Все →
        </Link>
      }
    >
      {rows.length === 0 ? (
        <div className="py-10 text-center text-text-faint">Нет данных</div>
      ) : (
        <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-text-faint">
              <th className="border-b border-border px-3 py-2.5 text-left"></th>
              <th className="border-b border-border px-3 py-2.5 text-left">Город</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Точка</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Рейтинг</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Δ</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Без ответа</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const c = ratingClass(r.rating);
              return (
                <tr key={r.organization_id} className="cursor-pointer hover:bg-surface-2">
                  <td className="border-b border-border px-3 py-3.5">
                    <span className={`inline-block h-[22px] w-1 rounded ${c.health}`} />
                  </td>
                  <td className="border-b border-border px-3 py-3.5 text-text-dim">
                    <Link href={`/organizations/${r.organization_id}`}>{r.city ?? "—"}</Link>
                  </td>
                  <td className="border-b border-border px-3 py-3.5">
                    <Link href={`/organizations/${r.organization_id}`}>{r.name ?? "без названия"}</Link>
                  </td>
                  <td className="border-b border-border px-3 py-3.5">
                    <span className={`inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-0.5 font-mono text-xs font-semibold ${c.pill}`}>
                      {r.rating ?? "—"} ★
                    </span>
                  </td>
                  <td className="border-b border-border px-3 py-3.5 font-mono text-[11px]">
                    {r.rating_delta === null ? (
                      <span className="text-text-faint">—</span>
                    ) : r.rating_delta === 0 ? (
                      <span className="text-text-faint">• 0</span>
                    ) : (
                      <span className={r.rating_delta < 0 ? "text-bad" : "text-good"}>
                        {r.rating_delta < 0 ? "▼ −" : "▲ +"}
                        {Math.abs(r.rating_delta).toFixed(1)}
                      </span>
                    )}
                  </td>
                  <td className="border-b border-border px-3 py-3.5 font-semibold">
                    {r.unanswered_count > 0 ? (
                      <span className="text-bad">{r.unanswered_count}</span>
                    ) : (
                      r.unanswered_count
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}
    </Panel>
  );
}
