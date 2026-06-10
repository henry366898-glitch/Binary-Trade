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


class SportEventStatus(str, enum.Enum):
    SCHEDULED = "scheduled"   # pre-match — betting open
    LIVE = "live"             # in progress — betting closed (Stage 1)
    FINISHED = "finished"     # result known — bets can settle


class BetStatus(str, enum.Enum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"
    VOID = "void"             # push / cancelled — stake refunded


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


class SportEvent(Document):
    """A simulated sporting fixture with embedded betting markets.

    Markets are stored as plain dicts so the schema can flex per sport:
        markets = [
          {"key": "1x2", "name": "Match Result",
           "selections": [{"key": "home", "name": "...", "odds": 2.10}, ...]},
          {"key": "totals", "name": "Total", "line": 2.5,
           "selections": [{"key": "over", "name": "Over 2.5", "odds": 1.9, "line": 2.5}, ...]},
          {"key": "spread", "name": "Handicap",
           "selections": [{"key": "home", "name": "... -1.5", "odds": 2.0, "line": -1.5}, ...]},
        ]
    `sim` holds the hidden generative parameters used to produce a coherent
    result at finish time. It is never sent to clients.
    """
    sport: str
    league: str
    country: Optional[str] = None
    home: str
    away: str
    start_time: datetime
    status: SportEventStatus = SportEventStatus.SCHEDULED
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    markets: list = Field(default_factory=list)
    result: Optional[dict] = None         # {winner, home_score, away_score}
    sim: Optional[dict] = None            # hidden generative params
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "sport_events"
        indexes = ["sport", "status", "start_time"]


class Bet(Document):
    """A wager placed against the shared virtual balance.

    A single bet has one leg; a parlay (Stage 2) has many. Each leg snapshots
    the odds at placement so later odds drift cannot change the payout.
        legs = [{event_id, sport, match, market_key, market_name,
                 selection_key, selection_name, odds, line, result}]
    """
    user_id: PydanticObjectId
    bet_type: str = "single"             # single | parlay (later)
    stake: float
    legs: list = Field(default_factory=list)
    combined_odds: float
    potential_payout: float
    status: BetStatus = BetStatus.OPEN
    profit: float = 0.0
    placed_at: datetime = Field(default_factory=datetime.utcnow)
    settled_at: Optional[datetime] = None

    class Settings:
        name = "bets"
        indexes = ["user_id", "status", "placed_at"]


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
