"""Sportsbook endpoints: list events, place bets, view my bets + stats.

Bets are settled by app.services.sportsbook_settlement. Wagers use the SAME
virtual balance as trading (single-wallet, per product decision).
"""
from datetime import datetime

from beanie.operators import Inc
from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.models.db import Bet, BetStatus, SportEvent, SportEventStatus, User
from app.models.schemas import BetOut, BetPlaceIn, BetStatsOut
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/sportsbook", tags=["sportsbook"])


def _require_enabled() -> None:
    if not settings.SPORTSBOOK_ENABLED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sportsbook is disabled")


def _event_out(e: SportEvent) -> dict:
    """Client-safe event view — never exposes the hidden `sim` params."""
    return {
        "id": str(e.id),
        "sport": e.sport,
        "league": e.league,
        "country": e.country,
        "home": e.home,
        "away": e.away,
        "start_time": e.start_time,
        "status": e.status,
        "home_score": e.home_score,
        "away_score": e.away_score,
        "markets": e.markets,
        "result": e.result,
    }


def _bet_out(b: Bet) -> BetOut:
    return BetOut(
        id=str(b.id),
        bet_type=b.bet_type,
        stake=b.stake,
        legs=b.legs,
        combined_odds=b.combined_odds,
        potential_payout=b.potential_payout,
        status=b.status,
        profit=b.profit,
        placed_at=b.placed_at,
        settled_at=b.settled_at,
    )


@router.get("/sports")
async def list_sports(
    _: None = Depends(_require_enabled),
    __: User = Depends(get_current_user),
):
    """Sports currently available to bet on — derived from live/upcoming events."""
    sports = await SportEvent.get_motor_collection().distinct(
        "sport",
        {"status": {"$in": [SportEventStatus.SCHEDULED.value, SportEventStatus.LIVE.value]}},
    )
    return {
        "sports": [{"sport": s} for s in sorted(sports)],
        "min_bet": settings.MIN_BET_AMOUNT,
        "max_bet": settings.MAX_BET_AMOUNT,
    }


@router.get("/events")
async def list_events(
    sport: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    _: None = Depends(_require_enabled),
    __: User = Depends(get_current_user),
):
    """Upcoming + live fixtures (default). Pass status_filter to narrow."""
    query: dict = {}
    if sport:
        query["sport"] = sport
    if status_filter:
        query["status"] = status_filter
    else:
        query["status"] = {"$in": [SportEventStatus.SCHEDULED.value, SportEventStatus.LIVE.value]}

    events = await SportEvent.find(query).sort(SportEvent.start_time).limit(min(limit, 300)).to_list()
    return {"events": [_event_out(e) for e in events]}


@router.post("/bets", response_model=BetOut, status_code=201)
async def place_bet(
    data: BetPlaceIn,
    _: None = Depends(_require_enabled),
    user: User = Depends(get_current_user),
):
    if not (settings.MIN_BET_AMOUNT <= data.stake <= settings.MAX_BET_AMOUNT):
        raise HTTPException(
            400, f"Stake must be between ${settings.MIN_BET_AMOUNT:g} and ${settings.MAX_BET_AMOUNT:g}"
        )

    event = await SportEvent.get(data.event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    if event.status != SportEventStatus.SCHEDULED:
        raise HTTPException(400, "Betting is closed for this event (already started)")

    market = next((m for m in event.markets if m.get("key") == data.market_key), None)
    if not market:
        raise HTTPException(400, "Unknown market for this event")
    selection = next((s for s in market.get("selections", []) if s.get("key") == data.selection_key), None)
    if not selection:
        raise HTTPException(400, "Unknown selection for this market")

    odds = float(selection["odds"])
    if user.balance < data.stake:
        raise HTTPException(400, "Insufficient balance")

    # Atomically deduct the stake from the shared balance.
    await User.find_one(User.id == user.id).update(Inc({User.balance: -data.stake}))

    leg = {
        "event_id": str(event.id),
        "sport": event.sport,
        "match": f"{event.home} vs {event.away}",
        "market_key": market["key"],
        "market_name": market.get("name", market["key"]),
        "selection_key": selection["key"],
        "selection_name": selection.get("name", selection["key"]),
        "odds": odds,
        "line": selection.get("line"),
        "result": None,
    }
    bet = Bet(
        user_id=user.id,
        bet_type="single",
        stake=data.stake,
        legs=[leg],
        combined_odds=odds,
        potential_payout=round(data.stake * odds, 2),
        status=BetStatus.OPEN,
        placed_at=datetime.utcnow(),
    )
    await bet.insert()
    return _bet_out(bet)


@router.get("/bets", response_model=list[BetOut])
async def my_bets(
    limit: int = 50,
    _: None = Depends(_require_enabled),
    user: User = Depends(get_current_user),
):
    bets = await Bet.find(Bet.user_id == user.id).sort(-Bet.placed_at).limit(limit).to_list()
    return [_bet_out(b) for b in bets]


@router.get("/stats", response_model=BetStatsOut)
async def bet_stats(
    _: None = Depends(_require_enabled),
    user: User = Depends(get_current_user),
):
    bets = await Bet.find(Bet.user_id == user.id).to_list()
    settled = [b for b in bets if b.status in (BetStatus.WON, BetStatus.LOST)]
    wins = sum(1 for b in settled if b.status == BetStatus.WON)
    losses = sum(1 for b in settled if b.status == BetStatus.LOST)
    total = wins + losses
    fresh = await User.get(user.id)
    return BetStatsOut(
        total_bets=len(settled),
        wins=wins,
        losses=losses,
        win_rate=(wins / total * 100) if total else 0.0,
        total_staked=round(sum(b.stake for b in bets), 2),
        total_profit=round(sum(b.profit for b in settled), 2),
        balance=fresh.balance if fresh else user.balance,
    )
