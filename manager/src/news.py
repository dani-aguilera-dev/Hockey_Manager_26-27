"""Noticias generadas a partir del estado del juego (sin datos externos)."""
from __future__ import annotations

from typing import Any

from .models import GameState


def _form(state: GameState) -> str:
    played = [f for f in state.fixtures if f.phase == "regular" and f.played and state.club_id in (f.home_id, f.away_id)]
    played.sort(key=lambda f: f.round)
    out = []
    for f in played[-5:]:
        gf = f.home_goals if f.home_id == state.club_id else f.away_goals
        ga = f.away_goals if f.home_id == state.club_id else f.home_goals
        out.append("V" if gf > ga else ("E" if gf == ga else "D"))
    return " ".join(out) if out else "sin partidos"


def news_feed(state: GameState, limit: int = 8) -> list[dict[str, Any]]:
    user = state.user_team
    table = state.table()
    pos = next((i for i, t in enumerate(table, 1) if t.id == user.id), 0)
    items: list[dict[str, Any]] = []
    fx = state.next_user_fixture()
    if fx:
        home = state.teams[fx.home_id]
        away = state.teams[fx.away_id]
        rival = away if home.id == user.id else home
        venue = "en casa" if home.id == user.id else "a domicilio"
        items.append({
            "category": "Previa", "hot": True,
            "headline": f"{user.name} y {rival.name} miden su momento",
            "body": f"Jornada {fx.round} · {fx.date}. El equipo llega {venue} con forma {_form(state)} y es {pos}º en {state.competition}.",
            "date": fx.date, "crest_id": user.id, "crest_id2": rival.id,
        })
    if state.last_result:
        p = state.last_result
        items.append({
            "category": "Resultado",
            "headline": f"{p.get('home_name','')} {p.get('home_goals',0)}-{p.get('away_goals',0)} {p.get('away_name','')}",
            "body": f"{p.get('result','')} para el equipo. {p.get('user_goals',0)} goles a favor y {p.get('user_against',0)} en contra.",
            "date": p.get("date", state.date), "crest_id": state.club_id,
        })
    if table:
        leader = table[0]
        items.append({
            "category": "Liga",
            "headline": f"{leader.name} manda en {state.competition}",
            "body": f"{leader.points} puntos y {leader.goals_for - leader.goals_against:+d} de diferencia. Tu equipo es {pos}º con {user.points}.",
            "date": state.date, "crest_id": leader.id,
        })
    if state.transfer_offers:
        o = state.transfer_offers[0]
        items.append({
            "category": "Mercado",
            "headline": f"{o['from_club_name']} pregunta por {o['player_name']}",
            "body": f"Oferta de {o['fee']:,} € y salario de {o['salary']:,} €. La pelota está en tu tejado.".replace(",", "."),
            "date": state.date, "photo": next((p.photo for p in user.players if p.id == o.get("player_id")), ""),
        })
    else:
        items.append({
            "category": "Mercado",
            "headline": f"{len(state.free_agents)} agentes libres buscan equipo",
            "body": "El mercado sigue abierto. Hay perfiles de todas las posiciones esperando una llamada; el ojeador puede filtrar por precio y encaje.",
            "date": state.date,
        })
    if state.market_history:
        e = state.market_history[-1]
        items.append({
            "category": "Mercado",
            "headline": f"{e.get('player','Un jugador')} cambia de club",
            "body": f"{e.get('from','')} → {e.get('to','')}. {e.get('fee',0):,} € de traspaso.".replace(",", "."),
            "date": state.date,
        })
    injured = [p for p in user.players if p.injury > 0]
    if injured:
        p = injured[0]
        items.append({
            "category": "Enfermería",
            "headline": f"{p.name} estará {p.injury} partido(s) de baja",
            "body": f"El cuerpo médico trabaja para recuperar al jugador. La plantilla pierde profundidad.",
            "date": state.date,
        })
    if user.youth:
        best = max(user.youth, key=lambda p: p.potential)
        items.append({
            "category": "Cantera",
            "headline": f"{best.name}, la perla que empuja desde abajo",
            "body": f"{best.subposition} de {best.age} años · overall {best.overall:.1f} · potencial {best.potential:.1f}. La academia está en {user.academy_rating}/100.",
            "date": state.date,
        })
    if fx:
        home = state.teams[fx.home_id]
        away = state.teams[fx.away_id]
        rival = away if home.id == user.id else home
        items.append({
            "category": "Scouting",
            "headline": f"Cómo juega {rival.name}",
            "body": f"Sale con {rival.tactics.formation}, mentalidad {rival.tactics.mentality.replace('_', ' ')} y presión {rival.tactics.press}. Moral {rival.morale}/20 y cohesión {rival.cohesion}/20.",
            "date": state.date, "crest_id": rival.id,
        })
    items.append({
        "category": "Afición",
        "headline": f"{user.stadium_name} vuelve a latir",
        "body": f"El club espera un ambiente especial en el próximo partido. La masa social y la grada pueden empujar al equipo en los minutos finales.",
        "date": state.date, "crest_id": user.id,
    })
    items.append({
        "category": "Club",
        "headline": f"La junta mantiene la confianza en {user.name}",
        "body": f"Confianza {user.board_confidence}/100 · presión {user.board_pressure} · paciencia {user.board_patience}/5. Objetivo: {user.board_expectation}.",
        "date": state.date, "crest_id": user.id,
    })
    if state.cup_active:
        items.append({
            "category": "Copa",
            "headline": "La Copa del Rey entra en escena",
            "body": "Los ocho mejores de DHA se citan en un fin de semana de eliminatorias a partido único.",
            "date": state.date,
        })
    return items[:limit]
