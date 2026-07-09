"use client";

import Link from "next/link";
import { useState } from "react";
import { deleteOrganization, scrapeOrganization, updateOrganization } from "@/lib/api";
import type { Organization, ScrapeMode } from "@/lib/types";
import { ModeSelect } from "./mode-select";
import { ProviderBadges } from "./provider-badges";

function statusClass(status: Organization["last_scrape_status"]) {
  if (status === "success") return "bg-green-100 text-green-800";
  if (status === "failed") return "bg-red-100 text-red-800";
  if (status === "needs_manual_action") return "bg-amber-100 text-amber-900";
  if (status === "running") return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-700";
}

interface OrganizationsTableProps {
  items: Organization[];
  onRefresh: () => void;
}

export function OrganizationsTable({ items, onRefresh }: OrganizationsTableProps) {
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
    return <p className="text-sm text-slate-500">Организации не добавлены.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-slate-600">
          <tr>
            <th className="px-3 py-2">Название</th>
            <th className="px-3 py-2">URL</th>
            <th className="px-3 py-2">Карты</th>
            <th className="px-3 py-2">Рейтинг</th>
            <th className="px-3 py-2">Отзывов</th>
            <th className="px-3 py-2">Режим</th>
            <th className="px-3 py-2">Статус</th>
            <th className="px-3 py-2">Последний успех</th>
            <th className="px-3 py-2">Действия</th>
          </tr>
        </thead>
        <tbody>
          {items.map((org) => (
            <tr key={org.id} className="border-t">
              <td className="px-3 py-2">
                <Link href={`/organizations/${org.id}`} className="text-blue-600 hover:underline">
                  {org.name ?? "—"}
                </Link>
              </td>
              <td className="max-w-xs truncate px-3 py-2" title={org.yandex_url}>
                {org.yandex_url}
              </td>
              <td className="px-3 py-2">
                <ProviderBadges org={org} />
              </td>
              <td className="px-3 py-2">{org.rating ?? "—"}</td>
              <td className="px-3 py-2">{org.review_count ?? "—"}</td>
              <td className="px-3 py-2">
                <ModeSelect
                  value={rowModes[org.id] ?? org.preferred_scrape_mode}
                  onChange={(mode) => handleModeChange(org, mode)}
                />
              </td>
              <td className="px-3 py-2">
                <span className={`rounded px-2 py-0.5 text-xs ${statusClass(org.last_scrape_status)}`}>
                  {org.last_scrape_status}
                </span>
              </td>
              <td className="px-3 py-2">
                {org.last_successful_scrape_at
                  ? new Date(org.last_successful_scrape_at).toLocaleString("ru-RU")
                  : "—"}
              </td>
              <td className="px-3 py-2">
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => handleScrape(org)}
                    disabled={loadingId === org.id}
                    className="rounded bg-slate-800 px-2 py-1 text-xs text-white hover:bg-slate-900 disabled:opacity-50"
                  >
                    {loadingId === org.id ? "..." : "Обновить"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(org.id)}
                    className="rounded border px-2 py-1 text-xs text-red-600 hover:bg-red-50"
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
  );
}
