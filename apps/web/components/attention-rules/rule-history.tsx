"use client";

import { useEffect, useState } from "react";
import { getAttentionRuleEvents } from "@/lib/api";
import type { AttentionEvent } from "@/lib/types";

function formatFired(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function RuleHistory({ ruleId }: { ruleId: string }) {
  const [events, setEvents] = useState<AttentionEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getAttentionRuleEvents(ruleId)
      .then((items) => {
        if (alive) setEvents(items);
      })
      .catch((err) => {
        if (alive) setError((err as Error).message);
      });
    return () => {
      alive = false;
    };
  }, [ruleId]);

  if (error) return <div className="text-xs text-bad">{error}</div>;
  if (events === null) return <div className="text-xs text-text-faint">Загрузка истории…</div>;
  if (events.length === 0) {
    return <div className="text-xs text-text-faint">Правило ещё ни разу не срабатывало.</div>;
  }

  // Группируем строки одного срабатывания по fired_at.
  const groups = new Map<string, AttentionEvent[]>();
  for (const ev of events) {
    const bucket = groups.get(ev.fired_at) ?? [];
    bucket.push(ev);
    groups.set(ev.fired_at, bucket);
  }

  return (
    <div className="space-y-2" data-testid="rule-history">
      <div className="text-xs font-semibold uppercase text-text-faint">История срабатываний</div>
      {[...groups.entries()].map(([firedAt, items]) => (
        <div key={firedAt} className="rounded border border-border/60 bg-surface px-3 py-2">
          <div className="text-[11px] text-text-faint">{formatFired(firedAt)}</div>
          <ul className="mt-1 space-y-0.5">
            {items.map((ev) => (
              <li key={ev.id} className="flex items-baseline justify-between gap-3 text-xs">
                <span className="text-text-dim">{ev.title}</span>
                <span className="font-mono text-bad">{ev.value}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
