import type { ScrapeRun } from "@/lib/types";

function statusClass(status: ScrapeRun["status"]) {
  if (status === "success") return "bg-good/15 text-good";
  if (status === "failed") return "bg-bad/15 text-bad";
  if (status === "needs_manual_action") return "bg-warn/15 text-warn ring-1 ring-warn/40";
  if (status === "running") return "bg-info/15 text-info";
  return "bg-surface-3 text-text-dim";
}

function duration(run: ScrapeRun) {
  if (!run.finished_at) return "—";
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  return `${Math.round(ms / 1000)}s`;
}

interface ScrapeRunStatusProps {
  items: ScrapeRun[];
}

export function ScrapeRunStatusTable({ items }: ScrapeRunStatusProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-surface py-12 text-center text-sm text-text-faint">
        Сборы ещё не выполнялись.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-surface p-[22px]">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="text-[11px] uppercase tracking-wider text-text-faint">
            <th className="border-b border-border px-3 py-2.5 text-left">Режим</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Статус</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Начало</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Длительность</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Seen / Inserted</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Ошибка</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Debug</th>
          </tr>
        </thead>
        <tbody>
          {items.map((run) => (
            <tr key={run.id} className="align-top transition-colors hover:bg-surface-2">
              <td className="border-b border-border px-3 py-3 font-mono text-[11px] text-text-dim">{run.mode}</td>
              <td className="border-b border-border px-3 py-3">
                <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${statusClass(run.status)}`}>
                  {run.status}
                </span>
              </td>
              <td className="whitespace-nowrap border-b border-border px-3 py-3 font-mono text-[11px] text-text-dim">
                {new Date(run.started_at).toLocaleString("ru-RU")}
              </td>
              <td className="border-b border-border px-3 py-3 font-mono text-xs">{duration(run)}</td>
              <td className="border-b border-border px-3 py-3 font-mono text-xs">
                {run.reviews_seen} / {run.reviews_inserted}
              </td>
              <td className="max-w-xs border-b border-border px-3 py-3 text-bad">{run.error_message ?? "—"}</td>
              <td className="border-b border-border px-3 py-3 font-mono text-[11px] text-text-faint">
                {run.debug_screenshot_path && <div className="truncate">{run.debug_screenshot_path}</div>}
                {run.debug_html_path && <div className="truncate">{run.debug_html_path}</div>}
                {!run.debug_screenshot_path && !run.debug_html_path && "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
