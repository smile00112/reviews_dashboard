import type { WeekdayBlock } from "@/lib/types";
import { Panel } from "../panel";

/** Colour by average rating, matching the prototype's heatmap legend. */
function ratingColor(rating: number): string {
  if (rating >= 4.5) return "#d4ff3a";
  if (rating >= 4.0) return "#fbbf24";
  return "#f87171";
}

const LEGEND = [
  { label: "≤ 4.0", color: "#f87171" },
  { label: "4.0–4.5", color: "#fbbf24" },
  { label: "≥ 4.5", color: "#d4ff3a" },
];

/**
 * Review volume and average rating per weekday.
 *
 * The prototype drew a weekday x time-of-day grid; reviews carry only a
 * calendar date (no posting time), so the time axis is deliberately absent
 * rather than filled with invented data.
 */
export function WeekdayBreakdown({ block }: { block: WeekdayBlock }) {
  const max = Math.max(1, ...block.days.map((d) => d.count));
  const hasData = block.days.some((d) => d.count > 0);

  return (
    <Panel
      title="Оценки по дням недели"
      meta="Длина полосы — количество отзывов · цвет — средний рейтинг"
      action={
        <div className="flex flex-wrap gap-3.5 text-[11px] text-text-dim">
          {LEGEND.map((l) => (
            <span key={l.label} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: l.color }}
              />
              {l.label}
            </span>
          ))}
        </div>
      }
    >
      {!hasData ? (
        <div className="py-10 text-center text-text-faint">
          Нет отзывов с датой за выбранный период
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-1.5 py-1.5">
            {block.days.map((day) => (
              <div
                key={day.weekday}
                className="grid grid-cols-[40px_1fr_120px] items-center gap-3"
              >
                <div className="font-mono text-xs font-semibold uppercase text-text-faint">
                  {day.label}
                </div>
                <div className="h-[26px] overflow-hidden rounded bg-surface-2">
                  <div
                    className="h-full rounded transition-[width] duration-500"
                    style={{
                      width: `${(day.count / max) * 100}%`,
                      background:
                        day.avg_rating === null ? "#2a3041" : ratingColor(day.avg_rating),
                      opacity: day.avg_rating === null ? 0.5 : 0.85,
                    }}
                  />
                </div>
                <div className="text-right font-mono text-xs">
                  <b className="font-semibold text-text">
                    {day.count.toLocaleString("ru-RU")}
                  </b>
                  <span className="ml-2 text-text-faint">
                    {day.avg_rating === null ? "—" : `${day.avg_rating.toFixed(2)} ★`}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {block.insight && (
            <div className="mt-4 rounded-lg border-l-[3px] border-accent bg-surface-2 px-3.5 py-3 text-[12.5px] text-text-dim">
              💡 {block.insight}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
