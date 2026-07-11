"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getOrganization, listOrganizationReviews } from "@/lib/api";
import type { Organization, Review } from "@/lib/types";
import { ReviewsTable } from "@/components/reviews-table";

function PlatformCard({
  title,
  url,
  rating,
  reviewCount,
  ratingCount,
}: {
  title: string;
  url: string | null;
  rating: number | null;
  reviewCount: number | null;
  ratingCount: number | null;
}) {
  return (
    <div className="rounded-lg border bg-white p-3">
      <div className="text-sm font-medium text-slate-800">{title}</div>
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-0.5 block truncate text-xs text-blue-600 hover:underline"
          title={url}
        >
          {url}
        </a>
      ) : (
        <div className="mt-0.5 text-xs text-slate-400">Нет ссылки</div>
      )}
      <dl className="mt-2 space-y-0.5 text-sm text-slate-600">
        <div className="flex justify-between">
          <dt>Рейтинг</dt>
          <dd>{rating ?? "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Отзывов</dt>
          <dd>{reviewCount ?? "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Оценок</dt>
          <dd>{ratingCount ?? "—"}</dd>
        </div>
      </dl>
    </div>
  );
}

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
        <p className="text-sm text-slate-600">
          Статус — Яндекс: {org.yandex_scrape_status} · 2ГИС: {org.gis2_scrape_status}
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <PlatformCard
            title="Яндекс"
            url={org.yandex_url}
            rating={org.rating}
            reviewCount={org.review_count}
            ratingCount={org.yandex_rating_count}
          />
          <PlatformCard
            title="2ГИС"
            url={org.gis2_url}
            rating={org.gis2_rating}
            reviewCount={org.gis2_review_count}
            ratingCount={org.gis2_rating_count}
          />
          <PlatformCard
            title="Google Maps"
            url={org.google_url}
            rating={org.google_rating}
            reviewCount={org.google_review_count}
            ratingCount={org.google_rating_count}
          />
        </div>
      </div>
      <ReviewsTable items={reviews} emptyMessage="Отзывы для этой организации ещё не собраны." />
    </div>
  );
}
