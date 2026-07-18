import type {
  AspectsResponse,
  Company,
  CompanyBranches,
  CurrentUser,
  DashboardOverview,
  Job,
  JobRun,
  JobRunDetail,
  JobRunStatus,
  Organization,
  OverviewPeriod,
  OverviewPlatform,
  Review,
  ReviewStatus,
  ReviewsSummary,
  ScrapeMode,
  ScrapeRun,
  SessionInfo,
} from "./types";

// Relative base: requests go to the web origin and Next.js rewrites /api/* to
// the backend (see next.config.ts), so the session cookie is same-origin.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    const detail = await response.text();
    const error = new Error(detail || `Request failed: ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

// --- Auth ---
export async function login(email: string, password: string): Promise<CurrentUser> {
  return request<CurrentUser>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  await request<void>("/api/auth/logout", { method: "POST" });
}

export async function getMe(): Promise<CurrentUser> {
  return request<CurrentUser>("/api/auth/me");
}

// --- Companies ---
export async function listCompanies(): Promise<Company[]> {
  const data = await request<{ items: Company[] }>("/api/companies");
  return data.items;
}

export async function createCompany(name: string, is_active = true): Promise<Company> {
  return request<Company>("/api/companies", {
    method: "POST",
    body: JSON.stringify({ name, is_active }),
  });
}

export async function getCompany(id: string): Promise<Company> {
  return request<Company>(`/api/companies/${id}`);
}

export async function updateCompany(
  id: string,
  payload: { name?: string; is_active?: boolean },
): Promise<Company> {
  return request<Company>(`/api/companies/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteCompany(id: string): Promise<void> {
  await request<void>(`/api/companies/${id}`, { method: "DELETE" });
}

export async function getCompanyBranches(id: string): Promise<CompanyBranches> {
  return request<CompanyBranches>(`/api/companies/${id}/branches`);
}

// --- Network overview dashboard (feature 009) ---
export async function getDashboardOverview(params: {
  period?: OverviewPeriod;
  platform?: OverviewPlatform;
  orgIds?: string[];
  companyId?: string;
}): Promise<DashboardOverview> {
  const qs = new URLSearchParams();
  if (params.period) qs.set("period", params.period);
  if (params.platform) qs.set("platform", params.platform);
  if (params.companyId) qs.set("company_id", params.companyId);
  for (const id of params.orgIds ?? []) qs.append("org_ids", id);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<DashboardOverview>(`/api/dashboard/overview${suffix}`);
}

// --- Organizations (branches) ---
// Operator-editable multi-platform metrics (2GIS/Google have no scraper).
export interface PlatformMetricsPayload {
  yandex_rating_count?: number | null;
  gis2_url?: string | null;
  gis2_rating?: number | null;
  gis2_review_count?: number | null;
  gis2_rating_count?: number | null;
  google_url?: string | null;
  google_rating?: number | null;
  google_review_count?: number | null;
  google_rating_count?: number | null;
}

export interface OrganizationCreatePayload extends PlatformMetricsPayload {
  yandex_url: string;
  preferred_scrape_mode?: ScrapeMode;
  name?: string | null;
  city?: string | null;
  region?: string | null;
  address?: string | null;
  company_id?: string | null;
}

export interface OrganizationUpdatePayload extends PlatformMetricsPayload {
  preferred_scrape_mode?: ScrapeMode;
  name?: string | null;
  city?: string | null;
  region?: string | null;
  address?: string | null;
  company_id?: string | null;
}

export async function listOrganizations(companyId?: string): Promise<Organization[]> {
  const suffix = companyId ? `?company_id=${companyId}` : "";
  const data = await request<{ items: Organization[] }>(`/api/organizations${suffix}`);
  return data.items;
}

export async function createOrganization(payload: OrganizationCreatePayload): Promise<Organization> {
  return request<Organization>("/api/organizations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateOrganization(
  id: string,
  payload: OrganizationUpdatePayload,
): Promise<Organization> {
  return request<Organization>(`/api/organizations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteOrganization(id: string): Promise<void> {
  await request<void>(`/api/organizations/${id}`, { method: "DELETE" });
}

export async function getOrganization(id: string): Promise<Organization> {
  return request<Organization>(`/api/organizations/${id}`);
}

export async function listReviews(params: Record<string, string | number | boolean | undefined> = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<{ items: Review[]; total: number; limit: number; offset: number }>(
    `/api/reviews${suffix}`,
  );
}

export async function getReviewsSummary(
  params: Record<string, string | number | boolean | undefined> = {},
): Promise<ReviewsSummary> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<ReviewsSummary>(`/api/reviews/summary${suffix}`);
}

export async function getReviewAspects(
  params: Record<string, string | undefined> = {},
): Promise<AspectsResponse> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AspectsResponse>(`/api/reviews/aspects${suffix}`);
}

export async function patchReview(
  id: string,
  payload: { status?: ReviewStatus; is_paid?: boolean; paid_cost?: number | null },
): Promise<Review> {
  return request<Review>(`/api/reviews/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listOrganizationReviews(organizationId: string) {
  return request<{ items: Review[]; total: number }>(
    `/api/organizations/${organizationId}/reviews`,
  );
}

export async function scrapeOrganization(id: string, mode?: ScrapeMode) {
  return request<{ scrape_run_id: string; status: string }>(
    `/api/organizations/${id}/scrape`,
    { method: "POST", body: JSON.stringify({ mode }) },
  );
}

export async function scrapeAll(mode: ScrapeMode = "public") {
  return request<{ scrape_run_id: string; status: string; organization_count: number }>(
    "/api/scrape/all",
    { method: "POST", body: JSON.stringify({ mode }) },
  );
}

export async function listScrapeRuns() {
  return request<{ items: ScrapeRun[] }>("/api/scrape-runs");
}

export async function getScrapeRun(runId: string): Promise<ScrapeRun> {
  return request<ScrapeRun>(`/api/scrape-runs/${runId}`);
}

export async function getSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/api/scraper/yandex/session");
}

export async function loginYandex(): Promise<{ status: string; message: string }> {
  return request("/api/scraper/yandex/login", { method: "POST" });
}

export async function checkSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/api/scraper/yandex/session/check", { method: "POST" });
}

// --- Фоновые задачи ---
export async function listJobs(): Promise<Job[]> {
  const data = await request<{ items: Job[] }>("/api/jobs");
  return data.items;
}

export async function updateJob(
  id: string,
  payload: { is_enabled?: boolean; schedule_cron?: string | null; options?: Record<string, unknown> },
): Promise<Job> {
  return request<Job>(`/api/jobs/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function runJobNow(id: string): Promise<{ job_run_id: string; status: JobRunStatus }> {
  return request<{ job_run_id: string; status: JobRunStatus }>(`/api/jobs/${id}/run`, {
    method: "POST",
  });
}

export async function listJobRuns(params: {
  job_id?: string;
  status?: JobRunStatus;
  since?: string;
  limit?: number;
} = {}): Promise<JobRun[]> {
  const query = new URLSearchParams();
  if (params.job_id) query.set("job_id", params.job_id);
  if (params.status) query.set("status", params.status);
  if (params.since) query.set("since", params.since);
  query.set("limit", String(params.limit ?? 50));
  const data = await request<{ items: JobRun[] }>(`/api/job-runs?${query.toString()}`);
  return data.items;
}

export async function getJobRun(
  id: string,
  params: { limit?: number; offset?: number } = {},
): Promise<JobRunDetail> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<JobRunDetail>(`/api/job-runs/${id}${suffix}`);
}
