# Data Model: Yandex Reviews MVP

**Date**: 2026-06-14

## Entity Relationship Overview

```text
organizations 1──* reviews
organizations 1──* scrape_runs
scrape_runs (organization_id nullable for bulk-all parent runs)
scraper_sessions (standalone; provider = yandex)
```

## organizations

Stores tracked Yandex Maps organizations.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | |
| name | text | nullable | Filled by scraper when available |
| yandex_url | text | NOT NULL | Original URL from user |
| normalized_url | text | NOT NULL | Canonical URL after cleanup |
| external_id | text | nullable | Yandex ID if parsed |
| address | text | nullable | |
| rating | numeric | nullable | |
| review_count | integer | nullable | |
| preferred_scrape_mode | enum | NOT NULL | `public`, `operator_auth` |
| last_successful_scrape_at | timestamptz | nullable | |
| last_scrape_status | enum | NOT NULL | `pending`, `running`, `success`, `failed`, `needs_manual_action` |
| created_at | timestamptz | NOT NULL | |
| updated_at | timestamptz | NOT NULL | |

**Validation**:
- `yandex_url` MUST match Yandex Maps URL patterns (`https://yandex.` / `yandex.ru` / `yandex.com`)
- Default `last_scrape_status` on create: `pending`
- Default `preferred_scrape_mode`: `public`

## reviews

Stores collected Yandex reviews.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | |
| organization_id | UUID | FK → organizations, NOT NULL | |
| source | text | NOT NULL | Fixed: `yandex_maps` |
| scrape_mode | enum | NOT NULL | `public`, `operator_auth` |
| external_review_id | text | nullable | If found on page |
| author_name | text | nullable | |
| rating | integer | NOT NULL | 1–5 |
| review_text | text | NOT NULL | |
| review_date_text | text | nullable | Original string from Yandex |
| review_date | date/timestamptz | nullable | Parsed when possible |
| response_text | text | nullable | Visible business response only |
| content_hash | text | NOT NULL | Dedup key component |
| first_seen_at | timestamptz | NOT NULL | |
| last_seen_at | timestamptz | NOT NULL | Updated on re-scrape sighting |

**Unique constraint**: `(organization_id, content_hash)`

**content_hash algorithm**:

```text
SHA-256(normalize(author_name) + "|" + rating + "|" + normalize(review_date_text) + "|" + normalize(review_text))
```

Normalization: trim, collapse whitespace, lowercase author and date fields; preserve Cyrillic in review text body normalization (whitespace only).

## scrape_runs

One scrape execution attempt.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | |
| organization_id | UUID | FK → organizations, nullable | Null = bulk-all parent run |
| mode | enum | NOT NULL | `public`, `operator_auth` |
| status | enum | NOT NULL | `queued`, `running`, `success`, `failed`, `needs_manual_action` |
| started_at | timestamptz | NOT NULL | |
| finished_at | timestamptz | nullable | |
| reviews_seen | integer | NOT NULL, default 0 | |
| reviews_inserted | integer | NOT NULL, default 0 | |
| reviews_updated | integer | NOT NULL, default 0 | |
| error_code | text | nullable | |
| error_message | text | nullable | |
| debug_screenshot_path | text | nullable | |
| debug_html_path | text | nullable | |

**State transitions**:

```text
queued → running → success | failed | needs_manual_action
```

## scraper_sessions

Metadata for authenticated Playwright sessions (not cookie contents).

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | |
| provider | text | NOT NULL | Fixed: `yandex` |
| storage_state_path | text | NOT NULL | Path to local JSON file |
| status | enum | NOT NULL | `missing`, `valid`, `expired`, `needs_manual_action` |
| last_login_at | timestamptz | nullable | |
| last_checked_at | timestamptz | nullable | |

**Security**: API returns status metadata only; never file contents or credentials.

## Indexes (recommended)

- `reviews(organization_id, review_date DESC NULLS LAST, first_seen_at DESC)`
- `scrape_runs(organization_id, started_at DESC)`
- `scrape_runs(started_at DESC)` for global history
- `organizations(last_scrape_status)` for board filtering (optional)

## Enum Summary

| Enum | Values |
|------|--------|
| preferred_scrape_mode / scrape run mode | `public`, `operator_auth` |
| last_scrape_status (org) | `pending`, `running`, `success`, `failed`, `needs_manual_action` |
| scrape_run.status | `queued`, `running`, `success`, `failed`, `needs_manual_action` |
| scraper_session.status | `missing`, `valid`, `expired`, `needs_manual_action` |
