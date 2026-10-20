"""Finanzas de club: salarios, patrocinio, taquilla y viajes."""
from __future__ import annotations

from typing import Any


def sponsor_income(team) -> int:
    """Ingreso estimado de patrocinio por jornada."""
    annual = team.wage_budget * (0.55 + max(1, team.club_tier) * 0.04)
    return int(max(0, annual) / 22)


def round_wage_cost(team) -> tuple[int, int]:
    """Salarios de jugadores y staff por jornada."""
    players = int(team.player_wage_bill() / 22)
    staff = int(team.staff_wage_bill() / 22)
    return players, staff


def apply_round_finances(state: Any) -> None:
    """Cierra las cuentas de la jornada actual para los clubes DHA."""
    if getattr(state, "finance_round", 0) == state.round:
        return
    for team in state.teams.values():
        if team.league != "DHA":
            continue
        fixtures = [f for f in state.fixtures if f.phase == "regular" and f.round == state.round and f.played]
        gate = sum(int(f.home_stats.get("gate_revenue", 0)) for f in fixtures if f.home_id == team.id)
        travel = sum(int((f.travel or {}).get("cost", 0)) for f in fixtures if f.away_id == team.id)
        sponsor = sponsor_income(team)
        player_wages, staff_wages = round_wage_cost(team)
        wages = player_wages + staff_wages
        team.budget += sponsor - wages
        entry = {
            "round": state.round,
            "gate": gate,
            "sponsor": sponsor,
            "player_wages": player_wages,
            "staff_wages": staff_wages,
            "wages": wages,
            "travel": travel,
            "net": gate + sponsor - wages - travel,
            "cash_after": team.budget,
        }
        team.finance_log.append(entry)
        team.finance_log = team.finance_log[-30:]
        if team.id == state.club_id and team.budget < 0:
            team.board_confidence = max(0, team.board_confidence - 3)
            team.fan_confidence = max(0, team.fan_confidence - 1)
    state.finance_round = state.round


def financial_summary(team) -> dict:
    log = team.finance_log
    gate = sum(int(e.get("gate", 0)) for e in log)
    sponsor = sum(int(e.get("sponsor", 0)) for e in log)
    player_wages = sum(int(e.get("player_wages", 0)) for e in log)
    staff_wages = sum(int(e.get("staff_wages", 0)) for e in log)
    travel = sum(int(e.get("travel", 0)) for e in log)
    income = gate + sponsor
    expenses = player_wages + staff_wages + travel
    return {
        "cash": team.budget,
        "transfer_budget": team.transfer_budget,
        "player_wage_bill": team.player_wage_bill(),
        "staff_wage_bill": team.staff_wage_bill(),
        "annual_wage_bill": team.player_wage_bill() + team.staff_wage_bill(),
        "round_player_wages": int(team.player_wage_bill() / 22),
        "round_staff_wages": int(team.staff_wage_bill() / 22),
        "sponsor_round": sponsor_income(team),
        "gate": gate,
        "sponsor": sponsor,
        "player_wages": player_wages,
        "staff_wages": staff_wages,
        "travel": travel,
        "income": income,
        "expenses": expenses,
        "net": income - expenses,
        "entries": log[-6:],
    }
