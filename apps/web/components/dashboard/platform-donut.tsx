import type { PlatformCount } from "@/lib/types";
import { Donut, DonutLegend } from "./donut";
import { Panel } from "./panel";

const META: Record<string, { label: string; color: string }> = {
  yandex: { label: "📍 Яндекс Карты", color: "#ffcc00" },
  gis2: { label: "📍 2ГИС", color: "#2ecc71" },
  google: { label: "📍 Google Business", color: "#4285f4" },
};

export function PlatformDonutPanel({ breakdown }: { breakdown: PlatformCount[] }) {
  const items = breakdown.map((p) => ({
    label: META[p.platform]?.label ?? p.platform,
    value: p.review_count,
    color: META[p.platform]?.color ?? "#8b91a3",
  }));
  return (
    <Panel title="Отзывы по каталогам" meta="Распределение по площадкам">
      <Donut segments={items} />
      <DonutLegend items={items} />
    </Panel>
  );
}
