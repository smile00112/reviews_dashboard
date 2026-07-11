import type { SentimentBlock } from "@/lib/types";
import { Donut, DonutLegend } from "./donut";
import { Panel } from "./panel";

export function SentimentDonutPanel({ sentiment }: { sentiment: SentimentBlock }) {
  const segments = [
    { label: "Положительные", value: sentiment.positive, color: "#4ade80" },
    { label: "Нейтральные", value: sentiment.neutral, color: "#8b91a3" },
    { label: "Отрицательные", value: sentiment.negative, color: "#f87171" },
  ];
  return (
    <Panel title="Тональность отзывов" meta="Положит. / нейтр. / отриц.">
      <Donut segments={segments} centerLabel={`${sentiment.positive_percent}%`} />
      <DonutLegend
        items={[
          { label: "😊 Положительные", value: sentiment.positive, color: "#4ade80" },
          { label: "😐 Нейтральные", value: sentiment.neutral, color: "#8b91a3" },
          { label: "😞 Отрицательные", value: sentiment.negative, color: "#f87171" },
        ]}
      />
    </Panel>
  );
}
