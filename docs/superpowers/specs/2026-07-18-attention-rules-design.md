# Правила блока «Требуют внимания» — дизайн

**Дата:** 2026-07-18
**Статус:** утверждён, готов к планированию реализации

## Задача

Блок «⚡ Требуют внимания за последние 24 часа» на `/overview` (фича 009) сейчас
строится по пяти захардкоженным правилам в `DashboardService._attention`
(`apps/api/app/services/dashboard_service.py`): SLA 24 ч без ответа, свежий
негатив за 2 ч, эскалированные отзывы, падение рейтинга ≤ −0.2, рост аспекта.
Пороги и состав правил менять нельзя без деплоя.

Нужен функционал создания и управления этими правилами-триггерами: оператор
создаёт произвольное число правил, задаёт пороги, скоуп (вся сеть / компания /
список организаций), серьёзность, включает и выключает их. Блок на `/overview`
строится по включённым правилам.

## Принятые решения

| Решение | Выбор | Причина |
|---|---|---|
| Что управляется | Правила-триггеры (не KPI-цели, не обработка событий) | Выбор пользователя. |
| Модель | Произвольное число правил с типом и скоупом | Разным компаниям — разные пороги. |
| Скоуп | `global` / `company` / явный список организаций | Покрывает все случаи. |
| Оценка | On-the-fly в `DashboardService`, событий в БД нет | Как сейчас; без новых джоб, retention и дедупа событий (YAGNI). |
| Стартовое состояние | Миграция сидит 5 глобальных включённых правил с текущими порогами | Поведение дашборда после деплоя не меняется. Паттерн jobs (0014). |
| UI | Отдельная страница `/attention-rules` + шестерёнка в панели на `/overview` | Форма с полями по типу не влезает в модалку без потери ясности. |
| Доступ | Мутации admin-only, `GET` — под сессией | Паттерн проекта; overview тоже под сессией. |
| `organization_ids` | JSONB-массив, не M2M-таблица | Организаций десятки, удаляются редко; несуществующие id при оценке молча игнорируются. |

## Схема данных

Миграция `0015_attention_rules`, ветка от head `0014_background_jobs`.

### `attention_rules`

```
id                UUID PK
rule_type         enum attention_rule_type
                  (unanswered_overdue | fresh_negative | escalated |
                   rating_drop | aspect_spike)
name              varchar(200) NULL      -- своё название; NULL → дефолтный заголовок
is_enabled        bool NOT NULL DEFAULT true
severity          enum attention_severity (urgent | warn | info)
params            JSONB NOT NULL DEFAULT '{}'
scope_type        enum attention_scope (global | company | organizations)
company_id        UUID NULL FK companies ON DELETE CASCADE  -- при scope=company
organization_ids  JSONB NOT NULL DEFAULT '[]'               -- при scope=organizations
created_at, updated_at
```

Enum-типы — строковые enum в `models/enums.py` (`AttentionRuleType`,
`AttentionSeverity`, `AttentionScope`); severity-значения совпадают со
строками, которые уже отдаёт `attention[]` (`urgent`/`warn`/`info`).
JSONB-колонки — `JSON().with_variant(JSONB, "postgresql")` (SQLite-тесты).

### Параметры по типам

Валидируются Pydantic-схемами per type; дефолты = текущие хардкоды.

| rule_type | params | дефолт |
|---|---|---|
| `unanswered_overdue` | `hours: int ≥ 1` | 24 |
| `fresh_negative` | `window_hours: int ≥ 1`, `max_rating: int 1–4` | 2, 2 |
| `escalated` | — | `{}` |
| `rating_drop` | `threshold: float < 0`, `top: int 1–10` | −0.2, 3 |
| `aspect_spike` | `min_recent: int ≥ 1`, `top: int 1–10` | 3, 3 |

Лишние ключи в `params` — ошибка валидации (`extra="forbid"`).

### Сиды

5 глобальных включённых правил: по одному на каждый тип, `params` = дефолты,
severity: `unanswered_overdue`/`fresh_negative` → `urgent`, остальные → `warn`
(как в текущем коде). `name` = NULL.

## Backend

### `AttentionRuleService` (`services/attention_rule_service.py`)

CRUD поверх `Session` (паттерн остальных сервисов):

- `list_rules()` — все правила, сортировка по `created_at`.
- `create_rule(data)` / `update_rule(id, data)` — валидация:
  - `params` по Pydantic-схеме типа (при update тип менять нельзя — 422);
  - `scope_type=company` → `company_id` обязателен и существует;
  - `scope_type=organizations` → `organization_ids` непустой, все id существуют;
  - `scope_type=global` → `company_id`/`organization_ids` обнуляются.
- `delete_rule(id)` — жёсткое удаление.

### Роутер `api/attention_rules.py`

| Метод | Путь | Доступ |
|---|---|---|
| GET | `/api/attention-rules` | сессия (`get_current_user`) |
| POST | `/api/attention-rules` | `require_admin` |
| PATCH | `/api/attention-rules/{id}` | `require_admin` |
| DELETE | `/api/attention-rules/{id}` | `require_admin` |

Схемы в `schemas/attention_rule.py`. Роутер регистрируется в `app/main.py`.

### Оценка в `DashboardService._attention`

Переписывается с хардкодов на правила:

1. Загрузить включённые правила одним запросом.
2. Для каждого правила resolve скоуп → множество org id
   (`global` → все выбранные на странице; `company` → организации компании;
   `organizations` → список из правила). Пересечь с фильтрами страницы
   (`org_ids`/`company_id`/`platform`). Пустое пересечение → правило
   пропускается.
3. Оценить существующей логикой типа с параметрами из `params`, severity —
   из правила. Отзывы уже загружены (`all_reviews`) — фильтрация по org set
   в памяти, новых запросов на правило нет.
4. Item получает `rule_id` и `rule_name` (NULL → None). Кастомное `name`
   попадает в subtitle, заголовок остаётся вычисляемым
   («12 отзывов без ответа > 24ч» с числом из правила).

Несколько правил одного типа → несколько независимых items. Сортировка:
severity (urgent → warn → info), внутри severity — по `value` убыв.
Правил нет / все выключены → `attention: []` (пустая панель, как при
пустой сети).

`AttentionItem`-схема расширяется полями `rule_id: UUID | None`,
`rule_name: str | None` — additive, фронт старые поля не теряет.

## Frontend

### Страница `/attention-rules`

Server component загружает список, клиентские компоненты под `components/`:

- Таблица: тип (русская подпись), имя, скоуп (Вся сеть / имя компании /
  N организаций), параметры кратко («> 24 ч», «≤ 2★ за 2 ч»), severity,
  toggle `is_enabled` (PATCH сразу), кнопки редактировать/удалить (confirm).
- Форма создания/редактирования: select типа (при редактировании disabled) →
  поля параметров по типу; select скоупа → company-select или
  мультиселект организаций; severity; name.
- Ошибки API (422 валидация params/scope) показываются у полей.

### `lib/api.ts` / `lib/types.ts`

`AttentionRule`, `AttentionRuleCreate`, `AttentionRuleUpdate`; функции
`getAttentionRules`, `createAttentionRule`, `updateAttentionRule`,
`deleteAttentionRule`. `AttentionItem` дополняется `rule_id`/`rule_name`.

### Панель на `/overview`

В `attention-list.tsx` в заголовок панели добавляется ссылка-шестерёнка ⚙ на
`/attention-rules`. Item с `rule_name` показывает имя правила в subtitle.

## Тесты

pytest:

- `test_attention_rules_api.py` — CRUD-контракт; валидация params по типу
  (лишний ключ, неверный диапазон → 422); scope-валидация (company без
  `company_id`, несуществующие org id → 422); анонимный POST → 401,
  review_operator → 403 (паттерн `test_scrape_endpoints_require_admin.py`).
- `test_dashboard_attention_rules.py` — сид-правила дают текущее поведение;
  выключенное правило не даёт items; кастомный порог меняет результат
  (например `hours=1` ловит отзыв, который `hours=48` пропускает); правило
  со скоупом company/organizations считает только свои организации;
  два правила одного типа → два items; пересечение скоупа с фильтром
  страницы; несуществующий org id в `organization_ids` игнорируется.
- Миграция: сиды создаются, downgrade чистый.

e2e (`attention-rules.spec.ts`): страница рендерится со списком из 5
сид-правил; создание правила через форму; toggle enable; шестерёнка с
`/overview` ведёт на страницу. Гейт по `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`
как в `overview.spec.ts`.

## Вне скоупа

Персистентные события и их обработка (dismiss/acknowledge/назначение),
KPI-цели с прогрессом, уведомления, новые типы правил, история срабатываний.
