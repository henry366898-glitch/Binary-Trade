"""
Simulated sports feed (educational, virtual money).

There is NO real sports-data provider wired in. This module fabricates a rolling
catalogue of global fixtures (via app.services.sportsbook_logic), advances them
through scheduled -> live -> finished, and produces a result that the settlement
engine grades bets against.

Design seam: to plug in a real provider later, replace `_top_up_schedule()` /
`_advance_events()` with calls that map provider payloads onto the SportEvent shape.
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta

from app.config import settings
from app.models.db import SportEvent, SportEventStatus
from app.services.sportsbook_logic import (
    CATALOGUE, SPORT_PROFILES, build_fixture, simulate_result,
)

logger = logging.getLogger(__name__)


def _build_event(sport: str) -> SportEvent:
    f = build_fixture(sport)
    now = datetime.utcnow()
    start_in = random.randint(20, settings.SPORTSBOOK_SCHEDULE_WINDOW)
    return SportEvent(
        sport=sport,
        league=f["league"],
        country=f["country"],
        home=f["home"],
        away=f["away"],
        start_time=now + timedelta(seconds=start_in),
        status=SportEventStatus.SCHEDULED,
        markets=f["markets"],
        sim=f["sim"],
        created_at=now,
        updated_at=now,
    )


async def _top_up_schedule() -> None:
    upcoming = await SportEvent.find(
        SportEvent.status == SportEventStatus.SCHEDULED
    ).count()
    need = settings.SPORTSBOOK_MIN_UPCOMING - upcoming
    if need <= 0:
        return
    sports = list(CATALOGUE.keys())
    for i in range(need):
        await _build_event(sports[i % len(sports)]).insert()
    logger.info("Sportsbook: scheduled %d new fixtures (had %d).", need, upcoming)


async def _advance_events() -> None:
    now = datetime.utcnow()

    # scheduled -> live (kick-off reached)
    to_start = await SportEvent.find(
        SportEvent.status == SportEventStatus.SCHEDULED,
        SportEvent.start_time <= now,
    ).to_list()
    for ev in to_start:
        scored = SPORT_PROFILES.get(ev.sport, {}).get("avg_total") is not None
        ev.status = SportEventStatus.LIVE
        ev.home_score = 0 if scored else None
        ev.away_score = 0 if scored else None
        ev.updated_at = now
        await ev.save()

    # live -> finished (after the simulated match length)
    cutoff = now - timedelta(seconds=settings.SPORTSBOOK_LIVE_SECONDS)
    to_finish = await SportEvent.find(
        SportEvent.status == SportEventStatus.LIVE,
        SportEvent.start_time <= cutoff,
    ).to_list()
    for ev in to_finish:
        result = simulate_result(ev.sport, ev.sim or {})
        ev.result = result
        ev.home_score = result["home_score"]
        ev.away_score = result["away_score"]
        ev.status = SportEventStatus.FINISHED
        ev.updated_at = now
        await ev.save()
        logger.info("Sportsbook: finished %s %s vs %s -> %s", ev.sport, ev.home, ev.away, result)


async def feed_loop() -> None:
    """Keeps the simulated catalogue topped up and advances match states."""
    logger.info("Sportsbook feed loop started")
    while True:
        try:
            await _top_up_schedule()
            await _advance_events()
        except Exception as e:  # noqa: BLE001 — keep the loop alive
            logger.exception("Sportsbook feed error: %s", e)
        await asyncio.sleep(3.0)
