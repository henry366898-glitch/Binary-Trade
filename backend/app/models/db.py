"""Database models — Users, Trades, Transactions."""
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


class TradeDirection(str, enum.Enum):
    UP = "up"
    DOWN = "down"


class TradeStatus(str, enum.Enum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"
    TIE = "tie"  # rare: entry == exit price


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_number: Mapped[str | None] = mapped_column(String(16), unique=True, index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    full_name: Mapped[str] = mapped_column(String(128))
    phone_number: Mapped[str] = mapped_column(String(32), index=True)
    country: Mapped[str] = mapped_column(String(64))
    referral_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agreed_to_marketing: Mapped[bool] = mapped_column(Boolean, default=False)

    balance: Mapped[float] = mapped_column(Float, default=0.0)
    balance_resets_used: Mapped[int] = mapped_column(Integer, default=0)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    trades: Mapped[list["Trade"]] = relationship(back_populates="user")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[TradeDirection] = mapped_column(SQLEnum(TradeDirection))
    amount: Mapped[float] = mapped_column(Float)
    payout_rate: Mapped[float] = mapped_column(Float)  # e.g. 0.85

    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float, nullable=True)

    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    settled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    status: Mapped[TradeStatus] = mapped_column(SQLEnum(TradeStatus), default=TradeStatus.OPEN, index=True)
    profit: Mapped[float] = mapped_column(Float, default=0.0)

    user: Mapped["User"] = relationship(back_populates="trades")


class AdminRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"


class AdjustmentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[AdminRole] = mapped_column(SQLEnum(AdminRole), default=AdminRole.ADMIN)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)


class AcademyClick(Base):
    __tablename__ = "academy_clicks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    academy_name: Mapped[str] = mapped_column(String(64), index=True)
    surface: Mapped[str] = mapped_column(String(32))  # "modal_low" | "modal_zero" | "nudge_streak" | "footer" | "toast"
    balance_at_click: Mapped[float] = mapped_column(Float)
    total_trades_at_click: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class BalanceAdjustment(Base):
    __tablename__ = "balance_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True, index=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    payment_type_id: Mapped[int | None] = mapped_column(ForeignKey("payment_types.id"), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Float)  # positive = credit, negative = debit
    balance_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[AdjustmentStatus] = mapped_column(SQLEnum(AdjustmentStatus), default=AdjustmentStatus.APPROVED, index=True)
    proof_image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_details: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON-encoded
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PaymentType(Base):
    __tablename__ = "payment_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deposit_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    withdrawal_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    deposit_min: Mapped[float] = mapped_column(Float, default=0.0)
    deposit_max: Mapped[float] = mapped_column(Float, default=100_000.0)
    withdrawal_min: Mapped[float] = mapped_column(Float, default=0.0)
    withdrawal_max: Mapped[float] = mapped_column(Float, default=100_000.0)
    instructions: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    fields: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON list of {label, value}
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
