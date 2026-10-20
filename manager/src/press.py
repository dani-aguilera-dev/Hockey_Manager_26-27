"""Ruedas de prensa sencillas: preguntas, respuestas y efectos."""
from __future__ import annotations

import random

from .models import GameState

QUESTIONS = [
    {
        "id": "partido",
        "question": "¿Cómo afrontáis el próximo partido?",
        "options": [
            ("Vamos a por la victoria", {"morale": 1, "fan": 1, "board": 0}, "El equipo se crece ante la prensa."),
            ("Respetamos mucho al rival", {"morale": 0, "fan": 0, "board": 1}, "Mensaje prudente y profesional."),
            ("Es una final para nosotros", {"morale": 1, "fan": 1, "board": -1}, "La afición responde, la junta frunce el ceño."),
        ],
    },
    {
        "id": "presion",
        "question": "¿Siente presión por los resultados?",
        "options": [
            ("Asumo toda la responsabilidad", {"morale": 0, "fan": 1, "board": 2}, "La junta valora tu compromiso."),
            ("El equipo está conmigo", {"morale": 1, "fan": 1, "board": -1}, "El grupo agradece tu defensa."),
            ("Pensamos en el proceso", {"morale": 0, "fan": -1, "board": 1}, "Discurso de proyecto; parte de la afición duda."),
        ],
    },
]


def press_questions(state: GameState) -> list[dict]:
    rival = "el próximo rival"
    if state.fixtures:
        fx = state.next_user_fixture()
        if fx:
            opp_id = fx.away_id if fx.home_id == state.club_id else fx.home_id
            rival = state.teams.get(opp_id).name if opp_id in state.teams else rival
    qs = []
    for q in QUESTIONS:
        qq = dict(q)
        if q["id"] == "partido":
            qq["question"] = f"¿Cómo afrontáis el partido contra {rival}?"
        qs.append(qq)
    return qs


def answer_press(state: GameState, question_id: str, option_index: int) -> dict:
    q = next((x for x in press_questions(state) if x["id"] == question_id), None)
    if not q or not (0 <= option_index < len(q["options"])):
        return {"ok": False, "message": "Respuesta no válida."}
    label, effects, headline = q["options"][option_index]
    team = state.user_team
    team.morale = max(1, min(20, team.morale + effects.get("morale", 0)))
    team.fan_confidence = max(0, min(100, team.fan_confidence + effects.get("fan", 0)))
    team.board_confidence = max(0, min(100, team.board_confidence + effects.get("board", 0)))
    state.press_history.append({
        "round": state.round, "question": q["question"], "answer": label, "headline": headline,
    })
    state.press_history = state.press_history[-30:]
    return {"ok": True, "message": headline, "effects": effects}


def mark_press_done(state: GameState) -> None:
    state.press_done_round = state.round
