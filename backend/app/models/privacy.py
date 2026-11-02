"""Explicit member consent for a versioned external-processing purpose."""

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProcessingConsent(Base, TimestampMixin):
    __tablename__ = "processing_consents"
    __table_args__ = (
        UniqueConstraint("household_id", "user_id", "purpose", name="uq_processing_consent_scope"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(80), default="deepseek_recipes_v1")
    policy_version: Mapped[str] = mapped_column(String(40))
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
