# Data Model: Overview filters

**Feature**: 013-overview-filters | **Date**: 2026-07-19

## Изменения схемы БД

**Нет.** Фича не добавляет таблиц, колонок, индексов и миграций. Используются существующие связи.

## Задействованные сущности (существующие)

### Company (`companies`)

| Поле | Тип | Роль в фиче |
|---|---|---|
| `id` | UUID | значение фильтра «Бренды» (`company_id` в query string и в API) |
| `name` | str | подпись пункта в выпадающем списке |
| `is_active` | bool | неактивные компании в фильтре не показываются (FR-014) |

### Organization (`organizations`)

| Поле | Тип | Роль в фиче |
|---|---|---|
| `id` | UUID | значения фильтра «Филиалы» (`org_ids`) |
| `company_id` | UUID \| NULL | сужает список филиалов при выбранном бренде; NULL = «без бренда», виден только при сброшенном фильтре брендов |
| `name`, `city` | str \| NULL | подпись пункта в выпадающем списке |

Отношение: `Company 1 — N Organization` (`Organization.company = relationship("Company", back_populates="branches")`).

### Review (`reviews`)

| Поле | Тип | Роль в фиче |
|---|---|---|
| `review_date` | DATE \| NULL | дата публикации — основа членства в диапазоне |
| `first_seen_at` | TIMESTAMP | резерв для даты публикации (через `_published_expr`) и часы отсчёта для ответных метрик |
| `organization_id` | UUID | связывает отзыв с выбранным брендом/филиалами |

## Модель периода (уровень приложения, не БД)

| Понятие | Сегодня | После фичи |
|---|---|---|
| Токен периода | `day \| week \| 30d \| 90d \| year \| all` | + `custom` |
| Нижняя граница | `cutoff = now - PERIOD_DAYS[period]` (None для `all`) | то же; для `custom` — начало дня `date_from` |
| Верхняя граница | отсутствует (всегда «до сейчас») | новый `until: date \| None`; для `custom` — `date_to`, иначе `None` |
| `days` (знаменатель `avg_per_day`) | `PERIOD_DAYS[period]` | для `custom` — `(date_to - date_from).days + 1` |
| `period_start` (базис снимков рейтинга) | `cutoff.date()` | для `custom` — `date_from` |

### Правила валидации

1. `period == "custom"` → обе даты обязательны, иначе `422`.
2. `date_from > date_to` → `422`.
3. `date_from == date_to` → корректный однодневный диапазон.
4. Даты при `period != "custom"` игнорируются.
5. Границы включительные: отзыв входит, если `published >= date_from AND published <= date_to`.

### Инварианты

- `until = None` даёт SQL, побайтово эквивалентный текущему → payload для существующих периодов
  value-identical (контракт фичи 012).
- Число SELECT'ов на запрос обзора не меняется.
- Ни одна из «сейчас»-метрик (`new_today`, 2ч, 24ч, «Требует внимания», 14-дневные аспекты) не зависит
  от `until`.
