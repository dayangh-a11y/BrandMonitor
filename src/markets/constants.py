"""Market type registry — each market is a distinct scoring model."""

from __future__ import annotations

PLATFORM_VERSION = "1.0.0"

MARKET_TYPES = {
    "win": {
        "id": "WIN",
        "title": "Win Market",
        "description": "Winner, Top 3, winning confidence & probability",
        "score_model": "win_strength",
    },
    "place": {
        "id": "PLACE",
        "title": "Place Market",
        "description": "Top2/Top3/Top5 probabilities and podium confidence",
        "score_model": "place_strength",
    },
    "head_to_head": {
        "id": "H2H",
        "title": "Head-to-Head Market",
        "description": "Pairwise finish-ahead matrix for every horse pair",
        "score_model": "pairwise_h2h",
    },
    "without_favorite": {
        "id": "WITHOUT_FAVORITE",
        "title": "Without Favorite Market",
        "description": "Exclude strongest favorite; rerank remaining field",
        "score_model": "win_strength_ex_favorite",
    },
    "value": {
        "id": "VALUE",
        "title": "Value Market",
        "description": "Horses stronger than public perception (rating/odds)",
        "score_model": "value_gap",
    },
    "risk": {
        "id": "RISK",
        "title": "Risk Market",
        "description": "Risk, reliability, variance, consistency, volatility",
        "score_model": "risk_profile",
    },
    "surprise": {
        "id": "SURPRISE",
        "title": "Surprise Market",
        "description": "Dark / hidden / improved / underrated / overrated",
        "score_model": "surprise_signals",
    },
    "matchup": {
        "id": "MATCHUP",
        "title": "Direct Matchup",
        "description": "A vs B factor-by-factor finish-ahead probabilities",
        "score_model": "direct_matchup",
    },
}
