# Multi-provider Map Links in the UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show and edit the additive `twogis_url` / `google_url` provider links in the web dashboard, and sync the frontend scrape-mode list with the backend's 5 modes.

**Architecture:** Backend gains two optional update fields applied by field-presence (so a link can be cleared); frontend types/mode-select catch up to the backend enum, the org table shows clickable provider badges, and the org detail page gets a small inline link editor. Provider links are display/reference only — they never feed the scrape URL or the dedup hash.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy (apps/api), Next.js App Router + React + Tailwind (apps/web), pytest, TypeScript.

## Global Constraints

- Read-only product: `twogis_url` / `google_url` are display/reference only. They MUST NOT feed the scrape URL (`ScrapeService` scrapes `yandex_url`) or the dedup `content_hash`. (constitution)
- Backend layering is strict: `api/` → `services/` → `models/`; routers stay thin and delegate to services. (CLAUDE.md)
- All web backend calls go through `lib/api.ts`; types mirror the API in `lib/types.ts`. (CLAUDE.md)
- Org & scrape-run API contract tests are required before merge. (constitution)
- Backend `ScrapeMode` values (verbatim): `public`, `operator_auth`, `public_http`, `scrapeops`, `twogis_api`.
- Run backend tests from `apps/api`; run lint from `apps/web`.

---

### Task 1: Backend — accept and persist `twogis_url` / `google_url` on update

**Files:**
- Modify: `apps/api/app/schemas/organization.py` (the `OrganizationUpdate` class)
- Modify: `apps/api/app/services/organization_service.py` (the `update` method, lines 36-46)
- Test: `apps/api/tests/test_organizations_api.py`

**Interfaces:**
- Consumes: existing `OrganizationUpdate` schema, `OrganizationService.update(organization_id, data)`, the `client` pytest fixture (FastAPI TestClient).
- Produces: `OrganizationUpdate` now carries optional `twogis_url: str | None` and `google_url: str | None`; `PATCH /api/organizations/{id}` persists them, clears a link when the field is present with an empty/null value, and leaves a link unchanged when the field is absent.

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_organizations_api.py`:

```python
def test_update_organization_map_links(client):
    create_resp = client.post(
        "/api/organizations",
        json={
            "yandex_url": "https://yandex.ru/maps/org/test/987654321/",
            "preferred_scrape_mode": "public",
        },
    )
    assert create_resp.status_code == 201
    org_id = create_resp.json()["id"]

    # Set both links.
    set_resp = client.patch(
        f"/api/organizations/{org_id}",
        json={
            "twogis_url": "https://go.2gis.com/abc12",
            "google_url": "https://maps.app.goo.gl/xyz34",
        },
    )
    assert set_resp.status_code == 200
    body = set_resp.json()
    assert body["twogis_url"] == "https://go.2gis.com/abc12"
    assert body["google_url"] == "https://maps.app.goo.gl/xyz34"

    # Absent field leaves the link unchanged; present empty string clears it.
    partial_resp = client.patch(
        f"/api/organizations/{org_id}",
        json={"twogis_url": ""},
    )
    assert partial_resp.status_code == 200
    partial = partial_resp.json()
    assert partial["twogis_url"] is None
    assert partial["google_url"] == "https://maps.app.goo.gl/xyz34"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_organizations_api.py::test_update_organization_map_links -v`
Expected: FAIL — `twogis_url` is ignored (assertion error: `None != "https://go.2gis.com/abc12"`), because `OrganizationUpdate` has no such field and `update` never sets it.

- [ ] **Step 3: Add the fields to the update schema**

In `apps/api/app/schemas/organization.py`, replace the `OrganizationUpdate` class:

```python
class OrganizationUpdate(BaseModel):
    preferred_scrape_mode: ScrapeMode | None = None
    name: str | None = None
    twogis_url: str | None = None
    google_url: str | None = None
```

- [ ] **Step 4: Apply the fields by presence in the service**

In `apps/api/app/services/organization_service.py`, replace the body of `update` (lines 36-46) with:

```python
    def update(self, organization_id: UUID, data: OrganizationUpdate) -> Organization | None:
        org = self.get(organization_id)
        if not org:
            return None
        if data.preferred_scrape_mode is not None:
            org.preferred_scrape_mode = data.preferred_scrape_mode
        if data.name is not None:
            org.name = data.name
        # Link fields are applied by presence (not `is not None`) so a caller can
        # clear a link with "" / null; an absent field leaves it unchanged.
        # Empty string normalizes to None. Display/reference only — never scraped.
        fields_set = data.model_fields_set
        if "twogis_url" in fields_set:
            org.twogis_url = data.twogis_url or None
        if "google_url" in fields_set:
            org.google_url = data.google_url or None
        self.db.commit()
        self.db.refresh(org)
        return org
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd apps/api && pytest tests/test_organizations_api.py::test_update_organization_map_links -v`
Expected: PASS

- [ ] **Step 6: Run the full org API test file to confirm no regression**

Run: `cd apps/api && pytest tests/test_organizations_api.py -v`
Expected: PASS (all tests, including the existing `test_create_list_update_delete_organization`)

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/schemas/organization.py apps/api/app/services/organization_service.py apps/api/tests/test_organizations_api.py
git commit -m "feat(008): accept twogis_url/google_url on organization update"
```

---

### Task 2: Frontend — sync types and scrape-mode select with the backend

**Files:**
- Modify: `apps/web/lib/types.ts` (the `ScrapeMode` type and the `Organization` interface)
- Modify: `apps/web/components/mode-select.tsx` (the `<select>` options)
- Modify: `apps/web/lib/api.ts` (the `updateOrganization` payload type)

**Interfaces:**
- Consumes: existing `ScrapeMode`, `Organization`, and `updateOrganization` in `apps/web/lib`.
- Produces: `ScrapeMode = "public" | "operator_auth" | "public_http" | "scrapeops" | "twogis_api"`; `Organization` has `twogis_url: string | null` and `google_url: string | null`; `updateOrganization(id, payload)` accepts optional `twogis_url` / `google_url`. These are relied on by Task 3 and Task 4.

- [ ] **Step 1: Extend `ScrapeMode` and `Organization` in `types.ts`**

In `apps/web/lib/types.ts`, replace the first line:

```typescript
export type ScrapeMode =
  | "public"
  | "operator_auth"
  | "public_http"
  | "scrapeops"
  | "twogis_api";
```

Then, inside the `Organization` interface, add the two fields right after `normalized_url: string;`:

```typescript
  twogis_url: string | null;
  google_url: string | null;
```

- [ ] **Step 2: Add the two modes to `mode-select.tsx`**

In `apps/web/components/mode-select.tsx`, replace the three `<option>` lines with:

```tsx
      <option value="public">public</option>
      <option value="operator_auth">operator_auth</option>
      <option value="public_http">public_http</option>
      <option value="scrapeops">scrapeops</option>
      <option value="twogis_api">twogis_api</option>
```

- [ ] **Step 3: Extend the `updateOrganization` payload type in `api.ts`**

In `apps/web/lib/api.ts`, replace the `updateOrganization` signature's payload type:

```typescript
export async function updateOrganization(
  id: string,
  payload: {
    preferred_scrape_mode?: ScrapeMode;
    name?: string;
    twogis_url?: string | null;
    google_url?: string | null;
  },
): Promise<Organization> {
  return request<Organization>(`/api/organizations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
```

- [ ] **Step 4: Run lint to verify types compile**

Run: `cd apps/web && npm run lint`
Expected: PASS (no type errors; the new fields and modes are recognized)

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/types.ts apps/web/components/mode-select.tsx apps/web/lib/api.ts
git commit -m "feat(008): sync web types + mode select with backend (5 modes, map links)"
```

---

### Task 3: Frontend — provider-link badges column in the organizations table

**Files:**
- Create: `apps/web/components/provider-badges.tsx`
- Modify: `apps/web/components/organizations-table.tsx` (add a "Карты" header + cell)

**Interfaces:**
- Consumes: `Organization.yandex_url`, `Organization.twogis_url`, `Organization.google_url` (from Task 2).
- Produces: `ProviderBadges` component — `export function ProviderBadges({ org }: { org: Organization }): JSX.Element`. Renders three small badges (Я / 2ГИС / G); each is an `<a target="_blank">` when the corresponding URL is set, else a disabled grey `<span>`.

- [ ] **Step 1: Create the `ProviderBadges` component**

Create `apps/web/components/provider-badges.tsx`:

```tsx
import type { Organization } from "@/lib/types";

interface BadgeSpec {
  label: string;
  href: string | null;
  title: string;
}

function Badge({ label, href, title }: BadgeSpec) {
  const base = "rounded px-1.5 py-0.5 text-xs font-medium";
  if (!href) {
    return (
      <span className={`${base} bg-slate-100 text-slate-400`} title={`${title}: нет ссылки`}>
        {label}
      </span>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`${base} bg-slate-800 text-white hover:bg-slate-900`}
      title={title}
    >
      {label}
    </a>
  );
}

export function ProviderBadges({ org }: { org: Organization }) {
  return (
    <div className="flex gap-1">
      <Badge label="Я" href={org.yandex_url} title="Яндекс Карты" />
      <Badge label="2ГИС" href={org.twogis_url} title="2ГИС" />
      <Badge label="G" href={org.google_url} title="Google Maps" />
    </div>
  );
}
```

- [ ] **Step 2: Add the column to the organizations table**

In `apps/web/components/organizations-table.tsx`:

Add the import near the top (after the `ModeSelect` import):

```tsx
import { ProviderBadges } from "./provider-badges";
```

In the `<thead>` row, add a header cell after the `<th className="px-3 py-2">URL</th>` line:

```tsx
            <th className="px-3 py-2">Карты</th>
```

In the `<tbody>` row, add a cell right after the URL `<td>` (the one with `title={org.yandex_url}`), before the Рейтинг cell:

```tsx
              <td className="px-3 py-2">
                <ProviderBadges org={org} />
              </td>
```

- [ ] **Step 3: Run lint**

Run: `cd apps/web && npm run lint`
Expected: PASS

- [ ] **Step 4: Verify visually**

Run (in `apps/web`, with the API running): `npm run dev`, open `http://localhost:3000/organizations`.
Expected: each row shows a "Карты" column with Я / 2ГИС / G badges; badges with a URL are dark and clickable (open in a new tab), badges without a URL are grey and inert.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/provider-badges.tsx apps/web/components/organizations-table.tsx
git commit -m "feat(008): provider-link badges column in organizations table"
```

---

### Task 4: Frontend — provider links block + inline editor on the org detail page

**Files:**
- Create: `apps/web/components/org-links-editor.tsx`
- Modify: `apps/web/app/organizations/[id]/page.tsx` (render the editor, keep the page thin)

**Interfaces:**
- Consumes: `Organization` (from Task 2), `updateOrganization` (from Task 2), `ProviderBadges` (from Task 3).
- Produces: `OrgLinksEditor` component — `export function OrgLinksEditor({ org, onSaved }: { org: Organization; onSaved: (updated: Organization) => void }): JSX.Element`. Shows the current links and two inputs (2ГИС, Google); "Сохранить" calls `updateOrganization` with both fields and passes the updated org back via `onSaved`.

- [ ] **Step 1: Create the `OrgLinksEditor` component**

Create `apps/web/components/org-links-editor.tsx`:

```tsx
"use client";

import { useState } from "react";
import { updateOrganization } from "@/lib/api";
import type { Organization } from "@/lib/types";

interface OrgLinksEditorProps {
  org: Organization;
  onSaved: (updated: Organization) => void;
}

export function OrgLinksEditor({ org, onSaved }: OrgLinksEditorProps) {
  const [twogis, setTwogis] = useState(org.twogis_url ?? "");
  const [google, setGoogle] = useState(org.google_url ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const updated = await updateOrganization(org.id, {
        twogis_url: twogis.trim() === "" ? null : twogis.trim(),
        google_url: google.trim() === "" ? null : google.trim(),
      });
      onSaved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить ссылки");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="space-y-3 rounded-lg border bg-white p-4">
      <h2 className="text-sm font-semibold text-slate-700">Ссылки на карты</h2>
      <div className="flex flex-col gap-1">
        <label htmlFor="twogis-url" className="text-xs text-slate-600">
          2ГИС
        </label>
        <input
          id="twogis-url"
          type="url"
          value={twogis}
          onChange={(e) => setTwogis(e.target.value)}
          placeholder="https://go.2gis.com/..."
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="google-url" className="text-xs text-slate-600">
          Google Maps
        </label>
        <input
          id="google-url"
          type="url"
          value={google}
          onChange={(e) => setGoogle(e.target.value)}
          placeholder="https://maps.app.goo.gl/..."
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={saving}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {saving ? "Сохранение..." : "Сохранить"}
      </button>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </form>
  );
}
```

- [ ] **Step 2: Render the editor on the detail page**

In `apps/web/app/organizations/[id]/page.tsx`:

Add the import after the `ReviewsTable` import:

```tsx
import { OrgLinksEditor } from "@/components/org-links-editor";
```

Insert the editor between the org header `</div>` and the `<ReviewsTable ... />` line:

```tsx
      <OrgLinksEditor org={org} onSaved={setOrg} />
```

(`setOrg` already exists in the component's state; passing it as `onSaved` refreshes the displayed org in place after a save.)

- [ ] **Step 3: Run lint**

Run: `cd apps/web && npm run lint`
Expected: PASS

- [ ] **Step 4: Verify visually end-to-end**

Run (in `apps/web`, with the API running): `npm run dev`, open an org detail page at `http://localhost:3000/organizations/<id>`.
Expected: a "Ссылки на карты" block shows the current 2ГИС / Google values pre-filled; editing a value and clicking "Сохранить" persists it (reload the page to confirm), clearing a field and saving removes the link, and an API error shows a red message under the button.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/org-links-editor.tsx apps/web/app/organizations/[id]/page.tsx
git commit -m "feat(008): map-links block + inline editor on org detail page"
```

---

## Self-Review notes

- **Spec coverage:** Backend accept/persist links (Task 1) ✓; frontend type + mode sync (Task 2) ✓; table badges display (Task 3) ✓; detail-page display + edit (Task 4) ✓; empty→null clear + absent→unchanged (Task 1 test + Task 4 editor) ✓; light URL validation via `type="url"` (Tasks 3/4) ✓; inline error on failed PATCH (Task 4) ✓. Out-of-scope items (no scrape wiring, no create-form links, no separate Spec Kit spec) are respected — no task touches `ScrapeService` or `OrganizationCreate`.
- **Placeholder scan:** none — every code step shows complete code.
- **Type consistency:** `updateOrganization` payload (Task 2) matches the `OrganizationUpdate` schema (Task 1); `ProviderBadges` prop shape (Task 3) and `OrgLinksEditor` prop shape (Task 4) match their consumers; `onSaved={setOrg}` matches the `(updated: Organization) => void` signature.
