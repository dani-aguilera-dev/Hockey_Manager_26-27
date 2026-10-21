"""EHL: torneo europeo simplificado de final a ocho."""
from __future__ import annotations

import random

from .models import GameState

EURO_TEAMS = [
    ("HC Bloemendaal", "Países Bajos", 86.0),
    ("THC Hurley", "Países Bajos", 83.0),
    ("SV Kampong", "Países Bajos", 82.0),
    ("Rot-Weiss Köln", "Alemania", 84.0),
    ("Royal Léopold", "Bélgica", 80.0),
    ("Racing Club de France", "Francia", 78.0),
]


def _strength(team) -> float:
    line, _ = team.auto_lineup()
    a, d = team.lineup_strength(line)
    return (a + d) / 2


def create_ehl(state: GameState) -> None:
    dha = [t for t in state.teams.values() if t.league == "DHA"]
    dha.sort(key=lambda t: (-t.points, -(t.goals_for - t.goals_against), t.name))
    spanish = []
    for t in dha:
        if len(spanish) < 2:
            spanish.append(t)
    if state.cup_winner_id in state.teams and state.teams[state.cup_winner_id].league == "DHA":
        cup = state.teams[state.cup_winner_id]
        if cup not in spanish:
            spanish.append(cup)
    for t in dha:
        if len(spanish) >= 3:
            break
        if t not in spanish:
            spanish.append(t)
    participants = []
    for i, t in enumerate(spanish[:3], 1):
        participants.append({"id": t.id, "name": t.name, "country": "España", "strength": _strength(t), "spanish": True})
    for i, (name, country, strength) in enumerate(EURO_TEAMS[:5], 1):
        participants.append({"id": f"euro-{i}", "name": name, "country": country, "strength": strength, "spanish": False})
    rng = random.Random(state.seed + int(state.season[:4]) + 909)
    rng.shuffle(participants)
    fixtures = []
    for i in range(4):
        fixtures.append({"home": participants[2 * i], "away": participants[2 * i + 1],
                         "home_goals": 0, "away_goals": 0, "played": False, "winner_id": ""})
    state.ehl = {"round": 1, "fixtures": fixtures, "winner_id": "", "active": True,
                 "participants": [p["name"] for p in participants]}


def _sim_match(home, away, rng):
    hs, as_ = home["strength"], away["strength"]
    hg = max(0, int(rng.gauss(2.6 + (hs - as_) / 18, 1.3)))
    ag = max(0, int(rng.gauss(2.2 + (as_ - hs) / 18, 1.3)))
    winner = home["id"] if hg > ag else (away["id"] if ag > hg else "")
    if not winner:
        winner = home["id"] if rng.random() < 0.5 + (hs - as_) / 100 else away["id"]
    return hg, ag, winner


def simulate_ehl_round(state: GameState) -> None:
    ehl = state.ehl
    if not ehl or not ehl.get("active"):
        return
    rng = random.Random(state.seed + 1200 + ehl["round"])
    winners = []
    for fx in ehl["fixtures"]:
        if not fx["played"]:
            hg, ag, win = _sim_match(fx["home"], fx["away"], rng)
            fx["home_goals"], fx["away_goals"], fx["winner_id"], fx["played"] = hg, ag, win, True
        if fx["winner_id"]:
            winners.append(fx["home"] if fx["winner_id"] == fx["home"]["id"] else fx["away"])
    if ehl["round"] < 3:
        nxt = []
        for i in range(0, len(winners), 2):
            nxt.append({"home": winners[i], "away": winners[i + 1], "home_goals": 0,
                        "away_goals": 0, "played": False, "winner_id": ""})
        ehl["fixtures"] = nxt
        ehl["round"] += 1
    else:
        ehl["winner_id"] = winners[0]["id"] if winners else ""
        ehl["winner_name"] = winners[0]["name"] if winners else ""
        ehl["active"] = False


def simulate_ehl(state: GameState) -> None:
    while state.ehl.get("active"):
        simulate_ehl_round(state)
