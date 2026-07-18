# Фоновые задачи сбора данных — дизайн

**Дата:** 2026-07-18
**Статус:** утверждён, готов к планированию реализации

## Задача

Дашборду нужна страница управления фоновыми задачами сбора. Две категории задач, по одной на каждую площадку:

1. **Сбор данных организации** — рейтинг, количество отзывов, количество оценок.
2. **Сбор отзывов** — запускается для организации, только если количество отзывов на площадке не совпадает с количеством уже собранных.

Результаты каждого запуска логируются построчно (по организации) и доступны для просмотра в дашборде.

Площадки: Яндекс и 2ГИС. Google исключён — скрапера для него нет.

## Принятые решения

| Решение | Выбор | Причина |
|---|---|---|
| Запуск | Расписание (cron) + ручной запуск | Оператор не должен помнить о ежедневном сборе. |
| Единица настройки | Тип × площадка, глобально (4 задачи) | Расписание на организацию дало бы 120 записей при 30 организациях без выигрыша. |
| Условие сбора отзывов | Расхождение счётчиков → полный проход | Дедуп по `content_hash` уже отбрасывает известные отзывы. Докачка «сколько не хватает» врёт при удалённых отзывах. |
| Обработка организаций | Последовательно с задержкой | Антибот-защита площадок. |
| Хранение логов | Тот же Postgres, новые таблицы | Сотни строк в день, нужны JOIN к организациям. Отдельная БД = второй пул, миграции, бэкапы без выигрыша. |
| Retention | 20 дней, авто-очистка | |
| `scrape_runs` | Не трогаем | Таблица уже перегружена (parent/child, debug-артефакты); задача метрик в неё не ложится. Связь через `job_run_items.scrape_run_id`. |
| Планировщик | In-process APScheduler | Конституция запрещает Celery/очереди. APScheduler — планировщик внутри API-процесса, не очередь. |
| Доступ | Мутации admin-only, чтение открыто | Как остальной API проекта. |

## Схема данных

Миграция `0014_background_jobs`, ветка от текущего head `0013_review_idx_session_pend`.

### `jobs` — определение задачи

4 строки, сидятся миграцией.

```
id                UUID PK
kind              enum job_kind_enum (org_metrics | reviews)
platform          enum review_platform (yandex | gis2)
schedule_cron     text NULL
timezone          text NOT NULL DEFAULT 'Europe/Moscow'
is_enabled        bool NOT NULL DEFAULT false
options           JSONB NOT NULL DEFAULT '{}'   -- {delay_seconds, max_pages}
last_run_at       timestamptz NULL
next_run_at       timestamptz NULL
created_at, updated_at
UNIQUE (kind, platform)
```

Сиды: метрики — `0 4 * * *`, отзывы — `0 5 * * *` (после метрик, чтобы `review_count` был свежий). Обе выключены при старте — оператор включает сам.

### `job_runs` — запуск

```
id                    UUID PK
job_id                UUID FK jobs
trigger               enum job_trigger (schedule | manual)
triggered_by_user_id  UUID FK users NULL
status                enum job_run_status
                        (queued | running | success | partial |
                         failed | needs_manual_action | cancelled)
started_at, finished_at
orgs_total, orgs_succeeded, orgs_skipped, orgs_failed  int NOT NULL DEFAULT 0
error_message         text NULL
INDEX (job_id, started_at DESC)
```

### `job_run_items` — результат по организации

```
id              UUID PK
job_run_id      UUID FK job_runs ON DELETE CASCADE
organization_id UUID FK organizations
status          enum job_item_status (success | skipped | failed | needs_manual_action)
reason          text NULL       -- почему пропущено: "счётчики совпадают: 42 = 42"
payload         JSONB NOT NULL DEFAULT '{}'
scrape_run_id   UUID FK scrape_runs NULL
error_code, error_message  text NULL
duration_ms     int NULL
INDEX (job_run_id)
```

`payload` по типу задачи:

- `org_metrics`: `{rating_before, rating_after, review_count_before, review_count_after, rating_count_before, rating_count_after}`
- `reviews`: `{platform_total, scraped_before, reviews_seen, inserted, updated}`

### Retention

Внутренний cron 03:15 ежедневно: `DELETE FROM job_runs WHERE started_at < now() - interval '20 days'`. `job_run_items` уходят каскадом. Задача не отображается в таблице `jobs`.

## Бэкенд

### Сервисы

**`services/metrics_service.py`** — рефакторинг. Логика сбора метрик переезжает из `scripts/scrape_metrics.py` в сервис; CLI становится тонкой обёрткой. Без этого будут две расходящиеся реализации. Поведение скрапинга не меняется: 2ГИС через `TwogisApiScraper(metrics_only=True)`, Яндекс через `YandexHttpScraper(metrics_only=True)` с фолбэком на `YandexScrapeOpsScraper`. Правило «не перезаписывать null» сохраняется.

**`services/job_service.py`** — чтение и правка задач, создание `job_run`, листинги с фильтрами, cleanup по retention.

**`services/job_runner.py`** — исполнение. Перед стартом берёт `SELECT ... FROM jobs WHERE id = ? FOR UPDATE`; если у задачи есть `job_run` в статусе `running`, запуск отклоняется (409 для ручного, лог-skip для расписания). Блокировка на строке корректна и при нескольких репликах API.

Далее последовательно по активным организациям с непустым URL нужной площадки, с задержкой `options.delay_seconds` между организациями. Каждая организация даёт ровно один `job_run_item`.

- `org_metrics` → `MetricsService`.
- `reviews` → сравнение `Organization.<platform>_review_count` с `COUNT(reviews WHERE organization_id = ? AND platform = ?)`. Равны или счётчик площадки NULL → `skipped` с reason, скрапер не вызывается. Иначе `ScrapeService.create_run` + `execute_run` синхронно, `scrape_run_id` записывается в item.

Агрегация статуса запуска: все элементы `failed` → `failed`; ни одного `success`, но есть `needs_manual_action` → `needs_manual_action`; есть и успехи, и ошибки → `partial`; иначе `success`. Пустой список организаций → `success` с `orgs_total = 0`.

### Планировщик

APScheduler `BackgroundScheduler`, стартует в FastAPI lifespan (`main.py` — сейчас lifespan-хуков нет, добавляются). Управляется флагом `settings.jobs_scheduler_enabled`: `true` в docker, `false` в тестах и CLI.

На старте читает `jobs` и вешает `CronTrigger` на каждую включённую задачу с непустым `schedule_cron`. `PATCH /api/jobs/{id}` перерегистрирует триггер. Параметры: `coalesce=True`, `max_instances=1`, заданный `misfire_grace_time` — пропущенные из-за даунтайма запуски не размножаются. Каждое срабатывание открывает собственный `SessionLocal`, как существующие background-таски.

Новая зависимость: `apscheduler` в `pyproject.toml`.

### API — `api/jobs.py`

| Метод | Путь | Доступ | Ответ |
|---|---|---|---|
| GET | `/api/jobs` | открыт | список задач с последним запуском |
| PATCH | `/api/jobs/{id}` | admin | правка `is_enabled`, `schedule_cron`, `options`; перерегистрация триггера |
| POST | `/api/jobs/{id}/run` | admin | 202 + `job_run_id`; 409 если уже `running` |
| GET | `/api/job-runs` | открыт | фильтры `job_id`, `status`, `since`/`until`, `limit`/`offset` |
| GET | `/api/job-runs/{id}` | открыт | запуск + `items` с пагинацией |

Схемы в `schemas/job.py`. Невалидный cron в PATCH → 422.

## Фронтенд

Роут `/jobs`, пункт сайдбара «Фоновые задачи».

**Верх страницы** — 4 карточки (тип × площадка): статус-бейдж, человекочитаемое расписание («ежедневно в 04:00»), последний запуск и его исход, тумблер вкл/выкл, кнопка «Запустить сейчас» (заблокирована, пока задача выполняется), «Изменить расписание» → модалка с пресетами (каждый час / каждые 6 часов / ежедневно в HH:MM / свой cron).

**Низ страницы** — таблица запусков: задача, триггер (расписание / вручную и кем), старт, длительность, статус, `успешно / пропущено / ошибки`, итог изменений. Фильтры по задаче, статусу, периоду. Пагинация.

**Деталь запуска** — роут `/jobs/runs/[id]`: шапка с итогами и таблица `job_run_items` по организациям (статус, reason, было → стало, ошибка, ссылка на `scrape_run` где есть).

Polling каждые 5 секунд, пока в выдаче есть запуск в статусе `running` или `queued`; иначе не опрашиваем. Типы в `lib/types.ts`, вызовы через `lib/api.ts`.

## Тесты

pytest:

- агрегация статуса `job_run`: all-failed, partial, success, пустой список организаций;
- skip-логика отзывов: счётчики совпадают → `skipped` с reason, скрапер не вызван; счётчик площадки NULL → `skipped`;
- retention удаляет запуски старше 20 дней и не трогает свежие, items уходят каскадом;
- guard повторного запуска: `POST /api/jobs/{id}/run` при активном запуске → 409;
- контракты `/api/jobs` и `/api/job-runs`;
- admin-гейт на `PATCH` и `POST .../run`.

Планировщик в тестах выключен (`jobs_scheduler_enabled=false`) — runner проверяется напрямую.

E2E (Playwright): `/jobs` рендерит 4 задачи; ручной запуск создаёт `job_run` и он появляется в таблице; страница детали открывается и показывает items.

## Вне рамок

Celery и любые очереди; параллельный скрапинг организаций; расписания на уровне отдельной организации; Google; обход капчи — `needs_manual_action` остаётся первоклассным исходом; правка `scrape_runs`; уведомления о падениях (email/telegram).
