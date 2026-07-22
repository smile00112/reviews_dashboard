"use client";

import { useState } from "react";
import { updateSettings } from "@/lib/api";
import type { Settings } from "@/lib/types";
import { useCan } from "@/components/shell/user-context";

export function SettingsForm({ initial }: { initial: Settings }) {
  const canEdit = useCan("action:settings.edit");
  const [minutes, setMinutes] = useState<number>(initial.overview_sla_threshold_minutes);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const next = await updateSettings({ overview_sla_threshold_minutes: minutes });
      setMinutes(next.overview_sla_threshold_minutes);
      setMessage("Сохранено");
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(status === 401 || status === 403 ? "Нужны права администратора" : (err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-md space-y-4">
      <div className="space-y-1">
        <label htmlFor="sla" className="block text-sm font-medium">
          SLA на ответ, минут
        </label>
        <input
          id="sla"
          type="number"
          min={1}
          value={minutes}
          onChange={(e) => setMinutes(Number(e.target.value))}
          disabled={!canEdit}
          className="w-40 rounded border border-border bg-surface px-3 py-2 text-sm disabled:opacity-60"
          data-testid="sla-minutes"
        />
        <p className="text-xs text-text-dim">
          Порог, в пределах которого ответ на отзыв считается «в срок» (доля на обзоре сети).
        </p>
      </div>

      {message && <div className="text-sm text-good">{message}</div>}
      {error && <div className="text-sm text-bad">{error}</div>}

      {canEdit && (
        <button
          type="submit"
          disabled={saving || minutes < 1}
          className="rounded bg-accent px-3 py-2 text-xs font-semibold text-black disabled:opacity-50"
          data-testid="settings-save"
        >
          {saving ? "Сохранение…" : "Сохранить"}
        </button>
      )}
    </form>
  );
}
