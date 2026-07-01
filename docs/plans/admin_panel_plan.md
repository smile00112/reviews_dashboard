# План задачи для Claude Code — Админ-панель SERM Dashboard

**Проект:** SERM Dashboard «Суши Мастер»
**Стек:** Python 3.11+ · FastAPI · uvicorn · PostgreSQL 16 · SQLAlchemy (async) · Alembic · pydantic-settings
**Admin-фреймворк:** [SQLAdmin](https://aminalaee.dev/sqladmin/) (`sqladmin`)
**Цель:** установить админ-панель, настроить авторизацию и 2 роли (**админ** и **оператор отзывов**), вывести в админке **организации** и **отзывы**.

---

## 1. Область задачи (scope)

**Входит:**
1. Установка и монтирование admin-панели в существующее FastAPI-приложение.
2. Авторизация в админку (форма логин/пароль, сессии, хеширование паролей).
3. Две роли с разграничением доступа: `admin` и `review_operator`.
4. Разделы в админке: **Организации** (точки сети) и **Отзывы** с колонками, фильтрами, поиском.

**Не входит (осознанно вне этой итерации):**
- Кастомный фронтенд-дашборд из прототипа (KPI, графики Chart.js) — это отдельная задача.
- Интеграции с API Яндекс/Google/2ГИС и скрапер (Playwright) — уже есть/делается отдельно.
- Остальные 2 роли из ТЗ (Маркетолог, Управляющий точки) — добавим позже, роль-модель сразу проектируем расширяемой.

> **Обоснование выбора SQLAdmin.** Для связки FastAPI + SQLAlchemy это де-факто стандартный admin: монтируется как sub-app в тот же `FastAPI()`, использует существующие ORM-модели и тот же async-`engine`, даёт из коробки `AuthenticationBackend` (сессионный логин/логаут) и пер-вьюшные проверки `is_accessible(request)` / `is_visible(request)` + флаги `can_create/can_edit/can_delete`, чего достаточно для RBAC на 2 роли. Альтернатива — `starlette-admin` (богаче поля и пер-экшн права `can_edit(request)`), заложить как запасной вариант, если позже понадобится более тонкий контроль записи по ролям.

---

## 2. Роли и матрица доступа

Роль хранится в поле `User.role` (Enum). На этой итерации 2 значения, Enum спроектировать под рост.

| Ресурс | `admin` | `review_operator` (оператор отзывов) |
|---|---|---|
| Вход в админку | ✅ | ✅ |
| **Организации** | полный CRUD | только просмотр (список + карточка), без создания/редактирования/удаления |
| **Отзывы** | полный CRUD | просмотр + **редактирование** (ответ, статус, назначение, пометка «покупной»); создание и удаление — запрещены |
| **Пользователи** | полный CRUD | нет доступа (view скрыт) |

Механизм в SQLAdmin:
- `is_accessible(request)` / `is_visible(request)` — гейт всей вьюшки по роли (скрыть Users от оператора).
- `can_create` / `can_edit` / `can_delete` — на организациях для оператора; т.к. эти флаги на уровне класса, для «оператор = read-only, админ = CRUD» на одной модели использовать **раздельную регистрацию/условную вьюху по роли** ИЛИ переопределить проверки прав так, чтобы учитывать `request.session["role"]`. Реализовать наиболее простым рабочим способом и покрыть тестом.

---

## 3. Модели данных (минимум для админки)

Опираемся на дата-модель из ТЗ (раздел 11). Для этой задачи нужны 3 сущности. Если модели уже есть — расширить, не дублировать.

```
User
  id, name, email (unique), role: Enum(admin|review_operator), is_active: bool
  password_hash: str
  default_location_id (nullable, FK Organization), avatar_initials
  created_at

Organization  (в ТЗ — Location, «точка сети», в интерфейсе называем «Организация»)
  id, name, city, region, address, is_franchise: bool, manager_id (FK User, nullable)
  yandex_business_id, google_place_id, gis2_branch_id
  created_at

Review
  id, external_id, platform: Enum(yandex|google|gis2), organization_id (FK Organization)
  author_name, rating (1..5), text, created_at, fetched_at
  reply_text, reply_at, replied_by_user_id (FK User, nullable)
  status: Enum(new|in_progress|answered|escalated)
  sentiment_score (float, -1..1)
  is_paid: bool, paid_cost (int, ₽), paid_marked_by_user_id (FK User, nullable), paid_marked_at
  is_deleted_by_platform: bool, deleted_at
```

> Поле `2gis_branch_id` из ТЗ переименовать в `gis2_branch_id` — идентификатор Python/колонка не может начинаться с цифры.

---

## 4. Фазы реализации (задачи)

Выполнять последовательно, после каждой фазы — проверка, что приложение поднимается.

### Фаза 0 — Зависимости и конфиг
- [ ] Добавить зависимости: `sqladmin`, `passlib[bcrypt]` (или `argon2-cffi`), `itsdangerous` (для session middleware).
- [ ] В `core/config.py` (pydantic-settings) добавить: `ADMIN_SECRET_KEY`, `SESSION_MAX_AGE` (напр. 12ч). Секрет — из env, не хардкодить.
- [ ] Подключить `SessionMiddleware` к FastAPI (нужен sqladmin-аутентификации на сессиях).

### Фаза 1 — Модели и миграции
- [ ] Создать/расширить SQLAlchemy-модели `User`, `Organization`, `Review` (см. §3), Enum-типы для `role`, `platform`, `status`.
- [ ] Добавить в `User`: `password_hash`, `role`, `is_active`.
- [ ] Утилиты хеша пароля: `hash_password()`, `verify_password()` (bcrypt/argon2).
- [ ] Сгенерировать Alembic-миграцию, применить (`alembic upgrade head`). Проверить схему в Postgres.

### Фаза 2 — Установка и монтирование админки
- [ ] Инициализировать `Admin(app, engine, base_url="/admin", title="SERM Admin")` в точке сборки приложения.
- [ ] Проверить, что `/admin` открывается (пока без авторизации/вьюх).

### Фаза 3 — Авторизация
- [ ] Реализовать `AuthenticationBackend` (`sqladmin.authentication`): методы `login` (проверка email+пароль по БД, запись `user_id` и `role` в `request.session`), `logout`, `authenticate` (проверка сессии, редирект на логин если нет).
- [ ] Подключить backend в `Admin(..., authentication_backend=...)`.
- [ ] Учитывать `is_active`: неактивный пользователь не входит.
- [ ] Проверка: неавторизованный редиректится на `/admin/login`; неверный пароль — ошибка; выход завершает сессию.

### Фаза 4 — Роли и RBAC
- [ ] Базовый класс вьюхи с хелпером чтения роли из `request.session`.
- [ ] `UserAdmin`: `is_accessible/is_visible` → только `admin`.
- [ ] `OrganizationAdmin`: доступна обеим ролям; для `review_operator` — только чтение (см. §2).
- [ ] `ReviewAdmin`: доступна обеим; `review_operator` может редактировать, но не создавать/удалять.
- [ ] Проверка: под оператором раздел «Пользователи» отсутствует; организации не редактируются; отзывы редактируются.

### Фаза 5 — Вьюхи «Организации» и «Отзывы»
- [ ] `OrganizationAdmin`: `column_list` = name, city, region, is_franchise, кол-во отзывов (если легко), created_at; `column_searchable_list` = name, city; `column_sortable_list` = name, city, created_at; фильтры по city/region/is_franchise.
- [ ] `ReviewAdmin`: `column_list` = created_at, platform, organization, author_name, rating, status, is_paid; `column_searchable_list` = author_name, text; фильтры по platform, status, rating, is_paid; сортировка по created_at (по убыванию по умолчанию); удобное редактирование `reply_text`, `status`, `replied_by_user_id`.
- [ ] Человекочитаемые `name` у моделей (`__str__`) и русские подписи колонок (`column_labels`).

### Фаза 6 — Сиды (начальные пользователи)
- [ ] Скрипт/CLI-команда создания стартовых пользователей: один `admin`, один `review_operator` (пароли из env/аргументов, не в коде).
- [ ] Идемпотентность: повторный запуск не падает и не плодит дубли.

### Фаза 7 — Тесты и приёмка
- [ ] Тесты авторизации: успех, неверный пароль, неактивный юзер, доступ без сессии.
- [ ] Тесты RBAC: оператор не видит Users; не может редактировать организации; может редактировать отзыв.
- [ ] Пройти чек-лист §6.

---

## 5. Рекомендуемая файловая структура

```
app/
  core/
    config.py            # + ADMIN_SECRET_KEY, SESSION_MAX_AGE
    security.py          # hash_password / verify_password
  models/
    user.py              # User + Enum role
    organization.py      # Organization (=Location)
    review.py            # Review + Enum platform/status
  admin/
    __init__.py          # setup_admin(app, engine)
    auth.py              # AdminAuth(AuthenticationBackend)
    base.py              # RoleGatedModelView (хелпер роли)
    views.py             # UserAdmin, OrganizationAdmin, ReviewAdmin
  scripts/
    seed_users.py        # создание admin + operator
alembic/
  versions/xxxx_admin_rbac.py
```

---

## 6. Чек-лист приёмки

- [ ] `/admin` требует логин; вход по email+паролю работает; выход завершает сессию.
- [ ] Пароли хранятся только в виде хеша; секрет сессии берётся из env.
- [ ] Роль `admin`: полный CRUD по организациям, отзывам, пользователям.
- [ ] Роль `review_operator`: видит и редактирует отзывы; организации только читает; раздел «Пользователи» скрыт; создание/удаление отзывов недоступно.
- [ ] Разделы «Организации» и «Отзывы» показывают данные с поиском, фильтрами и сортировкой.
- [ ] Alembic-миграция применяется на чистой БД без ошибок.
- [ ] Есть сиды для стартовых admin и operator.
- [ ] Тесты авторизации и RBAC зелёные.
- [ ] Приложение стартует (`uvicorn`), существующий API/скрапер не сломаны.

---

## Приложение A — Порядок команд Spec-Kit

```bash
# Установка Spec-Kit (один раз в проекте)
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify init . --ai claude        # или: specify init serm-admin --ai claude
```

Затем в чате Claude Code последовательно:
`/speckit.constitution` → `/speckit.specify` → `/speckit.clarify` → `/speckit.plan` → `/speckit.tasks` → `/speckit.analyze` → `/speckit.implement`

Готовые формулировки для каждой команды — в отдельном промпте (см. сообщение с промптом).
