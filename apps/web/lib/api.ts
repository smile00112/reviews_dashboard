import type {
  Organization,
  Review,
  ScrapeMode,
  ScrapeRun,
  SessionInfo,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function listOrganizations(): Promise<Organization[]> {
  const data = await request<{ items: Organization[] }>("/api/organizations");
  return data.items;
}

export async function createOrganization(
  yandex_url: string,
  preferred_scrape_mode: ScrapeMode,
): Promise<Organization> {
  return request<Organization>("/api/organizations", {
    method: "POST",
    body: JSON.stringify({ yandex_url, preferred_scrape_mode }),
  });
}

export async function updateOrganization(
  id: string,
  payload: { preferred_scrape_mode?: ScrapeMode; name?: string },
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

export async function getSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/api/scraper/yandex/session");
}

export async function loginYandex(): Promise<{ status: string; message: string }> {
  return request("/api/scraper/yandex/login", { method: "POST" });
}

export async function checkSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/api/scraper/yandex/session/check", { method: "POST" });
}
