"""Pydantic schemas for request/response validation."""
import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models.db import AdjustmentStatus, AdminRole, BetStatus, TradeDirection, TradeStatus


ALLOWED_COUNTRIES = {
    "UAE", "India", "Pakistan", "Saudi Arabia",
    "Kuwait", "Bahrain", "Oman", "Qatar", "Other",
}
ALLOWED_REFERRAL_SOURCES = {
    "Google", "Facebook", "Instagram", "TikTok", "Friend", "Other",
}
PHONE_RE = re.compile(r"^\+\d{6,20}$")


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=2, max_length=128)
    phone_number: str = Field(min_length=6, max_length=32)
    country: str
    referral_source: Optional[str] = None
    agreed_to_marketing: bool = False

    @field_validator("phone_number")
    @classmethod
    def _phone_ok(cls, v: str) -> str:
        v = v.strip().replace(" ", "").replace("-", "")
        if not PHONE_RE.match(v):
            raise ValueError("Phone must be in international format, e.g. +971501234567")
        return v

    @field_validator("country")
    @classmethod
    def _country_ok(cls, v: str) -> str:
        if v not in ALLOWED_COUNTRIES:
            raise ValueError(f"country must be one of: {sorted(ALLOWED_COUNTRIES)}")
        return v

    @field_validator("referral_source")
    @classmethod
    def _referral_ok(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if v not in ALLOWED_REFERRAL_SOURCES:
            raise ValueError(f"referral_source must be one of: {sorted(ALLOWED_REFERRAL_SOURCES)}")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    account_number: Optional[str] = None
    email: str
    full_name: str
    balance: float
    balance_resets_used: int
    disabled_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TradePlace(BaseModel):
    symbol: str
    direction: TradeDirection
    amount: float = Field(gt=0)
    expiry_seconds: int = Field(ge=30, le=3600)


class TradeOut(BaseModel):
    id: str
    symbol: str
    direction: TradeDirection
    amount: float
    payout_rate: float
    entry_price: float
    exit_price: Optional[float] = None
    opened_at: datetime
    expires_at: datetime
    settled_at: Optional[datetime] = None
    status: TradeStatus
    profit: float

    class Config:
        from_attributes = True


class PriceTick(BaseModel):
    symbol: str
    bid: float
    ask: float
    time: float  # unix timestamp


class StatsOut(BaseModel):
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_profit: float
    balance: float


class AdminLogin(BaseModel):
    email: EmailStr
    password: str


class AdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: AdminRole = AdminRole.ADMIN


class AdminBootstrap(BaseModel):
    secret_key: str
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class AdminOut(BaseModel):
    id: str
    email: str
    role: AdminRole
    created_at: datetime
    created_by_id: Optional[str] = None

    class Config:
        from_attributes = True


class AdminTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: AdminOut


class AdminAuthStatus(BaseModel):
    has_admins: bool


class BalanceAdjustIn(BaseModel):
    amount: float = Field(ge=-100_000, le=100_000, description="positive = credit, negative = debit")
    reason: str = Field(min_length=3, max_length=255)


class BalanceAdjustOut(BaseModel):
    id: str
    user_id: str
    admin_id: Optional[str] = None
    requested_by_user_id: Optional[str] = None
    payment_type_id: Optional[str] = None
    amount: float
    balance_before: Optional[float] = None
    balance_after: Optional[float] = None
    reason: str
    status: AdjustmentStatus
    proof_image_path: Optional[str] = None
    bank_details: Optional[dict] = None
    reject_reason: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TransactionRequestIn(BaseModel):
    direction: str = Field(description="deposit | withdrawal")
    amount: float = Field(gt=0, le=100_000, description="positive amount; sign applied based on direction")
    note: str = Field(min_length=3, max_length=255)
    bank_details: Optional[dict] = None
    payment_type_id: Optional[str] = None

    @field_validator("direction")
    @classmethod
    def _dir_ok(cls, v: str) -> str:
        if v not in ("deposit", "withdrawal"):
            raise ValueError("direction must be 'deposit' or 'withdrawal'")
        return v


class PaymentFieldIn(BaseModel):
    label: str = Field(default="", max_length=64)
    value: Optional[str] = Field(default=None, max_length=512)


class PaymentTypeIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    enabled: bool = True
    deposit_enabled: bool = True
    withdrawal_enabled: bool = False
    deposit_min: float = Field(ge=0, le=1_000_000, default=0.0)
    deposit_max: float = Field(ge=0, le=1_000_000, default=100_000.0)
    withdrawal_min: float = Field(ge=0, le=1_000_000, default=0.0)
    withdrawal_max: float = Field(ge=0, le=1_000_000, default=100_000.0)
    instructions: Optional[str] = Field(default=None, max_length=2000)
    fields: list[PaymentFieldIn] = Field(default_factory=list)
    display_order: int = 0


class PaymentTypeOut(BaseModel):
    id: str
    name: str
    enabled: bool
    deposit_enabled: bool
    withdrawal_enabled: bool
    deposit_min: float
    deposit_max: float
    withdrawal_min: float
    withdrawal_max: float
    instructions: Optional[str] = None
    image_path: Optional[str] = None
    has_image: bool = False
    display_order: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Sportsbook ----------

class BetPlaceIn(BaseModel):
    event_id: str
    market_key: str
    selection_key: str
    stake: float = Field(gt=0, le=1_000_000)


class BetLegOut(BaseModel):
    event_id: str
    sport: str
    match: str
    market_key: str
    market_name: str
    selection_key: str
    selection_name: str
    odds: float
    line: Optional[float] = None
    result: Optional[str] = None        # won | lost | push | None (pending)


class BetOut(BaseModel):
    id: str
    bet_type: str
    stake: float
    legs: list[BetLegOut]
    combined_odds: float
    potential_payout: float
    status: BetStatus
    profit: float
    placed_at: datetime
    settled_at: Optional[datetime] = None


class BetStatsOut(BaseModel):
    total_bets: int
    wins: int
    losses: int
    win_rate: float
    total_staked: float
    total_profit: float
    balance: float
