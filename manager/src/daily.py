"""Simulación día a día: calendario, eventos, noticias y vestuario.

La simulación diaria no juega partidos. Se detiene en la fecha del próximo
partido del usuario para que pueda preparar el once y decidir cómo jugarlo.
"""
from __future__ import annotations

import random
import zlib
from datetime import date, timedelta
from typing import Any

from .models import GameState, PlayerState, TeamState


def _rng(state: GameState, day: date, salt: int = 0) -> random.Random:
    return random.Random(state.seed * 10000 + day.toordinal() * 37 + salt)


def add_event(state: GameState, day: date, category: str, headline: str, body: str,
              *, important: bool = False, team_id: str = "", player_id: str = "",
              league: str = "", kind: str = "news") -> dict[str, Any]:
    event = {
        "date": day.isoformat(), "category": category, "headline": headline,
        "body": body, "important": important, "team_id": team_id,
        "player_id": player_id, "league": league, "type": kind,
    }
    if any(e.get("headline") == headline for e in state.daily_events[-4:]):
        return event
    state.daily_events = (state.daily_events + [event])[-240:]
    if important:
        state.inbox = (state.inbox + [{
            "date": day.isoformat(), "from": category,
            "subject": headline, "body": body,
        }])[-80:]
    return event


def _pick_player(state: GameState, rng: random.Random) -> PlayerState:
    pool = state.user_team.available_players or state.user_team.players
    return rng.choice(pool)


def _chat_options(kind: str) -> list[dict[str, Any]]:
    if kind == "minutes":
        return [
            {"label": "Confiar en él y darle minutos", "effects": {"morale": 2, "cohesion": 1},
             "response": "El jugador agradece la confianza y promete aprovechar la oportunidad."},
            {"label": "Exigirle más en los entrenamientos", "effects": {"morale": -1, "form": 0.4},
             "response": "El mensaje es duro, pero el jugador responde con intensidad."},
            {"label": "Pedirle paciencia", "effects": {"morale": 1},
             "response": "Entiende la competencia interna y seguirá trabajando."},
        ]
    if kind == "contract":
        return [
            {"label": "Prometer una renovación", "effects": {"morale": 3, "cohesion": 1},
             "response": "El jugador se muestra ilusionado con su continuidad."},
            {"label": "Decir que se gane el contrato", "effects": {"morale": -1, "form": 0.3},
             "response": "Acepta el reto y sube el ritmo en la sesión."},
            {"label": "Dejar la decisión al director deportivo", "effects": {"morale": 0},
             "response": "El vestuario entiende que el club tiene que valorarlo."},
        ]
    return [
        {"label": "Hablar con el grupo", "effects": {"cohesion": 2, "morale": 1},
         "response": "La conversación deja un ambiente más unido en el vestuario."},
        {"label": "Marcar distancia profesional", "effects": {"cohesion": -1, "manager_rating": 1},
         "response": "El grupo entiende que la exigencia está por encima de todo."},
        {"label": "Escuchar y no prometer nada", "effects": {"morale": 1},
         "response": "El jugador agradece que le escuches."},
    ]


def add_player_chat(state: GameState, day: date, player: PlayerState, kind: str = "minutes") -> dict[str, Any]:
    text = {
        "minutes": "Entrenador, quería hablar contigo. Siento que puedo ayudar al equipo y necesito saber cuál es mi papel.",
        "contract": "Me gustaría saber si el club cuenta conmigo para el futuro. Estoy cómodo aquí, pero necesito claridad.",
        "mood": "He notado al grupo un poco tenso esta semana. ¿Cómo ves el ambiente para el próximo partido?",
    }.get(kind, "Entrenador, ¿podemos hablar un momento?")
    message = {
        "id": f"CH-{day.toordinal()}-{len(state.chat_messages)}-{zlib.crc32(player.id.encode('utf-8')) % 10000}",
        "date": day.isoformat(), "player_id": player.id, "player_name": player.name,
        "team_id": state.club_id, "kind": kind, "text": text,
        "options": _chat_options(kind), "answered": False, "answer": "", "response": "",
    }
    state.chat_messages = (state.chat_messages + [message])[-60:]
    state.daily_events = (state.daily_events + [{
        "date": day.isoformat(), "category": "Vestuario",
        "headline": f"{player.name} quiere hablar contigo",
        "body": text, "important": False, "team_id": state.club_id,
        "player_id": player.id, "league": state.competition, "type": "chat",
    }])[-240:]
    return message


def _league_event(state: GameState, day: date, rng: random.Random) -> None:
    table = state.table()
    if not table:
        return
    leader = table[0]
    user_pos = next((i for i, t in enumerate(table, 1) if t.id == state.club_id), 0)
    next_fx = state.next_user_fixture()
    rival = ""
    if next_fx:
        rival = state.teams[next_fx.away_id].name if next_fx.home_id == state.club_id else state.teams[next_fx.home_id].name
    if not any(t.played for t in state.teams.values() if t.league == state.competition):
        preseason = [
            (f"{state.competition}: cuenta atrás para el arranque",
             "Los clubes ultiman la pretemporada. La clasificación todavía no refleja partidos oficiales."),
            ("Pretemporada: sesiones y pruebas",
             f"Los técnicos de {state.competition} siguen ajustando sistemas y minutos de pretemporada."),
            ("La liga calienta motores",
             f"A falta de competición oficial, los clubes de {state.competition} cierran su preparación."),
            ("Últimos días para cerrar la plantilla",
             "El mercado sigue abierto y los clubes valoran sus últimas incorporaciones."),
        ]
        headline, body = rng.choice(preseason)
        add_event(state, day, "Liga", headline, body, league=state.competition, important=False)
        return
    variants = [
        (f"{leader.name} lidera {state.competition}",
         f"El líder suma {leader.points} puntos. {state.user_team.name} es {user_pos}º." + (f" Próximo rival: {rival}." if rival else "")),
        ("La zona alta aprieta",
         f"{leader.name} marca el ritmo y {state.user_team.name} pelea desde la {user_pos}ª plaza."),
        ("La jornada se acerca",
         f"Los clubes de {state.competition} preparan una nueva fecha de liga. El liderato está en juego."),
        ("Parte médico de la liga",
         f"Varios equipos ajustan sus plantillas antes de la próxima jornada de {state.competition}."),
    ]
    headline, body = rng.choice(variants)
    add_event(state, day, "Liga", headline, body, league=state.competition, important=False)

def _other_league_event(state: GameState, day: date, rng: random.Random) -> None:
    other = "DHB" if state.competition == "DHA" else "DHA"
    teams = [t for t in state.teams.values() if t.league == other]
    if not teams:
        return
    team = rng.choice(teams)
    if rng.random() < 0.5:
        headline = f"{team.name} prepara su próximo compromiso"
        body = f"En {other}, el club afina la semana con la vista puesta en la competición."
    else:
        headline = f"Movimiento en {other}: el mercado sigue vivo"
        body = f"{team.name} es uno de los clubes que sigue peinando el mercado en busca de refuerzos."
    add_event(state, day, "Otras ligas", headline, body, league=other, important=False)


def _market_event(state: GameState, day: date, rng: random.Random) -> None:
    teams = [t for t in state.teams.values() if t.league in ("DHA", "DHB") and t.id != state.club_id]
    if not teams:
        return
    team = rng.choice(teams)
    players = [p for p in team.players if p.available]
    if not players:
        return
    player = rng.choice(players)
    add_event(
        state, day, "Mercado",
        f"{team.name} sigue de cerca a {player.name}",
        f"El {player.subposition.lower()} de {player.age} años entra en la lista de clubes que buscan reforzar su plantilla.",
        player_id=player.id, team_id=team.id, league=team.league,
    )


def _injury_event(state: GameState, day: date, rng: random.Random) -> None:
    player = _pick_player(state, rng)
    if not player.available:
        return
    days_out = rng.randint(1, 4)
    player.injury = max(player.injury, days_out)
    player.form = max(1, player.form - 0.4)
    add_event(
        state, day, "Enfermería",
        f"{player.name} sufre una molestia en el entrenamiento",
        f"El cuerpo médico estima {days_out} partido(s) de baja. El jugador trabajará en recuperación.",
        important=True, team_id=state.club_id, player_id=player.id, league=state.competition,
    )


def _training_event(state: GameState, day: date, rng: random.Random) -> None:
    player = _pick_player(state, rng)
    player.form = min(10, player.form + 0.2)
    player.morale = min(20, player.morale + 1)
    add_event(
        state, day, "Entrenamiento",
        f"Buena sesión de {player.name}",
        "El cuerpo técnico destaca su intensidad y su actitud durante el entrenamiento.",
        team_id=state.club_id, player_id=player.id, league=state.competition,
    )


def _club_event(state: GameState, day: date, rng: random.Random) -> None:
    team = state.user_team
    options = [
        ("La afición prepara el próximo partido", f"El club espera un gran ambiente en {team.stadium_name}."),
        ("Reunión de la junta directiva", f"La junta repasa el presupuesto y el objetivo: {team.board_expectation}."),
        ("La cantera vuelve a sonreír", "Los técnicos de la academia destacan el crecimiento de los jóvenes."),
        ("Nueva sesión de video", "El staff prepara el plan táctico para el siguiente rival."),
    ]
    headline, body = rng.choice(options)
    add_event(state, day, "Club", headline, body, team_id=state.club_id, league=state.competition)


def daily_tick(state: GameState, day: date | None = None) -> list[dict[str, Any]]:
    """Genera un día de vida del club. No juega partidos."""
    day = day or date.fromisoformat(state.date)
    rng = _rng(state, day)
    before = len(state.daily_events)

    # Recuperación diaria suave para el usuario.
    for player in state.user_team.players:
        player.fatigue = max(0.0, player.fatigue - 1.2)

    # El mercado se mantiene vivo mientras la ventana esté abierta.
    try:
        from .market import market_window
        if market_window(state) != "cerrado" and rng.random() < 0.22:
            _market_event(state, day, rng)
    except Exception:
        pass

    roll = rng.random()
    if roll < 0.16:
        _injury_event(state, day, rng)
    elif roll < 0.35:
        _training_event(state, day, rng)
    elif roll < 0.55:
        _league_event(state, day, rng)
    elif roll < 0.68:
        _other_league_event(state, day, rng)
    elif roll < 0.82:
        _club_event(state, day, rng)
    elif rng.random() < 0.35:
        _league_event(state, day, rng)

    # Conversaciones de vestuario: no saturamos; como máximo una pendiente.
    unanswered = [m for m in state.chat_messages if not m.get("answered")]
    if len(unanswered) < 2 and rng.random() < 0.24:
        kind = rng.choice(["minutes", "contract", "mood"])
        add_player_chat(state, day, _pick_player(state, rng), kind=kind)

    return state.daily_events[before:]


def next_match_date(state: GameState) -> date | None:
    fixture = state.next_user_fixture()
    if not fixture:
        return None
    return date.fromisoformat(fixture.date)


def simulate_days(state: GameState, target_date: str | date | None = None,
                  days: int = 1, stop_at_match: bool = True) -> dict[str, Any]:
    """Avanza el calendario sin jugar partidos.

    Si se alcanza la fecha del próximo partido, se detiene ahí y devuelve
    ``stopped_at_match=True``. Nunca simula el partido por su cuenta.
    """
    if state.phase != "regular":
        return {"ok": False, "message": "La temporada no está en fase regular.", "days": 0}
    current = date.fromisoformat(state.date)
    match_day = next_match_date(state)
    if target_date:
        target = date.fromisoformat(target_date) if isinstance(target_date, str) else target_date
    else:
        target = current + timedelta(days=max(0, int(days)))
    if target < current:
        return {"ok": False, "message": "La fecha objetivo es anterior a hoy.", "days": 0}

    stopped = False
    if stop_at_match and match_day and target >= match_day:
        target = match_day
        stopped = True

    advanced = 0
    while current < target:
        current += timedelta(days=1)
        state.date = current.isoformat()
        advanced += 1
        if stop_at_match and match_day and current >= match_day:
            break
        daily_tick(state, current)

    hit_match = bool(match_day and date.fromisoformat(state.date) >= match_day and stopped)
    if hit_match:
        has_notice = any(e.get("type") == "matchday" and e.get("date") == state.date for e in state.daily_events[-8:])
        if not has_notice:
            rival = state.next_user_fixture()
            rival_name = ""
            if rival:
                rid = rival.away_id if rival.home_id == state.club_id else rival.home_id
                rival_name = state.teams[rid].name
            add_event(
                state, date.fromisoformat(state.date), "Partido",
                "Hoy hay partido" + (f" contra {rival_name}" if rival_name else ""),
                "El calendario se detiene en la fecha de partido para que prepares el once y decidas cómo jugarlo.",
                important=True, team_id=state.club_id, league=state.competition, kind="matchday",
            )
    return {
        "ok": True, "days": advanced, "date": state.date,
        "stopped_at_match": hit_match, "match_date": match_day.isoformat() if match_day else "",
        "events": state.daily_events[-advanced:] if advanced else [],
    }
