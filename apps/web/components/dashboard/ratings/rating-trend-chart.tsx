import type { TrendBlock } from "@/lib/types";
import { Panel } from "../panel";
import { ChartLegend, LineChart } from "./line-chart";

/** `2026-03` -> `мар 26` */
const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

export function formatMonth(key: string): string {
  const [year, month] = key.split("-");
  const idx = Number(month) - 1;
  if (!MONTHS[idx]) return key;
  return `${MONTHS[idx]} ${year.slice(2)}`;
}

export function RatingTrendChart({ block }: { block: TrendBlock }) {
  return (
    <Panel
      title="Динамика среднего рейтинга"
      meta="По площадкам, по месяцам"
      action={
        <ChartLegend items={block.series.map((s) => ({ label: s.label, color: s.color }))} />
      }
    >
      <LineChart
        labels={block.labels.map(formatMonth)}
        series={block.series.map((s) => ({
          label: s.label,
          color: s.color,
          points: s.points,
        }))}
        formatValue={(v) => v.toFixed(1)}
        emptyMessage="История рейтингов ещё накапливается"
      />
    </Panel>
  );
}
