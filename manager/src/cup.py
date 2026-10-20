"""Copa del Rey: cuadro eliminatorio de 16 equipos."""
from __future__ import annotations

import random
from datetime import date, timedelta

from .models import GameState, Fixture, TeamState

CUP_OFFSETS = [24, 52, 122, 171]
ROUND_NAMES = {1: "Octavos", 2: "Cuartos", 3: "Semifinal", 4: "Final"}
ROUND_PHASES = {1: "cup_r16", 2: "cup_qf", 3: "cup_sf", 4: "cup_final"}


def cup_start(state: GameState) -> date:
    first = next((f for f in state.fixtures if f.phase == "regular"), None)
    return date.fromisoformat(first.date) if first else date.fromisoformat(state.date)


def _strength(team: TeamState) -> float:
    line, _ = team.auto_lineup()
    a, d = team.lineup_strength(line)
    return a + d


def new_cup(state: GameState) -> None:
    dha = [t for t in state.teams.values() if t.league == "DHA"]
    dhb = sorted([t for t in state.teams.values() if t.league == "DHB"], key=_strength, reverse=True)[:4]
    teams = dha + dhb
    if len(teams) < 16:
        state.cup_active = False
        return
    rng = random.Random(state.seed + int(state.season[:4]) + 404)
    rng.shuffle(teams)
    start = cup_start(state) + timedelta(days=CUP_OFFSETS[0])
    state.fixtures = [f for f in state.fixtures if not f.phase.startswith("cup_")]
    for i in range(8):
        state.fixtures.append(Fixture(
            id=f"C1-{i+1}", round=101, date=start.isoformat(),
            home_id=teams[2 * i].id, away_id=teams[2 * i + 1].id,
            phase=ROUND_PHASES[1],
        ))
    state.cup_round = 1
    state.cup_active = True
    state.cup_winner_id = ""


def cup_round_fixtures(state: GameState) -> list[Fixture]:
    if not state.cup_active or state.cup_round not in ROUND_PHASES:
        return []
    phase = ROUND_PHASES[state.cup_round]
    return [f for f in state.fixtures if f.phase == phase]


def cup_next_user_fixture(state: GameState) -> Fixture | None:
    for f in cup_round_fixtures(state):
        if not f.played and state.club_id in (f.home_id, f.away_id):
            return f
    return None


def cup_status_text(state: GameState) -> str:
    if not state.cup_active:
        if state.cup_winner_id in state.teams:
            return f"Campeón: {state.teams[state.cup_winner_id].name}"
        return "Copa finalizada"
    return f"{ROUND_NAMES.get(state.cup_round, 'Copa')} pendiente"
