"""Gestión de la temporada DHA: calendario, jornadas, Final Four y playout."""
from __future__ import annotations

import random
import zlib
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .models import GameState, Fixture, TeamState, PlayerState
from .data_loader import load_teams
from .calendar import create_dha_fixtures, recompute_table, dha_table
from .logistics import travel_options, apply_travel
from .match_engine import MatchEngine, MatchResult
from .training import auto_plan, apply_training_plan

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


def _opponent_for_team(state: GameState, team_id: str) -> TeamState | None:
    for f in state.fixtures:
        if f.phase == "regular" and f.round == state.round and not f.played:
            if f.home_id == team_id:
                return state.teams.get(f.away_id)
            if f.away_id == team_id:
                return state.teams.get(f.home_id)
    return None


def ensure_ai_training(state: GameState) -> None:
    """Entrenamiento automático de los clubes IA para no regalar ventaja al usuario."""
    if state.phase != "regular" or state.ai_training_round == state.round:
        return
    for team in state.teams.values():
        if team.league != "DHA" or team.id == state.club_id:
            continue
        opponent = _opponent_for_team(state, team.id)
        rng = random.Random(state.seed * 1000 + state.round * 97 + zlib.crc32(team.id.encode("utf-8")) % 10000)
        plan = auto_plan(team, opponent, rng)
        apply_training_plan(team, plan, opponent, rng, delegated=True)
    state.ai_training_round = state.round


def ensure_week_training(state: GameState) -> dict | None:
    """Aplica el plan automático si el usuario no ha entrenado esta semana."""
    if state.phase != "regular" or state.week_trained:
        return None
    fx = state.next_user_fixture()
    opponent = None
    if fx:
        opp_id = fx.away_id if fx.home_id == state.club_id else fx.home_id
        opponent = state.teams.get(opp_id)
    rng = random.Random(state.seed * 1000 + state.round * 53 + 7)
    plan = auto_plan(state.user_team, opponent, rng)
    report = apply_training_plan(state.user_team, plan, opponent, rng, delegated=True)
    state.weekly_plan = plan
    state.training_report = report
    state.week_trained = True
    return report


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


def _update_team_management(team: TeamState, lineup: list[PlayerState], opponent: TeamState,
                            opponent_lineup: list[PlayerState], gf: int, ga: int) -> None:
    """Premia o castiga la gestión: continuidad, resultado, descanso y encaje."""
    if not lineup:
        return
    result = 1 if gf > ga else (0 if gf == ga else -1)
    previous = set(team.last_lineup)
    current = {p.id for p in lineup}
    continuity = len(previous & current) / max(1, len(lineup)) if previous else 0.65
    target_cohesion = 8.0 + continuity * 8.0 + result * 1.2
    team.cohesion = int(round(_clamp(team.cohesion * 0.65 + target_cohesion * 0.35, 1, 20)))
    team_strength = sum(team.lineup_strength(lineup)) / 2
    opp_strength = sum(opponent.lineup_strength(opponent_lineup)) / 2 if opponent_lineup else 60.0
    upset = 2.0 if result > 0 and opp_strength > team_strength + 4 else 0.0
    management = team.management_score(lineup)
    delta = result * 1.2 + (management - 55.0) * 0.02 + upset
    team.manager_rating = int(round(_clamp(team.manager_rating + delta, 0, 100)))
    team.last_lineup = [p.id for p in lineup]


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
    user_side = 0 if fixture.home_id == state.club_id else (1 if fixture.away_id == state.club_id else None)
    if user_side is None:
        ai_sides = {0, 1}
        auto_talk_sides = {0, 1}
    else:
        ai_sides = {1 - user_side}
        auto_talk_sides = {0, 1}  # en simulación rápida el segundo entrenador asume la charla
    engine = MatchEngine(home, away, rng, neutral=neutral, knockout=knockout,
                         home_lineup=h_line, away_lineup=a_line,
                         home_bench=h_bench, away_bench=a_bench, detailed=True,
                         ai_sides=ai_sides, auto_talk_sides=auto_talk_sides,
                         auto_sub_sides={0, 1})
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
    _update_team_management(home, engine.home_starters, away, engine.away_starters,
                            result.home_goals, result.away_goals)
    _update_team_management(away, engine.away_starters, home, engine.home_starters,
                            result.away_goals, result.home_goals)
    return result


def _reset_week_training(state: GameState) -> None:
    state.week_trained = False
    state.weekly_plan = []
    state.training_report = {}
    for t in state.teams.values():
        t.prep_bonus = 0.0


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
        "home_management": home.management_profile(),
        "away_management": away.management_profile(),
        "prep_bonus": state.user_team.prep_bonus,
        "shootout": result.shootout, "date": fixture.date,
    }


def play_round(state: GameState, user_lineup_ids: list[str] | None = None,
               travel_option_id: str | None = None) -> dict | None:
    """Simula la jornada regular actual. Devuelve el parte del partido del usuario."""
    if state.phase != "regular":
        return None
    ensure_week_training(state)
    ensure_ai_training(state)
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
    _reset_week_training(state)
    state.round += 1
    if state.round <= 22:
        next_fx = next((f for f in state.fixtures if f.phase == "regular" and f.round == state.round), None)
        if next_fx:
            state.date = next_fx.date
    else:
        state.date = "2027-04-10"
        finish_regular_season(state)
    return user_payload


@dataclass
class LiveRoundContext:
    fixture: Fixture
    engine: MatchEngine
    old_status: dict[str, tuple[int, int]]
    user_side: int
    travel: dict | None
    rng: random.Random


def prepare_live_round(state: GameState, user_lineup_ids: list[str] | None = None,
                       travel_option_id: str | None = None) -> LiveRoundContext:
    """Prepara el partido del usuario en modo directo.

    Simula primero el resto de la jornada y deja el partido del usuario listo
    para avanzar cuarto a cuarto o momento a momento. No actualiza clasificación
    ni recuperación hasta `finish_live_round`.
    """
    if state.phase != "regular":
        raise ValueError("La temporada ya ha terminado.")
    ensure_week_training(state)
    ensure_ai_training(state)
    round_no = state.round
    fixtures = [f for f in state.fixtures if f.phase == "regular" and f.round == round_no and not f.played]
    if not fixtures:
        raise ValueError("No hay partidos pendientes en esta jornada.")
    old_status = {p.id: (p.injury, p.suspension) for t in state.teams.values() for p in t.players}
    effective_ids = user_lineup_ids if user_lineup_ids is not None else (state.manual_lineup or None)
    user_lineup, user_bench = make_lineup(state.user_team, effective_ids)
    user_fixture = next((f for f in fixtures if state.club_id in (f.home_id, f.away_id)), None)
    if user_fixture is None:
        raise ValueError("El equipo del usuario no juega esta jornada.")
    # El resto de la jornada se resuelve antes del partido en directo.
    for idx, fx in enumerate(fixtures):
        if fx.id == user_fixture.id:
            continue
        rng_other = random.Random(state.seed * 1000 + round_no * 37 + idx)
        _simulate_fixture(state, fx, rng_other)
    home = state.teams[user_fixture.home_id]
    away = state.teams[user_fixture.away_id]
    if user_fixture.home_id == state.club_id:
        h_line, h_bench = user_lineup, user_bench
        a_line, a_bench = away.auto_lineup()
        user_side = 0
    else:
        a_line, a_bench = user_lineup, user_bench
        h_line, h_bench = home.auto_lineup()
        user_side = 1
    travel = None
    if user_fixture.away_id == state.club_id:
        _, _, cities = load_teams()
        opts = travel_options(state.user_team, home, cities, squad_size=18)
        chosen = next((o for o in opts if o["id"] == travel_option_id), None)
        if chosen is None:
            chosen = next((o for o in opts if o["id"] == "equilibrado" and o["cost"] <= state.user_team.budget), None)
        if chosen is None:
            chosen = min(opts, key=lambda o: o["cost"])
        if chosen["cost"] > state.user_team.budget:
            chosen = min(opts, key=lambda o: o["cost"])
        travel = apply_travel(state.user_team, chosen, players=user_lineup + user_bench)
        travel.update({
            "from": state.user_team.name, "to": home.name, "option_id": chosen["id"],
            "mode": chosen["mode"], "distance_km": chosen["distance_km"],
            "hotel_nights": chosen["hotel_nights"],
        })
        user_fixture.travel = travel
    else:
        travel = _travel_for_fixture(state, user_fixture, None, a_line, a_bench)
        user_fixture.travel = travel or {}
    idx_user = fixtures.index(user_fixture)
    rng = random.Random(state.seed * 1000 + round_no * 37 + idx_user)
    ai_side = 1 - user_side
    engine = MatchEngine(home, away, rng, neutral=False, knockout=False,
                         home_lineup=h_line, away_lineup=a_line,
                         home_bench=h_bench, away_bench=a_bench,
                         detailed=True, auto_sub_sides={ai_side},
                         ai_sides={ai_side}, auto_talk_sides={ai_side})
    return LiveRoundContext(
        fixture=user_fixture, engine=engine, old_status=old_status,
        user_side=user_side, travel=travel if user_side == 1 else None, rng=rng,
    )


def finish_live_round(state: GameState, ctx: LiveRoundContext) -> dict:
    """Cierra el partido en directo, actualiza la jornada y devuelve el parte."""
    engine = ctx.engine
    if engine.result is None:
        engine.simulate()
    result = engine.result
    if result is None:
        raise ValueError("El partido no tiene resultado.")
    fixture = ctx.fixture
    home = state.teams[fixture.home_id]
    away = state.teams[fixture.away_id]
    fixture.played = True
    fixture.home_goals = result.home_goals
    fixture.away_goals = result.away_goals
    fixture.home_stats = result.home_stats
    fixture.away_stats = result.away_stats
    fixture.events = result.events
    if not engine.neutral:
        fixture.attendance, gate = _attendance_and_gate(home, away, ctx.rng)
        result.home_stats["gate_revenue"] = gate
    _update_team_management(home, engine.home_starters, away, engine.away_starters,
                            result.home_goals, result.away_goals)
    _update_team_management(away, engine.away_starters, home, engine.home_starters,
                            result.away_goals, result.home_goals)
    user_payload = _user_result_payload(state, fixture, result, ctx.travel)
    state.last_result = user_payload
    _update_user_after_match(state, fixture, result)
    recompute_table(state.teams, state.fixtures)
    _recover_after_round(state, ctx.old_status)
    _reset_week_training(state)
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
