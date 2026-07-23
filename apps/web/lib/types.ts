export type ScrapeMode =
  | "public"
  | "operator_auth"
  | "public_http"
  | "scrapeops"
  | "twogis_api";

export type OrganizationScrapeStatus =
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "needs_manual_action";

export type ScrapeRunStatus =
  | "queued"
  | "running"
  | "success"
  | "failed"
  | "needs_manual_action";

export type SessionStatus =
  | "missing"
  | "valid"
  | "expired"
  | "needs_manual_action"
  | "pending"
  | "awaiting_code";

export interface Organization {
  id: string;
  name: string | null;
  yandex_url: string | null; // null for 2GIS-only orgs
  normalized_url: string | null;
  external_id: string | null;
  address: string | null;
  rating: number | null; // Yandex оценка
  review_count: number | null; // Yandex кол-во отзывов
  yandex_rating_count: number | null; // Yandex кол-во оценок
  gis2_url: string | null;
  gis2_rating: number | null;
  gis2_review_count: number | null;
  gis2_rating_count: number | null;
  google_url: string | null;
  google_rating: number | null;
  google_review_count: number | null;
  google_rating_count: number | null;
  preferred_scrape_mode: ScrapeMode;
  yandex_scrape_status: OrganizationScrapeStatus;
  gis2_scrape_status: OrganizationScrapeStatus;
  yandex_last_successful_scrape_at: string | null;
  gis2_last_successful_scrape_at: string | null;
  city: string | null;
  region: string | null;
  company_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Permission keys mirror apps/api/app/core/permissions.py (page:* / action:*).
export type PermissionKey = string;

export interface RoleSummary {
  id: string;
  slug: string;
  name: string;
  is_system: boolean;
}

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  role: RoleSummary;
  // Effective permission set; the frontend mirrors it for UX (nav/button gating).
  permissions: PermissionKey[];
}

export interface Role {
  id: string;
  slug: string;
  name: string;
  is_system: boolean;
  description: string | null;
  permissions: PermissionKey[]; // ["*"] sentinel for the admin system role
  user_count: number;
}

export interface PermissionItem {
  key: string;
  label: string;
}

export interface PermissionCatalog {
  pages: PermissionItem[];
  actions: PermissionItem[];
}

export interface Company {
  id: string;
  name: string;
  short_name: string | null;
  is_active: boolean;
  branch_count: number;
  created_at: string;
  updated_at: string;
}

export interface BranchCityGroup {
  city: string;
  branches: Organization[];
}

export interface CompanyBranches {
  company_id: string;
  groups: BranchCityGroup[];
}

export interface Review {
  id: string;
  organization_id: string;
  organization_name: string | null;
  source: string;
  scrape_mode: ScrapeMode;
  external_review_id: string | null;
  author_name: string | null;
  rating: number;
  review_text: string;
  review_date_text: string | null;
  review_date: string | null;
  response_text: string | null;
  first_seen_at: string;
  last_seen_at: string;
  // null = present on platform; set = no longer seen by a full scrape pass (feature 011)
  removed_at: string | null;
  response_first_seen_at: string | null;
  // real platform publication day of the business reply (ISO date), null when unknown
  response_date: string | null;
  status: ReviewStatus | null;
  is_paid: boolean;
  paid_cost: number | null;
  platform: ReviewPlatform | null;
  sentiment: string | null;
  sentiment_score: number | null;
  problems: ReviewProblem[] | null;
}

export type ReviewStatus = "new" | "in_progress" | "answered" | "escalated";
export type ReviewPlatform = "yandex" | "google" | "gis2";
export type StatusTab = "all" | "unanswered" | "in_progress" | "escalated" | "answered";
export type ReviewTone = "neg" | "pos";
export type ReviewPeriod = "24h" | "7d" | "30d" | "year";
export type ReviewSort = "new" | "criticality";

export interface ReviewProblem {
  category: string;
  description: string;
  keywords_found: string[];
  severity: string;
  context: string;
}

export interface ReviewsSummary {
  total: number;
  new_count: number;
  unanswered: number;
  in_progress: number;
  escalated: number;
  answered: number;
  overdue_24h: number;
  negative: number;
}

export interface AspectStat {
  category: string;
  label: string;
  mentions: number;
  delta_pct: number | null;
  pos: number;
  neu: number;
  neg: number;
}

export interface AspectTrend {
  category: string;
  days: number;
  series: { date: string; count: number }[];
}

export interface AspectsResponse {
  aspects: AspectStat[];
  trend: AspectTrend | null;
}

export interface ScrapeRun {
  id: string;
  organization_id: string | null;
  mode: ScrapeMode;
  status: ScrapeRunStatus;
  started_at: string;
  finished_at: string | null;
  reviews_seen: number;
  reviews_inserted: number;
  reviews_updated: number;
  full_pass: boolean;
  error_code: string | null;
  error_message: string | null;
  debug_screenshot_path: string | null;
  debug_html_path: string | null;
}

export interface SessionInfo {
  status: SessionStatus;
  last_login_at: string | null;
  last_checked_at: string | null;
  storage_state_path: string | null;
  message?: string | null;
  progress?: SessionProgressStep[] | null;
}

export interface SessionProgressStep {
  at: string;
  step: string;
  url: string | null;
}

// --- Network overview dashboard (feature 009) ---

export type OverviewPeriod = "day" | "week" | "30d" | "90d" | "year" | "all" | "custom";
export type OverviewPlatform = "all" | "yandex" | "google" | "gis2";

export interface OverviewHeader {
  new_in_period: number;
  unanswered_over_24h: number;
  fresh_negatives_2h: number;
}

export interface KpiHero {
  network_avg_rating: number | null;
  network_avg_rating_delta: number | null;
  new_in_period: number;
  new_today: number;
  /** Feature 014: period-over-period deltas; null when the period has no predecessor. */
  new_in_period_delta: number | null;
  unanswered_delta_period: number | null;
  period_days: number | null;
  total_reviews: number;
  avg_per_day: number;
  unanswered_total: number;
  unanswered_delta_24h: number;
  overdue_24h: number;
}

export interface KpiStrip {
  response_avg_min: number | null;
  response_median_min: number | null;
  response_p95_min: number | null;
  response_approximate: boolean;
  sla_percent: number | null;
  positivity_percent: number;
  reputation_index: number | null;
  /** Feature 014: period-over-period deltas; null when the period has no predecessor. */
  response_avg_min_delta: number | null;
  sla_percent_delta: number | null;
  positivity_percent_delta: number | null;
  reputation_index_delta: number | null;
}

export interface DistributionBar {
  star: number;
  count: number;
  percent: number;
}

export interface RatingDistribution {
  bars: DistributionBar[];
  share_4_5: number;
  share_1_3: number;
  total: number;
}

export interface SentimentBlock {
  positive: number;
  neutral: number;
  negative: number;
  positive_percent: number;
  neutral_percent: number;
  negative_percent: number;
  analyzed_total: number;
}

export interface PlatformCount {
  platform: string;
  review_count: number;
}

export interface PlatformCard {
  platform: string;
  weighted_rating: number | null;
  rating_delta: number | null;
  negativity_percent: number | null;
  response_speed_hours: number | null;
}

export interface AttentionItem {
  type: string;
  title: string;
  subtitle: string;
  value: number;
  severity: string;
  link: string;
  rule_id: string | null;
  rule_name: string | null;
}

export interface WorstLocation {
  organization_id: string;
  city: string | null;
  name: string | null;
  rating: number | null;
  rating_delta: number | null;
  unanswered_count: number;
}

export interface TrendingAspect {
  category: string;
  mentions: number;
  change_percent: number | null;
  sentiment: { pos: number; neu: number; neg: number };
}

export interface DashboardOverview {
  period: string;
  platform: string;
  generated_at: string;
  header: OverviewHeader;
  kpi_hero: KpiHero;
  kpi_strip: KpiStrip;
  rating_distribution: RatingDistribution;
  sentiment: SentimentBlock;
  platform_breakdown: PlatformCount[];
  platform_cards: PlatformCard[];
  attention: AttentionItem[];
  worst_locations: WorstLocation[];
  trending_aspects: TrendingAspect[];
}

// --- Ratings page (feature 014) ---
// `null` always means «нет данных» (render a placeholder or a line gap), never 0.
// The one exception is WeekdayStat.count, where 0 is a real measurement.
export interface StarShare {
  star: number;
  count: number;
  share: number;
}

export interface PlatformDistributionRow {
  platform: string;
  label: string;
  avg_rating: number | null;
  total_reviews: number | null;
  /** null when the platform stores no per-review rows (Google, 2ГИС). */
  stars: StarShare[] | null;
  removed_count: number | null;
}

export interface TrendSeries {
  platform: string;
  label: string;
  color: string;
  /** Index-aligned with TrendBlock.labels; null = gap (no snapshot that month). */
  points: (number | null)[];
}

export interface TrendBlock {
  labels: string[];
  series: TrendSeries[];
}

export interface ResponseSpeedBlock {
  labels: string[];
  median_minutes: (number | null)[];
  p95_minutes: (number | null)[];
  sla_target_minutes: number;
}

export interface WeekdayStat {
  /** 0 = Monday .. 6 = Sunday */
  weekday: number;
  label: string;
  count: number;
  avg_rating: number | null;
}

export interface WeekdayGridColumn {
  key: string;
  label: string;
}

export interface WeekdayGridCell {
  count: number;
  avg_rating: number | null; // null = нет данных, never rendered as 0
}

export interface WeekdayGridRow {
  /** 0 = Monday .. 6 = Sunday */
  weekday: number;
  label: string;
  /** index-aligned with WeekdayGrid.columns */
  cells: WeekdayGridCell[];
}

export interface WeekdayGrid {
  columns: WeekdayGridColumn[];
  rows: WeekdayGridRow[];
  insight: string | null;
}

export interface WeekdayBlock {
  days: WeekdayStat[];
  insight: string | null;
  grid?: WeekdayGrid | null;
}

export interface DashboardRatings {
  period: string;
  platform: string;
  generated_at: string;
  platform_distribution: PlatformDistributionRow[];
  rating_trend: TrendBlock;
  volume_trend: TrendBlock;
  response_speed: ResponseSpeedBlock;
  weekday: WeekdayBlock;
}

// --- Правила блока «Требуют внимания» ---
export type AttentionRuleType =
  | "unanswered_overdue"
  | "fresh_negative"
  | "escalated"
  | "rating_drop"
  | "aspect_spike";

export type AttentionSeverity = "urgent" | "warn" | "info";

export type AttentionScopeType = "global" | "company" | "organizations";

export interface AttentionRule {
  id: string;
  rule_type: AttentionRuleType;
  name: string | null;
  is_enabled: boolean;
  severity: AttentionSeverity;
  params: Record<string, number>;
  scope_type: AttentionScopeType;
  company_id: string | null;
  organization_ids: string[];
  // Feature 015: крон-модель.
  period_days: number;
  window_started_at: string;
  latched_at: string | null;
  is_latched: boolean;
  period_ends_at: string;
  created_at: string;
  updated_at: string;
}

export interface AttentionRuleCreatePayload {
  rule_type: AttentionRuleType;
  name?: string | null;
  is_enabled?: boolean;
  severity: AttentionSeverity;
  params?: Record<string, number>;
  scope_type?: AttentionScopeType;
  company_id?: string | null;
  organization_ids?: string[];
  period_days?: number;
}

export type AttentionRuleUpdatePayload = Partial<Omit<AttentionRuleCreatePayload, "rule_type">>;

export interface AttentionEvent {
  id: string;
  rule_id: string;
  fired_at: string;
  type: AttentionRuleType;
  severity: AttentionSeverity;
  title: string;
  subtitle: string | null;
  value: number;
  link: string;
}

export interface AttentionRuleRestartResult {
  rule: AttentionRule;
  events: AttentionEvent[];
}

// --- Фоновые задачи ---
export type JobKind = "org_metrics" | "reviews";

export type JobTrigger = "schedule" | "manual";

export type JobRunStatus =
  | "queued"
  | "running"
  | "success"
  | "partial"
  | "failed"
  | "needs_manual_action"
  | "cancelled";

export type JobItemStatus = "success" | "skipped" | "failed" | "needs_manual_action";

export interface JobRun {
  id: string;
  job_id: string;
  trigger: JobTrigger;
  triggered_by_user_id: string | null;
  status: JobRunStatus;
  started_at: string;
  finished_at: string | null;
  orgs_total: number;
  orgs_succeeded: number;
  orgs_skipped: number;
  orgs_failed: number;
  error_message: string | null;
}

export interface Job {
  id: string;
  kind: JobKind;
  platform: "yandex" | "gis2"; // Google out of scope
  schedule_cron: string | null;
  timezone: string;
  is_enabled: boolean;
  options: Record<string, unknown>;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run: JobRun | null;
}

export interface JobRunItem {
  id: string;
  organization_id: string;
  organization_name: string | null;
  status: JobItemStatus;
  reason: string | null;
  payload: Record<string, number | string | null>;
  scrape_run_id: string | null;
  error_code: string | null;
  error_message: string | null;
  duration_ms: number | null;
}

export interface JobRunDetail extends JobRun {
  job: Job;
  items: JobRunItem[];
}

export type Settings = {
  overview_sla_threshold_minutes: number;
};
