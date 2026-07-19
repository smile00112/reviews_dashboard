# Tasks: Overview filters — custom date range + brand filter

**Feature**: 013-overview-filters | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

**Тесты**: включены — Constitution Principle III требует автотесты на изменения контракта API обзора.

## Phase 1: Setup

- [X] T001 Прочитать текущую модель периода в `apps/api/app/services/dashboard_service.py` (`PERIOD_DAYS`, `overview`, `_review_cube`, `_response_base`, `_response_percentiles`) и зафиксировать все места использования `cutoff` перед правкой

## Phase 2: Foundational (блокирует US1; US2 не блокирует)

- [X] T002 Добавить `"custom": None` в `PERIOD_DAYS` в `apps/api/app/services/dashboard_service.py`, чтобы существующая проверка `period not in PERIOD_DAYS` пропускала новый токен
- [X] T003 ~~Хелпер `_until_dt`~~ **не понадобился**: членство в периоде везде считается по `_published_expr()` (DATE), поэтому верхняя граница — прямое `published <= until`, без timestamp-арифметики

---

## Phase 3: User Story 1 — Произвольный диапазон дат (P1)

**Goal**: Оператор задаёт «от»/«до» и получает дашборд за этот отрезок.

**Independent Test**: `?period=custom&date_from=…&date_to=…` возвращает 200 с числами, совпадающими с ручным подсчётом; на UI кнопка показывает диапазон.

### Тесты (пишутся первыми)

- [X] T004 [P] [US1] Тест границ включительно: отзывы ровно на `date_from` и ровно на `date_to` попадают в `new_in_period`, соседние дни — нет — в `apps/api/tests/test_dashboard_overview.py`
- [X] T005 [P] [US1] Тест однодневного диапазона (`date_from == date_to`) и пустого диапазона (нули без ошибки) в `apps/api/tests/test_dashboard_overview.py`
- [X] T006 [P] [US1] Тесты валидации 422: `period=custom` без одной/обеих дат, `date_from > date_to`; и 200 с игнором дат при `period=30d` — в `apps/api/tests/test_dashboard_overview.py`
- [X] T007 [P] [US1] Тест «сейчас»-окна не зависят от диапазона: при диапазоне в прошлом `fresh_negatives_2h` / `unanswered_over_24h` / `attention` совпадают со значениями при периоде `30d` — в `apps/api/tests/test_dashboard_overview.py`

### Реализация — backend

- [X] T008 [US1] Прокинуть `until: date | None = None` в `_review_cube` и добавить `published <= until` в условие `in_period` в `apps/api/app/services/dashboard_service.py`
- [X] T009 [US1] Прокинуть `until` в `_response_base`, `_response_percentiles` и `_unanswered_by_org` (фильтр `_published_expr() <= until`) в `apps/api/app/services/dashboard_service.py`
- [X] T010 [US1] Расширить `overview(...)` параметрами `date_from`/`date_to`: при `period == "custom"` вычислить `cutoff = start_of_day(date_from)`, `until = date_to`, `days = (date_to - date_from).days + 1`, `period_start = date_from`; передать `until` в T008/T009 — в `apps/api/app/services/dashboard_service.py`
- [X] T011 [US1] Добавить query-параметры `date_from`/`date_to` и валидацию (`custom` без дат → 422, `date_from > date_to` → 422, даты вне `custom` игнорируются) в `apps/api/app/api/dashboard.py`

### Реализация — frontend

- [X] T012 [P] [US1] Добавить `"custom"` в `OverviewPeriod` в `apps/web/lib/types.ts`
- [X] T013 [P] [US1] Добавить `dateFrom`/`dateTo` в `getDashboardOverview` в `apps/web/lib/api.ts` (передаются как `date_from`/`date_to`)
- [X] T014 [US1] Создать `apps/web/components/dashboard/date-range-picker.tsx`: `details`-блок с полями «от»/«до», кнопкой «Применить» (disabled при пустых полях или `from > to`), сообщением об ошибке и подписью выбранного диапазона на кнопке
- [X] T015 [US1] В `apps/web/components/dashboard/dashboard-filters.tsx` убрать чип «Всё время» из `PERIODS` и встроить `DateRangePicker` на его место; активное состояние кнопки при `period === "custom"`
- [X] T016 [US1] В `apps/web/app/(dashboard)/overview/page.tsx` читать `from`/`to` из query string с валидацией (кривые даты или `custom` без дат → откат на `30d`), передавать в `getDashboardOverview`, писать в URL через `pushParams`; выбор чипа периода очищает `from`/`to`

**Checkpoint**: US1 работает и тестируется независимо от US2.

---

## Phase 4: User Story 2 — Фильтр «Бренды» (P1)

**Goal**: Выбор бренда сужает дашборд и список филиалов до точек этой компании.

**Independent Test**: выбрать бренд на `/overview` — метрики только по его филиалам, список филиалов сужен.

**Note**: бэкенд уже принимает `company_id` (`apps/api/app/api/dashboard.py`) и фильтрует в `_selected_orgs` — новых серверных изменений нет, только регрессионный тест.

- [X] T017 [P] [US2] Тест: `?company_id=…` считает обзор только по филиалам компании (и по организациям без компании — только без фильтра) в `apps/api/tests/test_dashboard_overview.py`
- [X] T018 [US2] В `apps/web/components/dashboard/dashboard-filters.tsx` добавить `details`-фильтр «Бренды» перед «Филиалами»: одиночный выбор из списка компаний + пункт «Все бренды»
- [X] T019 [US2] Там же сузить список филиалов: `orgs.filter(o => !companyId || o.company_id === companyId)`
- [X] T020 [US2] В `apps/web/app/(dashboard)/overview/page.tsx` загрузить компании через `listCompanies()`, отфильтровать `is_active`, читать/писать `company_id` в query string, сбрасывать `org_ids` при смене бренда, сбрасывать неизвестный `company_id`

**Checkpoint**: US2 работает независимо от US1.

---

## Phase 5: User Story 3 — Комбинация фильтров (P2)

**Goal**: бренд + филиалы + площадка + диапазон применяются вместе и переживают перезагрузку.

- [X] T021 [US3] Тест комбинации `company_id` + `org_ids` + `platform` + `period=custom` (все ограничения одновременно, логическое И) в `apps/api/tests/test_dashboard_overview.py`
- [X] T022 [US3] Проверить `pushParams` в `apps/web/app/(dashboard)/overview/page.tsx`: смена одного фильтра сохраняет остальные (кроме намеренных сбросов — период чистит даты, бренд чистит филиалы)

---

## Phase 6: Polish & Cross-Cutting

- [X] T023 [P] Прогнать `pytest -v` в `apps/api` — весь набор зелёный, включая `tests/test_query_counts.py` (число SELECT'ов не выросло) и контрактные `tests/test_dashboard_overview.py` / `tests/test_dashboard_attention_rules.py`
- [X] T024 [P] Прогнать `npm run lint` в `apps/web`
- [X] T025 Пройти ручной чек-лист из [quickstart.md](./quickstart.md) (10 пунктов) на поднятом стеке
- [X] T026 Обновить раздел про дашборд в `CLAUDE.md`: у обзора появился `period=custom` с `date_from`/`date_to` (верхняя граница `until`) и UI-фильтр брендов поверх уже существующего `company_id`

---

## Dependencies

```text
Phase 1 (T001)
   └─> Phase 2 (T002, T003)          # только для US1
          └─> Phase 3 US1: T004-T007 (тесты) -> T008 -> T009 -> T010 -> T011 -> T012/T013 -> T014 -> T015 -> T016
Phase 4 US2: T017-T020                # НЕ зависит от Phase 2/3
Phase 5 US3: после US1 и US2
Phase 6: после всего
```

- T008/T009/T010/T011 — один и тот же файл-цепочка, строго последовательно.
- T015 и T018/T019 правят один файл (`dashboard-filters.tsx`) — не параллелить между собой.
- T016 и T020 правят один файл (`overview/page.tsx`) — не параллелить между собой.

## Parallel Opportunities

- **US1 тесты**: T004, T005, T006, T007 — один файл тестов, но независимые функции; можно писать одним заходом.
- **Frontend-мелочь**: T012 и T013 — разные файлы, параллельно.
- **US1 и US2 целиком** — независимые срезы, могут делаться разными исполнителями (пересечение только в двух общих файлах: `dashboard-filters.tsx`, `overview/page.tsx` — синхронизировать порядок).
- **Polish**: T023 и T024 — разные приложения, параллельно.

## Implementation Strategy

**MVP** = Phase 1 + Phase 2 + Phase 3 (US1, произвольный диапазон) — самостоятельная ценность, отгружается отдельно.

Затем Phase 4 (US2, бренды) — дешевле всего: только фронт + один регрессионный тест.
Затем Phase 5 (комбинации) и Phase 6 (верификация).

**Total**: 26 задач — US1: 13, US2: 4, US3: 2, Setup/Foundational: 3, Polish: 4.
