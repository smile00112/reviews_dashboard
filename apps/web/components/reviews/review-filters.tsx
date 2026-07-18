"use client";

import type { Organization, ReviewPeriod, ReviewPlatform, ReviewTone, ReviewsSummary } from "@/lib/types";

export interface FeedFilterState {
  tone?: ReviewTone;
  period?: ReviewPeriod;
  platform?: ReviewPlatform;
  organizationId?: string;
  paidOnly?: boolean;
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[12px] transition-colors ${
        active
          ? "border-accent bg-surface-3 text-text"
          : "border-border bg-surface-2 text-text-dim hover:border-text-faint hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}

const PERIODS: { key: ReviewPeriod; label: string }[] = [
  { key: "24h", label: "24ч" },
  { key: "7d", label: "7д" },
  { key: "30d", label: "30д" },
  { key: "year", label: "Год" },
];

const PLATFORMS: { key: ReviewPlatform; label: string }[] = [
  { key: "yandex", label: "Я" },
  { key: "google", label: "G" },
  { key: "gis2", label: "2Г" },
];

export function ReviewFilters({
  tone,
  period,
  platform,
  organizationId,
  paidOnly,
  orgs,
  summary,
  onChange,
  onReset,
}: FeedFilterState & {
  orgs: Organization[];
  summary: ReviewsSummary | null;
  onChange: (patch: FeedFilterState) => void;
  onReset: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-surface-1 p-3 text-[12px]">
      <div className="flex items-center gap-1.5">
        <span className="text-text-faint">Тональность:</span>
        <Chip active={!tone} onClick={() => onChange({ tone: undefined })}>Все</Chip>
        <Chip active={tone === "neg"} onClick={() => onChange({ tone: "neg" })}>
          😞 Негатив 1–3★
          {summary && summary.negative > 0 && (
            <span className="rounded bg-bad/15 px-1 font-mono text-[10px] text-bad">{summary.negative}</span>
          )}
        </Chip>
        <Chip active={tone === "pos"} onClick={() => onChange({ tone: "pos" })}>😊 Позитив 4–5★</Chip>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-text-faint">Период:</span>
        {PERIODS.map((p) => (
          <Chip
            key={p.key}
            active={period === p.key}
            onClick={() => onChange({ period: period === p.key ? undefined : p.key })}
          >
            {p.label}
          </Chip>
        ))}
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-text-faint">Площадка:</span>
        <Chip active={!platform} onClick={() => onChange({ platform: undefined })}>Все</Chip>
        {PLATFORMS.map((p) => (
          <Chip key={p.key} active={platform === p.key} onClick={() => onChange({ platform: p.key })}>
            {p.label}
          </Chip>
        ))}
      </div>
      <select
        value={organizationId ?? ""}
        onChange={(e) => onChange({ organizationId: e.target.value || undefined })}
        className="rounded-lg border border-border bg-surface-2 px-2 py-1 text-[12px] text-text-dim"
      >
        <option value="">Все локации</option>
        {orgs.map((org) => (
          <option key={org.id} value={org.id}>
            {org.name ?? org.yandex_url ?? org.gis2_url ?? org.id}
          </option>
        ))}
      </select>
      <Chip active={!!paidOnly} onClick={() => onChange({ paidOnly: paidOnly ? undefined : true })}>
        💎 Покупные
      </Chip>
      <button type="button" onClick={onReset} className="ml-auto text-[12px] text-text-faint hover:text-text">
        Сбросить
      </button>
    </div>
  );
}
