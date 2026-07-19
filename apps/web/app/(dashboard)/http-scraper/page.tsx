"use client";

import { useEffect, useState } from "react";

import { ReviewsTable } from "@/components/reviews-table";
import { ScrapeRunStatusTable } from "@/components/scrape-run-status";
import {
  getScrapeRun,
  listOrganizationReviews,
  listOrganizations,
  scrapeOrganization,
} from "@/lib/api";
import type { Organization, Review, ScrapeRun } from "@/lib/types";

const TERMINAL = new Set(["success", "failed", "needs_manual_action"]);
const POLL_MS = 1500;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function HttpScraperPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [run, setRun] = useState<ScrapeRun | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listOrganizations()
      // HTTP scraper is Yandex-only; 2GIS-only orgs have nothing to scrape here.
      .then((all) => setOrgs(all.filter((o) => o.yandex_url)))
      .catch((e) => setError(String(e)));
  }, []);

  async function runHttpScrape(org: Organization) {
    setBusy(true);
    setError(null);
    setRun(null);
    setReviews([]);
    setSelectedId(org.id);
    try {
      const { scrape_run_id } = await scrapeOrganization(org.id, "public_http");
      // Poll until the run reaches a terminal state.
      let current = await getScrapeRun(scrape_run_id);
      setRun(current);
      while (!TERMINAL.has(current.status)) {
        await sleep(POLL_MS);
        current = await getScrapeRun(scrape_run_id);
        setRun(current);
      }
      const data = await listOrganizationReviews(org.id);
      setReviews(data.items);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-4xl font-medium tracking-tight">HTTP-парсер</h1>
        <p className="mt-1.5 max-w-3xl text-sm text-text-dim">
          Браузерless-сбор отзывов через HTTP (requests + пагинация). Отдельный интерфейс;
          Playwright-режимы не затрагиваются. Результаты пишутся в общую базу с дедупом и
          аналитикой.
        </p>
      </div>

      {error && (
        <p className="rounded-lg border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{error}</p>
      )}

      <section className="space-y-2.5">
        <h2 className="text-[11px] font-medium uppercase tracking-wider text-text-faint">Организации</h2>
        {orgs.length === 0 ? (
          <div className="rounded-2xl border border-border bg-surface py-12 text-center text-sm text-text-faint">
            Нет организаций. Добавьте их на странице «Организации».
          </div>
        ) : (
          <ul className="divide-y divide-border rounded-2xl border border-border bg-surface">
            {orgs.map((org) => (
              <li key={org.id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-text">
                    {org.name ?? org.yandex_url}
                  </div>
                  <div className="truncate font-mono text-xs text-text-faint">{org.yandex_url}</div>
                </div>
                <button
                  type="button"
                  onClick={() => runHttpScrape(org)}
                  disabled={busy}
                  className="shrink-0 rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-bg transition-colors hover:bg-accent-dim disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
                >
                  {busy && selectedId === org.id ? "Сбор…" : "Собрать (HTTP)"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {run && (
        <section className="space-y-2.5">
          <h2 className="text-[11px] font-medium uppercase tracking-wider text-text-faint">Текущий сбор</h2>
          <ScrapeRunStatusTable items={[run]} />
        </section>
      )}

      {selectedId && (
        <section className="space-y-2.5">
          <h2 className="text-[11px] font-medium uppercase tracking-wider text-text-faint">Отзывы организации</h2>
          <ReviewsTable items={reviews} emptyMessage={busy ? "Сбор выполняется…" : "Отзывы не найдены."} />
        </section>
      )}
    </div>
  );
}
