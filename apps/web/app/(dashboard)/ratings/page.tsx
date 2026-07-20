"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getDashboardRatings, listCompanies, listOrganizations } from "@/lib/api";
import type {
  Company,
  DashboardRatings,
  Organization,
  OverviewPeriod,
  OverviewPlatform,
} from "@/lib/types";
import { DashboardFilters } from "@/components/dashboard/dashboard-filters";
import { PlatformDistributionTable } from "@/components/dashboard/ratings/platform-distribution-table";
import { RatingTrendChart } from "@/components/dashboard/ratings/rating-trend-chart";
import { VolumeTrendChart } from "@/components/dashboard/ratings/volume-trend-chart";
import { ResponseSpeedChart } from "@/components/dashboard/ratings/response-speed-chart";
import { WeekdayBreakdown } from "@/components/dashboard/ratings/weekday-breakdown";

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

function RatingsContent() {
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
  const [data, setData] = useState<DashboardRatings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listOrganizations().then(setOrgs).catch(() => setOrgs([]));
    listCompanies()
      .then((items) => setCompanies(items.filter((c) => c.is_active)))
      .catch(() => setCompanies([]));
  }, []);

  // A company_id that no longer exists is treated as "no brand".
  const activeCompanyId =
    companyId && companies.some((c) => c.id === companyId) ? companyId : null;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDashboardRatings({
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
      // Dates only travel with the custom period; any preset drops them.
      if (nextPeriod === "custom") {
        const from = next.dateFrom === undefined ? dateFrom : next.dateFrom;
        const to = next.dateTo === undefined ? dateTo : next.dateTo;
        if (from) qs.set("from", from);
        if (to) qs.set("to", to);
      }
      for (const id of next.orgIds ?? orgIds) qs.append("org_ids", id);
      router.replace(`/ratings?${qs.toString()}`, { scroll: false });
    },
    [router, period, platform, orgIds, activeCompanyId, dateFrom, dateTo],
  );

  const toggleOrg = (id: string) =>
    pushParams({ orgIds: orgIds.includes(id) ? orgIds.filter((o) => o !== id) : [...orgIds, id] });

  return (
    <div>
      <div className="mb-7 flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="font-display text-4xl font-medium tracking-tight">Рейтинги</h1>
          <p className="mt-1.5 text-sm text-text-dim">
            Сравнительный анализ оценок по площадкам, динамика, активность по дням недели
          </p>
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
          onRange={(from, to) => pushParams({ period: "custom", dateFrom: from, dateTo: to })}
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
          <div className="mb-4">
            <PlatformDistributionTable rows={data.platform_distribution} />
          </div>

          <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <RatingTrendChart block={data.rating_trend} />
            <VolumeTrendChart block={data.volume_trend} />
          </div>

          <div className="mb-4">
            <ResponseSpeedChart block={data.response_speed} />
          </div>

          <WeekdayBreakdown block={data.weekday} />
        </div>
      ) : null}
    </div>
  );
}

export default function RatingsPage() {
  return (
    <Suspense fallback={<div className="py-20 text-center text-text-faint">Загрузка…</div>}>
      <RatingsContent />
    </Suspense>
  );
}
