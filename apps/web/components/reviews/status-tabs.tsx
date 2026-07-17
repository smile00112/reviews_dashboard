"use client";

import type { ReviewsSummary, StatusTab } from "@/lib/types";

const TABS: { key: StatusTab; label: string; count: (s: ReviewsSummary) => number; danger?: boolean }[] = [
  { key: "all", label: "Все", count: (s) => s.total },
  { key: "unanswered", label: "Не отвечено", count: (s) => s.unanswered, danger: true },
  { key: "in_progress", label: "В работе", count: (s) => s.in_progress },
  { key: "escalated", label: "Эскалированные", count: (s) => s.escalated, danger: true },
  { key: "answered", label: "Отвечено", count: (s) => s.answered },
];

export function StatusTabs({
  tab,
  summary,
  onTab,
}: {
  tab: StatusTab;
  summary: ReviewsSummary | null;
  onTab: (tab: StatusTab) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {TABS.map((t) => {
        const active = tab === t.key;
        const count = summary ? t.count(summary) : null;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onTab(t.key)}
            className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2.5 text-[13px] font-medium transition-colors ${
              active
                ? "border-accent bg-surface-3 text-text"
                : "border-border bg-surface-2 text-text-dim hover:border-text-faint hover:text-text"
            }`}
          >
            {t.label}
            {count !== null && (
              <span
                className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${
                  t.danger && count > 0 ? "bg-bad/15 text-bad" : "bg-surface-3 text-text-faint"
                }`}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
