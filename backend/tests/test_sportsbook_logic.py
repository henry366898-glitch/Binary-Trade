"""
Dependency-free tests for the sportsbook odds/result/grading engine.

Runs with a bare Python (no beanie/motor/pytest needed) so CI can gate deploys
fast. Exits non-zero on any failure.

    python tests/test_sportsbook_logic.py
"""
import collections
import os
import random
import sys

# Make `app` importable no matter the working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import sportsbook_logic as L  # noqa: E402


def test_happy_path_grading():
    res = {"winner": "home", "home_score": 3, "away_score": 1}
    assert L.grade_leg({"market_key": "1x2", "selection_key": "home"}, res) == "won"
    assert L.grade_leg({"market_key": "1x2", "selection_key": "away"}, res) == "lost"
    assert L.grade_leg({"market_key": "1x2", "selection_key": "draw"}, res) == "lost"
    assert L.grade_leg({"market_key": "totals", "selection_key": "over", "line": 2.5}, res) == "won"
    assert L.grade_leg({"market_key": "totals", "selection_key": "under", "line": 2.5}, res) == "lost"
    assert L.grade_leg({"market_key": "spread", "selection_key": "home", "line": -1.5}, res) == "won"
    assert L.grade_leg({"market_key": "spread", "selection_key": "away", "line": 1.5}, res) == "lost"


def test_edge_draw_and_winner_only():
    draw = {"winner": "draw", "home_score": 2, "away_score": 2}
    assert L.grade_leg({"market_key": "1x2", "selection_key": "draw"}, draw) == "won"
    assert L.grade_leg({"market_key": "totals", "selection_key": "under", "line": 4.5}, draw) == "won"
    wo = {"winner": "away", "home_score": None, "away_score": None}
    assert L.grade_leg({"market_key": "moneyline", "selection_key": "away"}, wo) == "won"
    # totals on a scoreless (winner-only) result must not crash -> push
    assert L.grade_leg({"market_key": "totals", "selection_key": "over", "line": 2.5}, wo) == "push"


def test_invalid_inputs_degrade_gracefully():
    res = {"winner": "home", "home_score": 3, "away_score": 1}
    assert L.grade_leg({"market_key": "bogus", "selection_key": "x"}, res) == "push"
    assert L.grade_leg({"market_key": "totals", "selection_key": "over"}, res) == "push"  # no line


def test_regression_sweep_all_sports():
    random.seed(42)
    total_legs = 0
    for sport in L.SPORT_PROFILES:
        for _ in range(300):
            f = L.build_fixture(sport)
            for m in f["markets"]:
                implied = sum(1.0 / s["odds"] for s in m["selections"])
                assert implied > 1.0, (sport, m["key"], implied)   # house edge present
                for s in m["selections"]:
                    assert s["odds"] >= 1.01
            r = L.simulate_result(sport, f["sim"])
            if r["home_score"] is not None:
                hs, as_ = r["home_score"], r["away_score"]
                exp = "home" if hs > as_ else "away" if as_ > hs else "draw"
                assert r["winner"] == exp, (sport, r)
                if not L.SPORT_PROFILES[sport]["draws"]:
                    assert r["winner"] != "draw", (sport, r)
            for m in f["markets"]:
                for s in m["selections"]:
                    leg = {"market_key": m["key"], "selection_key": s["key"], "line": s.get("line")}
                    assert L.grade_leg(leg, r) in ("won", "lost", "push")
                    total_legs += 1
    assert total_legs > 1000


def test_home_edge_distribution():
    random.seed(7)
    wins = collections.Counter()
    for _ in range(3000):
        f = L.build_fixture("Soccer")
        wins[L.simulate_result("Soccer", f["sim"])["winner"]] += 1
    assert wins["home"] > wins["away"], wins


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\nAll {len(tests)} sportsbook logic tests passed.")
