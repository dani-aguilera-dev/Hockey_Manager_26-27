"""Gestión de la temporada DHA: calendario, jornadas, Final Four y playout."""
from __future__ import annotations

import random
import zlib
from datetime import date, timedelta
from typing import Any

from .models import GameState, Fixture, TeamState, PlayerState
from .data_loader import load_teams
from .calendar import create_dha_fixtures, recompute_table, dha_table
from .logistics import travel_options, apply_travel
from .match_engine import MatchEngine, MatchResult

DHA_TEAMS = 12
START_DATE = "2026-09-20"


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def new_game(club_id: str, manager_name: str = "Entrenador", seed: int | None = None) -> GameState:
    teams, clubs_by_id, cities_by_name = load_teams()
    if club_id not in teams:
        raise ValueError(f"Club desconocido: {club_id}")
    if teams[club_id].league != "DHA":
        raise ValueError("La Fase 1 solo permite dirigir clubes de DHA")
    dha_ids = sorted([t.id for t in teams.values() if t.league == "DHA"])
    fixtures = create_dha_fixtures(dha_ids, START_DATE)
    state = GameState(
        manager_name=manager_name, club_id=club_id, season="2026-27",
        seed=seed if seed is not None else random.randint(1, 999_999),
        round=1, date=fixtures[0].date, fixtures=fixtures, teams=teams,
    )
    # pequeña pretemporada: moral y forma iniciales razonables
    for t in state.teams.values():
        if t.league == "DHA":
            t.morale = 12
            for p in t.players:
                p.form = 6.2 + random.Random(state.seed + zlib.crc32(p.id.encode("utf-8")) % 1000).random() * 0.9
    state.inbox.append({
        "date": "2026-08-01", "from": "Junta Directiva",
        "subject": f"Bienvenido al {state.user_team.name}",
        "body": (f"La junta te confía el primer equipo para la temporada 2026-27. "
                 f"Objetivo: {state.user_team.board_expectation}. "
                 "La DHA arranca el 20 de septiembre. Tienes 22 jornadas para meter al equipo en el Top 4; "
                 "después se disputarán el Final Four y el playout."),
    })
    return state


def make_lineup(team: TeamState, player_ids: list[str] | None = None) -> tuple[list[PlayerState], list[PlayerState]]:
    if not player_ids:
        return team.auto_lineup()
    ids = list(dict.fromkeys(player_ids))
    by_id = {p.id: p for p in team.available_players}
    chosen = [by_id[i] for i in ids if i in by_id]
    if len(chosen) != 11:
        return team.auto_lineup()
    used = {p.id for p in chosen}
    bench = [p for p in sorted(team.available_players, key=lambda x: x.overall, reverse=True) if p.id not in used][:7]
    return chosen, bench


def _travel_for_fixture(state: GameState, fixture: Fixture, user_option_id: str | None, user_lineup: list[PlayerState], user_bench: list[PlayerState]) -> dict | None:
    """Aplica el viaje del equipo visitante. Devuelve resumen para el parte."""
    away = state.teams[fixture.away_id]
    home = state.teams[fixture.home_id]
    # cargar ciudades desde data_loader
    _, _, cities_by_name = load_teams()
    opts = travel_options(away, home, cities_by_name, squad_size=len(user_lineup) + len(user_bench) or 18)
    if not opts:
        return None
    chosen = None
    if away.id == state.club_id and user_option_id:
        chosen = next((o for o in opts if o["id"] == user_option_id), None)
    if not chosen:
        # IA o usuario sin elección: equilibrado si cabe, si no el más barato
        chosen = next((o for o in opts if o["id"] == "equilibrado" and o["cost"] <= away.budget), None)
        if not chosen:
            chosen = min(opts, key=lambda o: o["cost"])
    # si el usuario no puede pagar, usar el más barato
    if away.id == state.club_id and chosen["cost"] > away.budget:
        chosen = min(opts, key=lambda o: o["cost"])
    players = user_lineup + user_bench if away.id == state.club_id else None
    summary = apply_travel(away, chosen, players=players)
    summary["from"] = away.name
    summary["to"] = home.name
    summary["option_id"] = chosen["id"]
    summary["mode"] = chosen["mode"]
    summary["distance_km"] = chosen["distance_km"]
    summary["hotel_nights"] = chosen["hotel_nights"]
    return summary


def _attendance_and_gate(home: TeamState, away: TeamState, rng: random.Random) -> tuple[int, int]:
    cap = max(300, home.stadium_capacity or 1000)
    occ = 0.45 + rng.random() * 0.22
    # rival atractivo / derbi
    if away.name in ("Atlètic Terrassa HC", "Club Egara", "Junior FC", "FC Barcelona", "RC Polo"):
        occ += 0.08
    attendance = int(cap * min(0.98, occ))
    revenue = attendance * 12
    home.budget += revenue
    return attendance, revenue


def _simulate_fixture(state: GameState, fixture: Fixture, rng: random.Random,
                      user_lineup: list[PlayerState] | None = None,
                      user_bench: list[PlayerState] | None = None,
                      user_travel: dict | None = None,
                      neutral: bool = False, knockout: bool = False) -> MatchResult:
    home = state.teams[fixture.home_id]
    away = state.teams[fixture.away_id]
    if user_lineup and fixture.home_id == state.club_id:
        h_line, h_bench = user_lineup, user_bench or []
    else:
        h_line, h_bench = home.auto_lineup()
    if user_lineup and fixture.away_id == state.club_id:
        a_line, a_bench = user_lineup, user_bench or []
    else:
        a_line, a_bench = away.auto_lineup()
    # viaje del visitante (el usuario ya lo eligió; la IA usa equilibrado)
    if not neutral:
        tr = _travel_for_fixture(state, fixture, user_travel.get("option_id") if user_travel and away.id == state.club_id else None, a_line, a_bench)
        fixture.travel = tr or {}
    engine = MatchEngine(home, away, rng, neutral=neutral, knockout=knockout,
                         home_lineup=h_line, away_lineup=a_line,
                         home_bench=h_bench, away_bench=a_bench, detailed=True)
    result = engine.simulate()
    fixture.played = True
    fixture.home_goals = result.home_goals
    fixture.away_goals = result.away_goals
    fixture.home_stats = result.home_stats
    fixture.away_stats = result.away_stats
    fixture.events = result.events
    if not neutral:
        fixture.attendance, gate = _attendance_and_gate(home, away, rng)
        result.home_stats["gate_revenue"] = gate
    return result


def _user_result_payload(state: GameState, fixture: Fixture, result: MatchResult, travel: dict | None) -> dict:
    home = state.teams[fixture.home_id]
    away = state.teams[fixture.away_id]
    user_is_home = fixture.home_id == state.club_id
    gf = result.home_goals if user_is_home else result.away_goals
    ga = result.away_goals if user_is_home else result.home_goals
    user_ratings = result.home_ratings if user_is_home else result.away_ratings
    user_stats = result.home_stats if user_is_home else result.away_stats
    players = {p.id: p.name for p in state.user_team.players}
    ratings = {players.get(pid, pid): r for pid, r in user_ratings.items() if pid in players}
    return {
        "fixture_id": fixture.id, "round": fixture.round, "phase": fixture.phase,
        "home_id": home.id, "home_name": home.name, "away_id": away.id, "away_name": away.name,
        "home_goals": result.home_goals, "away_goals": result.away_goals,
        "user_is_home": user_is_home, "user_goals": gf, "user_against": ga,
        "result": "Victoria" if gf > ga else ("Empate" if gf == ga else "Derrota"),
        "events": result.events, "home_stats": result.home_stats, "away_stats": result.away_stats,
        "user_stats": user_stats, "ratings": ratings,
        "attendance": fixture.attendance,
        "travel": (travel or {}) if not user_is_home else {},
        "shootout": result.shootout, "date": fixture.date,
    }


def play_round(state: GameState, user_lineup_ids: list[str] | None = None,
               travel_option_id: str | None = None) -> dict | None:
    """Simula la jornada regular actual. Devuelve el parte del partido del usuario."""
    if state.phase != "regular":
        return None
    round_no = state.round
    fixtures = [f for f in state.fixtures if f.phase == "regular" and f.round == round_no and not f.played]
    if not fixtures:
        return None
    old_status = {p.id: (p.injury, p.suspension) for t in state.teams.values() for p in t.players}
    effective_ids = user_lineup_ids if user_lineup_ids is not None else (state.manual_lineup or None)
    user_lineup, user_bench = make_lineup(state.user_team, effective_ids)
    user_fixture = next((f for f in fixtures if state.club_id in (f.home_id, f.away_id)), None)
    user_travel = None
    if user_fixture and user_fixture.away_id == state.club_id:
        _, _, cities = load_teams()
        opts = travel_options(state.user_team, state.teams[user_fixture.home_id], cities, squad_size=18)
        user_travel = {"option_id": travel_option_id}
        # el resumen real se rellena al simular; aquí solo validamos que exista
        if travel_option_id and not any(o["id"] == travel_option_id for o in opts):
            user_travel["option_id"] = "equilibrado"
    user_payload = None
    for idx, fx in enumerate(fixtures):
        rng = random.Random(state.seed * 1000 + round_no * 37 + idx)
        is_user = state.club_id in (fx.home_id, fx.away_id)
        result = _simulate_fixture(
            state, fx, rng,
            user_lineup=user_lineup if is_user else None,
            user_bench=user_bench if is_user else None,
            user_travel=user_travel if is_user else None,
        )
        if is_user:
            user_payload = _user_result_payload(state, fx, result, fx.travel)
            state.last_result = user_payload
            _update_user_after_match(state, fx, result)
    # clasificación y recuperación
    recompute_table(state.teams, state.fixtures)
    _recover_after_round(state, old_status)
    state.round += 1
    if state.round <= 22:
        next_fx = next((f for f in state.fixtures if f.phase == "regular" and f.round == state.round), None)
        if next_fx:
            state.date = next_fx.date
    else:
        state.date = "2027-04-10"
        finish_regular_season(state)
    return user_payload


def _update_user_after_match(state: GameState, fixture: Fixture, result: MatchResult) -> None:
    user = state.user_team
    is_home = fixture.home_id == user.id
    gf = result.home_goals if is_home else result.away_goals
    ga = result.away_goals if is_home else result.home_goals
    if gf > ga:
        user.board_confidence = _clamp(user.board_confidence + 2, 0, 100)
        user.fan_confidence = _clamp(user.fan_confidence + 2, 0, 100)
        for p in user.players:
            p.morale = _clamp(p.morale + 1, 1, 20)
    elif gf < ga:
        user.board_confidence = _clamp(user.board_confidence - 2, 0, 100)
        user.fan_confidence = _clamp(user.fan_confidence - 2, 0, 100)
        for p in user.players:
            p.morale = _clamp(p.morale - 1, 1, 20)
    else:
        user.fan_confidence = _clamp(user.fan_confidence, 0, 100)
    if user.budget < 0:
        user.board_confidence = _clamp(user.board_confidence - 3, 0, 100)
    # goleadores: subida de moral
    for p in user.players:
        if p.season_goals and p.id in {e.get("player_id") for e in result.events if e.get("type") == "goal"}:
            p.morale = _clamp(p.morale + 1, 1, 20)


def _recover_after_round(state: GameState, old_status: dict[str, tuple[int, int]]) -> None:
    for t in state.teams.values():
        for p in t.players:
            p.fatigue = max(0.0, p.fatigue - 14.0)
            inj, sus = old_status.get(p.id, (0, 0))
            if inj > 0:
                p.injury = max(0, p.injury - 1)
            if sus > 0:
                p.suspension = max(0, p.suspension - 1)


def _best_dhb_team(state: GameState) -> TeamState:
    dhb = [t for t in state.teams.values() if t.league == "DHB"]
    if not dhb:
        return None
    def strength(t):
        line, _ = t.auto_lineup()
        a, d = t.lineup_strength(line)
        return a + d
    return max(dhb, key=strength)


def play_final_four(state: GameState, user_lineup_ids: list[str] | None = None) -> dict:
    """Simula semifinales, final y playout. Se llama automáticamente al acabar la liga."""
    table = dha_table(state.teams)
    if len(table) < 12:
        return {}
    semis = [(table[0], table[3]), (table[1], table[2])]
    results = []
    winners = []
    for i, (a, b) in enumerate(semis, 1):
        fx = Fixture(id=f"SF{i}", round=23, date="2027-04-10", home_id=a.id, away_id=b.id, phase="final4_sf")
        rng = random.Random(state.seed + 800 + i)
        ids = user_lineup_ids if user_lineup_ids is not None else (state.manual_lineup or None)
        line, bench = make_lineup(state.user_team, ids) if state.club_id in (a.id, b.id) else (None, None)
        res = _simulate_fixture(state, fx, rng, user_lineup=line, user_bench=bench, neutral=True, knockout=True)
        state.fixtures.append(fx)
        winner_id = res.shootout.get("winner_id") if res.shootout else (a.id if res.home_goals > res.away_goals else b.id)
        winners.append(state.teams[winner_id])
        results.append({"fixture": fx, "result": res, "winner_id": winner_id})
        if state.club_id in (a.id, b.id):
            state.last_result = _user_result_payload(state, fx, res, None)
    final = Fixture(id="F1", round=24, date="2027-04-11", home_id=winners[0].id, away_id=winners[1].id, phase="final4_final")
    rng = random.Random(state.seed + 900)
    ids = user_lineup_ids if user_lineup_ids is not None else (state.manual_lineup or None)
    line, bench = make_lineup(state.user_team, ids) if state.club_id in (winners[0].id, winners[1].id) else (None, None)
    res = _simulate_fixture(state, final, rng, user_lineup=line, user_bench=bench, neutral=True, knockout=True)
    state.fixtures.append(final)
    champion_id = res.shootout.get("winner_id") if res.shootout else (winners[0].id if res.home_goals > res.away_goals else winners[1].id)
    state.final4 = {
        "semifinals": [
            {"home_id": r["fixture"].home_id, "away_id": r["fixture"].away_id,
             "home_goals": r["result"].home_goals, "away_goals": r["result"].away_goals,
             "shootout": r["result"].shootout, "winner_id": r["winner_id"]}
            for r in results
        ],
        "final": {"home_id": final.home_id, "away_id": final.away_id,
                  "home_goals": res.home_goals, "away_goals": res.away_goals,
                  "shootout": res.shootout, "winner_id": champion_id},
        "champion_id": champion_id,
    }
    if state.club_id in (final.home_id, final.away_id):
        state.last_result = _user_result_payload(state, final, res, None)
    # playout: 11º DHA vs mejor DHB (representante, modelo)
    eleventh = table[10]
    dhb = _best_dhb_team(state)
    playout = {}
    if dhb:
        fx = Fixture(id="PO1", round=25, date="2027-04-17", home_id=eleventh.id, away_id=dhb.id, phase="playout")
        rng = random.Random(state.seed + 1000)
        ids = user_lineup_ids if user_lineup_ids is not None else (state.manual_lineup or None)
        line, bench = make_lineup(state.user_team, ids) if state.club_id in (eleventh.id, dhb.id) else (None, None)
        res = _simulate_fixture(state, fx, rng, user_lineup=line, user_bench=bench, neutral=True, knockout=True)
        state.fixtures.append(fx)
        winner_id = res.shootout.get("winner_id") if res.shootout else (eleventh.id if res.home_goals > res.away_goals else dhb.id)
        stays_id = eleventh.id if winner_id == eleventh.id else None
        promoted_id = None if stays_id else dhb.id
        relegated_id = None if stays_id else eleventh.id
        playout = {
            "home_id": eleventh.id, "away_id": dhb.id,
            "home_goals": res.home_goals, "away_goals": res.away_goals,
            "shootout": res.shootout, "winner_id": winner_id,
            "stays_id": stays_id, "promoted_id": promoted_id, "relegated_id": relegated_id,
            "direct_relegated_id": table[11].id,
            "note": "El representante DHB se elige por potencial de plantilla (modelo Fase 1).",
        }
        if state.club_id in (eleventh.id, dhb.id):
            state.last_result = _user_result_payload(state, fx, res, None)
    state.playout = playout
    state.phase = "season_end"
    state.history.append(season_summary(state))
    state.inbox.append({
        "date": "2027-04-18", "from": "Prensa",
        "subject": "Fin de la temporada 2026-27",
        "body": f"Campeón: {state.teams[champion_id].name}. Consulta el resumen de temporada en la oficina del club.",
    })
    return state.final4


def finish_regular_season(state: GameState, user_lineup_ids: list[str] | None = None) -> None:
    play_final_four(state, user_lineup_ids)
    state.date = "2027-06-30"


def season_summary(state: GameState) -> dict:
    table = dha_table(state.teams)
    scorers = []
    for t in state.teams.values():
        if t.league == "DHA":
            for p in t.players:
                if p.season_goals:
                    scorers.append({"player": p.name, "team": t.name, "goals": p.season_goals, "assists": p.season_assists})
    scorers.sort(key=lambda x: (-x["goals"], -x["assists"], x["player"]))
    champion = state.final4.get("champion_id")
    return {
        "season": state.season,
        "champion": state.teams[champion].name if champion in state.teams else None,
        "user_club": state.user_team.name,
        "user_position": next((i for i, t in enumerate(table, 1) if t.id == state.club_id), None),
        "table": [{"position": i, "team": t.name, "points": t.points, "played": t.played,
                   "won": t.won, "drawn": t.drawn, "lost": t.lost,
                   "gf": t.goals_for, "ga": t.goals_against, "gd": t.goals_for - t.goals_against}
                  for i, t in enumerate(table, 1)],
        "top_scorers": scorers[:10],
        "final4": state.final4,
        "playout": state.playout,
        "direct_relegated": state.teams[state.playout["direct_relegated_id"]].name if state.playout.get("direct_relegated_id") in state.teams else None,
    }
