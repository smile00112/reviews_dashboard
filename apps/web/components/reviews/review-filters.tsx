"use client";

import { useEffect, useRef } from "react";
import type {
  Company,
  Organization,
  ReviewPeriod,
  ReviewPlatform,
  ReviewTone,
  ReviewsSummary,
} from "@/lib/types";
import { DateRangePicker } from "@/components/dashboard/date-range-picker";
import { branchLabel } from "@/lib/org-label";

export interface FeedFilterState {
  tone?: ReviewTone;
  period?: ReviewPeriod;
  platform?: ReviewPlatform;
  organizationId?: string;
  companyId?: string;
  dateFrom?: string;
  dateTo?: string;
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
  companyId,
  dateFrom,
  dateTo,
  paidOnly,
  orgs,
  companies,
  summary,
  onChange,
  onReset,
}: FeedFilterState & {
  orgs: Organization[];
  companies: Company[];
  summary: ReviewsSummary | null;
  onChange: (patch: FeedFilterState) => void;
  onReset: () => void;
}) {
  const companyRef = useRef<HTMLDetailsElement>(null);

  // Native <details> doesn't close on an outside click — do it ourselves.
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      const target = e.target as Node;
      if (companyRef.current && !companyRef.current.contains(target)) {
        companyRef.current.open = false;
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const sortedCompanies = [...companies].sort((a, b) => a.name.localeCompare(b.name, "ru"));

  const companyById = new Map(companies.map((c) => [c.id, c]));
  const orgLabel = (org: Organization) => branchLabel(org, companyById);

  // A brand narrows the location list to its own branches (like /overview).
  const visibleOrgs = (companyId ? orgs.filter((o) => o.company_id === companyId) : orgs)
    .slice()
    .sort((a, b) => orgLabel(a).localeCompare(orgLabel(b), "ru"));
  const companyLabel = companies.find((c) => c.id === companyId)?.name ?? "Все бренды";
  const rangeActive = Boolean(dateFrom && dateTo);

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
            active={period === p.key && !rangeActive}
            // Picking a preset drops any custom range.
            onClick={() =>
              onChange({
                period: period === p.key ? undefined : p.key,
                dateFrom: undefined,
                dateTo: undefined,
              })
            }
          >
            {p.label}
          </Chip>
        ))}
        <DateRangePicker
          from={dateFrom ?? null}
          to={dateTo ?? null}
          active={rangeActive}
          // Applying a range drops the preset period.
          onApply={(from, to) => onChange({ period: undefined, dateFrom: from, dateTo: to })}
        />
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
      <details ref={companyRef} className="relative">
        <summary
          className={`inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[12px] ${
            companyId
              ? "border-accent bg-surface-3 text-text"
              : "border-border bg-surface-2 text-text-dim hover:text-text"
          }`}
        >
          {companyLabel} ▾
        </summary>
        <div className="absolute left-0 z-50 mt-1 max-h-80 w-64 overflow-y-auto rounded-lg border border-border bg-surface p-2 shadow-xl">
          <button
            type="button"
            onClick={() => {
              onChange({ companyId: undefined });
              if (companyRef.current) companyRef.current.open = false;
            }}
            className="mb-1 w-full rounded px-2 py-1.5 text-left text-[12px] text-text-dim hover:bg-surface-2"
          >
            Сбросить · все бренды
          </button>
          {sortedCompanies.map((c) => (
            <label
              key={c.id}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-[12.5px] hover:bg-surface-2"
            >
              <input
                type="radio"
                name="reviews-company"
                className="accent-accent"
                checked={companyId === c.id}
                onChange={() => {
                  onChange({ companyId: c.id });
                  if (companyRef.current) companyRef.current.open = false;
                }}
              />
              <span className="truncate">{c.name}</span>
            </label>
          ))}
          {companies.length === 0 && (
            <p className="px-2 py-1.5 text-[12px] text-text-faint">Брендов пока нет</p>
          )}
        </div>
      </details>
      <select
        value={organizationId ?? ""}
        onChange={(e) => onChange({ organizationId: e.target.value || undefined })}
        className="rounded-lg border border-border bg-surface-2 px-2 py-1 text-[12px] text-text-dim"
      >
        <option value="">Все локации</option>
        {visibleOrgs.map((org) => (
          <option key={org.id} value={org.id}>
            {orgLabel(org)}
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
