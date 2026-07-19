import type { Review } from "@/lib/types";

interface ReviewsTableProps {
  items: Review[];
  emptyMessage?: string;
}

export function ReviewsTable({
  items,
  emptyMessage = "Отзывы не найдены.",
}: ReviewsTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-surface py-12 text-center text-sm text-text-faint">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-surface p-[22px]">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="text-[11px] uppercase tracking-wider text-text-faint">
            <th className="border-b border-border px-3 py-2.5 text-left">Организация</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Автор</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Оценка</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Дата</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Текст</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Режим</th>
            <th className="border-b border-border px-3 py-2.5 text-left">Первый сбор</th>
          </tr>
        </thead>
        <tbody>
          {items.map((review) => (
            <tr
              key={review.id}
              className={`align-top transition-colors hover:bg-surface-2 ${review.removed_at ? "opacity-60" : ""}`}
            >
              <td className="border-b border-border px-3 py-3 text-text-dim">
                {review.organization_name ?? review.organization_id.slice(0, 8)}
              </td>
              <td className="border-b border-border px-3 py-3">{review.author_name ?? "—"}</td>
              <td className="border-b border-border px-3 py-3 font-mono text-xs">{review.rating}</td>
              <td className="border-b border-border px-3 py-3 text-text-dim">
                {review.review_date_text ?? review.review_date ?? "—"}
              </td>
              <td className="max-w-md border-b border-border px-3 py-3">
                {review.removed_at ? (
                  <span
                    className="mb-1 mr-2 inline-block rounded-md bg-bad/15 px-1.5 py-0.5 text-xs font-medium text-bad"
                    title={`Отзыв больше не найден на площадке (${new Date(review.removed_at).toLocaleDateString("ru-RU")})`}
                  >
                    Удалён с площадки {new Date(review.removed_at).toLocaleDateString("ru-RU")}
                  </span>
                ) : null}
                {review.review_text}
              </td>
              <td className="border-b border-border px-3 py-3 font-mono text-[11px] text-text-dim">
                {review.scrape_mode}
              </td>
              <td className="whitespace-nowrap border-b border-border px-3 py-3 font-mono text-[11px] text-text-dim">
                {new Date(review.first_seen_at).toLocaleString("ru-RU")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
