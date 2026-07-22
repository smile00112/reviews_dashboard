import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import AttentionRuleType, AttentionSeverity


class AttentionEvent(Base):
    """Снапшот одного срабатывания правила «Требуют внимания» (feature 015).

    Строка фиксирует то, что показывалось в блоке в момент срабатывания
    (title/subtitle/value/link/type/severity) — блок на /overview больше не
    считает вживую, а читает эти снапшоты. Одно срабатывание правила может
    создать несколько строк (например rating_drop — топ-N организаций); все они
    делят один ``fired_at`` (равный ``AttentionRule.latched_at`` того периода).
    Удаляются каскадно вместе с правилом.
    """

    __tablename__ = "attention_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attention_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[AttentionRuleType] = mapped_column(
        Enum(AttentionRuleType, name="attention_rule_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    severity: Mapped[AttentionSeverity] = mapped_column(
        Enum(AttentionSeverity, name="attention_severity_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(400), nullable=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    link: Mapped[str] = mapped_column(String(400), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
