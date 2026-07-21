import type { WeekdayBlock, WeekdayGrid } from "@/lib/types";
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

function WeekdayHeatmap({ grid }: { grid: WeekdayGrid }) {
  const maxCount = Math.max(
    1,
    ...grid.rows.flatMap((r) => r.cells.map((c) => c.count)),
  );

  return (
    <div className="overflow-x-auto">
      <div className="min-w-max">
        {/* Header row: blank corner + period labels */}
        <div
          className="grid gap-1.5"
          style={{
            gridTemplateColumns: `40px repeat(${grid.columns.length}, minmax(56px, 1fr))`,
          }}
        >
          <div />
          {grid.columns.map((col) => (
            <div
              key={col.key}
              className="pb-1 text-center font-mono text-[11px] uppercase text-text-faint"
            >
              {col.label}
            </div>
          ))}
        </div>

        {/* One grid row per weekday */}
        {grid.rows.map((row) => (
          <div
            key={row.weekday}
            className="mb-1.5 grid items-center gap-1.5"
            style={{
              gridTemplateColumns: `40px repeat(${grid.columns.length}, minmax(56px, 1fr))`,
            }}
          >
            <div className="font-mono text-xs font-semibold uppercase text-text-faint">
              {row.label}
            </div>
            {row.cells.map((cell, i) => {
              const empty = cell.avg_rating === null;
              // Intensity by volume: darker/stronger = more reviews.
              const intensity = empty ? 0 : 0.2 + 0.8 * (cell.count / maxCount);
              return (
                <div
                  key={grid.columns[i].key}
                  className="flex h-[34px] items-center justify-center rounded text-xs font-semibold"
                  title={
                    empty
                      ? "нет отзывов"
                      : `${row.label} · ${grid.columns[i].label}: ${cell.count.toLocaleString(
                          "ru-RU",
                        )} отз., ${cell.avg_rating!.toFixed(2)} ★`
                  }
                  style={{
                    background: empty ? "#1c2130" : ratingColor(cell.avg_rating!),
                    opacity: empty ? 0.4 : intensity,
                    color: empty ? "#4b5163" : "#0b0e14",
                  }}
                >
                  {empty ? "" : cell.avg_rating!.toFixed(1)}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Review volume and average rating per weekday.
 *
 * With a custom date range the block becomes a weekday x date-period heatmap
 * (prototype look); otherwise it stays a Mon-Sun bar chart. Reviews carry only
 * a calendar date (no posting time), so there is deliberately no hour-of-day
 * axis — the columns are periods of the selected range instead.
 */
export function WeekdayBreakdown({ block }: { block: WeekdayBlock }) {
  const grid = block.grid ?? null;
  const max = Math.max(1, ...block.days.map((d) => d.count));
  const hasBars = block.days.some((d) => d.count > 0);
  const hasGrid = grid !== null && grid.rows.some((r) => r.cells.some((c) => c.count > 0));

  const meta = grid
    ? "Строки — дни недели · столбцы — периоды диапазона · цвет — средний рейтинг"
    : "Длина полосы — количество отзывов · цвет — средний рейтинг";

  return (
    <Panel
      title="Оценки по дням недели"
      meta={meta}
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
      {grid ? (
        !hasGrid ? (
          <div className="py-10 text-center text-text-faint">
            Нет отзывов с датой за выбранный период
          </div>
        ) : (
          <>
            <WeekdayHeatmap grid={grid} />
            {grid.insight && (
              <div className="mt-4 rounded-lg border-l-[3px] border-accent bg-surface-2 px-3.5 py-3 text-[12.5px] text-text-dim">
                💡 {grid.insight}
              </div>
            )}
          </>
        )
      ) : !hasBars ? (
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
