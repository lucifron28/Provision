import enum

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class HouseholdRole(str, enum.Enum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class Household(Base, TimestampMixin):
    __tablename__ = "households"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    shopping_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    inventory_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )

    memberships: Mapped[list["HouseholdMembership"]] = relationship(
        "HouseholdMembership", back_populates="household", cascade="all, delete-orphan"
    )


class HouseholdMembership(Base, TimestampMixin):
    __tablename__ = "household_memberships"
    __table_args__ = (
        UniqueConstraint("household_id", "user_id", name="uq_household_membership_pair"),
        CheckConstraint("role IN ('OWNER', 'MEMBER')", name="ck_household_membership_role"),
        Index(
            "uq_household_memberships_user_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default IS TRUE"),
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), default=HouseholdRole.MEMBER.value, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    household: Mapped[Household] = relationship("Household", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="memberships")
