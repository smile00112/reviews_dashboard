"use client";

import { useState } from "react";
import type { Job } from "@/lib/types";

const PRESETS: { label: string; cron: string }[] = [
  { label: "Каждый час", cron: "0 * * * *" },
  { label: "Каждые 6 часов", cron: "0 */6 * * *" },
  { label: "Ежедневно в 04:00", cron: "0 4 * * *" },
  { label: "Ежедневно в 05:00", cron: "0 5 * * *" },
];

interface ScheduleModalProps {
  job: Job;
  onClose: () => void;
  onSubmit: (cron: string) => Promise<void>;
}

export function ScheduleModal({ job, onClose, onSubmit }: ScheduleModalProps) {
  const [cron, setCron] = useState(job.schedule_cron ?? "0 4 * * *");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-4">
        <div className="font-medium">Расписание</div>
        <div className="mt-3 flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset.cron}
              type="button"
              className={`rounded border px-2 py-1 text-xs ${
                cron === preset.cron ? "border-accent text-accent" : "border-border"
              }`}
              onClick={() => setCron(preset.cron)}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <label className="mt-3 block text-xs text-text-dim">
          Cron ({job.timezone})
          <input
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1 font-mono text-xs"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            data-testid="cron-input"
          />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="rounded border border-border px-3 py-1.5 text-xs" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-black"
            onClick={() => onSubmit(cron)}
            data-testid="cron-save"
          >
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}
