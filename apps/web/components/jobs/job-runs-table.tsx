import Link from "next/link";
import type { Job, JobRun } from "@/lib/types";
import { JOB_LABELS, PLATFORM_LABELS, jobStatusClass } from "./job-card";

function duration(run: JobRun) {
  if (!run.finished_at) return "—";
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  return `${Math.round(ms / 1000)}s`;
}

interface JobRunsTableProps {
  runs: JobRun[];
  jobs: Job[];
}

export function JobRunsTable({ runs, jobs }: JobRunsTableProps) {
  const byId = new Map(jobs.map((job) => [job.id, job]));

  if (runs.length === 0) {
    return <p className="text-sm text-text-dim">Запусков пока нет.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="min-w-full text-sm">
        <thead className="bg-surface-2 text-left text-text-dim">
          <tr>
            <th className="px-3 py-2">Задача</th>
            <th className="px-3 py-2">Триггер</th>
            <th className="px-3 py-2">Начало</th>
            <th className="px-3 py-2">Длительность</th>
            <th className="px-3 py-2">Статус</th>
            <th className="px-3 py-2">Успешно / пропущено / ошибки</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const job = byId.get(run.job_id);
            return (
              <tr key={run.id} className="border-t border-border" data-testid="job-run-row">
                <td className="px-3 py-2">
                  {job ? `${JOB_LABELS[job.kind]} — ${PLATFORM_LABELS[job.platform]}` : "—"}
                </td>
                <td className="px-3 py-2">{run.trigger === "manual" ? "вручную" : "по расписанию"}</td>
                <td className="px-3 py-2">{new Date(run.started_at).toLocaleString("ru-RU")}</td>
                <td className="px-3 py-2">{duration(run)}</td>
                <td className="px-3 py-2">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${jobStatusClass(run.status)}`}>
                    {run.status}
                  </span>
                </td>
                <td className="px-3 py-2">
                  {run.orgs_succeeded} / {run.orgs_skipped} / {run.orgs_failed}
                </td>
                <td className="px-3 py-2 text-xs">
                  <Link className="text-accent" href={`/jobs/runs/${run.id}`}>
                    подробнее
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
