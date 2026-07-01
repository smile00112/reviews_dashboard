from typing import List, Type

from starlette.requests import Request
from sqladmin.filters import AllUniqueStringValuesFilter, BooleanFilter
from sqladmin.forms import get_model_form
from wtforms import Form

from app.admin.base import RoleGatedModelView, _role_ctx
from app.models.organization import Organization
from app.models.review import Review
from app.models.user import User

# Fields operator may read AND write in the review edit form.
_OPERATOR_REVIEW_FIELDS = ["reply_text", "status", "is_paid"]

# All fields admin may write in the review edit form.
_ADMIN_REVIEW_FIELDS = [
    "status", "is_paid", "platform", "paid_cost",
    "paid_marked_by_user_id", "reply_text", "reply_at", "replied_by_user_id",
]


class UserAdmin(RoleGatedModelView, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-users"

    column_list = ["name", "email", "role", "is_active", "created_at"]
    column_searchable_list = ["name", "email"]
    column_sortable_list = ["name", "email", "role", "created_at"]
    column_labels = {
        "name": "Имя", "email": "Email", "role": "Роль",
        "is_active": "Активен", "created_at": "Создан",
    }

    form_columns = ["name", "email", "role", "is_active", "avatar_initials", "default_location_id"]

    can_create = True
    can_edit = True
    can_delete = True

    def is_accessible(self, request: Request) -> bool:
        return self._get_role(request) == "admin"

    def is_visible(self, request: Request) -> bool:
        return self._get_role(request) == "admin"


class OrganizationAdmin(RoleGatedModelView, model=Organization):
    name = "Организация"
    name_plural = "Организации"
    icon = "fa-solid fa-building"

    column_list = ["name", "city", "region", "is_franchise", "created_at"]
    column_searchable_list = ["name", "city"]
    column_sortable_list = ["name", "city", "created_at"]
    column_filters = [
        AllUniqueStringValuesFilter(Organization.city, "Город"),
        AllUniqueStringValuesFilter(Organization.region, "Регион"),
        BooleanFilter(Organization.is_franchise, "Франшиза"),
    ]
    column_labels = {
        "name": "Название", "city": "Город", "region": "Регион",
        "is_franchise": "Франшиза", "created_at": "Создана",
    }

    # Admin can create/edit/delete; operator gets read-only via can_create_for_role.
    can_create = True
    can_edit = True
    can_delete = True

    def is_accessible(self, request: Request) -> bool:
        return self._get_role(request) in ("admin", "review_operator")

    def is_visible(self, request: Request) -> bool:
        return self._get_role(request) in ("admin", "review_operator")

    def can_create_for_role(self, role: str | None) -> bool:
        return role == "admin"

    def can_delete_for_role(self, role: str | None) -> bool:
        return role == "admin"

    async def check_can_edit(self, request: Request, model) -> bool:
        return self._get_role(request) == "admin"


class ReviewAdmin(RoleGatedModelView, model=Review):
    name = "Отзыв"
    name_plural = "Отзывы"
    icon = "fa-solid fa-star"

    column_list = ["first_seen_at", "platform", "organization_id", "author_name", "rating", "status", "is_paid"]
    column_default_sort = ("first_seen_at", True)
    column_searchable_list = ["author_name", "review_text"]
    column_filters = [
        AllUniqueStringValuesFilter(Review.platform, "Платформа"),
        AllUniqueStringValuesFilter(Review.status, "Статус"),
        BooleanFilter(Review.is_paid, "Покупной"),
    ]
    column_labels = {
        "author_name": "Автор", "rating": "Оценка", "status": "Статус",
        "is_paid": "Покупной", "first_seen_at": "Дата", "platform": "Платформа",
        "organization_id": "Организация",
    }

    form_columns = _ADMIN_REVIEW_FIELDS

    can_create = True
    can_edit = True
    can_delete = True

    def is_accessible(self, request: Request) -> bool:
        return self._get_role(request) in ("admin", "review_operator")

    def is_visible(self, request: Request) -> bool:
        return self._get_role(request) in ("admin", "review_operator")

    def can_create_for_role(self, role: str | None) -> bool:
        return role == "admin"

    def can_delete_for_role(self, role: str | None) -> bool:
        return role == "admin"

    async def check_can_edit(self, request: Request, model) -> bool:
        return self._get_role(request) in ("admin", "review_operator")

    async def scaffold_form(self, rules: List[str] | None = None) -> Type[Form]:
        role = _role_ctx.get()
        if role == "review_operator":
            return await get_model_form(
                model=self.model,
                session_maker=self.session_maker,
                only=_OPERATOR_REVIEW_FIELDS,
                column_labels=self._column_labels,
                form_args=self.form_args,
                form_widget_args=self.form_widget_args,
                form_class=self.form_base_class,
                form_overrides=self.form_overrides,
                form_ajax_refs=self._form_ajax_refs,
                form_include_pk=self.form_include_pk,
                form_converter=self.form_converter,
            )
        return await super().scaffold_form(rules)

    async def on_model_change(self, data: dict, model, is_created: bool, request: Request) -> None:
        if self._get_role(request) == "review_operator":
            for field in list(data.keys()):
                if field not in _OPERATOR_REVIEW_FIELDS:
                    del data[field]
