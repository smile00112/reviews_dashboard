"use client";

import { useState } from "react";
import { updateOrganization } from "@/lib/api";
import type { Organization } from "@/lib/types";

interface OrgLinksEditorProps {
  org: Organization;
  onSaved: (updated: Organization) => void;
}

export function OrgLinksEditor({ org, onSaved }: OrgLinksEditorProps) {
  const [twogis, setTwogis] = useState(org.twogis_url ?? "");
  const [google, setGoogle] = useState(org.google_url ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const updated = await updateOrganization(org.id, {
        twogis_url: twogis.trim() === "" ? null : twogis.trim(),
        google_url: google.trim() === "" ? null : google.trim(),
      });
      onSaved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить ссылки");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="space-y-3 rounded-lg border bg-white p-4">
      <h2 className="text-sm font-semibold text-slate-700">Ссылки на карты</h2>
      <div className="flex flex-col gap-1">
        <label htmlFor="twogis-url" className="text-xs text-slate-600">
          2ГИС
        </label>
        <input
          id="twogis-url"
          type="url"
          value={twogis}
          onChange={(e) => setTwogis(e.target.value)}
          placeholder="https://go.2gis.com/..."
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="google-url" className="text-xs text-slate-600">
          Google Maps
        </label>
        <input
          id="google-url"
          type="url"
          value={google}
          onChange={(e) => setGoogle(e.target.value)}
          placeholder="https://maps.app.goo.gl/..."
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={saving}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {saving ? "Сохранение..." : "Сохранить"}
      </button>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </form>
  );
}
