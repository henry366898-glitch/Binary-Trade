"""
Real sports feed — backed by The Odds API (app.services.odds_api).

Replaces the earlier simulated generator. Two responsibilities, on a single
loop with independent timers (to protect the API quota):

  * refresh ODDS  — pull upcoming events + odds, upsert by provider_id, and flip
                    scheduled -> live once kick-off passes.
  * refresh SCORES — pull completed results, set the event result + finished, so
                     the settlement engine can grade bets.

If ODDS_API_KEY is not configured the loop logs a warning and exits — we show NO
events rather than fabricating fake ones.
"""
import asyncio
import logging
import time
from datetime import datetime

from app.config import settings
from app.models.db import SportEvent, SportEventStatus
from app.services import odds_api

logger = logging.getLogger(__name__)

PROVIDER = "the-odds-api"


async def _upsert_event(fixture: dict) -> None:
    pid = fixture.get("provider_id")
    start = fixture.get("start_time")
    if not pid or not start:
        return
    now = datetime.utcnow()
    status = SportEventStatus.SCHEDULED if start > now else SportEventStatus.LIVE

    existing = await SportEvent.find_one(SportEvent.provider_id == pid)
    if existing:
        # Don't resurrect a finished event; just refresh odds/start while pre-match.
        if existing.status != SportEventStatus.FINISHED:
            existing.markets = fixture["markets"]
            existing.start_time = start
            existing.league = fixture["league"]
            existing.sport = fixture["sport"]
            if existing.status == SportEventStatus.SCHEDULED and status == SportEventStatus.LIVE:
                existing.status = SportEventStatus.LIVE
            existing.updated_at = now
            await existing.save()
        return

    await SportEvent(
        sport=fixture["sport"],
        league=fixture["league"],
        country=None,
        home=fixture["home"],
        away=fixture["away"],
        start_time=start,
        status=status,
        markets=fixture["markets"],
        provider=PROVIDER,
        provider_id=pid,
        created_at=now,
        updated_at=now,
    ).insert()


async def _refresh_odds() -> None:
    for sport_key in settings.ODDS_SPORT_KEYS:
        try:
            raw_events = await odds_api.fetch_odds(sport_key)
        except Exception as e:  # noqa: BLE001 — one sport failing shouldn't stop others
            logger.warning("Odds fetch failed for %s: %s", sport_key, e)
            continue
        count = 0
        for raw in raw_events:
            fixture = odds_api.map_event_to_fixture(raw)
            if fixture:
                await _upsert_event(fixture)
                count += 1
        logger.info("Odds: %s -> %d events upserted", sport_key, count)

    # Flip any scheduled events whose kick-off has passed to live.
    now = datetime.utcnow()
    stale = await SportEvent.find(
        SportEvent.status == SportEventStatus.SCHEDULED,
        SportEvent.start_time <= now,
    ).to_list()
    for ev in stale:
        ev.status = SportEventStatus.LIVE
        ev.updated_at = now
        await ev.save()


async def _refresh_scores() -> None:
    for sport_key in settings.ODDS_SPORT_KEYS:
        try:
            raw_scores = await odds_api.fetch_scores(sport_key)
        except Exception as e:  # noqa: BLE001
            logger.warning("Scores fetch failed for %s: %s", sport_key, e)
            continue
        for raw in raw_scores:
            result = odds_api.extract_result(raw)
            if not result:
                continue
            ev = await SportEvent.find_one(SportEvent.provider_id == raw.get("id"))
            if not ev or ev.status == SportEventStatus.FINISHED:
                continue
            ev.result = result
            ev.home_score = result["home_score"]
            ev.away_score = result["away_score"]
            ev.status = SportEventStatus.FINISHED
            ev.updated_at = datetime.utcnow()
            await ev.save()
            logger.info("Scores: finished %s %s vs %s -> %s", ev.sport, ev.home, ev.away, result)


async def feed_loop() -> None:
    """Polls The Odds API for fixtures/odds and results."""
    if not settings.ODDS_API_KEY:
        logger.warning(
            "Sportsbook: ODDS_API_KEY not set — real feed disabled. "
            "No events will be shown until a key is configured."
        )
        return

    logger.info("Sportsbook real feed loop started (provider=%s)", PROVIDER)
    last_odds = 0.0
    while True:
        try:
            now = time.monotonic()
            if now - last_odds >= settings.ODDS_POLL_SECONDS:
                await _refresh_odds()
                last_odds = now
            await _refresh_scores()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — keep the loop alive
            logger.exception("Sportsbook feed error: %s", e)
        await asyncio.sleep(settings.ODDS_SCORES_POLL_SECONDS)
