"""MongoDB document models — Users, Trades, Transactions."""
from datetime import datetime
from typing import Optional
import enum

from beanie import Document, PydanticObjectId
from pydantic import Field


class TradeDirection(str, enum.Enum):
    UP = "up"
    DOWN = "down"


class TradeStatus(str, enum.Enum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"
    TIE = "tie"


class AdminRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"


class AdjustmentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class User(Document):
    account_number: Optional[str] = None
    email: str
    password_hash: str
    full_name: str
    phone_number: str
    country: str
    referral_source: Optional[str] = None
    agreed_to_marketing: bool = False
    balance: float = 0.0
    balance_resets_used: int = 0
    disabled_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
        indexes = ["email", "account_number"]


class Trade(Document):
    user_id: PydanticObjectId
    symbol: str
    direction: TradeDirection
    amount: float
    payout_rate: float
    entry_price: float
    exit_price: Optional[float] = None
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    settled_at: Optional[datetime] = None
    status: TradeStatus = TradeStatus.OPEN
    profit: float = 0.0

    class Settings:
        name = "trades"
        indexes = ["user_id", "status", "expires_at"]


class AdminUser(Document):
    email: str
    password_hash: str
    role: AdminRole = AdminRole.ADMIN
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by_id: Optional[PydanticObjectId] = None

    class Settings:
        name = "admin_users"
        indexes = ["email"]


class AcademyClick(Document):
    user_id: PydanticObjectId
    academy_name: str
    surface: str
    balance_at_click: float
    total_trades_at_click: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "academy_clicks"
        indexes = ["user_id", "created_at"]


class BalanceAdjustment(Document):
    user_id: PydanticObjectId
    admin_id: Optional[PydanticObjectId] = None
    requested_by_user_id: Optional[PydanticObjectId] = None
    payment_type_id: Optional[PydanticObjectId] = None
    amount: float
    balance_before: Optional[float] = None
    balance_after: Optional[float] = None
    reason: str
    status: AdjustmentStatus = AdjustmentStatus.PENDING
    proof_image_path: Optional[str] = None
    bank_details: Optional[dict] = None
    reject_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None

    class Settings:
        name = "balance_adjustments"
        indexes = ["user_id", "status", "created_at"]


class PaymentType(Document):
    name: str
    enabled: bool = True
    deposit_enabled: bool = True
    withdrawal_enabled: bool = False
    deposit_min: float = 0.0
    deposit_max: float = 100_000.0
    withdrawal_min: float = 0.0
    withdrawal_max: float = 100_000.0
    instructions: Optional[str] = None
    fields: list = Field(default_factory=list)  # list of {label, value} dicts
    image_path: Optional[str] = None
    display_order: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "payment_types"
        indexes = ["name"]
