"use client";

import { useState } from "react";
import type { Job, JobKind, JobRunStatus } from "@/lib/types";
import { ScheduleModal } from "./schedule-modal";

export const JOB_LABELS: Record<JobKind, string> = {
  org_metrics: "Данные организаций",
  reviews: "Отзывы",
};

export const PLATFORM_LABELS: Record<Job["platform"], string> = {
  yandex: "Яндекс",
  gis2: "2ГИС",
};

export function jobStatusClass(status: JobRunStatus): string {
  if (status === "success") return "bg-green-100 text-green-800";
  if (status === "partial") return "bg-amber-100 text-amber-900";
  if (status === "failed") return "bg-red-100 text-red-800";
  if (status === "needs_manual_action") return "bg-amber-200 text-amber-950 ring-1 ring-amber-400";
  if (status === "running" || status === "queued") return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-700";
}

/** Человекочитаемое расписание для частых форм; иначе — сырой cron. */
export function describeCron(cron: string | null): string {
  if (!cron) return "не задано";
  const daily = cron.match(/^(\d{1,2}) (\d{1,2}) \* \* \*$/);
  if (daily) return `ежедневно в ${daily[2].padStart(2, "0")}:${daily[1].padStart(2, "0")}`;
  const everyHours = cron.match(/^0 \*\/(\d{1,2}) \* \* \*$/);
  if (everyHours) return `каждые ${everyHours[1]} ч`;
  if (cron === "0 * * * *") return "каждый час";
  return cron;
}

interface JobCardProps {
  job: Job;
  onToggle: (job: Job, enabled: boolean) => Promise<void>;
  onRun: (job: Job) => Promise<void>;
  onSchedule: (job: Job, cron: string) => Promise<void>;
  error: string | null;
}

export function JobCard({ job, onToggle, onRun, onSchedule, error }: JobCardProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const running = job.last_run?.status === "running" || job.last_run?.status === "queued";

  async function guarded(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4" data-testid="job-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-medium">
            {JOB_LABELS[job.kind]} — {PLATFORM_LABELS[job.platform]}
          </div>
          <div className="mt-1 text-xs text-text-dim">{describeCron(job.schedule_cron)}</div>
        </div>
        <label className="flex items-center gap-2 text-xs text-text-dim">
          <input
            type="checkbox"
            checked={job.is_enabled}
            disabled={busy}
            onChange={(e) => guarded(() => onToggle(job, e.target.checked))}
          />
          вкл
        </label>
      </div>

      <div className="mt-3 text-xs">
        {job.last_run ? (
          <span className={`rounded px-2 py-0.5 font-medium ${jobStatusClass(job.last_run.status)}`}>
            {job.last_run.status}
          </span>
        ) : (
          <span className="text-text-faint">ещё не запускалась</span>
        )}
        {job.last_run_at && (
          <span className="ml-2 text-text-dim">{new Date(job.last_run_at).toLocaleString("ru-RU")}</span>
        )}
      </div>

      {error && <div className="mt-2 text-xs text-red-700">{error}</div>}

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          className="rounded border border-border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          disabled={busy || running}
          onClick={() => guarded(() => onRun(job))}
          data-testid="job-run-now"
        >
          Запустить сейчас
        </button>
        <button
          type="button"
          className="rounded border border-border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          disabled={busy}
          onClick={() => setModalOpen(true)}
        >
          Изменить расписание
        </button>
      </div>

      {modalOpen && (
        <ScheduleModal
          job={job}
          onClose={() => setModalOpen(false)}
          onSubmit={(cron) => guarded(() => onSchedule(job, cron))}
        />
      )}
    </div>
  );
}
