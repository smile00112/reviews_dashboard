"use client";

import { useState } from "react";
import { createCompany } from "@/lib/api";

export function CompanyForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [shortName, setShortName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createCompany({ name: name.trim(), short_name: shortName.trim() || null });
      setName("");
      setShortName("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать организацию");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-wrap items-end gap-3 rounded-2xl border border-border bg-surface p-5"
    >
      <div className="flex min-w-[280px] flex-1 flex-col gap-1.5">
        <label className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">
          Название организации
        </label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Например, Coffee Co"
          className="rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[13.5px] text-text outline-none focus:border-accent"
        />
      </div>
      <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
        <label className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">
          Краткое название
        </label>
        <input
          value={shortName}
          onChange={(e) => setShortName(e.target.value)}
          placeholder="Например, Кофемания"
          className="rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[13.5px] text-text outline-none focus:border-accent"
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="rounded-lg bg-accent px-4 py-2.5 text-[13px] font-semibold text-bg hover:bg-accent-dim disabled:opacity-50"
      >
        {loading ? "Создание…" : "+ Организация"}
      </button>
      {error && <p className="w-full text-[13px] text-bad">{error}</p>}
    </form>
  );
}
