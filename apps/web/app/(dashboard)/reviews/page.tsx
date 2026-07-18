"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  getReviewAspects,
  getReviewsSummary,
  listOrganizations,
  listReviews,
} from "@/lib/api";
import type {
  AspectsResponse,
  Organization,
  Review,
  ReviewPeriod,
  ReviewPlatform,
  ReviewSort,
  ReviewTone,
  ReviewsSummary,
  StatusTab,
} from "@/lib/types";
import { StatusTabs } from "@/components/reviews/status-tabs";
import { ReviewFilters, type FeedFilterState } from "@/components/reviews/review-filters";
import { ReviewCard } from "@/components/reviews/review-card";
import { AspectsPanel } from "@/components/reviews/aspects-panel";

const PAGE_SIZE = 50;

const STATUS_TABS: readonly StatusTab[] = ["all", "unanswered", "in_progress", "escalated", "answered"];
const TONES: readonly ReviewTone[] = ["neg", "pos"];
const PERIODS: readonly ReviewPeriod[] = ["24h", "7d", "30d", "year"];
const PLATFORMS: readonly ReviewPlatform[] = ["yandex", "google", "gis2"];
const SORTS: readonly ReviewSort[] = ["new", "criticality"];
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function pick<T extends string>(value: string | null, allowed: readonly T[]): T | undefined {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : undefined;
}

function ReviewsContent() {
  const router = useRouter();
  const params = useSearchParams();

  // URL is the single source of filter state (deep links from the overview
  // attention feed arrive as /reviews?rating=1, /reviews?status=escalated).
  const tab = pick(params.get("status"), STATUS_TABS) ?? "all";
  const tone = pick(params.get("tone"), TONES);
  const period = pick(params.get("period"), PERIODS);
  const platform = pick(params.get("platform"), PLATFORMS);
  const rawOrg = params.get("organization_id");
  const organizationId = rawOrg && UUID_RE.test(rawOrg) ? rawOrg : undefined;
  const paidOnly = params.get("is_paid") === "true" || undefined;
  const aspect = params.get("aspect") ?? undefined;
  const sort = pick(params.get("sort"), SORTS) ?? "new";
  const rawRating = params.get("rating");
  const rating = rawRating && /^[1-5]$/.test(rawRating) ? rawRating : undefined;
  const newOnly = params.get("new_only") === "true" || undefined;

  const [reviews, setReviews] = useState<Review[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<ReviewsSummary | null>(null);
  const [aspects, setAspects] = useState<AspectsResponse | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const requestGen = useRef(0);

  const setParams = useCallback(
    (patch: Record<string, string | undefined>) => {
      const next = new URLSearchParams(params.toString());
      Object.entries(patch).forEach(([key, value]) => {
        if (value === undefined) next.delete(key);
        else next.set(key, value);
      });
      const qs = next.toString();
      router.replace(qs ? `/reviews?${qs}` : "/reviews");
    },
    [params, router],
  );

  const feedParams = useCallback(
    (offset: number) => ({
      status: tab === "all" ? undefined : tab,
      tone,
      period,
      platform,
      organization_id: organizationId,
      is_paid: paidOnly,
      aspect,
      sort,
      rating,
      new_only: newOnly,
      limit: PAGE_SIZE,
      offset,
    }),
    [tab, tone, period, platform, organizationId, paidOnly, aspect, sort, rating, newOnly],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    requestGen.current += 1;
    Promise.all([
      listReviews(feedParams(0)),
      getReviewsSummary({
        tone, period, platform, organization_id: organizationId, is_paid: paidOnly, aspect, rating,
      }),
      getReviewAspects({ period: period ?? "30d", organization_id: organizationId, platform, aspect }),
      listOrganizations(),
    ])
      .then(([feed, sum, asp, organizations]) => {
        if (cancelled) return;
        setReviews(feed.items);
        setTotal(feed.total);
        setSummary(sum);
        setAspects(asp);
        setOrgs(organizations);
      })
      .catch(console.error)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [feedParams, tone, period, platform, organizationId, paidOnly, aspect, rating]);

  async function loadMore() {
    const gen = requestGen.current;
    setLoadingMore(true);
    try {
      const feed = await listReviews(feedParams(reviews.length));
      if (gen !== requestGen.current) return;
      setReviews((prev) => [...prev, ...feed.items]);
      setTotal(feed.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingMore(false);
    }
  }

  function onFilterChange(patch: FeedFilterState) {
    setParams({
      tone: "tone" in patch ? patch.tone : tone,
      period: "period" in patch ? patch.period : period,
      platform: "platform" in patch ? patch.platform : platform,
      organization_id: "organizationId" in patch ? patch.organizationId : organizationId,
      is_paid: "paidOnly" in patch ? (patch.paidOnly ? "true" : undefined) : paidOnly ? "true" : undefined,
    });
  }

  function onPatched(updated: Review) {
    setReviews((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  }

  const subtitle = summary
    ? `${summary.total} отзывов · ${summary.new_count} новых · ${summary.unanswered} без ответа · ${summary.overdue_24h} просрочены > 24ч`
    : "";

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Отзывы</h1>
        {subtitle && <p className="mt-1 text-[13px] text-text-faint">{subtitle}</p>}
      </div>

      <StatusTabs tab={tab} summary={summary} onTab={(t) => setParams({ status: t === "all" ? undefined : t })} />

      <ReviewFilters
        tone={tone}
        period={period}
        platform={platform}
        organizationId={organizationId}
        paidOnly={paidOnly}
        orgs={orgs}
        summary={summary}
        onChange={onFilterChange}
        onReset={() => router.replace("/reviews")}
      />

      <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[14px] font-semibold">Лента отзывов</div>
              <div className="text-[11.5px] text-text-faint">
                {sort === "new" ? "Хронологически · самые новые сверху" : "Критичные сверху"}
              </div>
            </div>
            <div className="flex gap-1 rounded-lg border border-border bg-surface-2 p-0.5 text-[12px]">
              <button
                type="button"
                onClick={() => setParams({ sort: undefined })}
                className={`rounded px-2.5 py-1 ${sort === "new" ? "bg-surface-3 text-text" : "text-text-dim"}`}
              >
                ↻ Новые
              </button>
              <button
                type="button"
                onClick={() => setParams({ sort: "criticality" })}
                className={`rounded px-2.5 py-1 ${sort === "criticality" ? "bg-surface-3 text-text" : "text-text-dim"}`}
              >
                ⚡ По критичности
              </button>
            </div>
          </div>

          {loading ? (
            <div className="py-20 text-center text-text-faint">Загрузка…</div>
          ) : reviews.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface-1 py-14 text-center">
              <div className="text-3xl">📭</div>
              <div className="mt-2 font-semibold">Под выбранные фильтры ничего не нашлось</div>
              <div className="mt-1 text-[12.5px] text-text-faint">
                Попробуйте сбросить часть фильтров или расширить период.
              </div>
              <button
                type="button"
                onClick={() => router.replace("/reviews")}
                className="mt-4 rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[12.5px] text-text-dim hover:text-text"
              >
                Сбросить фильтры
              </button>
            </div>
          ) : (
            <>
              {reviews.map((review) => (
                <ReviewCard
                  key={review.id}
                  review={review}
                  onPatched={onPatched}
                  onAspect={(category) => setParams({ aspect: category })}
                />
              ))}
              {reviews.length < total && (
                <button
                  type="button"
                  disabled={loadingMore}
                  onClick={loadMore}
                  className="w-full rounded-xl border border-border bg-surface-1 py-2.5 text-[13px] text-text-dim hover:text-text disabled:opacity-50"
                >
                  {loadingMore ? "Загрузка…" : `Показать ещё (${total - reviews.length})`}
                </button>
              )}
            </>
          )}
        </div>

        <AspectsPanel
          data={aspects}
          activeAspect={aspect ?? null}
          onAspect={(category) => setParams({ aspect: category ?? undefined })}
        />
      </div>
    </div>
  );
}

export default function ReviewsPage() {
  return (
    <Suspense fallback={<div className="py-20 text-center text-text-faint">Загрузка…</div>}>
      <ReviewsContent />
    </Suspense>
  );
}
