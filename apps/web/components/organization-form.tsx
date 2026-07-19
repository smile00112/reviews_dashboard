"use client";

import { useState } from "react";
import { createOrganization } from "@/lib/api";
import type { ScrapeMode } from "@/lib/types";
import { ModeSelect } from "./mode-select";

interface OrganizationFormProps {
  onCreated: () => void;
}

export function OrganizationForm({ onCreated }: OrganizationFormProps) {
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<ScrapeMode>("public");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await createOrganization({ yandex_url: url, preferred_scrape_mode: mode });
      setUrl("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create organization");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-wrap items-end gap-3 rounded-2xl border border-border bg-surface p-[22px]"
    >
      <div className="flex min-w-[280px] flex-1 flex-col gap-1.5">
        <label htmlFor="yandex-url" className="text-[11px] font-medium uppercase tracking-wider text-text-faint">
          URL организации Яндекс Карт
        </label>
        <input
          id="yandex-url"
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://yandex.ru/maps/org/..."
          className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-text placeholder:text-text-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] font-medium uppercase tracking-wider text-text-faint">Режим</label>
        <ModeSelect value={mode} onChange={setMode} />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors hover:bg-accent-dim disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
      >
        {loading ? "Добавление..." : "Добавить"}
      </button>
      {error && <p className="w-full text-sm text-bad">{error}</p>}
    </form>
  );
}
