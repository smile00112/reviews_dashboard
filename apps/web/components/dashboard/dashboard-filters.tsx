"use client";

import type { Company, Organization, OverviewPeriod, OverviewPlatform } from "@/lib/types";
import { DateRangePicker } from "@/components/dashboard/date-range-picker";

// «Всё время» is gone (feature 013) — its slot belongs to the custom range control.
const PERIODS: { key: OverviewPeriod; label: string }[] = [
  { key: "day", label: "День" },
  { key: "week", label: "Неделя" },
  { key: "30d", label: "30 дней" },
  { key: "90d", label: "90 дней" },
  { key: "year", label: "Год" },
];

const PLATFORMS: { key: OverviewPlatform; label: string }[] = [
  { key: "all", label: "Все площадки" },
  { key: "yandex", label: "Яндекс" },
  { key: "google", label: "Google" },
  { key: "gis2", label: "2ГИС" },
];

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
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors ${
        active
          ? "border-accent bg-surface-3 text-text"
          : "border-border bg-surface-2 text-text-dim hover:border-text-faint hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}

export function DashboardFilters({
  period,
  platform,
  orgIds,
  orgs,
  companies,
  companyId,
  dateFrom,
  dateTo,
  onPeriod,
  onPlatform,
  onRange,
  onCompany,
  onToggleOrg,
  onClearOrgs,
}: {
  period: OverviewPeriod;
  platform: OverviewPlatform;
  orgIds: string[];
  orgs: Organization[];
  companies: Company[];
  companyId: string | null;
  dateFrom: string | null;
  dateTo: string | null;
  onPeriod: (p: OverviewPeriod) => void;
  onPlatform: (p: OverviewPlatform) => void;
  onRange: (from: string, to: string) => void;
  onCompany: (id: string | null) => void;
  onToggleOrg: (id: string) => void;
  onClearOrgs: () => void;
}) {
  const selected = new Set(orgIds);
  // Picking a brand narrows the branch list to that brand's locations (FR-009).
  const visibleOrgs = companyId ? orgs.filter((o) => o.company_id === companyId) : orgs;
  const orgLabel =
    orgIds.length === 0 ? "Все филиалы" : `Филиалов: ${orgIds.length}`;
  const companyLabel = companies.find((c) => c.id === companyId)?.name ?? "Все бренды";

  return (
    <div className="flex flex-wrap gap-2">
      {PERIODS.map((p) => (
        <Chip key={p.key} active={period === p.key} onClick={() => onPeriod(p.key)}>
          {p.label}
        </Chip>
      ))}
      <DateRangePicker
        from={dateFrom}
        to={dateTo}
        active={period === "custom"}
        onApply={onRange}
      />
      <span className="mx-1 w-px self-stretch bg-border" />
      {PLATFORMS.map((p) => (
        <Chip key={p.key} active={platform === p.key} onClick={() => onPlatform(p.key)}>
          {p.label}
        </Chip>
      ))}
      <span className="mx-1 w-px self-stretch bg-border" />
      <details className="relative">
        <summary
          className={`inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] ${
            companyId
              ? "border-accent bg-surface-3 text-text"
              : "border-border bg-surface-2 text-text-dim hover:text-text"
          }`}
        >
          {companyLabel} ▾
        </summary>
        <div className="absolute right-0 z-50 mt-1 max-h-80 w-64 overflow-y-auto rounded-lg border border-border bg-surface p-2 shadow-xl">
          <button
            type="button"
            onClick={() => onCompany(null)}
            className="mb-1 w-full rounded px-2 py-1.5 text-left text-[12px] text-text-dim hover:bg-surface-2"
          >
            Сбросить · все бренды
          </button>
          {companies.map((c) => (
            <label
              key={c.id}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-[12.5px] hover:bg-surface-2"
            >
              <input
                type="radio"
                name="overview-company"
                className="accent-accent"
                checked={companyId === c.id}
                onChange={() => onCompany(c.id)}
              />
              <span className="truncate">{c.name}</span>
            </label>
          ))}
          {companies.length === 0 && (
            <p className="px-2 py-1.5 text-[12px] text-text-faint">Брендов пока нет</p>
          )}
        </div>
      </details>
      <details className="relative">
        <summary
          className={`inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] ${
            orgIds.length > 0
              ? "border-accent bg-surface-3 text-text"
              : "border-border bg-surface-2 text-text-dim hover:text-text"
          }`}
        >
          {orgLabel} ▾
        </summary>
        <div className="absolute right-0 z-50 mt-1 max-h-80 w-64 overflow-y-auto rounded-lg border border-border bg-surface p-2 shadow-xl">
          <button
            type="button"
            onClick={onClearOrgs}
            className="mb-1 w-full rounded px-2 py-1.5 text-left text-[12px] text-text-dim hover:bg-surface-2"
          >
            Сбросить · все филиалы
          </button>
          {visibleOrgs.map((o) => (
            <label
              key={o.id}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-[12.5px] hover:bg-surface-2"
            >
              <input
                type="checkbox"
                className="accent-accent"
                checked={selected.has(o.id)}
                onChange={() => onToggleOrg(o.id)}
              />
              <span className="truncate">
                {o.name ?? "без названия"}
                {o.city && <span className="text-text-faint"> · {o.city}</span>}
              </span>
            </label>
          ))}
        </div>
      </details>
    </div>
  );
}
