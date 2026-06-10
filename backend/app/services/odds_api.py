"""
The Odds API (https://the-odds-api.com) client + response mappers.

The HTTP fetch functions are thin; the MAPPERS (`map_event_to_fixture`,
`extract_result`) are pure and stdlib-only so they can be unit-tested against
sample payloads without a live key or network. httpx is lazy-imported inside the
fetch functions for the same reason.

Markets are mapped onto the same shape the rest of the app already uses, so bet
placement, grading (sportsbook_logic.grade_leg) and the frontend are unchanged:
  1x2/moneyline -> selections home/draw/away
  spread        -> selections home/away with `line` (handicap point)
  totals        -> selections over/under with `line` (point)
"""
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

# Map a The Odds API sport_key prefix -> our display sport name.
_SPORT_PREFIX = [
    ("soccer", "Soccer"),
    ("basketball", "Basketball"),
    ("americanfootball", "American Football"),
    ("baseball", "Baseball"),
    ("icehockey", "Ice Hockey"),
    ("cricket", "Cricket"),
    ("rugbyleague", "Rugby"),
    ("rugbyunion", "Rugby"),
    ("rugby", "Rugby"),
    ("tennis", "Tennis"),
    ("mma", "MMA"),
    ("boxing", "Boxing"),
    ("aussierules", "Aussie Rules"),
    ("handball", "Handball"),
]


def sport_name(sport_key: str, sport_title: str | None = None) -> str:
    for prefix, name in _SPORT_PREFIX:
        if sport_key.startswith(prefix):
            return name
    return sport_title or sport_key


def _parse_time(iso: str) -> datetime | None:
    """ISO-8601 (…Z) -> naive UTC datetime (to match datetime.utcnow() usage)."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _pick_bookmaker(bookmakers: list, preferred: str | None) -> dict | None:
    if not bookmakers:
        return None
    if preferred:
        for b in bookmakers:
            if b.get("key") == preferred:
                return b
    return bookmakers[0]


def map_event_to_fixture(raw: dict, preferred_bookmaker: str | None = None) -> dict | None:
    """Map one The Odds API odds event into our internal fixture/markets shape.

    Returns None if the event has no usable home/away or no markets.
    """
    home = raw.get("home_team")
    away = raw.get("away_team")
    if not home or not away:
        return None
    bk = _pick_bookmaker(raw.get("bookmakers", []), preferred_bookmaker)
    if not bk:
        return None

    markets_out = []
    for m in bk.get("markets", []):
        key = m.get("key")
        outcomes = m.get("outcomes", []) or []

        if key == "h2h":
            has_draw = any(o.get("name") == "Draw" for o in outcomes)
            sels = []
            for o in outcomes:
                name = o.get("name")
                if name == home:
                    skey = "home"
                elif name == away:
                    skey = "away"
                elif name == "Draw":
                    skey = "draw"
                else:
                    continue
                sels.append({"key": skey, "name": name, "odds": float(o.get("price", 0))})
            if len(sels) >= 2:
                markets_out.append({
                    "key": "1x2" if has_draw else "moneyline",
                    "name": "Match Result",
                    "selections": sels,
                })

        elif key == "spreads":
            sels = []
            for o in outcomes:
                name = o.get("name")
                point = o.get("point")
                skey = "home" if name == home else "away" if name == away else None
                if skey is None or point is None:
                    continue
                sels.append({
                    "key": skey,
                    "name": f"{name} {float(point):+g}",
                    "odds": float(o.get("price", 0)),
                    "line": float(point),
                })
            if len(sels) >= 2:
                markets_out.append({"key": "spread", "name": "Handicap", "selections": sels})

        elif key == "totals":
            sels = []
            for o in outcomes:
                name = (o.get("name") or "").lower()  # "Over" / "Under"
                point = o.get("point")
                if name not in ("over", "under") or point is None:
                    continue
                sels.append({
                    "key": name,
                    "name": f"{o.get('name')} {float(point):g}",
                    "odds": float(o.get("price", 0)),
                    "line": float(point),
                })
            if len(sels) == 2:
                markets_out.append({
                    "key": "totals", "name": "Total Points",
                    "line": sels[0]["line"], "selections": sels,
                })

    if not markets_out:
        return None

    return {
        "provider_id": raw.get("id"),
        "sport_key": raw.get("sport_key"),
        "sport": sport_name(raw.get("sport_key", ""), raw.get("sport_title")),
        "league": raw.get("sport_title") or raw.get("sport_key"),
        "home": home,
        "away": away,
        "start_time": _parse_time(raw.get("commence_time")),
        "markets": markets_out,
    }


def extract_result(raw_score: dict) -> dict | None:
    """Map a The Odds API scores event into a result, or None if not completed."""
    if not raw_score.get("completed"):
        return None
    home = raw_score.get("home_team")
    away = raw_score.get("away_team")
    scores = {s.get("name"): s.get("score") for s in (raw_score.get("scores") or [])}
    try:
        hs = int(scores.get(home))
        as_ = int(scores.get(away))
    except (TypeError, ValueError):
        return None
    winner = "home" if hs > as_ else "away" if as_ > hs else "draw"
    return {"winner": winner, "home_score": hs, "away_score": as_}


# --------------------------------------------------------------------------
# HTTP fetch (lazy httpx import; only runs when a key is configured)
# --------------------------------------------------------------------------
async def _get(path: str, params: dict) -> list:
    import httpx  # lazy — keeps mappers importable without httpx installed

    params = {**params, "apiKey": settings.ODDS_API_KEY}
    url = f"{settings.ODDS_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params)
        remaining = resp.headers.get("x-requests-remaining")
        if remaining is not None:
            logger.info("Odds API %s -> %s (quota remaining: %s)", path, resp.status_code, remaining)
        resp.raise_for_status()
        return resp.json()


async def fetch_odds(sport_key: str) -> list:
    return await _get(f"/sports/{sport_key}/odds", {
        "regions": settings.ODDS_API_REGIONS,
        "markets": settings.ODDS_API_MARKETS,
        "oddsFormat": settings.ODDS_API_ODDS_FORMAT,
    })


async def fetch_scores(sport_key: str) -> list:
    return await _get(f"/sports/{sport_key}/scores", {
        "daysFrom": settings.ODDS_SCORES_DAYS_FROM,
    })
