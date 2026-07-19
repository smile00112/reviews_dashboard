# Quickstart: Overview filters — validation guide

**Feature**: 013-overview-filters

## Предпосылки

- Postgres с данными (или тестовая SQLite-фикстура из `apps/api/tests`).
- Хотя бы 2 компании, у каждой ≥1 организация, и отзывы с разными `review_date`.

## Backend

```bash
cd apps/api
pytest -v                                   # весь набор — регрессия обязана быть зелёной
pytest tests/test_dashboard_overview.py -v  # новые кейсы произвольного диапазона
pytest tests/test_query_counts.py -v        # число запросов не выросло
```

Ручная проверка API (сессионная кука нужна, как для любого запроса обзора):

```bash
# произвольный диапазон
curl -s "http://localhost:8000/api/dashboard/overview?period=custom&date_from=2026-05-01&date_to=2026-05-31" | jq '.period, .header'

# фильтр по бренду
curl -s "http://localhost:8000/api/dashboard/overview?company_id=<COMPANY_UUID>" | jq '.kpi_hero.total_reviews'

# ошибки валидации -> 422
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8000/api/dashboard/overview?period=custom&date_from=2026-05-01"
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8000/api/dashboard/overview?period=custom&date_from=2026-05-31&date_to=2026-05-01"
```

Ожидаемо: `200 / 200 / 422 / 422`. Суммы `header.new_in_period` за диапазон совпадают с прямым
подсчётом отзывов за тот же отрезок (SC-002).

## Frontend

```bash
cd apps/web
npm run lint
npm run test:e2e     # требует поднятые API + web
```

Ручной прогон на `/overview`:

1. Чипа «Всё время» нет; на его месте — «Произвольный диапазон». *(FR-001)*
2. Клик → раскрывается блок с полями «от»/«до». *(FR-002)*
3. «от» > «до» → «Применить» заблокировано, видно сообщение. *(FR-004)*
4. Валидные даты → применить: цифры дашборда меняются, кнопка показывает диапазон и подсвечена. *(FR-003, FR-005)*
5. Клик по «30 дней» → произвольный диапазон сброшен. *(FR-006)*
6. Рядом с «Филиалами» есть «Бренды» с пунктом «Все бренды». *(FR-007)*
7. Выбор бренда → метрики только по его филиалам, список филиалов сужен. *(FR-008, FR-009)*
8. Отметить филиалы → сменить бренд → выбор филиалов очищен. *(FR-010)*
9. Скопировать URL, открыть в новой вкладке → тот же экран. *(FR-011, SC-004)*
10. Подставить в URL `period=custom` без дат и несуществующий `company_id` → страница открывается на
    периоде «30 дней» без бренда, без ошибок. *(FR-012)*

## Ссылки

- Контракт API: [contracts/dashboard-overview.md](./contracts/dashboard-overview.md)
- Модель периода и сущности: [data-model.md](./data-model.md)
- Решения: [research.md](./research.md)
