"""
Pure sportsbook logic — NO database / framework imports.

Kept dependency-free so the odds model, result simulation, and bet grading can
be unit-tested in isolation (and so the rules live in one place). The feed and
settlement services import from here.
"""
import math
import random

# Bookmaker margin baked into the odds (overround). 1.06 ≈ ~6% house edge.
MARGIN = 1.06

# profile: draws -> can a match end level; avg_total -> expected combined score
#          (None => winner-only sport: only a moneyline market, no totals/spread)
SPORT_PROFILES = {
    "Soccer":            {"draws": True,  "avg_total": 2.7},
    "Basketball":        {"draws": False, "avg_total": 218.0},
    "American Football": {"draws": False, "avg_total": 45.0},
    "Baseball":          {"draws": False, "avg_total": 8.5},
    "Ice Hockey":        {"draws": False, "avg_total": 5.5},
    "Cricket":           {"draws": False, "avg_total": 320.0},
    "Rugby":             {"draws": False, "avg_total": 44.0},
    "Handball":          {"draws": False, "avg_total": 55.0},
    "Tennis":            {"draws": False, "avg_total": None},
    "MMA":               {"draws": False, "avg_total": None},
}

# sport -> list of {league, country, teams: [...]}.  Broad/representative, extend freely.
CATALOGUE = {
    "Soccer": [
        {"league": "Premier League", "country": "England",
         "teams": ["Arsenal", "Man City", "Liverpool", "Chelsea", "Tottenham", "Man Utd", "Newcastle", "Aston Villa"]},
        {"league": "La Liga", "country": "Spain",
         "teams": ["Real Madrid", "Barcelona", "Atletico", "Sevilla", "Valencia", "Real Sociedad", "Betis", "Villarreal"]},
        {"league": "Serie A", "country": "Italy",
         "teams": ["Inter", "Juventus", "AC Milan", "Napoli", "Roma", "Lazio", "Atalanta", "Fiorentina"]},
        {"league": "Bundesliga", "country": "Germany",
         "teams": ["Bayern", "Dortmund", "Leipzig", "Leverkusen", "Frankfurt", "Wolfsburg", "Stuttgart", "Freiburg"]},
        {"league": "Ligue 1", "country": "France",
         "teams": ["PSG", "Marseille", "Monaco", "Lyon", "Lille", "Nice", "Rennes", "Lens"]},
        {"league": "Brasileirão", "country": "Brazil",
         "teams": ["Flamengo", "Palmeiras", "Corinthians", "São Paulo", "Grêmio", "Fluminense", "Santos", "Internacional"]},
        {"league": "ADNOC Pro League", "country": "UAE",
         "teams": ["Al Ain", "Shabab Al Ahli", "Al Wasl", "Al Jazira", "Sharjah", "Al Nasr", "Al Wahda", "Bani Yas"]},
    ],
    "Basketball": [
        {"league": "NBA", "country": "USA",
         "teams": ["Lakers", "Celtics", "Warriors", "Bucks", "Nuggets", "Heat", "Suns", "Mavericks"]},
        {"league": "EuroLeague", "country": "Europe",
         "teams": ["Real Madrid", "Barcelona", "Olympiacos", "Panathinaikos", "Fenerbahçe", "Bayern", "Milan", "Monaco"]},
    ],
    "American Football": [
        {"league": "NFL", "country": "USA",
         "teams": ["Chiefs", "Eagles", "49ers", "Cowboys", "Bills", "Ravens", "Bengals", "Lions"]},
    ],
    "Baseball": [
        {"league": "MLB", "country": "USA",
         "teams": ["Yankees", "Dodgers", "Astros", "Braves", "Mets", "Cubs", "Red Sox", "Padres"]},
    ],
    "Ice Hockey": [
        {"league": "NHL", "country": "USA/Canada",
         "teams": ["Bruins", "Maple Leafs", "Rangers", "Oilers", "Avalanche", "Lightning", "Panthers", "Golden Knights"]},
    ],
    "Cricket": [
        {"league": "IPL", "country": "India",
         "teams": ["Mumbai Indians", "Chennai", "Bangalore", "Kolkata", "Delhi", "Rajasthan", "Hyderabad", "Punjab"]},
        {"league": "International T20", "country": "World",
         "teams": ["India", "Australia", "England", "Pakistan", "South Africa", "New Zealand", "Sri Lanka", "West Indies"]},
    ],
    "Rugby": [
        {"league": "Six Nations", "country": "Europe",
         "teams": ["England", "France", "Ireland", "Wales", "Scotland", "Italy"]},
    ],
    "Handball": [
        {"league": "EHF Champions League", "country": "Europe",
         "teams": ["Barcelona", "Kiel", "Veszprém", "PSG", "Magdeburg", "Aalborg"]},
    ],
    "Tennis": [
        {"league": "ATP Tour", "country": "World",
         "teams": ["Djokovic", "Alcaraz", "Sinner", "Medvedev", "Zverev", "Rune", "Tsitsipas", "Rublev"]},
        {"league": "WTA Tour", "country": "World",
         "teams": ["Swiatek", "Sabalenka", "Gauff", "Rybakina", "Pegula", "Vondrousova", "Jabeur", "Zheng"]},
    ],
    "MMA": [
        {"league": "UFC", "country": "World",
         "teams": ["Jones", "Makhachev", "Adesanya", "Pereira", "O'Malley", "Edwards", "Volkanovski", "Du Plessis"]},
    ],
}


def odds_from_prob(prob: float) -> float:
    """Decimal odds from a probability, with the bookmaker margin applied."""
    prob = min(max(prob, 0.02), 0.97)
    return max(round(1.0 / (prob * MARGIN), 2), 1.01)


def poisson(lmbda: float) -> int:
    """Knuth's Poisson sampler (lmbda is small-to-moderate here)."""
    lmbda = max(lmbda, 0.01)
    L = math.exp(-lmbda)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1


def round_half(x: float) -> float:
    """Round to the nearest half-integer (… .5) so lines avoid pushes."""
    n = round(x * 2)
    if n % 2 == 0:          # landed on a whole number -> bump to nearest .5
        n += 1
    return n / 2.0


def build_fixture(sport: str) -> dict:
    """Generate one fixture's teams, markets (with odds) and hidden sim params.

    Returns: {home, away, league, country, markets, sim}
    """
    profile = SPORT_PROFILES[sport]
    block = random.choice(CATALOGUE[sport])
    home, away = random.sample(block["teams"], 2)

    s_home = random.uniform(0.7, 1.3) * 1.10   # small home edge
    s_away = random.uniform(0.7, 1.3)
    total_s = s_home + s_away

    draws = profile["draws"]
    if draws:
        closeness = 1 - abs(s_home - s_away) / total_s
        p_draw = 0.18 + 0.12 * closeness
    else:
        p_draw = 0.0
    rem = 1 - p_draw
    p_home = rem * s_home / total_s
    p_away = rem * s_away / total_s

    markets = [{
        "key": "1x2" if draws else "moneyline",
        "name": "Match Result",
        "selections": (
            [
                {"key": "home", "name": home, "odds": odds_from_prob(p_home)},
                {"key": "draw", "name": "Draw", "odds": odds_from_prob(p_draw)},
                {"key": "away", "name": away, "odds": odds_from_prob(p_away)},
            ] if draws else
            [
                {"key": "home", "name": home, "odds": odds_from_prob(p_home)},
                {"key": "away", "name": away, "odds": odds_from_prob(p_away)},
            ]
        ),
    }]

    sim = {"p_home": p_home, "p_draw": p_draw, "p_away": p_away}

    avg_total = profile["avg_total"]
    if avg_total is not None:
        line = round_half(avg_total + random.uniform(-avg_total * 0.06, avg_total * 0.06))
        markets.append({
            "key": "totals", "name": "Total Points", "line": line,
            "selections": [
                {"key": "over", "name": f"Over {line:g}", "odds": odds_from_prob(0.5), "line": line},
                {"key": "under", "name": f"Under {line:g}", "odds": odds_from_prob(0.5), "line": line},
            ],
        })
        margin_pts = max(0.5, abs(s_home - s_away) * avg_total * 0.25)
        hcap = -round_half(margin_pts) if s_home >= s_away else round_half(margin_pts)
        markets.append({
            "key": "spread", "name": "Handicap",
            "selections": [
                {"key": "home", "name": f"{home} {hcap:+g}", "odds": odds_from_prob(0.5), "line": hcap},
                {"key": "away", "name": f"{away} {-hcap:+g}", "odds": odds_from_prob(0.5), "line": -hcap},
            ],
        })
        sim["lam_home"] = (avg_total / 2.0) * (s_home / (total_s / 2.0))
        sim["lam_away"] = (avg_total / 2.0) * (s_away / (total_s / 2.0))

    return {
        "home": home, "away": away,
        "league": block["league"], "country": block.get("country"),
        "markets": markets, "sim": sim,
    }


def simulate_result(sport: str, sim: dict) -> dict:
    """Produce a coherent final result from the hidden sim params."""
    sim = sim or {}
    profile = SPORT_PROFILES.get(sport, {})
    avg_total = profile.get("avg_total")

    if avg_total is None:
        r = random.random()
        winner = "home" if r < sim.get("p_home", 0.5) else "away"
        return {"winner": winner, "home_score": None, "away_score": None}

    hs = poisson(sim.get("lam_home", avg_total / 2.0))
    as_ = poisson(sim.get("lam_away", avg_total / 2.0))
    if not profile.get("draws") and hs == as_:
        if sim.get("p_home", 0.5) >= sim.get("p_away", 0.5):
            hs += 1
        else:
            as_ += 1
    if hs > as_:
        winner = "home"
    elif as_ > hs:
        winner = "away"
    else:
        winner = "draw"
    return {"winner": winner, "home_score": hs, "away_score": as_}


def grade_leg(leg: dict, result: dict) -> str:
    """Return 'won' | 'lost' | 'push' for one leg given the event result."""
    mk = leg.get("market_key")
    sel = leg.get("selection_key")

    if mk in ("1x2", "moneyline"):
        return "won" if sel == result.get("winner") else "lost"

    if mk == "totals":
        hs, as_ = result.get("home_score"), result.get("away_score")
        if hs is None or as_ is None:
            return "push"
        total = hs + as_
        line = leg.get("line")
        if line is None or abs(total - line) < 1e-9:
            return "push"
        over = total > line
        if sel == "over":
            return "won" if over else "lost"
        return "won" if not over else "lost"

    if mk == "spread":
        hs, as_ = result.get("home_score"), result.get("away_score")
        if hs is None or as_ is None:
            return "push"
        line = leg.get("line") or 0.0
        diff = (hs + line) - as_ if sel == "home" else (as_ + line) - hs
        if abs(diff) < 1e-9:
            return "push"
        return "won" if diff > 0 else "lost"

    return "push"
