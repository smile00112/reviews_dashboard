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
      className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
    >
      <option value="public">public</option>
      <option value="operator_auth">operator_auth</option>
      <option value="public_http">public_http</option>
    </select>
  );
}
