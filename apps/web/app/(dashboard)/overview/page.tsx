"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getDashboardOverview, listOrganizations } from "@/lib/api";
import type {
  DashboardOverview,
  Organization,
  OverviewPeriod,
  OverviewPlatform,
} from "@/lib/types";
import { KpiHeroCards } from "@/components/dashboard/kpi-hero";
import { KpiStripRow } from "@/components/dashboard/kpi-strip";
import { RatingDistributionPanel } from "@/components/dashboard/rating-distribution";
import { SentimentDonutPanel } from "@/components/dashboard/sentiment-donut";
import { PlatformDonutPanel } from "@/components/dashboard/platform-donut";
import { PlatformCards } from "@/components/dashboard/platform-cards";
import { AttentionList } from "@/components/dashboard/attention-list";
import { WorstLocationsTable } from "@/components/dashboard/worst-locations-table";
import { TrendingAspectsTable } from "@/components/dashboard/trending-aspects-table";
import { DashboardFilters } from "@/components/dashboard/dashboard-filters";

const PERIODS = new Set<OverviewPeriod>(["day", "week", "30d", "90d", "year", "all"]);
const PLATFORMS = new Set<OverviewPlatform>(["all", "yandex", "google", "gis2"]);

/** Russian plural agreement: pick(one, few, many) by count. */
function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

function OverviewContent() {
  const router = useRouter();
  const params = useSearchParams();

  const period = (PERIODS.has(params.get("period") as OverviewPeriod)
    ? params.get("period")
    : "30d") as OverviewPeriod;
  const platform = (PLATFORMS.has(params.get("platform") as OverviewPlatform)
    ? params.get("platform")
    : "all") as OverviewPlatform;
  const orgIds = useMemo(() => params.getAll("org_ids"), [params]);

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listOrganizations().then(setOrgs).catch(() => setOrgs([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDashboardOverview({ period, platform, orgIds })
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Ошибка загрузки");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [period, platform, orgIds]);

  const pushParams = useCallback(
    (next: { period?: OverviewPeriod; platform?: OverviewPlatform; orgIds?: string[] }) => {
      const qs = new URLSearchParams();
      qs.set("period", next.period ?? period);
      qs.set("platform", next.platform ?? platform);
      for (const id of next.orgIds ?? orgIds) qs.append("org_ids", id);
      router.replace(`/overview?${qs.toString()}`, { scroll: false });
    },
    [router, period, platform, orgIds],
  );

  const toggleOrg = (id: string) =>
    pushParams({ orgIds: orgIds.includes(id) ? orgIds.filter((o) => o !== id) : [...orgIds, id] });

  return (
    <div>
      <div className="mb-7 flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="font-display text-4xl font-medium tracking-tight">Обзор сети</h1>
          {data && (
            <p className="mt-1.5 text-sm text-text-dim">
              {data.header.new_in_period}{" "}
              {plural(data.header.new_in_period, "новый отзыв", "новых отзыва", "новых отзывов")} ·{" "}
              {data.header.unanswered_over_24h} без ответа &gt; 24ч · {data.header.fresh_negatives_2h}{" "}
              {plural(data.header.fresh_negatives_2h, "негатив", "негатива", "негативов")} за 2ч
            </p>
          )}
        </div>
        <DashboardFilters
          period={period}
          platform={platform}
          orgIds={orgIds}
          orgs={orgs}
          onPeriod={(p) => pushParams({ period: p })}
          onPlatform={(p) => pushParams({ platform: p })}
          onToggleOrg={toggleOrg}
          onClearOrgs={() => pushParams({ orgIds: [] })}
        />
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="py-20 text-center text-text-faint">Загрузка…</div>
      ) : data ? (
        <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <KpiHeroCards hero={data.kpi_hero} />
          <KpiStripRow strip={data.kpi_strip} />

          <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <RatingDistributionPanel dist={data.rating_distribution} />
            <SentimentDonutPanel sentiment={data.sentiment} />
            <PlatformDonutPanel breakdown={data.platform_breakdown} />
          </div>

          <PlatformCards cards={data.platform_cards} />

          <div className="mb-4">
            <AttentionList items={data.attention} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <WorstLocationsTable rows={data.worst_locations} />
            <TrendingAspectsTable aspects={data.trending_aspects} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function OverviewPage() {
  return (
    <Suspense fallback={<div className="py-20 text-center text-text-faint">Загрузка…</div>}>
      <OverviewContent />
    </Suspense>
  );
}
