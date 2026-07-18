"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { getJobRun } from "@/lib/api";
import type { JobRunDetail } from "@/lib/types";
import { JOB_LABELS, PLATFORM_LABELS, jobStatusClass } from "@/components/jobs/job-card";

const ITEM_STATUS_LABELS: Record<string, string> = {
  success: "успешно",
  skipped: "пропущено",
  failed: "ошибка",
  needs_manual_action: "нужен оператор",
};

function formatPayload(payload: Record<string, number | string | null>): string {
  const entries = Object.entries(payload).filter(([, value]) => value !== null && value !== undefined);
  if (entries.length === 0) return "—";
  return entries.map(([key, value]) => `${key}=${value}`).join(", ");
}

export default function JobRunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [run, setRun] = useState<JobRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJobRun(id)
      .then(setRun)
      .catch((err: Error) => setError(err.message));
  }, [id]);

  // Пока запуск идёт — обновляем; закончился — перестаём опрашивать.
  useEffect(() => {
    if (!run || (run.status !== "running" && run.status !== "queued")) return;
    const timer = setInterval(() => {
      getJobRun(id).then(setRun).catch(console.error);
    }, 5000);
    return () => clearInterval(timer);
  }, [run, id]);

  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (!run) return <p className="text-sm text-text-dim">Загрузка…</p>;

  return (
    <div className="space-y-4">
      <Link className="text-xs text-accent" href="/jobs">
        ← к задачам
      </Link>
      <h1 className="text-2xl font-semibold">
        {JOB_LABELS[run.job.kind]} — {PLATFORM_LABELS[run.job.platform]}
      </h1>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${jobStatusClass(run.status)}`}>
          {run.status}
        </span>
        <span className="text-text-dim">{new Date(run.started_at).toLocaleString("ru-RU")}</span>
        <span className="text-text-dim">
          организаций: {run.orgs_total} · успешно {run.orgs_succeeded} · пропущено {run.orgs_skipped} · ошибок{" "}
          {run.orgs_failed}
        </span>
      </div>
      {run.error_message && <p className="text-sm text-red-700">{run.error_message}</p>}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="min-w-full text-sm">
          <thead className="bg-surface-2 text-left text-text-dim">
            <tr>
              <th className="px-3 py-2">Организация</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2">Детали</th>
              <th className="px-3 py-2">Причина / ошибка</th>
              <th className="px-3 py-2">Сбор</th>
            </tr>
          </thead>
          <tbody>
            {run.items.map((item) => (
              <tr key={item.id} className="border-t border-border align-top" data-testid="job-run-item">
                <td className="px-3 py-2">{item.organization_name ?? item.organization_id}</td>
                <td className="px-3 py-2">{ITEM_STATUS_LABELS[item.status] ?? item.status}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatPayload(item.payload)}</td>
                <td className="max-w-xs px-3 py-2 text-xs">
                  {item.reason ?? item.error_message ?? "—"}
                </td>
                <td className="px-3 py-2 text-xs">{item.scrape_run_id ? "есть" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {run.items.length === 0 && <p className="text-sm text-text-dim">Строк по организациям нет.</p>}
    </div>
  );
}
