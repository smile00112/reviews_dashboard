import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import AttentionRuleType, AttentionScope, AttentionSeverity


class AttentionRule(Base):
    """Настраиваемое правило блока «Требуют внимания» на /overview."""

    __tablename__ = "attention_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_type: Mapped[AttentionRuleType] = mapped_column(
        Enum(AttentionRuleType, name="attention_rule_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity: Mapped[AttentionSeverity] = mapped_column(
        Enum(AttentionSeverity, name="attention_severity_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    params: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    scope_type: Mapped[AttentionScope] = mapped_column(
        Enum(AttentionScope, name="attention_scope_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AttentionScope.global_,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    # JSONB-список строковых UUID, не M2M: организаций десятки, удаляются редко;
    # несуществующие id при оценке молча игнорируются.
    organization_ids: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    # Feature 015 — крон-модель. period_days = длительность одного периода
    # срабатывания; window_started_at = начало текущего периода («время начала
    # работы»); latched_at = момент срабатывания в текущем периоде (NULL = не
    # сработало, «armed»). Свип каждые 30 минут делает ролловер по истечении
    # периода и защёлкивает правило при выполнении условия.
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    latched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # История срабатываний. ORM-каскад удаляет события вместе с правилом даже там,
    # где FK ON DELETE CASCADE не применяется (SQLite в тестах без включённой прагмы).
    events: Mapped[list["AttentionEvent"]] = relationship(  # noqa: F821
        "AttentionEvent", cascade="all, delete-orphan"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def is_latched(self) -> bool:
        return self.latched_at is not None
