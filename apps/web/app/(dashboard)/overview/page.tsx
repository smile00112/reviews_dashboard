"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getDashboardOverview, listCompanies, listOrganizations } from "@/lib/api";
import type {
  Company,
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

const PERIODS = new Set<OverviewPeriod>([
  "day",
  "week",
  "30d",
  "90d",
  "year",
  "all",
  "custom",
]);
const PLATFORMS = new Set<OverviewPlatform>(["all", "yandex", "google", "gis2"]);
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** `YYYY-MM-DD` or null — anything malformed is dropped (FR-012). */
function isoDateParam(raw: string | null): string | null {
  if (!raw || !ISO_DATE.test(raw)) return null;
  return Number.isNaN(Date.parse(raw)) ? null : raw;
}

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

  const rawPeriod = (PERIODS.has(params.get("period") as OverviewPeriod)
    ? params.get("period")
    : "30d") as OverviewPeriod;
  const platform = (PLATFORMS.has(params.get("platform") as OverviewPlatform)
    ? params.get("platform")
    : "all") as OverviewPlatform;
  const orgIds = useMemo(() => params.getAll("org_ids"), [params]);
  const companyId = params.get("company_id");

  // A custom range needs a valid, ordered pair — otherwise fall back to 30d.
  const rawFrom = isoDateParam(params.get("from"));
  const rawTo = isoDateParam(params.get("to"));
  const rangeOk = rawFrom !== null && rawTo !== null && rawFrom <= rawTo;
  const period: OverviewPeriod = rawPeriod === "custom" && !rangeOk ? "30d" : rawPeriod;
  const dateFrom = period === "custom" ? rawFrom : null;
  const dateTo = period === "custom" ? rawTo : null;

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listOrganizations().then(setOrgs).catch(() => setOrgs([]));
    listCompanies()
      .then((items) => setCompanies(items.filter((c) => c.is_active)))
      .catch(() => setCompanies([]));
  }, []);

  // A company_id that no longer exists is treated as "no brand" (FR-012).
  const activeCompanyId =
    companyId && companies.some((c) => c.id === companyId) ? companyId : null;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDashboardOverview({
      period,
      platform,
      orgIds,
      companyId: activeCompanyId ?? undefined,
      dateFrom: dateFrom ?? undefined,
      dateTo: dateTo ?? undefined,
    })
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
  }, [period, platform, orgIds, activeCompanyId, dateFrom, dateTo]);

  const pushParams = useCallback(
    (next: {
      period?: OverviewPeriod;
      platform?: OverviewPlatform;
      orgIds?: string[];
      companyId?: string | null;
      dateFrom?: string | null;
      dateTo?: string | null;
    }) => {
      const qs = new URLSearchParams();
      const nextPeriod = next.period ?? period;
      qs.set("period", nextPeriod);
      qs.set("platform", next.platform ?? platform);
      const nextCompany = next.companyId === undefined ? activeCompanyId : next.companyId;
      if (nextCompany) qs.set("company_id", nextCompany);
      // Dates only travel with the custom period; any preset drops them (FR-006).
      if (nextPeriod === "custom") {
        const from = next.dateFrom === undefined ? dateFrom : next.dateFrom;
        const to = next.dateTo === undefined ? dateTo : next.dateTo;
        if (from) qs.set("from", from);
        if (to) qs.set("to", to);
      }
      for (const id of next.orgIds ?? orgIds) qs.append("org_ids", id);
      router.replace(`/overview?${qs.toString()}`, { scroll: false });
    },
    [router, period, platform, orgIds, activeCompanyId, dateFrom, dateTo],
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
          companies={companies}
          companyId={activeCompanyId}
          dateFrom={dateFrom}
          dateTo={dateTo}
          onPeriod={(p) => pushParams({ period: p, dateFrom: null, dateTo: null })}
          onPlatform={(p) => pushParams({ platform: p })}
          onRange={(from, to) =>
            pushParams({ period: "custom", dateFrom: from, dateTo: to })
          }
          // Switching brands drops branch picks — they belong to the old brand (FR-010).
          onCompany={(id) => pushParams({ companyId: id, orgIds: [] })}
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
