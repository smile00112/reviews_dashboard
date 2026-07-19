# Research: Overview filters — custom date range + brand filter

**Feature**: 013-overview-filters | **Date**: 2026-07-19

## R1 — Как сейчас задаётся период обзора

**Findings**: `DashboardService.overview` (apps/api/app/services/dashboard_service.py:394) берёт токен периода,
маппит его через `PERIOD_DAYS` в число дней и получает ОДНУ границу: `cutoff = now - timedelta(days=days)`
(`None` для `all`). Далее `cutoff` расходится в три места:

- `_review_cube(scope, cutoff, now)` → `in_period = published >= cutoff.date()`;
- `_response_percentiles(scope, cutoff, platform)`;
- `_response_base(org_ids, cutoff)` (общий фильтр периода для «ответных» строк).

`days` дополнительно используется в `_kpi_hero` как знаменатель `avg_per_day`, а `period_start = cutoff.date()`
— как точка отсчёта для снимков рейтинга (`_earliest_snapshot_ratings`).

**Decision**: Добавить второй, верхний предел `until` рядом с существующим `cutoff` — не переписывать модель
периода. Токены остаются, добавляется режим `period="custom"` с парой `date_from`/`date_to`.

**Rationale**: Точечное изменение: три сигнатуры + одно условие в кубе. Контракт payload не меняется, поэтому
`test_dashboard_overview.py` / `test_dashboard_attention_rules.py` (контракт фичи 012) остаются зелёными без правок.

**Alternatives rejected**:
- Ввести объект `Period` и переписать все вызовы — ломает контракт 012 и `test_query_counts.py` без пользы.
- Отдельный эндпоинт `/overview/range` — дублирование всей агрегации.

## R2 — Верхняя граница периода и «сейчас»-окна

**Findings**: `new_today`, `fresh_negatives_2h`, `overdue_24h`, `unanswered_delta_24h` считаются от `now`
и не зависят от периода уже сегодня. `_attention` и `_aspect_rows` имеют собственные фиксированные окна
(24ч/2ч/14 дней).

**Decision**: `until` влияет ТОЛЬКО на «периодные» агрегаты (`in_period`, ответные метрики периода).
Окна реакции не трогаем.

**Rationale**: Сохраняет текущую семантику дашборда; иначе «диапазон в прошлом» обнулил бы блок
«Требует внимания», который по смыслу отвечает на вопрос «что горит сейчас». Зафиксировано в FR-003.

## R3 — Единицы верхней границы (дата vs timestamp)

**Findings**: Членство в периоде считается по `_published_expr()` — это `DATE` (coalesce
`review_date`, дата `first_seen_at`), а не timestamp. Нижняя граница уже сравнивается как `>= cutoff.date()`.

**Decision**: Верхняя граница — `published <= date_to` (сравнение дат, включительно). Никакой возни с
«концом дня» в timestamp-арифметике не нужно; для ответных метрик, где фильтр идёт по `first_seen_at`,
верхняя граница — `first_seen_at < start_of_day(date_to + 1 day)` через тот же `_dt_param`.

**Rationale**: Одна семантика с существующим кодом, SQLite/Postgres совместимо (`_dt_param` уже решает
naive/aware разницу).

## R4 — Фильтр по бренду на бэкенде

**Findings**: `GET /api/dashboard/overview` УЖЕ принимает `company_id: UUID | None`
(apps/api/app/api/dashboard.py:24), а `_selected_orgs` уже фильтрует `Organization.company_id == company_id`.
`GET /api/companies` уже отдаёт список компаний, а `apps/web/lib/api.ts:66` — `listCompanies()`.
`Organization` в `apps/web/lib/types.ts:53` уже несёт `company_id`.

**Decision**: Бэкенд по бренду НЕ трогаем. Фильтр «Бренды» — чисто фронтовая работа: прокинуть
`companyId` в `getDashboardOverview` (параметр уже поддержан клиентом) и сузить список филиалов
по `org.company_id === companyId` на клиенте.

**Rationale**: Список организаций (~600) грузится один раз и уже лежит в состоянии страницы; отдельный
запрос «филиалы бренда» не нужен.

**Alternatives rejected**: `GET /api/companies/{id}/branches` — лишний round-trip, данные уже есть.

## R5 — Одиночный или множественный выбор бренда

**Decision**: Одиночный (radio-подобный), с пунктом «Все бренды».

**Rationale**: Бэкенд принимает ровно один `company_id`; множественный выбор потребовал бы изменения
контракта API ради сценария, который уже покрывается множественным выбором филиалов.

## R6 — Хранение состояния фильтров

**Findings**: Страница уже держит период/площадку/филиалы в query string и восстанавливает их из
`useSearchParams` (`apps/web/app/(dashboard)/overview/page.tsx:39-45`).

**Decision**: Добавить `company_id`, `from`, `to` в тот же query string. Невалидные значения
(нераспарсенная дата, `from > to`, неизвестный бренд) молча игнорируются с откатом к дефолтам —
как уже сделано для `period`/`platform`.

**Rationale**: FR-011/FR-012 бесплатно; никакого нового механизма состояния.

## R7 — Валидация на бэкенде

**Decision**: `period=custom` требует обе даты; иначе 422. `date_from > date_to` → 422.
Даты без `period=custom` игнорируются. Токен `all` остаётся валидным в API (его убирают только из UI).

**Rationale**: Явная ошибка на кривой запрос, при этом UI никогда её не увидит (кнопка «Применить»
блокируется до валидного ввода — FR-004).
