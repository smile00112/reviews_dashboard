"use client";

import { useCallback, useEffect, useState } from "react";
import {
  checkSession,
  listOrganizations,
  loginYandex,
  scrapeAll,
} from "@/lib/api";
import type { Organization, ScrapeMode, SessionInfo } from "@/lib/types";
import { ModeSelect } from "@/components/mode-select";
import { OrganizationForm } from "@/components/organization-form";
import { OrganizationsTable } from "@/components/organizations-table";

export default function OrganizationsPage() {
  const [items, setItems] = useState<Organization[]>([]);
  const [bulkMode, setBulkMode] = useState<ScrapeMode>("public");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    const [orgs, sessionInfo] = await Promise.all([listOrganizations(), getSessionSafe()]);
    setItems(orgs);
    setSession(sessionInfo);
  }, []);

  async function getSessionSafe() {
    try {
      return await checkSession();
    } catch {
      return null;
    }
  }

  useEffect(() => {
    refresh().catch(console.error);
  }, [refresh]);

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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Организации</h1>
        <div className="flex items-center gap-2">
          <ModeSelect value={bulkMode} onChange={setBulkMode} />
          <button
            type="button"
            onClick={handleScrapeAll}
            disabled={loading || items.length === 0}
            className="rounded bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Обновить все
          </button>
        </div>
      </div>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Сессия Yandex (operator_auth)</h2>
        <p className="text-sm text-slate-600">
          Статус: <strong>{session?.status ?? "unknown"}</strong>
          {session?.last_login_at && (
            <span className="ml-2">· login: {new Date(session.last_login_at).toLocaleString("ru-RU")}</span>
          )}
        </p>
        <button
          type="button"
          onClick={handleLogin}
          className="mt-2 rounded border px-3 py-1 text-sm hover:bg-slate-50"
        >
          Войти в Yandex
        </button>
        {sessionMessage && <p className="mt-2 text-sm text-slate-600">{sessionMessage}</p>}
      </section>

      <OrganizationForm onCreated={refresh} />
      <OrganizationsTable items={items} onRefresh={refresh} />
    </div>
  );
}
