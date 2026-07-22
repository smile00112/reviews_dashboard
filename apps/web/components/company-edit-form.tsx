"use client";

import { useState } from "react";
import { updateCompany } from "@/lib/api";
import type { Company } from "@/lib/types";

const fieldLabel = "mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-text-faint";
const fieldInput =
  "w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[13.5px] text-text outline-none focus:border-accent";

export function CompanyEditForm({
  company,
  onSaved,
  onClose,
}: {
  company: Company;
  onSaved: () => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(company.name);
  const [shortName, setShortName] = useState(company.short_name ?? "");
  const [isActive, setIsActive] = useState(company.is_active);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await updateCompany(company.id, {
        name: name.trim(),
        short_name: shortName.trim() || null,
        is_active: isActive,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить организацию");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-10 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-border bg-surface p-7">
        <h2 className="mb-6 font-display text-2xl font-medium">Редактировать организацию</h2>

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className={fieldLabel}>Название организации</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Например, Coffee Co"
              className={fieldInput}
            />
          </div>

          <div className="mb-4">
            <label className={fieldLabel}>Краткое название</label>
            <input
              value={shortName}
              onChange={(e) => setShortName(e.target.value)}
              placeholder="Например, Кофемания"
              className={fieldInput}
            />
            <p className="mt-1 text-[11px] text-text-faint">
              Показывается в списках точек. Пусто — используется полное название.
            </p>
          </div>

          <label className="mb-4 flex cursor-pointer items-center gap-2 text-[13.5px] text-text">
            <input
              type="checkbox"
              className="accent-accent"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
            />
            Активна
          </label>

          {error && <p className="mt-3 text-[13px] text-bad">{error}</p>}

          <div className="mt-6 flex justify-end gap-3 border-t border-border pt-5">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-[13px] font-medium text-text hover:bg-surface-3"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-accent px-4 py-2.5 text-[13px] font-semibold text-bg hover:bg-accent-dim disabled:opacity-50"
            >
              {loading ? "Сохранение…" : "Сохранить"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
