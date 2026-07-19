# Contract: `GET /api/dashboard/overview` (feature 013 delta)

Аутентификация: как сейчас (`get_current_user`). Метод и путь не меняются. **Форма ответа не меняется.**

## Query-параметры

| Параметр | Тип | Дефолт | Статус | Заметки |
|---|---|---|---|---|
| `period` | str | `30d` | **расширен** | `day \| week \| 30d \| 90d \| year \| all \| custom` — добавлен `custom` |
| `platform` | str | `all` | без изменений | `all \| yandex \| google \| gis2` |
| `org_ids` | UUID[] | — | без изменений | повторяемый параметр |
| `company_id` | UUID | — | без изменений (уже поддержан) | фильтр «Бренды» |
| `date_from` | date (`YYYY-MM-DD`) | — | **новый** | нижняя граница, включительно; обязателен при `period=custom` |
| `date_to` | date (`YYYY-MM-DD`) | — | **новый** | верхняя граница, включительно; обязателен при `period=custom` |

## Правила валидации

| Запрос | Ответ |
|---|---|
| `period=custom&date_from=2026-05-01&date_to=2026-05-31` | `200`, агрегаты за май включительно |
| `period=custom&date_from=2026-05-01` (нет `date_to`) | `422` |
| `period=custom` (нет обеих дат) | `422` |
| `period=custom&date_from=2026-05-31&date_to=2026-05-01` | `422` |
| `period=custom&date_from=2026-05-10&date_to=2026-05-10` | `200`, один календарный день |
| `period=30d&date_from=…&date_to=…` | `200`, даты игнорируются |
| `period=bogus` | `422` (как сейчас) |
| `date_from=not-a-date` | `422` (валидация FastAPI) |

## Семантика

- Членство в периоде: `published_date >= date_from AND published_date <= date_to`, где
  `published_date = COALESCE(review_date, DATE(first_seen_at))`.
- Ответные метрики периода (доля ответов, средняя/медиана/p95 задержки, SLA) ограничены тем же
  диапазоном по `first_seen_at`.
- **Не** ограничены диапазоном (собственные окна, как и для преднастроенных периодов):
  `new_today`, `fresh_negatives_2h`, `unanswered_over_24h`, `unanswered_delta_24h`, блок `attention`,
  `trending_aspects` (14 дней).
- `avg_per_day` при `custom` делится на длину диапазона в днях включительно.
- Дельта рейтинга берёт базой ближайший снимок на/после `date_from`.

## Обратная совместимость

- Без `date_from`/`date_to` ответ **побайтово** совпадает с текущим для любого периода.
- Число SQL-запросов на вызов не меняется (`test_query_counts.py` без правок).
- Поле `period` в ответе просто отражает пришедший токен (`"custom"` при произвольном диапазоне).

## Контракт фронтенда (`/overview`)

Query string страницы: `period`, `platform`, `org_ids` (повтор), `company_id`, `from`, `to`.

| Ситуация | Поведение |
|---|---|
| `period=custom` + валидные `from`/`to` | применён произвольный диапазон |
| `period=custom` без/с кривыми датами | откат на `30d`, даты отброшены |
| `from > to` | откат на `30d` |
| `company_id` отсутствует среди загруженных компаний | бренд сброшен |
| выбран чип периода | `from`/`to` удаляются из URL |
| сменён `company_id` | `org_ids` очищается |
