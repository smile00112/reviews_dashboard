import type { TrendBlock } from "@/lib/types";
import { Panel } from "../panel";
import { ChartLegend, LineChart } from "./line-chart";
import { formatTrendLabel, granularityMeta } from "./trend-labels";

export function RatingTrendChart({ block }: { block: TrendBlock }) {
  return (
    <Panel
      title="Динамика среднего рейтинга"
      meta={`По площадкам, ${granularityMeta(block.granularity)}`}
      action={
        <ChartLegend items={block.series.map((s) => ({ label: s.label, color: s.color }))} />
      }
    >
      <LineChart
        labels={block.labels.map((l) => formatTrendLabel(l, block.granularity))}
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
