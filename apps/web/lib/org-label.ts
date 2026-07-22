import type { Company, Organization } from "@/lib/types";

/**
 * Location label for branch pickers: "<краткое название бренда>, <адрес>, <город>".
 * Each part is skipped when empty. The brand comes from the parent company's
 * `short_name` ONLY — the full company name is intentionally never used here.
 * When no part is available we fall back to the branch name / URL / id.
 */
export function branchLabel(org: Organization, companyById: Map<string, Company>): string {
  const brand = org.company_id ? companyById.get(org.company_id)?.short_name : null;
  const parts = [brand, org.address, org.city].filter(
    (p): p is string => Boolean(p && p.trim()),
  );
  return parts.length > 0
    ? parts.join(", ")
    : org.name ?? org.yandex_url ?? org.gis2_url ?? org.id;
}
