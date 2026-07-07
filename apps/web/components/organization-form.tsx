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
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3 rounded-lg border bg-white p-4">
      <div className="flex min-w-[280px] flex-1 flex-col gap-1">
        <label htmlFor="yandex-url" className="text-sm font-medium text-slate-700">
          URL организации Яндекс Карт
        </label>
        <input
          id="yandex-url"
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://yandex.ru/maps/org/..."
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-slate-700">Режим</label>
        <ModeSelect value={mode} onChange={setMode} />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "Добавление..." : "Добавить"}
      </button>
      {error && <p className="w-full text-sm text-red-600">{error}</p>}
    </form>
  );
}
