"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getOrganization, listOrganizationReviews } from "@/lib/api";
import type { Organization, Review } from "@/lib/types";
import { ReviewsTable } from "@/components/reviews-table";

export default function OrganizationDetailPage() {
  const params = useParams<{ id: string }>();
  const [org, setOrg] = useState<Organization | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);

  useEffect(() => {
    if (!params.id) return;
    Promise.all([getOrganization(params.id), listOrganizationReviews(params.id)])
      .then(([organization, data]) => {
        setOrg(organization);
        setReviews(data.items);
      })
      .catch(console.error);
  }, [params.id]);

  if (!org) {
    return <p className="text-sm text-slate-500">Загрузка...</p>;
  }

  return (
    <div className="space-y-4">
      <Link href="/organizations" className="text-sm text-blue-600 hover:underline">
        ← Назад к списку
      </Link>
      <div>
        <h1 className="text-2xl font-semibold">{org.name ?? "Организация"}</h1>
        <p className="text-sm text-slate-600">{org.yandex_url}</p>
        <p className="text-sm text-slate-600">
          Статус: {org.last_scrape_status} · Рейтинг: {org.rating ?? "—"} · Отзывов: {org.review_count ?? "—"}
        </p>
      </div>
      <ReviewsTable items={reviews} emptyMessage="Отзывы для этой организации ещё не собраны." />
    </div>
  );
}
