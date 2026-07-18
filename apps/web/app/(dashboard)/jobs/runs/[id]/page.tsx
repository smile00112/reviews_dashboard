"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { getJobRun } from "@/lib/api";
import type { JobRunDetail, JobRunItem } from "@/lib/types";
import { JOB_LABELS, PLATFORM_LABELS, jobStatusClass } from "@/components/jobs/job-card";

const ITEM_STATUS_LABELS: Record<string, string> = {
  success: "успешно",
  skipped: "пропущено",
  failed: "ошибка",
  needs_manual_action: "нужен оператор",
};

// Server default/hard cap for a single page of items (see GET /api/job-runs/{id}).
const ITEMS_PAGE_SIZE = 200;

function formatPayload(payload: Record<string, number | string | null>): string {
  const entries = Object.entries(payload).filter(([, value]) => value !== null && value !== undefined);
  if (entries.length === 0) return "—";
  return entries.map(([key, value]) => `${key}=${value}`).join(", ");
}

export default function JobRunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [run, setRun] = useState<JobRunDetail | null>(null);
  const [items, setItems] = useState<JobRunItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  // У упавшего посреди прогона запуска orgs_total больше числа реально
  // записанных items — сервер отдаст пустую страницу, и кнопка зациклилась бы.
  const [exhausted, setExhausted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJobRun(id)
      .then((data) => {
        setRun(data);
        setItems(data.items);
      })
      .catch((err: Error) => setError(err.message));
  }, [id]);

  // Пока запуск идёт — обновляем; закончился — перестаём опрашивать.
  // Зависимость — производный boolean, а не сам run: каждый тик приносит
  // новый объект, и зависимость от него пересоздавала бы интервал на каждом
  // опросе (см. тот же паттерн hasActiveRuns на странице /jobs).
  // Опрос перезагружает только первую страницу items (плюс шапку запуска) —
  // любые ранее подгруженные через "Показать ещё" страницы при этом
  // отбрасываются. Для активного запуска это приемлемо: пока он не завершён,
  // список организаций всё равно продолжает меняться.
  const isActive = run?.status === "running" || run?.status === "queued";
  useEffect(() => {
    if (!isActive) return;
    const timer = setInterval(() => {
      getJobRun(id)
        .then((data) => {
          setRun(data);
          setItems(data.items);
        })
        .catch(console.error);
    }, 5000);
    return () => clearInterval(timer);
  }, [isActive, id]);

  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (!run) return <p className="text-sm text-text-dim">Загрузка…</p>;

  const hasMore = !exhausted && items.length < run.orgs_total;

  async function loadMore() {
    setLoadingMore(true);
    try {
      const next = await getJobRun(id, { limit: ITEMS_PAGE_SIZE, offset: items.length });
      if (next.items.length === 0) setExhausted(true);
      setItems((prev) => [...prev, ...next.items]);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingMore(false);
    }
  }

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

      <p className="text-xs text-text-dim">
        показано {items.length} из {run.orgs_total}
      </p>

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
            {items.map((item) => (
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
      {items.length === 0 && <p className="text-sm text-text-dim">Строк по организациям нет.</p>}
      {hasMore && (
        <button
          type="button"
          data-testid="job-run-items-more"
          onClick={loadMore}
          disabled={loadingMore}
          className="rounded border border-border px-3 py-1.5 text-xs font-medium text-text-dim hover:bg-surface-2 disabled:opacity-50"
        >
          {loadingMore ? "Загрузка…" : "Показать ещё"}
        </button>
      )}
    </div>
  );
}
