"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getOrganization, listOrganizationReviews } from "@/lib/api";
import type { Organization, Review } from "@/lib/types";
import { ReviewsTable } from "@/components/reviews-table";
import { useCan } from "@/components/shell/user-context";

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
    <div className="rounded-2xl border border-border bg-surface p-4">
      <div className="text-[11px] font-medium uppercase tracking-wider text-text-faint">{title}</div>
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1 block truncate text-xs text-text-dim hover:text-accent"
          title={url}
        >
          {url}
        </a>
      ) : (
        <div className="mt-1 text-xs text-text-faint">Нет ссылки</div>
      )}
      <dl className="mt-3 space-y-1 text-sm text-text-dim">
        <div className="flex justify-between">
          <dt>Рейтинг</dt>
          <dd className="font-mono text-text">{rating ?? "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Отзывов</dt>
          <dd className="font-mono text-text">{reviewCount ?? "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Оценок</dt>
          <dd className="font-mono text-text">{ratingCount ?? "—"}</dd>
        </div>
      </dl>
    </div>
  );
}

export default function OrganizationDetailPage() {
  const params = useParams<{ id: string }>();
  const canManage = useCan("action:org.manage");
  const [org, setOrg] = useState<Organization | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [showRemoved, setShowRemoved] = useState(false);

  useEffect(() => {
    if (!params.id) return;
    Promise.all([
      getOrganization(params.id),
      listOrganizationReviews(params.id, showRemoved ? "all" : "active"),
    ])
      .then(([organization, data]) => {
        setOrg(organization);
        setReviews(data.items);
      })
      .catch(console.error);
  }, [params.id, showRemoved]);

  if (!org) {
    return <p className="text-sm text-text-faint">Загрузка...</p>;
  }

  return (
    <div className="space-y-5">
      <Link href="/organizations" className="text-sm text-text-dim hover:text-accent">
        ← Назад к списку
      </Link>
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-4xl font-medium tracking-tight">{org.name ?? "Организация"}</h1>
            {!org.is_active && (
              <span className="rounded-full border border-border bg-surface-2 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
                Неактивна
              </span>
            )}
          </div>
          {canManage && (
            <Link
              href={`/organizations/${org.id}/edit`}
              className="rounded-lg border border-border bg-surface-2 px-4 py-2 text-[13px] font-semibold text-text hover:bg-surface-3"
            >
              Изменить
            </Link>
          )}
        </div>
        <p className="mt-1.5 text-sm text-text-dim">
          Статус — Яндекс: {org.yandex_scrape_status} · 2ГИС: {org.gis2_scrape_status}
          {!org.is_active && " · сбор отзывов отключён"}
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
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
      <label className="flex items-center gap-2 text-sm text-text-dim">
        <input
          type="checkbox"
          checked={showRemoved}
          onChange={(event) => setShowRemoved(event.target.checked)}
          className="accent-accent"
        />
        Показать удалённые с площадки
      </label>
      <ReviewsTable items={reviews} emptyMessage="Отзывы для этой организации ещё не собраны." />
    </div>
  );
}
