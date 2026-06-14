import type { ScrapeRun } from "@/lib/types";

function statusClass(status: ScrapeRun["status"]) {
  if (status === "success") return "bg-green-100 text-green-800";
  if (status === "failed") return "bg-red-100 text-red-800";
  if (status === "needs_manual_action") return "bg-amber-200 text-amber-950 ring-1 ring-amber-400";
  if (status === "running") return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-700";
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
    return <p className="text-sm text-slate-500">Сборы ещё не выполнялись.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-slate-600">
          <tr>
            <th className="px-3 py-2">Режим</th>
            <th className="px-3 py-2">Статус</th>
            <th className="px-3 py-2">Начало</th>
            <th className="px-3 py-2">Длительность</th>
            <th className="px-3 py-2">Seen / Inserted</th>
            <th className="px-3 py-2">Ошибка</th>
            <th className="px-3 py-2">Debug</th>
          </tr>
        </thead>
        <tbody>
          {items.map((run) => (
            <tr key={run.id} className="border-t align-top">
              <td className="px-3 py-2">{run.mode}</td>
              <td className="px-3 py-2">
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${statusClass(run.status)}`}>
                  {run.status}
                </span>
              </td>
              <td className="px-3 py-2">{new Date(run.started_at).toLocaleString("ru-RU")}</td>
              <td className="px-3 py-2">{duration(run)}</td>
              <td className="px-3 py-2">
                {run.reviews_seen} / {run.reviews_inserted}
              </td>
              <td className="max-w-xs px-3 py-2 text-red-700">{run.error_message ?? "—"}</td>
              <td className="px-3 py-2 text-xs">
                {run.debug_screenshot_path && <div>{run.debug_screenshot_path}</div>}
                {run.debug_html_path && <div>{run.debug_html_path}</div>}
                {!run.debug_screenshot_path && !run.debug_html_path && "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
