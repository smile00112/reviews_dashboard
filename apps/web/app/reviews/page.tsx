"use client";

import { useEffect, useState } from "react";
import { listOrganizations, listReviews } from "@/lib/api";
import type { Organization, Review } from "@/lib/types";
import { ReviewsTable } from "@/components/reviews-table";

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [rating, setRating] = useState("");
  const [newOnly, setNewOnly] = useState(false);

  async function load() {
    const [orgs, data] = await Promise.all([
      listOrganizations(),
      listReviews({
        organization_id: organizationId || undefined,
        rating: rating || undefined,
        new_only: newOnly || undefined,
      }),
    ]);
    setOrganizations(orgs);
    setReviews(data.items);
  }

  useEffect(() => {
    load().catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Все отзывы</h1>
      <div className="flex flex-wrap gap-3 rounded-lg border bg-white p-4 text-sm">
        <label className="flex flex-col gap-1">
          Организация
          <select
            value={organizationId}
            onChange={(e) => setOrganizationId(e.target.value)}
            className="rounded border px-2 py-1"
          >
            <option value="">Все</option>
            {organizations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name ?? org.yandex_url}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          Оценка
          <select value={rating} onChange={(e) => setRating(e.target.value)} className="rounded border px-2 py-1">
            <option value="">Все</option>
            {[5, 4, 3, 2, 1].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 self-end pb-1">
          <input type="checkbox" checked={newOnly} onChange={(e) => setNewOnly(e.target.checked)} />
          Только новые
        </label>
        <button
          type="button"
          onClick={() => load()}
          className="self-end rounded bg-slate-800 px-3 py-1 text-white hover:bg-slate-900"
        >
          Применить
        </button>
      </div>
      <ReviewsTable items={reviews} />
    </div>
  );
}
