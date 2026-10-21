"""Gestión de la temporada DHA: calendario, jornadas, Final Four y playout."""
from __future__ import annotations

import random
import zlib
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .models import GameState, Fixture, TeamState, PlayerState
from .data_loader import load_teams
from .calendar import create_dha_fixtures, create_fixtures, recompute_table, dha_table, league_table
from .logistics import travel_options, apply_travel
from .match_engine import MatchEngine, MatchResult
from .training import auto_plan, apply_training_plan
from .finance import apply_round_finances
from .youth import initial_youth, develop_youth, intake, generate_youth
from .cup import new_cup, cup_round_fixtures, cup_start, ROUND_NAMES, ROUND_PHASES, CUP_OFFSETS
from .ehl import create_ehl, simulate_ehl

DHA_TEAMS = 12
START_DATE = "2026-09-20"


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def new_game(club_id: str, manager_name: str = "Entrenador", seed: int | None = None) -> GameState:
    teams, clubs_by_id, cities_by_name = load_teams()
    if club_id not in teams:
        raise ValueError(f"Club desconocido: {club_id}")
    if teams[club_id].league not in ("DHA", "DHB"):
        raise ValueError("Solo se puede dirigir un club de DHA o DHB")
    league = teams[club_id].league
    dha_ids = sorted([t.id for t in teams.values() if t.league == "DHA"])
    fixtures = create_dha_fixtures(dha_ids, START_DATE) if league == "DHA" else []
    state = GameState(
        manager_name=manager_name, club_id=club_id, season="2026-27",
        competition=league,
        seed=seed if seed is not None else random.randint(1, 999_999),
        round=1, date=(fixtures[0].date if fixtures else START_DATE), fixtures=fixtures, teams=teams,
    )
    # La 1ª Andaluza no se simula: sus jugadores pasan al mercado como agentes libres.
    state.free_agents = []
    for tid, t in list(state.teams.items()):
        if t.league == "1A":
            for p in t.players:
                p.team_name = "Agente libre"
                p.salary = max(p.salary, int(max(6000, (p.overall - 45) * 1400)))
                state.free_agents.append(p)
            del state.teams[tid]
    # pequeña pretemporada: moral y forma iniciales razonables
    for t in state.teams.values():
        if t.league == "DHA":
            t.morale = 12
            for p in t.players:
                p.form = 6.2 + random.Random(state.seed + zlib.crc32(p.id.encode("utf-8")) % 1000).random() * 0.9
    initial_youth(state.teams, state.seed)
    if league == "DHB":
        setup_dhb_phase1(state, START_DATE)
    state.inbox.append({
        "date": "2026-08-01", "from": "Junta Directiva",
        "subject": f"Bienvenido al {state.user_team.name}",
        "body": (f"La junta te confía el primer equipo para la temporada 2026-27. "
                 f"Objetivo: {state.user_team.board_expectation}. "
                 f"La {state.competition} arranca el 20 de septiembre. "
                 f"Tienes {state.total_rounds} jornadas para cumplir el objetivo de la junta."),
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
        if team.league not in ("DHA", "DHB") or team.id == state.club_id:
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
    apply_round_finances(state)
    _reset_week_training(state)
    state.round += 1
    _maybe_setup_dhb_phase2(state)
    _maybe_create_cup(state)
    if state.round <= state.total_rounds:
        next_fx = next((f for f in state.fixtures if f.phase == "regular" and f.round == state.round), None)
        if next_fx:
            state.date = next_fx.date
    else:
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
    apply_round_finances(state)
    _reset_week_training(state)
    state.round += 1
    _maybe_setup_dhb_phase2(state)
    _maybe_create_cup(state)
    if state.round <= state.total_rounds:
        next_fx = next((f for f in state.fixtures if f.phase == "regular" and f.round == state.round), None)
        if next_fx:
            state.date = next_fx.date
    else:
        finish_regular_season(state)
    return user_payload


def _maybe_setup_dhb_phase2(state: GameState) -> None:
    if state.competition == "DHB" and state.dhb_phase == 1 and state.round == 15:
        setup_dhb_phase2(state)


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


def _background_table(state: GameState, league: str) -> list[dict]:
    teams = [t for t in state.teams.values() if t.league == league]
    if len(teams) < 2:
        return []
    ids = sorted(t.id for t in teams)
    fixtures = create_fixtures(ids, state.date)
    rng = random.Random(state.seed + (17 if league == "DHA" else 23) + int(state.season[:4]))
    rows = {t.id: {"team": t, "points": 0, "gf": 0, "ga": 0, "won": 0, "drawn": 0, "lost": 0} for t in teams}
    for fx in fixtures:
        h, a = rows[fx.home_id], rows[fx.away_id]
        hl, _ = h["team"].auto_lineup()
        al, _ = a["team"].auto_lineup()
        ha, hd = h["team"].lineup_strength(hl)
        aa, ad = a["team"].lineup_strength(al)
        hg = max(0, int(rng.gauss(2.4 + (ha + 4 - ad) / 14, 1.4)))
        ag = max(0, int(rng.gauss(2.2 + (aa - hd) / 14, 1.4)))
        h["gf"] += hg; h["ga"] += ag; a["gf"] += ag; a["ga"] += hg
        if hg > ag:
            h["points"] += 3; h["won"] += 1; a["lost"] += 1
        elif hg < ag:
            a["points"] += 3; a["won"] += 1; h["lost"] += 1
        else:
            h["points"] += 1; a["points"] += 1; h["drawn"] += 1; a["drawn"] += 1
    return sorted(rows.values(), key=lambda r: (-r["points"], -(r["gf"] - r["ga"]), -r["gf"], r["team"].name))


def simulate_cup_round(state: GameState, user_lineup_ids: list[str] | None = None) -> dict | None:
    """Simula cuartos, semifinal o final/tercer puesto a partido único."""
    if not state.cup_active:
        return None
    fixtures = cup_round_fixtures(state)
    if not fixtures:
        return None
    current_round = state.cup_round
    payload = None
    winners = []
    losers = []
    for idx, fx in enumerate(fixtures):
        if fx.played:
            home_won = fx.home_goals > fx.away_goals
            winners.append(fx.home_id if home_won else fx.away_id)
            losers.append(fx.away_id if home_won else fx.home_id)
            continue
        rng = random.Random(state.seed + current_round * 300 + idx)
        is_user = state.club_id in (fx.home_id, fx.away_id)
        line, bench = make_lineup(state.user_team, user_lineup_ids if user_lineup_ids is not None else (state.manual_lineup or None)) if is_user else (None, None)
        res = _simulate_fixture(state, fx, rng, user_lineup=line, user_bench=bench, neutral=False, knockout=True)
        home_won = res.shootout.get("winner_id") == fx.home_id if res.shootout else fx.home_goals > fx.away_goals
        winner = fx.home_id if home_won else fx.away_id
        loser = fx.away_id if home_won else fx.home_id
        winners.append(winner)
        losers.append(loser)
        if is_user:
            payload = _user_result_payload(state, fx, res, fx.travel)
            state.last_result = payload
    if current_round == 1:
        next_phase = ROUND_PHASES[2]
        from datetime import date as _date
        base = cup_start(state).toordinal() + CUP_OFFSETS[1]
        for i in range(0, len(winners), 2):
            state.fixtures.append(Fixture(
                id=f"C2-{i//2+1}", round=102, date=_date.fromordinal(base).isoformat(),
                home_id=winners[i], away_id=winners[i + 1], phase=next_phase,
            ))
        state.cup_round = 2
    elif current_round == 2:
        from datetime import date as _date
        base = cup_start(state).toordinal() + CUP_OFFSETS[2]
        date_s = _date.fromordinal(base).isoformat()
        state.fixtures.append(Fixture(
            id="C3-F", round=103, date=date_s, home_id=winners[0], away_id=winners[1], phase=ROUND_PHASES[3],
        ))
        state.fixtures.append(Fixture(
            id="C3-T", round=103, date=date_s, home_id=losers[0], away_id=losers[1], phase="cup_third",
        ))
        state.cup_round = 3
    else:
        final = next((f for f in fixtures if f.phase == ROUND_PHASES[3]), None)
        third = next((f for f in fixtures if f.phase == "cup_third"), None)
        if final:
            winner = final.home_id if final.home_goals > final.away_goals else final.away_id
            if final.home_goals == final.away_goals:
                winner = state.seed % 2 == 0 and final.home_id or final.away_id
            state.cup_winner_id = winner
            if winner in state.teams:
                state.teams[winner].budget += 50000
                state.teams[winner].board_confidence = min(100, state.teams[winner].board_confidence + 4)
            if winner == state.club_id:
                state.user_team.fan_confidence = min(100, state.user_team.fan_confidence + 8)
                state.inbox.append({"date": state.date, "from": "Prensa", "subject": "¡Campeón de Copa!",
                                    "body": "El club ha ganado la Copa del Rey. La afición está eufórica."})
        if third:
            state.cup_third_id = third.home_id if third.home_goals > third.away_goals else third.away_id
        state.cup_active = False
    return payload
def simulate_cup_remaining(state: GameState) -> None:
    while state.cup_active:
        simulate_cup_round(state)
        if state.cup_round > 3:
            break


def _maybe_create_cup(state: GameState) -> None:
    """La Copa se crea tras la primera vuelta (jornada 11) con los 8 mejores de DHA."""
    if state.competition != "DHA":
        return
    if state.cup_active or state.cup_winner_id:
        return
    if state.round == 12:
        new_cup(state)
def _dhb_groups_by_strength(state: GameState) -> dict[str, list[str]]:
    teams = sorted([t for t in state.teams.values() if t.league == "DHB"], key=lambda t: sum(t.lineup_strength(t.auto_lineup()[0])), reverse=True)
    groups = {"A": [], "B": []}
    for i, t in enumerate(teams):
        groups["A" if i % 2 == 0 else "B"].append(t.id)
    return groups


def _dhb_group_table(state: GameState, group: str) -> list[TeamState]:
    ids = set(state.dhb_groups.get(group, []))
    teams = [t for t in state.teams.values() if t.id in ids]
    return sorted(teams, key=lambda t: (-t.points, -(t.goals_for - t.goals_against), -t.goals_for, t.name))


def setup_dhb_phase1(state: GameState, start: str) -> None:
    groups = _dhb_groups_by_strength(state)
    state.dhb_phase = 1
    state.dhb_groups = groups
    state.dhb_group = next((g for g, ids in groups.items() if state.club_id in ids), "A")
    fixtures: list[Fixture] = []
    for g, ids in groups.items():
        for f in create_fixtures(ids, start):
            f.id = f"D{g}-{f.id}"
            fixtures.append(f)
    state.fixtures = sorted(fixtures, key=lambda f: (f.round, f.date, f.id))
    state.round = 1
    state.date = state.fixtures[0].date if state.fixtures else start


def setup_dhb_phase2(state: GameState) -> None:
    a = _dhb_group_table(state, "A")
    b = _dhb_group_table(state, "B")
    group_a = [t.id for t in a[:4]] + [t.id for t in b[:4]]
    group_b = [t.id for t in a[4:]] + [t.id for t in b[4:]]
    last_date = max((date.fromisoformat(f.date) for f in state.fixtures if f.phase == "regular"), default=date.fromisoformat(state.date))
    start = (last_date + timedelta(days=7)).isoformat()
    fixtures: list[Fixture] = []
    for g, ids in (("A", group_a), ("B", group_b)):
        for f in create_fixtures(ids, start, double=False):
            f.id = f"P{g}-{f.id}"
            f.round += 14
            fixtures.append(f)
    state.fixtures.extend(fixtures)
    state.fixtures.sort(key=lambda f: (f.round, f.date, f.id))
    state.dhb_phase = 2
    state.dhb_groups = {"A": group_a, "B": group_b}
    state.dhb_group = next((g for g, ids in state.dhb_groups.items() if state.club_id in ids), "A")


def _fast_group_rows(state: GameState, ids: list[str], start: str, double: bool, rng: random.Random) -> dict[str, dict]:
    fixtures = create_fixtures(ids, start, double=double)
    rows = {tid: {"team": state.teams[tid], "points": 0, "gf": 0, "ga": 0} for tid in ids}
    for fx in fixtures:
        h, a = rows[fx.home_id], rows[fx.away_id]
        hl, _ = h["team"].auto_lineup()
        al, _ = a["team"].auto_lineup()
        ha, hd = h["team"].lineup_strength(hl)
        aa, ad = a["team"].lineup_strength(al)
        hg = max(0, int(rng.gauss(2.4 + (ha + 4 - ad) / 14, 1.4)))
        ag = max(0, int(rng.gauss(2.2 + (aa - hd) / 14, 1.4)))
        h["gf"] += hg; h["ga"] += ag; a["gf"] += ag; a["ga"] += hg
        if hg > ag:
            h["points"] += 3
        elif ag > hg:
            a["points"] += 3
        else:
            h["points"] += 1; a["points"] += 1
    return rows


def _background_dhb_table(state: GameState) -> list[dict]:
    teams = [t for t in state.teams.values() if t.league == "DHB"]
    if len(teams) < 8:
        return []
    groups = _dhb_groups_by_strength(state)
    rng = random.Random(state.seed + 707 + int(state.season[:4]))
    start = state.date
    rows_a = _fast_group_rows(state, groups["A"], start, True, rng)
    rows_b = _fast_group_rows(state, groups["B"], start, True, rng)
    def top(rows):
        return sorted(rows.values(), key=lambda r: (-r["points"], -(r["gf"] - r["ga"]), -r["gf"]))[:4]
    group_a = [r["team"].id for r in top(rows_a)] + [r["team"].id for r in top(rows_b)]
    phase1_points = {tid: r["points"] for tid, r in {**rows_a, **rows_b}.items()}
    phase1_gf = {tid: r["gf"] for tid, r in {**rows_a, **rows_b}.items()}
    phase1_ga = {tid: r["ga"] for tid, r in {**rows_a, **rows_b}.items()}
    last_start = (date.fromisoformat(state.fixtures[0].date) + timedelta(days=98)).isoformat()
    rows2 = _fast_group_rows(state, group_a, last_start, False, rng)
    for tid, r in rows2.items():
        r["points"] += phase1_points.get(tid, 0)
        r["gf"] += phase1_gf.get(tid, 0)
        r["ga"] += phase1_ga.get(tid, 0)
    return sorted(rows2.values(), key=lambda r: (-r["points"], -(r["gf"] - r["ga"]), -r["gf"], r["team"].name))


def _simulate_dhb_final4(state: GameState, user_lineup_ids: list[str] | None = None) -> str | None:
    table = _dhb_group_table(state, "A")
    if len(table) < 4:
        return None
    semis = [(table[0], table[3]), (table[1], table[2])]
    winners = []
    results = []
    for i, (a, b) in enumerate(semis, 1):
        fx = Fixture(id=f"DHB-SF{i}", round=200 + i, date="2027-04-10", home_id=a.id, away_id=b.id, phase="dhb_sf")
        rng = random.Random(state.seed + 1700 + i)
        ids = user_lineup_ids if user_lineup_ids is not None else (state.manual_lineup or None)
        line, bench = make_lineup(state.user_team, ids) if state.club_id in (a.id, b.id) else (None, None)
        res = _simulate_fixture(state, fx, rng, user_lineup=line, user_bench=bench, neutral=True, knockout=True)
        state.fixtures.append(fx)
        win = res.shootout.get("winner_id") if res.shootout else (a.id if res.home_goals > res.away_goals else b.id)
        winners.append(state.teams[win])
        results.append((fx, res, win))
    final = Fixture(id="DHB-F", round=204, date="2027-04-11", home_id=winners[0].id, away_id=winners[1].id, phase="dhb_final")
    rng = random.Random(state.seed + 1800)
    ids = user_lineup_ids if user_lineup_ids is not None else (state.manual_lineup or None)
    line, bench = make_lineup(state.user_team, ids) if state.club_id in (winners[0].id, winners[1].id) else (None, None)
    res = _simulate_fixture(state, final, rng, user_lineup=line, user_bench=bench, neutral=True, knockout=True)
    state.fixtures.append(final)
    champion = res.shootout.get("winner_id") if res.shootout else (winners[0].id if res.home_goals > res.away_goals else winners[1].id)
    state.final4 = {
        "semifinals": [{"home_id": fx.home_id, "away_id": fx.away_id, "home_goals": r.home_goals,
                        "away_goals": r.away_goals, "shootout": r.shootout, "winner_id": w}
                       for fx, r, w in results],
        "final": {"home_id": final.home_id, "away_id": final.away_id, "home_goals": res.home_goals,
                  "away_goals": res.away_goals, "shootout": res.shootout, "winner_id": champion},
        "champion_id": champion,
    }
    return champion


def play_final_four(state: GameState, user_lineup_ids: list[str] | None = None) -> dict:
    """Simula semifinales, final y playout de DHA."""
    table = league_table(state.teams, "DHA")
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
            "note": "El representante DHB se elige por potencial de plantilla (modelo).",
        }
        if state.club_id in (eleventh.id, dhb.id):
            state.last_result = _user_result_payload(state, fx, res, None)
    state.playout = playout
    return state.final4


def _board_target(team: TeamState, competition: str) -> int:
    e = (team.board_expectation or "").lower()
    if "ganar la liga" in e or "título" in e:
        return 1
    if "final four" in e or "top 4" in e:
        return 4
    if "top 6" in e:
        return 6
    if "top 8" in e:
        return 8
    if "ascenso" in e:
        return 2
    if "play-off" in e or "playoff" in e:
        return 4
    if "permanencia" in e or "salvación" in e:
        return 10 if competition == "DHA" else 12
    return 8


def _board_review(state: GameState) -> dict:
    table = state.table()
    pos = next((i for i, t in enumerate(table, 1) if t.id == state.club_id), len(table))
    target = _board_target(state.user_team, state.competition)
    met = pos <= target
    before = state.user_team.board_confidence
    if met:
        delta = 10 if pos < target else 6
        budget_factor = 1.12
        message = "La junta está satisfecha con el objetivo cumplido."
    else:
        delta = -12 if pos > target + 3 else -8
        budget_factor = 0.90
        message = "La junta considera que el equipo se ha quedado corto."
    state.user_team.board_confidence = max(0, min(100, before + delta))
    state.user_team.transfer_budget = int(state.user_team.transfer_budget * budget_factor)
    if state.user_team.board_confidence <= 15:
        message += " Hay riesgo de destitución."
    review = {
        "target": target, "position": pos, "met": met,
        "confidence_before": before, "confidence_after": state.user_team.board_confidence,
        "transfer_budget_after": state.user_team.transfer_budget,
        "message": message,
    }
    state.board_review = review
    state.inbox.append({"date": state.date, "from": "Junta Directiva", "subject": "Revisión de temporada",
                        "body": f"{message} Objetivo: {target}º · Posición: {pos}º."})
    return review


def _process_age_and_retirements(state: GameState) -> None:
    """Envejece a los jugadores y decide retiradas al final de la temporada."""
    state.retirements = []
    rng = random.Random(state.seed + int(state.season[:4]) + 313)
    for team in state.teams.values():
        if team.league not in ("DHA", "DHB"):
            continue
        kept = []
        for p in team.players:
            p.age += 1
            chance = 0.0
            if p.age >= 40:
                chance = 1.0
            elif p.age >= 37:
                chance = 0.75
            elif p.age >= 35:
                chance = 0.40
            elif p.age >= 33:
                chance = 0.15
            elif p.age >= 31:
                chance = 0.03
            if p.overall < 58 and p.age >= 30:
                chance += 0.05
            # Las estrellas cuidan más su carrera y se retiran algo más tarde.
            if p.overall >= 85:
                chance *= 0.50
            elif p.overall >= 78:
                chance *= 0.75
            if rng.random() < chance:
                state.retirements.append({
                    "season": state.season, "player": p.name, "club": team.name,
                    "age": p.age, "overall": round(p.overall, 1), "goals": p.season_goals,
                })
                if p.overall >= 78 or team.id == state.club_id:
                    state.inbox.append({
                        "date": state.date, "from": "Club",
                        "subject": f"Retirada de {p.name}",
                        "body": f"{p.name} se retira a los {p.age} años tras una carrera en {team.name}.",
                    })
                continue
            kept.append(p)
        team.players = kept
    kept_free = []
    for p in state.free_agents:
        p.age += 1
        chance = 0.95 if p.age >= 37 else (0.55 if p.age >= 35 else (0.25 if p.age >= 33 else 0.0))
        if rng.random() < chance:
            state.retirements.append({
                "season": state.season, "player": p.name, "club": "Agente libre",
                "age": p.age, "overall": round(p.overall, 1), "goals": p.season_goals,
            })
        else:
            kept_free.append(p)
    state.free_agents = kept_free


def finish_regular_season(state: GameState, user_lineup_ids: list[str] | None = None) -> None:
    if state.competition == "DHA" and not state.cup_active and not state.cup_winner_id:
        new_cup(state)
    if state.cup_active:
        simulate_cup_remaining(state)
    if state.competition == "DHA":
        play_final_four(state, user_lineup_ids)
        table = league_table(state.teams, "DHA")
        dhb_rows = _background_dhb_table(state)
        p = state.playout or {}
        if p.get("promoted_id"):
            # El playout lo gana un equipo DHB: sube el campeón DHB y el ganador del playout.
            promoted = [dhb_rows[0]["team"].id] if dhb_rows else []
            if p["promoted_id"] not in promoted:
                promoted.append(p["promoted_id"])
            for row in dhb_rows:
                if len(promoted) >= 2:
                    break
                if row["team"].id not in promoted:
                    promoted.append(row["team"].id)
            relegated = [table[10].id, table[11].id] if len(table) >= 12 else []
        else:
            # El 11º se mantiene: solo baja el 12º y sube el campeón DHB.
            promoted = [dhb_rows[0]["team"].id] if dhb_rows else []
            relegated = [table[11].id] if len(table) >= 12 else []
        state.promoted_ids = list(dict.fromkeys(promoted))
        state.relegated_ids = list(dict.fromkeys(relegated))
    else:
        _simulate_dhb_final4(state, user_lineup_ids)
        table_a = _dhb_group_table(state, "A")
        dha_rows = _background_table(state, "DHA")
        state.promoted_ids = [t.id for t in table_a[:2]]
        state.relegated_ids = [r["team"].id for r in dha_rows[-2:]]
        state.playout = {}
    create_ehl(state)
    simulate_ehl(state)
    _process_age_and_retirements(state)
    state.phase = "season_end"
    state.date = f"{int(state.season[:4]) + 1}-06-30"
    _board_review(state)
    state.history.append(season_summary(state))
    champ = season_summary(state).get("champion") or "—"
    state.inbox.append({
        "date": state.date, "from": "Prensa",
        "subject": f"Fin de la temporada {state.season}",
        "body": f"Campeón: {champ}. Consulta el resumen de temporada y decide si continúas el proyecto.",
    })


def season_summary(state: GameState) -> dict:
    table = state.table() if state.competition == "DHB" else league_table(state.teams, state.competition)
    scorers = []
    for t in state.teams.values():
        if t.league == state.competition:
            for p in t.players:
                if p.season_goals:
                    scorers.append({"player": p.name, "team": t.name, "goals": p.season_goals, "assists": p.season_assists})
    scorers.sort(key=lambda x: (-x["goals"], -x["assists"], x["player"]))
    champion_id = state.final4.get("champion_id")
    if not champion_id and table:
        champion_id = table[0].id
    promoted_names = [state.teams[i].name for i in state.promoted_ids if i in state.teams]
    relegated_names = [state.teams[i].name for i in state.relegated_ids if i in state.teams]
    return {
        "season": state.season,
        "competition": state.competition,
        "group": state.dhb_group if state.competition == "DHB" else "A",
        "champion": state.teams[champion_id].name if champion_id in state.teams else None,
        "user_club": state.user_team.name,
        "user_position": next((i for i, t in enumerate(table, 1) if t.id == state.club_id), None),
        "table": [{"position": i, "team": t.name, "points": t.points, "played": t.played,
                   "won": t.won, "drawn": t.drawn, "lost": t.lost,
                   "gf": t.goals_for, "ga": t.goals_against, "gd": t.goals_for - t.goals_against}
                  for i, t in enumerate(table, 1)],
        "top_scorers": scorers[:10],
        "final4": state.final4,
        "playout": state.playout,
        "promoted": promoted_names,
        "relegated": relegated_names,
        "cup_winner": state.teams[state.cup_winner_id].name if state.cup_winner_id in state.teams else None,
        "cup_third": state.teams[state.cup_third_id].name if state.cup_third_id in state.teams else None,
        "ehl_winner": state.ehl.get("winner_name", "") if state.ehl else None,
        "ehl_participants": state.ehl.get("participants", []) if state.ehl else [],
        "retirements": state.retirements,
        "board_review": state.board_review,
        "direct_relegated": state.teams[state.playout["direct_relegated_id"]].name if state.playout.get("direct_relegated_id") in state.teams else None,
    }


def advance_to_next_season(state: GameState) -> None:
    """Cierra la temporada y prepara la siguiente, con ascensos y descensos."""
    if state.phase != "season_end":
        return
    new_year = int(state.season[:4]) + 1
    for tid in state.promoted_ids:
        if tid in state.teams:
            state.teams[tid].league = "DHA"
    for tid in state.relegated_ids:
        if tid in state.teams:
            state.teams[tid].league = "DHB"
    rng = random.Random(state.seed + new_year * 100)
    for team in state.teams.values():
        if team.league not in ("DHA", "DHB"):
            continue
        kept = []
        for p in team.players:
            expired = int(p.contract_until[:4]) <= new_year
            if expired:
                continue
            p.apps = p.season_goals = p.season_assists = 0
            p.rating_sum = 0.0
            p.fatigue = 0
            p.injury = 0
            p.suspension = 0
            p.form = 6.5
            kept.append(p)
        team.players = kept
        develop_youth(team, rng, new_year)
        intake(team, rng, new_year)
        while len(team.players) < 18:
            if team.youth:
                p = team.youth.pop(0)
                p.perfil = "Jugador"
                p.team_name = team.name
                team.players.append(p)
            else:
                p = generate_youth(team, rng, new_year, len(team.players) + 1, age=18)
                p.perfil = "Jugador"
                team.players.append(p)
        team.played = team.won = team.drawn = team.lost = 0
        team.goals_for = team.goals_against = team.points = 0
        team.finance_log = []
        team.prep_bonus = 0.0
        team.last_lineup = []
        team.cohesion = 12
    state.competition = state.user_team.league
    start = date.fromisoformat(state.fixtures[0].date) + timedelta(days=364)
    state.season = f"{new_year}-{str(new_year + 1)[-2:]}"
    state.phase = "regular"
    if state.competition == "DHB":
        state.dhb_groups = {}
        setup_dhb_phase1(state, start.isoformat())
    else:
        ids = sorted(t.id for t in state.teams.values() if t.league == "DHA")
        fixtures = create_fixtures(ids, start.isoformat())
        state.fixtures = fixtures
        state.round = 1
        state.date = fixtures[0].date
        state.dhb_phase = 1
        state.dhb_groups = {}
        state.dhb_group = "A"
    state.final4 = {}
    state.playout = {}
    state.last_result = {}
    state.manual_lineup = []
    state.week_trained = False
    state.weekly_plan = []
    state.training_report = {}
    state.ai_training_round = 0
    state.finance_round = 0
    state.transfer_offers = []
    state.market_offers_round = 0
    state.promoted_ids = []
    state.relegated_ids = []
    new_cup(state)
    state.inbox.append({
        "date": state.date, "from": "Junta Directiva",
        "subject": f"Temporada {state.season} · {state.competition}",
        "body": f"Comienza una nueva temporada en {state.competition}. Revisa plantilla, contratos y mercado de verano.",
    })
