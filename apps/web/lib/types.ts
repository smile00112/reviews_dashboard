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
  | "needs_manual_action";

export interface Organization {
  id: string;
  name: string | null;
  yandex_url: string;
  normalized_url: string;
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
  created_at: string;
  updated_at: string;
}

export type UserRole = "admin" | "review_operator";

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
}

export interface Company {
  id: string;
  name: string;
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
}

// --- Network overview dashboard (feature 009) ---

export type OverviewPeriod = "day" | "week" | "30d" | "90d" | "year" | "all";
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
