"""
Sportsbook settlement engine.

Mirrors the trade settlement loop: on a short tick, find OPEN bets whose every
leg references a FINISHED event, grade each leg, decide the bet outcome, and
credit the user's (shared) balance atomically on a win or void.

Stage 1 handles single bets. The parlay logic (all legs must win) is already
implemented here so Stage 2 only needs the multi-leg bet slip on the frontend.
"""
import asyncio
import logging
from datetime import datetime

from beanie import PydanticObjectId
from beanie.operators import Inc

from app.models.db import Bet, BetStatus, SportEvent, SportEventStatus, User
from app.services.sportsbook_logic import grade_leg

logger = logging.getLogger(__name__)


async def _settle_bet(bet: Bet, events: dict[str, SportEvent]) -> bool:
    """Grade and settle a single bet. Returns True if it was settled."""
    # Every leg's event must be finished before we can grade the bet.
    for leg in bet.legs:
        ev = events.get(str(leg["event_id"]))
        if ev is None or ev.status != SportEventStatus.FINISHED or not ev.result:
            return False

    leg_results = []
    for leg in bet.legs:
        ev = events[str(leg["event_id"])]
        outcome = grade_leg(leg, ev.result)
        leg["result"] = outcome
        leg_results.append(outcome)

    # Pushes are treated as odds 1.0 (returned), losses kill the whole bet.
    if any(r == "lost" for r in leg_results):
        bet.status = BetStatus.LOST
        bet.profit = -bet.stake
        refund = 0.0
    elif all(r == "push" for r in leg_results):
        bet.status = BetStatus.VOID
        bet.profit = 0.0
        refund = bet.stake
    else:
        # Effective odds = product of winning legs (pushes count as 1.0)
        eff_odds = 1.0
        for leg, r in zip(bet.legs, leg_results):
            if r == "won":
                eff_odds *= float(leg["odds"])
        payout = round(bet.stake * eff_odds, 2)
        bet.status = BetStatus.WON
        bet.profit = round(payout - bet.stake, 2)
        refund = payout

    bet.settled_at = datetime.utcnow()
    await bet.save()

    if refund > 0:
        await User.find_one(User.id == bet.user_id).update(Inc({User.balance: refund}))

    logger.info(
        "Sportsbook: settled bet %s status=%s profit=%.2f refund=%.2f",
        bet.id, bet.status, bet.profit, refund,
    )
    return True


async def settlement_loop() -> None:
    logger.info("Sportsbook settlement loop started")
    while True:
        try:
            open_bets = await Bet.find(Bet.status == BetStatus.OPEN).to_list()
            if open_bets:
                # Batch-load the events referenced by the open bets.
                ids = {str(leg["event_id"]) for b in open_bets for leg in b.legs}
                obj_ids = [PydanticObjectId(i) for i in ids]
                evs = await SportEvent.find({"_id": {"$in": obj_ids}}).to_list()
                events = {str(e.id): e for e in evs}
                for bet in open_bets:
                    await _settle_bet(bet, events)
        except Exception as e:  # noqa: BLE001 — keep the loop alive
            logger.exception("Sportsbook settlement error: %s", e)
        await asyncio.sleep(2.0)
