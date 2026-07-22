"""Permission catalog for the configurable RBAC system (feature 016).

Single source of truth for what page- and action-permissions exist. Pure data
(stdlib only) — safe to import from Alembic migrations, services, and the API.

A permission is an opaque string key in one of two namespaces:
  - ``page:<name>``   — access to a control-panel page (nav + entry).
  - ``action:<name>`` — performing a gated mutation (enforced server-side).

Grants live in the ``role_permissions`` table; absence of a grant means denied.
The immutable ``admin`` system role bypasses grants entirely (see PermissionService).

Constitution v1.5.0, Principle VII. Note: there is deliberately NO reply/posting
permission — posting replies to providers is out of scope (Principle II).
"""

from __future__ import annotations

# --- Page permissions --------------------------------------------------------

PAGE_PERMISSIONS: dict[str, str] = {
    "page:overview": "Обзор сети",
    "page:ratings": "Рейтинги",
    "page:companies": "Организации",
    "page:organizations": "Все филиалы",
    "page:reviews": "Отзывы",
    "page:scrape_runs": "История сборов",
    "page:jobs": "Фоновые задачи",
    "page:attention_rules": "Правила внимания",
    "page:http_scraper": "HTTP-парсер",
    "page:settings": "Настройки",
    "page:roles": "Роли и доступ",
}

# --- Action permissions ------------------------------------------------------

ACTION_PERMISSIONS: dict[str, str] = {
    "action:org.manage": "Управление филиалами",
    "action:company.manage": "Управление организациями",
    "action:scrape.run": "Запуск сбора",
    "action:job.manage": "Управление фоновыми задачами",
    "action:review.edit_status": "Изменение статуса отзыва",
    "action:attention.manage": "Управление правилами внимания",
    "action:settings.edit": "Изменение настроек",
    "action:scraper_session.manage": "Управление сессией парсера",
    "action:users.manage": "Управление пользователями",
    "action:roles.manage": "Управление ролями и доступом",
}

ALL_PERMISSIONS: dict[str, str] = {**PAGE_PERMISSIONS, **ACTION_PERMISSIONS}


def is_valid_permission(key: str) -> bool:
    """True if ``key`` is a member of the known catalog."""
    return key in ALL_PERMISSIONS


def catalog() -> dict[str, list[dict[str, str]]]:
    """Catalog grouped for the matrix UI: {"pages": [...], "actions": [...]}."""
    return {
        "pages": [{"key": k, "label": v} for k, v in PAGE_PERMISSIONS.items()],
        "actions": [{"key": k, "label": v} for k, v in ACTION_PERMISSIONS.items()],
    }


# --- Seed data ---------------------------------------------------------------

ADMIN_SLUG = "admin"

# The immutable system role. No grant rows are stored for it — PermissionService
# resolves it to the full catalog. It can never be deleted, renamed, or reduced.
DEFAULT_ROLES: list[dict] = [
    {
        "slug": ADMIN_SLUG,
        "name": "Администратор",
        "is_system": True,
        "description": "Полный доступ ко всем страницам и действиям.",
        "grants": [],  # full access via the is_system shortcut
    },
    {
        "slug": "call_center",
        "name": "Колл-центр",
        "is_system": False,
        "description": "Работа с отзывами: чтение и изменение статуса.",
        "grants": [
            "page:overview",
            "page:ratings",
            "page:reviews",
            "action:review.edit_status",
        ],
    },
    {
        "slug": "manager",
        "name": "Менеджер",
        "is_system": False,
        "description": "Чтение и аналитика без управления пользователями и настройками.",
        "grants": [
            "page:overview",
            "page:ratings",
            "page:companies",
            "page:organizations",
            "page:reviews",
            "page:scrape_runs",
            "page:jobs",
            "page:attention_rules",
        ],
    },
]

# Maps the legacy ``users.role`` enum value → the new role slug it becomes.
LEGACY_ROLE_MAP: dict[str, str] = {
    "admin": "admin",
    "review_operator": "call_center",
}
