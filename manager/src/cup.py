"""Copa del Rey: 8 mejores de DHA al final de la primera vuelta.

Formato oficial: cuartos, semifinal y final en fin de semana, a partido único.
No participan equipos de DHB.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .models import GameState, Fixture, TeamState

CUP_OFFSETS = [216, 217, 218]
ROUND_NAMES = {1: "Cuartos", 2: "Semifinal", 3: "Final y 3º puesto"}
ROUND_PHASES = {1: "cup_qf", 2: "cup_sf", 3: "cup_final"}


def cup_start(state: GameState) -> date:
    first = next((f for f in state.fixtures if f.phase == "regular"), None)
    return date.fromisoformat(first.date) if first else date.fromisoformat(state.date)


def _strength(team: TeamState) -> float:
    line, _ = team.auto_lineup()
    a, d = team.lineup_strength(line)
    return a + d


def new_cup(state: GameState) -> None:
    """Crea la Copa con los 8 mejores de DHA tras la primera vuelta."""
    if state.competition != "DHA":
        state.cup_active = False
        return
    table = sorted([t for t in state.teams.values() if t.league == "DHA"],
                   key=lambda t: (-t.points, -(t.goals_for - t.goals_against), -t.goals_for, t.name))
    if len(table) < 8:
        state.cup_active = False
        return
    seeded = table[:8]
    # Sorteo 1v8, 2v7, 3v6, 4v5.
    pairs = [(seeded[0], seeded[7]), (seeded[1], seeded[6]), (seeded[2], seeded[5]), (seeded[3], seeded[4])]
    start = cup_start(state) + timedelta(days=CUP_OFFSETS[0])
    state.fixtures = [f for f in state.fixtures if not f.phase.startswith("cup_")]
    for i, (a, b) in enumerate(pairs, 1):
        state.fixtures.append(Fixture(
            id=f"C1-{i}", round=101, date=start.isoformat(),
            home_id=a.id, away_id=b.id, phase=ROUND_PHASES[1],
        ))
    state.cup_round = 1
    state.cup_active = True
    state.cup_winner_id = ""
    state.cup_third_id = ""


def cup_round_fixtures(state: GameState) -> list[Fixture]:
    if not state.cup_active or state.cup_round not in ROUND_PHASES:
        return []
    if state.cup_round == 3:
        return [f for f in state.fixtures if f.phase in (ROUND_PHASES[3], "cup_third")]
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
        return "Pendiente (tras la jornada 11)"
    return f"{ROUND_NAMES.get(state.cup_round, 'Copa')} pendiente"
