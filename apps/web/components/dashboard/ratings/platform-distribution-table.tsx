import type { PlatformDistributionRow } from "@/lib/types";
import { Panel } from "../panel";

/** Prototype platform badges: colour + single-letter mark. */
const PLATFORM_BADGE: Record<string, { bg: string; fg: string; mark: string }> = {
  yandex: { bg: "#ffcc00", fg: "#000", mark: "Я" },
  google: { bg: "#4285f4", fg: "#fff", mark: "G" },
  gis2: { bg: "#2ecc71", fg: "#fff", mark: "2" },
};

const STAR_COLOR: Record<number, string> = {
  5: "#d4ff3a",
  4: "#9ae600",
  3: "#fbbf24",
  2: "#fb923c",
  1: "#f87171",
};

const STARS = [5, 4, 3, 2, 1];

/** Rating pill tone thresholds, matching the prototype's high/mid/low. */
function ratingTone(rating: number): string {
  if (rating >= 4.5) return "text-good";
  if (rating >= 4.0) return "text-warn";
  return "text-bad";
}

function NoData() {
  return <span className="text-text-faint">нет данных</span>;
}

export function PlatformDistributionTable({ rows }: { rows: PlatformDistributionRow[] }) {
  return (
    <Panel
      title="Распределение оценок по площадкам"
      meta="Сравнение долей 1–5★ для каждой площадки"
    >
      {rows.length === 0 ? (
        <div className="py-10 text-center text-text-faint">Нет данных за выбранный период</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr>
                {["", "Площадка", "Ср. рейтинг"].map((h) => (
                  <th
                    key={h || "logo"}
                    className="border-b border-border px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-text-faint"
                  >
                    {h}
                  </th>
                ))}
                {STARS.map((s) => (
                  <th
                    key={s}
                    className="border-b border-border px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-text-faint"
                  >
                    {s}★
                  </th>
                ))}
                {["Распределение", "Удалено"].map((h) => (
                  <th
                    key={h}
                    className="border-b border-border px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-text-faint"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const badge = PLATFORM_BADGE[row.platform] ?? {
                  bg: "#5a6175",
                  fg: "#fff",
                  mark: "?",
                };
                const byStar = new Map(row.stars?.map((s) => [s.star, s]) ?? []);
                return (
                  <tr key={row.platform} className="last:[&>td]:border-b-0">
                    <td className="border-b border-border px-3 py-3.5">
                      <div
                        className="flex h-7 w-7 items-center justify-center rounded-md font-display text-[13px] font-bold"
                        style={{ background: badge.bg, color: badge.fg }}
                      >
                        {badge.mark}
                      </div>
                    </td>
                    <td className="border-b border-border px-3 py-3.5">
                      <b className="font-semibold">{row.label}</b>
                      {row.total_reviews !== null && (
                        <div className="text-[11px] text-text-faint">
                          {row.total_reviews.toLocaleString("ru-RU")} отзывов
                        </div>
                      )}
                    </td>
                    <td className="border-b border-border px-3 py-3.5">
                      {row.avg_rating === null ? (
                        <NoData />
                      ) : (
                        <span
                          className={`inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-0.5 font-mono text-xs font-semibold ${ratingTone(
                            row.avg_rating,
                          )}`}
                        >
                          {row.avg_rating.toFixed(2)} ★
                        </span>
                      )}
                    </td>

                    {/* Per-star columns — a single «нет данных» spanning them all
                        when the platform stores no per-review rows. */}
                    {row.stars === null ? (
                      <td className="border-b border-border px-3 py-3.5" colSpan={STARS.length}>
                        <NoData />
                      </td>
                    ) : (
                      STARS.map((star) => (
                        <td
                          key={star}
                          className="border-b border-border px-3 py-3.5 font-mono text-xs"
                        >
                          {byStar.get(star)?.share ?? 0}%
                        </td>
                      ))
                    )}

                    <td className="border-b border-border px-3 py-3.5">
                      {row.stars === null ? (
                        <NoData />
                      ) : (
                        <div className="flex h-1.5 w-[100px] overflow-hidden rounded-[3px] bg-surface-3">
                          {STARS.map((star) => (
                            <span
                              key={star}
                              style={{
                                width: `${byStar.get(star)?.share ?? 0}%`,
                                background: STAR_COLOR[star],
                              }}
                            />
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="border-b border-border px-3 py-3.5 font-mono text-xs">
                      {row.removed_count === null ? (
                        <NoData />
                      ) : (
                        row.removed_count.toLocaleString("ru-RU")
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
