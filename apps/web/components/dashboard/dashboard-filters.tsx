"use client";

import { useEffect, useRef, useState } from "react";
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

  const companyRef = useRef<HTMLDetailsElement>(null);
  const orgRef = useRef<HTMLDetailsElement>(null);
  const [orgInput, setOrgInput] = useState("");
  const [orgQuery, setOrgQuery] = useState("");

  // Apply the branch search 700ms after the last keystroke.
  useEffect(() => {
    const t = setTimeout(() => setOrgQuery(orgInput), 700);
    return () => clearTimeout(t);
  }, [orgInput]);

  // Close either dropdown on a click outside of it (native <details> doesn't).
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      const target = e.target as Node;
      if (companyRef.current && !companyRef.current.contains(target)) {
        companyRef.current.open = false;
      }
      if (orgRef.current && !orgRef.current.contains(target)) {
        orgRef.current.open = false;
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const q = orgQuery.trim().toLowerCase();
  const filteredOrgs = q
    ? visibleOrgs.filter((o) =>
        `${o.name ?? ""} ${o.city ?? ""}`.toLowerCase().includes(q),
      )
    : visibleOrgs;
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
      <details ref={companyRef} className="relative">
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
      <details ref={orgRef} className="relative">
        <summary
          className={`inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] ${
            orgIds.length > 0
              ? "border-accent bg-surface-3 text-text"
              : "border-border bg-surface-2 text-text-dim hover:text-text"
          }`}
        >
          {orgLabel} ▾
        </summary>
        <div className="absolute right-0 z-50 mt-1 flex max-h-80 w-64 flex-col rounded-lg border border-border bg-surface p-2 shadow-xl">
          <input
            type="text"
            value={orgInput}
            onChange={(e) => setOrgInput(e.target.value)}
            placeholder="Поиск по названию или городу…"
            className="mb-1 w-full rounded border border-border bg-surface-2 px-2 py-1.5 text-[12.5px] text-text placeholder:text-text-faint focus:border-accent focus:outline-none"
          />
          <button
            type="button"
            onClick={onClearOrgs}
            className="mb-1 w-full rounded px-2 py-1.5 text-left text-[12px] text-text-dim hover:bg-surface-2"
          >
            Сбросить · все филиалы
          </button>
          <div className="-mx-2 overflow-y-auto px-2">
          {filteredOrgs.map((o) => (
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
          {filteredOrgs.length === 0 && (
            <p className="px-2 py-1.5 text-[12px] text-text-faint">Ничего не найдено</p>
          )}
          </div>
        </div>
      </details>
    </div>
  );
}
