import Link from "next/link";
import type { AttentionItem } from "@/lib/types";
import { Panel } from "./panel";

const ICON: Record<string, string> = {
  unanswered_overdue: "⏰",
  fresh_negative: "💢",
  escalated: "🔥",
  aspect_spike: "🚨",
  rating_drop: "📉",
};

function borderColor(severity: string): string {
  return severity === "urgent" ? "border-l-bad" : severity === "warn" ? "border-l-warn" : "border-l-info";
}

export function AttentionList({ items }: { items: AttentionItem[] }) {
  return (
    <Panel
      title="⚡ Требуют внимания за последние 24 часа"
      meta="События, которые нельзя пропустить · отсортировано по критичности"
      action={
        <div className="flex items-center gap-2">
          <Link
            href="/attention-rules"
            title="Настроить правила"
            aria-label="Настроить правила"
            className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-[13px] hover:bg-surface-3"
          >
            ⚙
          </Link>
          <Link href="/reviews" className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-[13px] hover:bg-surface-3">
            К отзывам →
          </Link>
        </div>
      }
    >
      {items.length === 0 ? (
        <div className="py-10 text-center text-text-faint">Нет событий, требующих внимания</div>
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((it, i) => (
            <Link
              key={`${it.type}-${i}`}
              href={it.link}
              className={`flex items-center gap-3 rounded-lg border-l-[3px] bg-surface-2 px-3.5 py-3 transition-colors hover:bg-surface-3 ${borderColor(it.severity)}`}
            >
              <span className="text-lg">{ICON[it.type] ?? "•"}</span>
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-semibold">{it.title}</div>
                <div className="text-xs text-text-dim">{it.subtitle}</div>
              </div>
              <span className="font-mono text-sm font-bold text-bad">{it.value}</span>
              <span className="text-text-faint">→</span>
            </Link>
          ))}
        </div>
      )}
    </Panel>
  );
}
