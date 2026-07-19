"use client";

import type { ScrapeMode } from "@/lib/types";

interface ModeSelectProps {
  value: ScrapeMode;
  onChange: (value: ScrapeMode) => void;
  id?: string;
}

export function ModeSelect({ value, onChange, id }: ModeSelectProps) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value as ScrapeMode)}
      className="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-[13px] text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <option value="public">public</option>
      <option value="operator_auth">operator_auth</option>
      <option value="public_http">public_http</option>
      <option value="scrapeops">scrapeops</option>
      <option value="twogis_api">twogis_api</option>
    </select>
  );
}
