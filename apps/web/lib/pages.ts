import type { CurrentUser } from "@/lib/types";

// Maps a control-panel route to the page-permission that gates it (feature 016).
// Order matters for `pageForPath` (longest/most-specific prefixes first).
export const PAGE_ROUTES: { prefix: string; page: string }[] = [
  { prefix: "/settings/roles", page: "roles" },
  { prefix: "/overview", page: "overview" },
  { prefix: "/ratings", page: "ratings" },
  { prefix: "/companies", page: "companies" },
  { prefix: "/organizations", page: "organizations" },
  { prefix: "/reviews", page: "reviews" },
  { prefix: "/scrape-runs", page: "scrape_runs" },
  { prefix: "/jobs", page: "jobs" },
  { prefix: "/attention-rules", page: "attention_rules" },
  { prefix: "/http-scraper", page: "http_scraper" },
  { prefix: "/settings", page: "settings" },
];

/** The page-permission name guarding `pathname`, or null if the route is ungated. */
export function pageForPath(pathname: string): string | null {
  for (const { prefix, page } of PAGE_ROUTES) {
    if (pathname === prefix || pathname.startsWith(prefix + "/")) return page;
  }
  return null;
}

export function canAccessPage(user: CurrentUser, page: string): boolean {
  return user.permissions.includes(`page:${page}`);
}

/** First route the user is allowed to open, for post-login / redirect landing. */
export function firstAllowedPath(user: CurrentUser): string | null {
  for (const { prefix, page } of PAGE_ROUTES) {
    if (prefix === "/settings/roles") continue; // never a default landing
    if (canAccessPage(user, page)) return prefix;
  }
  return null;
}
