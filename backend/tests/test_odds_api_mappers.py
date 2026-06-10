"""
Tests for the pure The Odds API response mappers (no network / key needed).

Sample payloads mirror the documented The Odds API v4 /odds and /scores shapes.
Run: python tests/test_odds_api_mappers.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import odds_api as O  # noqa: E402
from app.services import sportsbook_logic as L  # noqa: E402

# A soccer event (has Draw) with h2h + spreads + totals from one bookmaker.
SOCCER_ODDS = {
    "id": "abc123",
    "sport_key": "soccer_epl",
    "sport_title": "EPL",
    "commence_time": "2030-01-01T15:00:00Z",
    "home_team": "Arsenal",
    "away_team": "Chelsea",
    "bookmakers": [{
        "key": "pinnacle", "title": "Pinnacle",
        "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Arsenal", "price": 1.8},
                {"name": "Chelsea", "price": 4.5},
                {"name": "Draw", "price": 3.7},
            ]},
            {"key": "spreads", "outcomes": [
                {"name": "Arsenal", "price": 1.95, "point": -1.5},
                {"name": "Chelsea", "price": 1.95, "point": 1.5},
            ]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "price": 1.9, "point": 2.5},
                {"name": "Under", "price": 1.9, "point": 2.5},
            ]},
        ],
    }],
}

# A basketball event (no draw -> moneyline) from one bookmaker.
NBA_ODDS = {
    "id": "nba1",
    "sport_key": "basketball_nba",
    "sport_title": "NBA",
    "commence_time": "2030-01-02T01:00:00Z",
    "home_team": "Lakers",
    "away_team": "Celtics",
    "bookmakers": [{
        "key": "fanduel",
        "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Lakers", "price": 2.1},
                {"name": "Celtics", "price": 1.75},
            ]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "price": 1.9, "point": 215.5},
                {"name": "Under", "price": 1.9, "point": 215.5},
            ]},
        ],
    }],
}

SOCCER_SCORE_DONE = {
    "id": "abc123", "sport_key": "soccer_epl",
    "completed": True, "home_team": "Arsenal", "away_team": "Chelsea",
    "scores": [{"name": "Arsenal", "score": "3"}, {"name": "Chelsea", "score": "1"}],
}
SOCCER_SCORE_LIVE = {
    "id": "abc123", "completed": False, "home_team": "Arsenal", "away_team": "Chelsea",
    "scores": [{"name": "Arsenal", "score": "1"}, {"name": "Chelsea", "score": "0"}],
}


def test_soccer_mapping():
    f = O.map_event_to_fixture(SOCCER_ODDS)
    assert f is not None
    assert f["provider_id"] == "abc123"
    assert f["sport"] == "Soccer"
    assert f["home"] == "Arsenal" and f["away"] == "Chelsea"
    assert f["start_time"] is not None and f["start_time"].tzinfo is None
    mk = {m["key"]: m for m in f["markets"]}
    assert set(mk) == {"1x2", "spread", "totals"}
    # 1x2 has draw, keys mapped correctly
    keys = {s["key"] for s in mk["1x2"]["selections"]}
    assert keys == {"home", "draw", "away"}
    # spread carries the handicap line
    home_spread = next(s for s in mk["spread"]["selections"] if s["key"] == "home")
    assert home_spread["line"] == -1.5
    # totals carries the line on the market + selections
    assert mk["totals"]["line"] == 2.5


def test_nba_moneyline_no_draw():
    f = O.map_event_to_fixture(NBA_ODDS)
    mk = {m["key"]: m for m in f["markets"]}
    assert "moneyline" in mk and "1x2" not in mk
    assert {s["key"] for s in mk["moneyline"]["selections"]} == {"home", "away"}


def test_result_extraction_and_grading_integration():
    # not completed -> None
    assert O.extract_result(SOCCER_SCORE_LIVE) is None
    res = O.extract_result(SOCCER_SCORE_DONE)
    assert res == {"winner": "home", "home_score": 3, "away_score": 1}
    # Feed a mapped leg into the SAME grader the settlement engine uses.
    f = O.map_event_to_fixture(SOCCER_ODDS)
    mk = {m["key"]: m for m in f["markets"]}
    home_leg = {"market_key": "1x2", "selection_key": "home", "line": None}
    assert L.grade_leg(home_leg, res) == "won"
    over_leg = {"market_key": "totals", "selection_key": "over", "line": mk["totals"]["line"]}
    assert L.grade_leg(over_leg, res) == "won"   # total 4 > 2.5
    # Arsenal -1.5: (3 - 1.5) - 1 = 0.5 > 0 -> won
    hsp = next(s for s in mk["spread"]["selections"] if s["key"] == "home")
    assert L.grade_leg({"market_key": "spread", "selection_key": "home", "line": hsp["line"]}, res) == "won"


def test_bad_event_returns_none():
    assert O.map_event_to_fixture({"home_team": "A", "away_team": "B", "bookmakers": []}) is None
    assert O.map_event_to_fixture({"bookmakers": [{"markets": []}]}) is None


def test_sport_name_mapping():
    assert O.sport_name("soccer_uefa_champs_league") == "Soccer"
    assert O.sport_name("americanfootball_nfl") == "American Football"
    assert O.sport_name("icehockey_nhl") == "Ice Hockey"
    assert O.sport_name("unknown_key", "Some Title") == "Some Title"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\nAll {len(tests)} odds-API mapper tests passed.")
