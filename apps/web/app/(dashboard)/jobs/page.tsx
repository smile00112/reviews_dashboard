"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listJobRuns, listJobs, runJobNow, updateJob } from "@/lib/api";
import type { Job, JobRun, JobRunStatus } from "@/lib/types";
import { JobCard } from "@/components/jobs/job-card";
import { JobRunsTable } from "@/components/jobs/job-runs-table";

const STATUS_FILTERS: (JobRunStatus | "")[] = [
  "",
  "success",
  "partial",
  "failed",
  "needs_manual_action",
  "running",
];

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [runs, setRuns] = useState<JobRun[]>([]);
  const [jobFilter, setJobFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<JobRunStatus | "">("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const filters = useRef({ jobFilter, statusFilter });
  filters.current = { jobFilter, statusFilter };

  const refresh = useCallback(async () => {
    const { jobFilter: job_id, statusFilter: status } = filters.current;
    const [nextJobs, nextRuns] = await Promise.all([
      listJobs(),
      listJobRuns({ job_id: job_id || undefined, status: status || undefined }),
    ]);
    setJobs(nextJobs);
    setRuns(nextRuns);
  }, []);

  useEffect(() => {
    refresh().catch(console.error);
  }, [refresh, jobFilter, statusFilter]);

  // Опрос только пока что-то выполняется: в покое страница не дёргает API.
  useEffect(() => {
    const active = runs.some((run) => run.status === "running" || run.status === "queued");
    if (!active) return;
    const timer = setInterval(() => refresh().catch(console.error), 5000);
    return () => clearInterval(timer);
  }, [runs, refresh]);

  function setError(jobId: string, message: string | null) {
    setErrors((prev) => {
      const next = { ...prev };
      if (message) next[jobId] = message;
      else delete next[jobId];
      return next;
    });
  }

  async function act(job: Job, action: () => Promise<unknown>) {
    setError(job.id, null);
    try {
      await action();
      await refresh();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(
        job.id,
        status === 409
          ? "Задача уже выполняется"
          : status === 401 || status === 403
            ? "Нужны права администратора"
            : (err as Error).message,
      );
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Фоновые задачи</h1>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {jobs.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            error={errors[job.id] ?? null}
            onChanged={refresh}
            onToggle={(target, enabled) =>
              act(target, () => updateJob(target.id, { is_enabled: enabled }))
            }
            onRun={(target) => act(target, () => runJobNow(target.id))}
            onSchedule={(target, cron) =>
              act(target, () => updateJob(target.id, { schedule_cron: cron }))
            }
          />
        ))}
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">Запуски</h2>
          <select
            className="rounded border border-border bg-transparent px-2 py-1 text-xs"
            value={jobFilter}
            onChange={(e) => setJobFilter(e.target.value)}
            data-testid="job-filter"
          >
            <option value="">все задачи</option>
            {jobs.map((job) => (
              <option key={job.id} value={job.id}>
                {job.kind} / {job.platform}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-border bg-transparent px-2 py-1 text-xs"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as JobRunStatus | "")}
            data-testid="status-filter"
          >
            {STATUS_FILTERS.map((value) => (
              <option key={value} value={value}>
                {value || "все статусы"}
              </option>
            ))}
          </select>
        </div>
        <JobRunsTable runs={runs} jobs={jobs} />
      </div>
    </div>
  );
}
