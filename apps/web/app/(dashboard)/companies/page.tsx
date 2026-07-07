"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { deleteCompany, listCompanies } from "@/lib/api";
import type { Company } from "@/lib/types";
import { CompanyForm } from "@/components/company-form";
import { useIsAdmin } from "@/components/shell/user-context";

export default function CompaniesPage() {
  const isAdmin = useIsAdmin();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setCompanies(await listCompanies());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить организации");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDelete(id: string) {
    if (!confirm("Удалить организацию? Филиалы сохранятся, но станут не привязаны.")) return;
    await deleteCompany(id);
    load();
  }

  return (
    <div>
      <div className="mb-7 flex items-end justify-between gap-6">
        <div>
          <h1 className="font-display text-4xl font-medium tracking-tight">Организации</h1>
          <p className="mt-1.5 text-[14px] text-text-dim">
            Компании и их филиалы по городам. Филиал — точка сбора отзывов с карт.
          </p>
        </div>
      </div>

      {isAdmin && (
        <div className="mb-6">
          <CompanyForm onCreated={load} />
        </div>
      )}

      {error && <p className="mb-4 text-[13px] text-bad">{error}</p>}

      {loading ? (
        <p className="text-text-faint">Загрузка…</p>
      ) : companies.length === 0 ? (
        <div className="rounded-2xl border border-border bg-surface p-16 text-center text-text-faint">
          Пока нет организаций. {isAdmin ? "Создайте первую выше." : ""}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {companies.map((c) => (
            <div key={c.id} className="rounded-2xl border border-border bg-surface p-5 transition-colors hover:border-text-faint">
              <div className="flex items-start justify-between gap-3">
                <Link href={`/companies/${c.id}`} className="min-w-0 flex-1">
                  <div className="truncate font-display text-lg font-medium">{c.name}</div>
                  <div className="mt-1 text-[12px] text-text-dim">
                    {c.branch_count} {pluralBranches(c.branch_count)}
                    {!c.is_active && " · неактивна"}
                  </div>
                </Link>
                {isAdmin && (
                  <button
                    type="button"
                    onClick={() => handleDelete(c.id)}
                    className="rounded-md px-2 py-1 text-[12px] text-bad hover:bg-surface-2"
                  >
                    Удалить
                  </button>
                )}
              </div>
              <Link
                href={`/companies/${c.id}`}
                className="mt-4 inline-block text-[13px] font-medium text-accent hover:underline"
              >
                Открыть →
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function pluralBranches(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "филиал";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "филиала";
  return "филиалов";
}
