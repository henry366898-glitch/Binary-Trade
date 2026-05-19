"""Pydantic schemas for request/response validation."""
import re
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models.db import AdjustmentStatus, AdminRole, TradeDirection, TradeStatus


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
    referral_source: str | None = None
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
    def _referral_ok(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in ALLOWED_REFERRAL_SOURCES:
            raise ValueError(f"referral_source must be one of: {sorted(ALLOWED_REFERRAL_SOURCES)}")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    account_number: str | None = None
    email: str
    full_name: str
    balance: float
    balance_resets_used: int
    disabled_at: datetime | None = None
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
    id: int
    symbol: str
    direction: TradeDirection
    amount: float
    payout_rate: float
    entry_price: float
    exit_price: float | None
    opened_at: datetime
    expires_at: datetime
    settled_at: datetime | None
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
    id: int
    email: str
    role: AdminRole
    created_at: datetime
    created_by_id: int | None = None

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
    id: int
    user_id: int
    admin_id: int | None = None
    requested_by_user_id: int | None = None
    payment_type_id: int | None = None
    amount: float
    balance_before: float | None = None
    balance_after: float | None = None
    reason: str
    status: AdjustmentStatus
    proof_image_path: str | None = None
    bank_details: dict | None = None
    reject_reason: str | None = None
    created_at: datetime
    processed_at: datetime | None = None

    @field_validator("bank_details", mode="before")
    @classmethod
    def _decode_bank(cls, v):
        if isinstance(v, str):
            import json as _json
            try: return _json.loads(v)
            except Exception: return None
        return v

    class Config:
        from_attributes = True


class TransactionRequestIn(BaseModel):
    """Client-initiated deposit or withdrawal request."""
    direction: str = Field(description="deposit | withdrawal")
    amount: float = Field(gt=0, le=100_000, description="positive amount; sign applied based on direction")
    note: str = Field(min_length=3, max_length=255)
    # bank_details is now a free-form dict so it can mirror the payment type's custom fields.
    # Old keys (account_holder, account_number, ifsc, iban, branch) still work; new payment-type
    # fields are stored under their admin-defined labels.
    bank_details: dict | None = None
    payment_type_id: int | None = None

    @field_validator("direction")
    @classmethod
    def _dir_ok(cls, v: str) -> str:
        if v not in ("deposit", "withdrawal"):
            raise ValueError("direction must be 'deposit' or 'withdrawal'")
        return v


class PaymentFieldIn(BaseModel):
    # label is allowed to be blank here so the admin form can send rows in any
    # state — the router strips entries with an empty label before saving.
    label: str = Field(default="", max_length=64)
    value: str | None = Field(default=None, max_length=512)


class PaymentTypeIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    enabled: bool = True
    deposit_enabled: bool = True
    withdrawal_enabled: bool = False
    deposit_min: float = Field(ge=0, le=1_000_000, default=0.0)
    deposit_max: float = Field(ge=0, le=1_000_000, default=100_000.0)
    withdrawal_min: float = Field(ge=0, le=1_000_000, default=0.0)
    withdrawal_max: float = Field(ge=0, le=1_000_000, default=100_000.0)
    instructions: str | None = Field(default=None, max_length=2000)
    fields: list[PaymentFieldIn] = Field(default_factory=list)
    display_order: int = 0


class PaymentTypeOut(BaseModel):
    id: int
    name: str
    enabled: bool
    deposit_enabled: bool
    withdrawal_enabled: bool
    deposit_min: float
    deposit_max: float
    withdrawal_min: float
    withdrawal_max: float
    instructions: str | None = None
    image_path: str | None = None
    has_image: bool = False
    display_order: int
    created_at: datetime

    @field_validator("has_image", mode="before")
    @classmethod
    def _has_image(cls, v, info):
        # default value comes through; allow auto-derivation from image_path on the SQLAlchemy obj
        return v


    class Config:
        from_attributes = True
