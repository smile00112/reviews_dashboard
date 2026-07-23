"use client";

import Link from "next/link";
import { useState } from "react";
import { deleteOrganization, scrapeOrganization, updateOrganization } from "@/lib/api";
import type { Organization, OrganizationScrapeStatus, ScrapeMode } from "@/lib/types";
import { ModeSelect } from "./mode-select";

function statusClass(status: OrganizationScrapeStatus) {
  if (status === "success") return "bg-good/15 text-good";
  if (status === "failed") return "bg-bad/15 text-bad";
  if (status === "needs_manual_action") return "bg-warn/15 text-warn";
  if (status === "running") return "bg-info/15 text-info";
  return "bg-surface-3 text-text-dim";
}

// Per-platform status badges (Yandex / 2GIS) stacked in one cell.
function StatusBadges({ org }: { org: Organization }) {
  return (
    <div className="flex flex-col gap-1">
      <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${statusClass(org.yandex_scrape_status)}`}>
        Я: {org.yandex_scrape_status}
      </span>
      <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${statusClass(org.gis2_scrape_status)}`}>
        2G: {org.gis2_scrape_status}
      </span>
    </div>
  );
}

function formatTs(value: string | null) {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

interface OrganizationsTableProps {
  items: Organization[];
  total: number;
  onRefresh: () => void;
  onLoadMore: () => void;
  loadingMore: boolean;
}

// Compact platform cell: рейтинг · отзывов · оценок
function PlatformCell({
  rating,
  reviewCount,
  ratingCount,
}: {
  rating: number | null;
  reviewCount: number | null;
  ratingCount: number | null;
}) {
  if (rating == null && reviewCount == null && ratingCount == null) {
    return <span className="text-text-faint">—</span>;
  }
  return (
    <span className="whitespace-nowrap font-mono text-xs">
      {rating ?? "—"} · {reviewCount ?? "—"} · {ratingCount ?? "—"}
    </span>
  );
}

export function OrganizationsTable({
  items,
  total,
  onRefresh,
  onLoadMore,
  loadingMore,
}: OrganizationsTableProps) {
  const [rowModes, setRowModes] = useState<Record<string, ScrapeMode>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);

  async function handleScrape(org: Organization) {
    const mode = rowModes[org.id] ?? org.preferred_scrape_mode;
    setLoadingId(org.id);
    try {
      await scrapeOrganization(org.id, mode);
      onRefresh();
    } finally {
      setLoadingId(null);
    }
  }

  async function handleModeChange(org: Organization, mode: ScrapeMode) {
    setRowModes((prev) => ({ ...prev, [org.id]: mode }));
    await updateOrganization(org.id, { preferred_scrape_mode: mode });
    onRefresh();
  }

  async function handleDelete(id: string) {
    if (!confirm("Удалить организацию?")) return;
    await deleteOrganization(id);
    onRefresh();
  }

  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-surface py-12 text-center text-text-faint">
        Организации не добавлены.
      </div>
    );
  }

  const remaining = total - items.length;

  return (
    <div className="rounded-2xl border border-border bg-surface p-[22px]">
      <div className="mb-[18px] flex items-center justify-between">
        <div className="font-display text-lg font-medium tracking-tight">Список организаций</div>
        <div className="font-mono text-xs text-text-faint">
          {items.length} / {total}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-text-faint">
              <th className="border-b border-border px-3 py-2.5 text-left">Название</th>
              <th className="border-b border-border px-3 py-2.5 text-left" title="рейтинг · отзывов · оценок">
                Яндекс
              </th>
              <th className="border-b border-border px-3 py-2.5 text-left" title="рейтинг · отзывов · оценок">
                2ГИС
              </th>
              <th className="border-b border-border px-3 py-2.5 text-left" title="рейтинг · отзывов · оценок">
                Google
              </th>
              <th className="border-b border-border px-3 py-2.5 text-left">Режим</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Статус</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Последний успех</th>
              <th className="border-b border-border px-3 py-2.5 text-left">Действия</th>
            </tr>
          </thead>
          <tbody>
            {items.map((org) => (
              <tr
                key={org.id}
                className={`transition-colors ${
                  org.is_active ? "hover:bg-surface-2" : "bg-warn/[0.07] hover:bg-warn/10"
                }`}
              >
                <td className="border-b border-border px-3 py-3">
                  <Link
                    href={`/organizations/${org.id}`}
                    className={`font-medium hover:text-accent ${org.is_active ? "text-text" : "text-text-dim"}`}
                  >
                    {org.name ?? "—"}
                  </Link>
                  {!org.is_active && (
                    <span className="ml-2 rounded-md bg-warn/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-warn">
                      Неактивна
                    </span>
                  )}
                </td>
                <td className="border-b border-border px-3 py-3">
                  <PlatformCell
                    rating={org.rating}
                    reviewCount={org.review_count}
                    ratingCount={org.yandex_rating_count}
                  />
                </td>
                <td className="border-b border-border px-3 py-3">
                  <PlatformCell
                    rating={org.gis2_rating}
                    reviewCount={org.gis2_review_count}
                    ratingCount={org.gis2_rating_count}
                  />
                </td>
                <td className="border-b border-border px-3 py-3">
                  <PlatformCell
                    rating={org.google_rating}
                    reviewCount={org.google_review_count}
                    ratingCount={org.google_rating_count}
                  />
                </td>
                <td className="border-b border-border px-3 py-3">
                  <ModeSelect
                    value={rowModes[org.id] ?? org.preferred_scrape_mode}
                    onChange={(mode) => handleModeChange(org, mode)}
                  />
                </td>
                <td className="border-b border-border px-3 py-3">
                  <StatusBadges org={org} />
                </td>
                <td className="whitespace-nowrap border-b border-border px-3 py-3 font-mono text-[11px] text-text-dim">
                  <div className="flex flex-col gap-1">
                    <span>Я: {formatTs(org.yandex_last_successful_scrape_at)}</span>
                    <span>2G: {formatTs(org.gis2_last_successful_scrape_at)}</span>
                  </div>
                </td>
                <td className="border-b border-border px-3 py-3">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => handleScrape(org)}
                      disabled={loadingId === org.id}
                      className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-xs hover:bg-surface-3 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      {loadingId === org.id ? "..." : "Обновить"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(org.id)}
                      className="rounded-lg border border-border px-2.5 py-1 text-xs text-bad hover:border-bad hover:bg-bad/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bad"
                    >
                      Удалить
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {remaining > 0 && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={loadingMore}
          className="mt-[10px] w-full rounded-lg border border-dashed border-border bg-transparent px-3 py-2.5 text-[12.5px] text-text-dim transition-colors hover:border-accent hover:text-accent disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {loadingMore ? "Загрузка…" : `Показать ещё ${Math.min(remaining, 25)} →`}
        </button>
      )}
    </div>
  );
}
