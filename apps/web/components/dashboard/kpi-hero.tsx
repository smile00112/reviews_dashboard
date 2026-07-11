import type { KpiHero } from "@/lib/types";

function fmtDelta(v: number | null, unit = ""): { text: string; dir: "up" | "down" | "flat" } {
  if (v === null || v === undefined) return { text: "—", dir: "flat" };
  const dir = v > 0 ? "up" : v < 0 ? "down" : "flat";
  const arrow = v > 0 ? "▲" : v < 0 ? "▼" : "•";
  return { text: `${arrow} ${v > 0 ? "+" : ""}${v}${unit}`, dir };
}

const deltaColor = { up: "text-good", down: "text-bad", flat: "text-text-faint" } as const;

export function KpiHeroCards({ hero }: { hero: KpiHero }) {
  const ratingDelta = fmtDelta(hero.network_avg_rating_delta);
  return (
    <div className="mb-3 grid grid-cols-1 gap-4 md:grid-cols-3">
      {/* Средний рейтинг сети */}
      <div className="rounded-2xl border border-accent bg-gradient-to-br from-surface to-surface-2 p-6">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-dim">
          Средний рейтинг сети
        </div>
        <div className="my-3 font-display text-5xl font-medium leading-none tracking-tight text-accent">
          {hero.network_avg_rating ?? "—"}
        </div>
        <div className={`inline-flex items-center gap-1 font-mono text-[12.5px] ${deltaColor[ratingDelta.dir]}`}>
          {ratingDelta.text} {hero.network_avg_rating_delta !== null && "vs прошлый период"}
        </div>
        <div className="mt-2 border-t border-dashed border-border pt-2 font-mono text-[11.5px] text-text-dim">
          vs рынок: <span className="text-text-faint">нет данных</span>
        </div>
      </div>

      {/* Новых за период */}
      <div className="rounded-2xl border border-accent bg-gradient-to-br from-surface to-surface-2 p-6">
        <div className="text-xs font-semibold uppercase tracking-wide text-text-dim">Новых за период</div>
        <div className="my-3 font-display text-5xl font-medium leading-none tracking-tight text-accent">
          {hero.new_in_period}
        </div>
        <div className="inline-flex items-center gap-1 font-mono text-[12.5px] text-good">
          ▲ {hero.new_today} сегодня
        </div>
        <div className="mt-2 border-t border-dashed border-border pt-2 font-mono text-[11.5px] text-text-faint">
          {hero.total_reviews.toLocaleString("ru-RU")} всего · {hero.avg_per_day}/день в среднем
        </div>
      </div>

      {/* Без ответа */}
      <div className="rounded-2xl border border-accent bg-gradient-to-br from-surface to-surface-2 p-6">
        <div className="text-xs font-semibold uppercase tracking-wide text-text-dim">Без ответа</div>
        <div className="my-3 font-display text-5xl font-medium leading-none tracking-tight text-bad">
          {hero.unanswered_total}
        </div>
        <div className="inline-flex items-center gap-1 font-mono text-[12.5px] text-bad">
          ▲ +{hero.unanswered_delta_24h} за сутки
        </div>
        <div className="mt-2 border-t border-dashed border-border pt-2 font-mono text-[11.5px] text-text-dim">
          <span className="text-bad">{hero.overdue_24h}</span> просрочены &gt; 24ч{" "}
          <span className="text-text-faint">· требуют внимания</span>
        </div>
      </div>
    </div>
  );
}
