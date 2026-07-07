"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  deleteOrganization,
  getCompany,
  getCompanyBranches,
  scrapeOrganization,
} from "@/lib/api";
import type { Company, CompanyBranches, Organization } from "@/lib/types";
import { BranchForm } from "@/components/branch-form";
import { useIsAdmin } from "@/components/shell/user-context";

export default function CompanyDetailPage() {
  const params = useParams<{ id: string }>();
  const companyId = params.id;
  const isAdmin = useIsAdmin();

  const [company, setCompany] = useState<Company | null>(null);
  const [branches, setBranches] = useState<CompanyBranches | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Organization | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, b] = await Promise.all([getCompany(companyId), getCompanyBranches(companyId)]);
      setCompany(c);
      setBranches(b);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить организацию");
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    load();
  }, [load]);

  function openAdd() {
    setEditing(null);
    setModalOpen(true);
  }

  function openEdit(branch: Organization) {
    setEditing(branch);
    setModalOpen(true);
  }

  async function handleDelete(branch: Organization) {
    if (!confirm(`Удалить филиал «${branch.name ?? branch.yandex_url}»? Отзывы этой точки будут удалены.`)) return;
    await deleteOrganization(branch.id);
    load();
  }

  async function handleScrape(branch: Organization) {
    try {
      await scrapeOrganization(branch.id, branch.preferred_scrape_mode);
      alert("Сбор запущен. Проверьте «Историю сборов».");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Не удалось запустить сбор");
    }
  }

  const totalBranches = branches?.groups.reduce((sum, g) => sum + g.branches.length, 0) ?? 0;

  return (
    <div>
      <div className="mb-6">
        <Link href="/companies" className="text-[13px] text-text-dim hover:text-text">
          ← Организации
        </Link>
      </div>

      {error && <p className="mb-4 text-[13px] text-bad">{error}</p>}

      <div className="mb-7 flex items-end justify-between gap-6">
        <div>
          <h1 className="font-display text-4xl font-medium tracking-tight">{company?.name ?? "…"}</h1>
          <p className="mt-1.5 text-[14px] text-text-dim">
            {totalBranches} {totalBranches === 1 ? "филиал" : "филиалов"} · {branches?.groups.length ?? 0} городов
          </p>
        </div>
        {isAdmin && (
          <button
            type="button"
            onClick={openAdd}
            className="rounded-lg bg-accent px-4 py-2.5 text-[13px] font-semibold text-bg hover:bg-accent-dim"
          >
            + Филиал
          </button>
        )}
      </div>

      {loading ? (
        <p className="text-text-faint">Загрузка…</p>
      ) : totalBranches === 0 ? (
        <div className="rounded-2xl border border-border bg-surface p-16 text-center text-text-faint">
          У организации пока нет филиалов. {isAdmin ? "Добавьте первый." : ""}
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {branches!.groups.map((group) => (
            <section key={group.city}>
              <div className="mb-3 flex items-center gap-2 border-b border-border pb-2 text-[13px] font-semibold">
                📍 {group.city}
                <span className="font-normal text-text-faint">· {group.branches.length}</span>
              </div>
              <div className="overflow-x-auto rounded-2xl border border-border bg-surface">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wider text-text-faint">
                      <th className="px-4 py-3">Точка</th>
                      <th className="px-4 py-3">Адрес</th>
                      <th className="px-4 py-3">Режим</th>
                      <th className="px-4 py-3">Статус</th>
                      <th className="px-4 py-3 text-right">Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.branches.map((b) => (
                      <tr key={b.id} className="border-t border-border">
                        <td className="px-4 py-3">
                          <div className="font-medium">{b.name ?? "—"}</div>
                          <a href={b.yandex_url} target="_blank" rel="noreferrer" className="text-[11px] text-text-faint hover:text-accent">
                            {b.yandex_url}
                          </a>
                        </td>
                        <td className="px-4 py-3 text-text-dim">{b.address ?? "—"}</td>
                        <td className="px-4 py-3 font-mono text-[12px] text-text-dim">{b.preferred_scrape_mode}</td>
                        <td className="px-4 py-3 text-text-dim">{b.last_scrape_status}</td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-1.5">
                            {isAdmin && (
                              <button onClick={() => handleScrape(b)} className="rounded-md border border-border px-2.5 py-1.5 text-[12px] hover:bg-surface-2">
                                Собрать
                              </button>
                            )}
                            {isAdmin && (
                              <button onClick={() => openEdit(b)} className="rounded-md border border-border px-2.5 py-1.5 text-[12px] hover:bg-surface-2">
                                Изменить
                              </button>
                            )}
                            {isAdmin && (
                              <button onClick={() => handleDelete(b)} className="rounded-md px-2.5 py-1.5 text-[12px] text-bad hover:bg-surface-2">
                                Удалить
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>
      )}

      {modalOpen && (
        <BranchForm
          companyId={companyId}
          branch={editing}
          onClose={() => setModalOpen(false)}
          onSaved={() => {
            setModalOpen(false);
            load();
          }}
        />
      )}
    </div>
  );
}
