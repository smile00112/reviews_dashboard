import type { RatingDistribution } from "@/lib/types";
import { Panel } from "./panel";

const STAR_COLOR: Record<number, string> = {
  5: "#d4ff3a",
  4: "#9ae600",
  3: "#fbbf24",
  2: "#fb923c",
  1: "#f87171",
};

export function RatingDistributionPanel({ dist }: { dist: RatingDistribution }) {
  const max = Math.max(1, ...dist.bars.map((b) => b.count));
  return (
    <Panel title="Распределение оценок" meta={`За выбранный период · всего ${dist.total.toLocaleString("ru-RU")}`}>
      <div className="flex flex-col gap-2.5 py-2">
        {dist.bars.map((b) => (
          <div key={b.star} className="grid grid-cols-[32px_1fr_110px] items-center gap-3">
            <div className="font-mono text-xs font-semibold text-text-dim">{b.star}★</div>
            <div className="h-[18px] overflow-hidden rounded bg-surface-2">
              <div
                className="h-full rounded transition-[width] duration-500"
                style={{ width: `${(b.count / max) * 100}%`, background: STAR_COLOR[b.star] }}
              />
            </div>
            <div className="text-right font-mono text-xs">
              <b className="font-semibold text-text">{b.count.toLocaleString("ru-RU")}</b>{" "}
              <span className="ml-1 text-text-faint">{b.percent}%</span>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex justify-between border-t border-border pt-2.5 text-xs">
        <span className="text-text-faint">
          Доля 4–5★: <b className="font-semibold text-good">{dist.share_4_5}%</b>
        </span>
        <span className="text-text-faint">
          Доля 1–3★: <b className="font-semibold text-bad">{dist.share_1_3}%</b>
        </span>
      </div>
    </Panel>
  );
}
