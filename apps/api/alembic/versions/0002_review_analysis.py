"""add review analysis columns (feature 002)

Revision ID: 0002_review_analysis
Revises: 0001_initial
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_review_analysis"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("sentiment", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("sentiment_score", sa.Float(), nullable=True))
    op.add_column("reviews", sa.Column("sentiment_confidence", sa.Float(), nullable=True))
    op.add_column("reviews", sa.Column("rating_sentiment_mismatch", sa.Boolean(), nullable=True))
    op.add_column("reviews", sa.Column("problems", postgresql.JSONB(), nullable=True))
    op.add_column("reviews", sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("reviews", "analyzed_at")
    op.drop_column("reviews", "problems")
    op.drop_column("reviews", "rating_sentiment_mismatch")
    op.drop_column("reviews", "sentiment_confidence")
    op.drop_column("reviews", "sentiment_score")
    op.drop_column("reviews", "sentiment")
