"use client";

import { useCallback, useEffect, useState } from "react";
import {
  checkSession,
  listCompanies,
  listOrganizationsPage,
  loginYandex,
  scrapeAll,
} from "@/lib/api";
import type { Company, Organization, ScrapeMode, SessionInfo } from "@/lib/types";
import { ModeSelect } from "@/components/mode-select";
import { OrganizationForm } from "@/components/organization-form";
import { OrganizationsTable } from "@/components/organizations-table";
import { useCan } from "@/components/shell/user-context";

const PAGE_SIZE = 25;

/** Russian plural agreement: pick(one, few, many) by count. */
function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

export default function OrganizationsPage() {
  const canScrape = useCan("action:scrape.run");
  const canManageSession = useCan("action:scraper_session.manage");
  const canManageOrg = useCan("action:org.manage");
  const [items, setItems] = useState<Organization[]>([]);
  const [total, setTotal] = useState(0);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<string>("");
  const [bulkMode, setBulkMode] = useState<ScrapeMode>("public");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // Reload the currently-visible window in one request (offset 0). Keeps the
  // same number of rows on screen after a create/delete/scrape/mode change.
  const refresh = useCallback(async () => {
    const windowSize = Math.max(items.length, PAGE_SIZE);
    const [page, sessionInfo] = await Promise.all([
      listOrganizationsPage({ limit: windowSize, offset: 0, companyId: companyId || undefined }),
      getSessionSafe(),
    ]);
    setItems(page.items);
    setTotal(page.total);
    setSession(sessionInfo);
  }, [items.length, companyId]);

  // Fetch the next page and append.
  async function loadMore() {
    setLoadingMore(true);
    try {
      const page = await listOrganizationsPage({
        limit: PAGE_SIZE,
        offset: items.length,
        companyId: companyId || undefined,
      });
      setItems((prev) => [...prev, ...page.items]);
      setTotal(page.total);
    } finally {
      setLoadingMore(false);
    }
  }

  async function getSessionSafe() {
    try {
      return await checkSession();
    } catch {
      return null;
    }
  }

  // Companies for the filter dropdown (fetched once).
  useEffect(() => {
    listCompanies().then(setCompanies).catch(console.error);
  }, []);

  // Fetch the first page on mount and whenever the company filter changes.
  useEffect(() => {
    Promise.all([
      listOrganizationsPage({ limit: PAGE_SIZE, offset: 0, companyId: companyId || undefined }),
      getSessionSafe(),
    ])
      .then(([page, sessionInfo]) => {
        setItems(page.items);
        setTotal(page.total);
        setSession(sessionInfo);
      })
      .catch(console.error);
  }, [companyId]);

  async function handleScrapeAll() {
    setLoading(true);
    try {
      await scrapeAll(bulkMode);
      await refresh();
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin() {
    setSessionMessage(null);
    try {
      const result = await loginYandex();
      setSessionMessage(result.message);
      await refresh();
    } catch (err) {
      setSessionMessage(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="font-display text-4xl font-medium tracking-tight">Организации</h1>
          <p className="mt-1.5 text-sm text-text-dim">
            {total} {plural(total, "точка", "точки", "точек")} в мониторинге
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={companyId}
            onChange={(e) => setCompanyId(e.target.value)}
            className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <option value="">Все компании</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.short_name ?? c.name}
              </option>
            ))}
          </select>
          {canScrape && (
            <>
              <ModeSelect value={bulkMode} onChange={setBulkMode} />
              <button
                type="button"
                onClick={handleScrapeAll}
                disabled={loading || total === 0}
                className="rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-bg transition-colors hover:bg-accent-dim disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
              >
                {loading ? "Обновление…" : "Обновить все"}
              </button>
            </>
          )}
        </div>
      </div>

      {canManageSession && (
      <section className="rounded-2xl border border-border bg-surface p-[22px]">
        <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-text-faint">
          Сессия Yandex (operator_auth)
        </div>
        <p className="text-sm text-text-dim">
          Статус: <strong className="text-text">{session?.status ?? "unknown"}</strong>
          {session?.last_login_at && (
            <span className="ml-2 font-mono text-xs">
              · login: {new Date(session.last_login_at).toLocaleString("ru-RU")}
            </span>
          )}
        </p>
        <button
          type="button"
          onClick={handleLogin}
          className="mt-3 rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm hover:bg-surface-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          Войти в Yandex
        </button>
        {sessionMessage && <p className="mt-2 text-sm text-text-dim">{sessionMessage}</p>}
      </section>
      )}

      {canManageOrg && <OrganizationForm onCreated={refresh} />}
      <OrganizationsTable
        items={items}
        total={total}
        onRefresh={refresh}
        onLoadMore={loadMore}
        loadingMore={loadingMore}
      />
    </div>
  );
}
