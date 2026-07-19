"use client";

import { useEffect, useRef, useState } from "react";

/** dd.mm.yyyy from an ISO `YYYY-MM-DD` (no Date parsing — avoids TZ shifts). */
function short(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y.slice(2)}`;
}

/**
 * "Произвольный диапазон" control: replaces the old «Всё время» chip.
 * Both bounds are inclusive calendar days; Apply stays disabled until the pair
 * is complete and ordered, so the API never sees a request it would 422.
 */
export function DateRangePicker({
  from,
  to,
  active,
  onApply,
}: {
  from: string | null;
  to: string | null;
  active: boolean;
  onApply: (from: string, to: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draftFrom, setDraftFrom] = useState(from ?? "");
  const [draftTo, setDraftTo] = useState(to ?? "");
  const boxRef = useRef<HTMLDivElement>(null);

  // Reopening always starts from what is currently applied.
  useEffect(() => {
    setDraftFrom(from ?? "");
    setDraftTo(to ?? "");
  }, [from, to]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const missing = !draftFrom || !draftTo;
  const inverted = !missing && draftFrom > draftTo;
  const error = inverted ? "«От» не может быть позже «до»" : null;

  const label =
    active && from && to ? `${short(from)} — ${short(to)}` : "Произвольный диапазон";

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors ${
          active
            ? "border-accent bg-surface-3 text-text"
            : "border-border bg-surface-2 text-text-dim hover:border-text-faint hover:text-text"
        }`}
      >
        {label} ▾
      </button>
      {open && (
        <div className="absolute left-0 z-50 mt-1 w-64 rounded-lg border border-border bg-surface p-3 shadow-xl">
          <label className="mb-2 block text-[12px] text-text-dim">
            От
            <input
              type="date"
              value={draftFrom}
              max={draftTo || undefined}
              onChange={(e) => setDraftFrom(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-surface-2 px-2 py-1.5 text-[12.5px] text-text"
            />
          </label>
          <label className="mb-2 block text-[12px] text-text-dim">
            До
            <input
              type="date"
              value={draftTo}
              min={draftFrom || undefined}
              onChange={(e) => setDraftTo(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-surface-2 px-2 py-1.5 text-[12.5px] text-text"
            />
          </label>
          {error && <p className="mb-2 text-[11.5px] text-bad">{error}</p>}
          <button
            type="button"
            disabled={missing || inverted}
            onClick={() => {
              onApply(draftFrom, draftTo);
              setOpen(false);
            }}
            className="w-full rounded border border-accent bg-surface-3 px-2 py-1.5 text-[12.5px] text-text disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-text-faint"
          >
            Применить
          </button>
        </div>
      )}
    </div>
  );
}
