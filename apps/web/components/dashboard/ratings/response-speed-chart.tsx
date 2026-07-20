import type { ResponseSpeedBlock } from "@/lib/types";
import { Panel } from "../panel";
import { ChartLegend, LineChart } from "./line-chart";

/** `2026-W12` -> `нед. 12` */
function formatWeek(key: string): string {
  const week = key.split("-W")[1];
  return week ? `нед. ${Number(week)}` : key;
}

/** Minutes -> compact axis label (`45м`, `3.5ч`). */
function formatMinutes(v: number): string {
  if (v < 90) return `${Math.round(v)}м`;
  return `${(v / 60).toFixed(1)}ч`;
}

export function ResponseSpeedChart({ block }: { block: ResponseSpeedBlock }) {
  const sla = block.sla_target_minutes;
  const legend = [
    { label: "Медиана", color: "#d4ff3a" },
    { label: "p95", color: "#fbbf24" },
    { label: `SLA-цель: ${formatMinutes(sla)}`, color: "#5a6175" },
  ];

  return (
    <Panel
      title="Скорость ответа на отзывы"
      meta="Медиана и 95-й перцентиль · по неделям · сильный хвост ≠ плохое среднее"
      action={<ChartLegend items={legend} />}
    >
      <LineChart
        labels={block.labels.map(formatWeek)}
        series={[
          { label: "Медиана", color: "#d4ff3a", points: block.median_minutes, width: 3 },
          { label: "p95", color: "#fbbf24", points: block.p95_minutes, dashed: true },
          {
            label: "SLA",
            color: "#5a6175",
            // Constant target line, drawn across the same buckets.
            points: block.labels.map(() => sla),
            dashed: true,
            width: 1.5,
          },
        ]}
        formatValue={formatMinutes}
        zeroBased
        emptyMessage="Нет отвеченных отзывов за выбранный период"
      />
    </Panel>
  );
}
