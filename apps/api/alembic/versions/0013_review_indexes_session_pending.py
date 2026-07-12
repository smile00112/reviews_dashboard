"""Review list/dashboard indexes + session_status 'pending' value (feature 010).

Additive only. ``ALTER TYPE ... ADD VALUE`` is irreversible on PostgreSQL — the
downgrade drops the indexes but leaves the enum value in place (harmless).

Revision ID: 0013_review_idx_session_pend
Revises: 0012_rating_snapshot
"""

from typing import Union

from alembic import op

# NB: alembic_version.version_num is varchar(32) — keep this id short.
revision: str = "0013_review_idx_session_pend"
down_revision: Union[str, None] = "0012_rating_snapshot"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_reviews_org_review_date", ["organization_id", "review_date"]),
    ("ix_reviews_org_first_seen", ["organization_id", "first_seen_at"]),
    ("ix_reviews_org_platform", ["organization_id", "platform"]),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE session_status_enum ADD VALUE IF NOT EXISTS 'pending'")
    for name, cols in _INDEXES:
        op.create_index(name, "reviews", cols)


def downgrade() -> None:
    for name, _ in reversed(_INDEXES):
        op.drop_index(name, table_name="reviews")
    # session_status_enum 'pending' intentionally not removed (see docstring).
