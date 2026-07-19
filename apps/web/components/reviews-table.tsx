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
    return <p className="rounded-lg border bg-white p-6 text-sm text-slate-500">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-slate-600">
          <tr>
            <th className="px-3 py-2">Организация</th>
            <th className="px-3 py-2">Автор</th>
            <th className="px-3 py-2">Оценка</th>
            <th className="px-3 py-2">Дата</th>
            <th className="px-3 py-2">Текст</th>
            <th className="px-3 py-2">Режим</th>
            <th className="px-3 py-2">Первый сбор</th>
          </tr>
        </thead>
        <tbody>
          {items.map((review) => (
            <tr key={review.id} className={`border-t align-top ${review.removed_at ? "opacity-60" : ""}`}>
              <td className="px-3 py-2">{review.organization_name ?? review.organization_id.slice(0, 8)}</td>
              <td className="px-3 py-2">{review.author_name ?? "—"}</td>
              <td className="px-3 py-2">{review.rating}</td>
              <td className="px-3 py-2">{review.review_date_text ?? review.review_date ?? "—"}</td>
              <td className="max-w-md px-3 py-2">
                {review.removed_at ? (
                  <span
                    className="mb-1 mr-2 inline-block rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-700"
                    title={`Отзыв больше не найден на площадке (${new Date(review.removed_at).toLocaleDateString("ru-RU")})`}
                  >
                    Удалён с площадки {new Date(review.removed_at).toLocaleDateString("ru-RU")}
                  </span>
                ) : null}
                {review.review_text}
              </td>
              <td className="px-3 py-2">{review.scrape_mode}</td>
              <td className="px-3 py-2">{new Date(review.first_seen_at).toLocaleString("ru-RU")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
