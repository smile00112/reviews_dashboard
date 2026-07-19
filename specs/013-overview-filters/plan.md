# Implementation Plan: Overview filters — custom date range + brand filter

**Branch**: `013-overview-filters` | **Date**: 2026-07-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-overview-filters/spec.md`

## Summary

Две правки панели фильтров `/overview`:

1. **Произвольный диапазон** — чип «Всё время» заменяется раскрывающимся блоком с полями «от»/«до».
   Технически: `GET /api/dashboard/overview` получает `period=custom` + `date_from`/`date_to`, а
   `DashboardService` — второй, верхний предел `until` рядом с существующим `cutoff`. Меняются три
   сигнатуры (`_review_cube`, `_response_percentiles`, `_response_base`) и одно условие членства в
   периоде. Форма ответа не меняется, контрактные тесты фичи 012 остаются нетронутыми.
2. **Фильтр «Бренды»** — бэкенд УЖЕ принимает `company_id` и фильтрует по нему организации
   (`_selected_orgs`), а веб-клиент уже умеет `listCompanies()` и `getDashboardOverview({companyId})`.
   Работа целиком фронтовая: dropdown брендов рядом с «Филиалами» + сужение списка филиалов по
   `org.company_id`.

## Technical Context

**Language/Version**: Python 3.11 (apps/api), TypeScript 5 / React 19 / Next.js App Router (apps/web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic v2; Next.js client components, Tailwind

**Storage**: PostgreSQL 16 (SQLite в тестах — отсюда `_dt_param` / `_published_expr` диалектные ветки)

**Testing**: pytest (`apps/api`), Playwright E2E (`apps/web`)

**Target Platform**: Docker Compose, web :3000 / api :8000

**Project Type**: Web application (monorepo `apps/api` + `apps/web`)

**Performance Goals**: Не хуже текущего обзора (~0.27 с на ответ). Число SELECT'ов не растёт —
`test_query_counts.py` остаётся зелёным.

**Constraints**: Payload обзора остаётся value-identical для существующих периодов; никакой
материализации строк отзывов; фильтры read-only.

**Scale/Scope**: ~600 организаций, ~52k отзывов, ~десятки компаний.

## Constitution Check

*GATE: пройден до Phase 0, перепроверен после Phase 1.*

| Принцип | Оценка |
|---|---|
| I. MVP Scope Discipline | ✅ Фильтры над уже собранными данными; ничего из out-of-scope списка не вводится. |
| II. Read-Only | ✅ Только чтение; ни одного write-пути не добавляется. |
| III. Critical-Path Testing | ✅ Новые тесты на диапазон в `test_dashboard_overview.py` (границы включительно, валидация 422) и на бренд-скоуп; контракт дедупликации не затрагивается. |
| IV. Scraper Reliability | ➖ Не применимо: скрейперы не трогаются. |
| V. Simplicity (YAGNI) | ✅ Второй предел вместо новой модели периода; бренд — без единой строки нового бэкенда. |
| VI. Deterministic Analytics | ✅ Аналитика не меняется. |
| VII. Admin Panel Security | ✅ Эндпоинт уже за `get_current_user`; новых маршрутов нет. |
| VIII. Multi-Provider | ➖ Не применимо. |

**Complexity Tracking**: нарушений нет — таблица не заполняется.

## Project Structure

### Documentation (this feature)

```text
specs/013-overview-filters/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── dashboard-overview.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── api/dashboard.py                  # + date_from/date_to params, валидация 422
│   └── services/dashboard_service.py     # + until: верхний предел периода
└── tests/
    ├── test_dashboard_overview.py        # + кейсы custom range
    └── test_query_counts.py              # без изменений (гарантия «не больше запросов»)

apps/web/
├── app/(dashboard)/overview/page.tsx     # + from/to/company_id в query string, загрузка компаний
├── components/dashboard/
│   ├── dashboard-filters.tsx             # - чип «Всё время», + диапазон, + бренды
│   └── date-range-picker.tsx             # новый: поля от/до + валидация + применить
└── lib/
    ├── api.ts                            # getDashboardOverview: + dateFrom/dateTo
    └── types.ts                          # OverviewPeriod: + "custom"
```

**Structure Decision**: существующая монорепо-структура; новых слоёв нет. Единственный новый файл —
`components/dashboard/date-range-picker.tsx`, чтобы `dashboard-filters.tsx` не разросся.

## Design

### Backend

**API** (`apps/api/app/api/dashboard.py`):

- Новые query-параметры `date_from: date | None`, `date_to: date | None`.
- `period="custom"` требует обе даты → иначе `422`.
- `date_from > date_to` → `422`.
- Даты при `period != "custom"` игнорируются.
- `PERIOD_DAYS` пополняется ключом `"custom": None`, чтобы существующая проверка `period not in PERIOD_DAYS`
  пропускала новый токен.

**Service** (`apps/api/app/services/dashboard_service.py`):

- `overview(..., date_from: date | None = None, date_to: date | None = None)`.
- При `period == "custom"`: `cutoff = start_of_day(date_from)`, `until = date_to`,
  `days = (date_to - date_from).days + 1` (знаменатель `avg_per_day`), `period_start = date_from`.
- `until` прокидывается в `_review_cube`, `_response_percentiles`, `_response_base`; во всех трёх
  `None` = «без верхней границы» (текущее поведение).
- В кубе: `in_period` дополняется `published <= until`; в ответных фильтрах —
  `first_seen_at < _dt_param(start_of_day(until + 1 day))`.
- «Сейчас»-окна (`new_today`, 2ч, 24ч), `_attention`, `_aspect_rows` не меняются (R2 / FR-003).

**Инварианты**: количество SELECT'ов не меняется; при `date_from`/`date_to = None` каждый SQL идентичен
сегодняшнему.

### Frontend

- `OverviewPeriod` = `"day" | "week" | "30d" | "90d" | "year" | "all" | "custom"` (токен `all` остаётся в
  типе и в API, но исчезает из панели чипов).
- Панель фильтров: чипы периода → разделитель → **Произвольный диапазон** (details) → разделитель →
  площадки → разделитель → **Бренды** (details) → **Филиалы** (details).
- Диапазон: два `input[type=date]`, кнопка «Применить» disabled пока `from`/`to` пусты или `from > to`,
  строка ошибки под полями. Применение → `period=custom&from=…&to=…`. Клик по любому чипу периода
  очищает `from`/`to`.
- Бренды: одиночный выбор + «Все бренды». Смена бренда → `org_ids` сбрасывается (FR-010).
- Список филиалов = `orgs.filter(o => !companyId || o.company_id === companyId)`.
- Разбор URL: невалидные `from`/`to` или `period=custom` без дат → откат на `30d`; `company_id`,
  которого нет в загруженном списке компаний, → сброс (FR-012).

## Post-Design Constitution Re-check

✅ Пройден повторно: изменения аддитивные, read-only, без новых сервисов, зависимостей и путей записи.
Контракт дедупликации и payload обзора не затронуты.
