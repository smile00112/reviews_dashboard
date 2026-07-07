export type ScrapeMode = "public" | "operator_auth" | "public_http";

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
  rating: number | null;
  review_count: number | null;
  preferred_scrape_mode: ScrapeMode;
  last_successful_scrape_at: string | null;
  last_scrape_status: OrganizationScrapeStatus;
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
