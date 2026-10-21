"""Mercado de fichajes, contratos y contratación de staff (Fase 3A)."""
from __future__ import annotations

import random
import zlib
from typing import Any

from .models import GameState, PlayerState, StaffMember, TeamState

STAFF_LABELS = {
    "head_coach": "Entrenador",
    "assistant": "Segundo entrenador",
    "fitness_coach": "Preparador físico",
    "gk_coach": "Entrenador de porteros",
    "performance_analyst": "Analista de rendimiento",
    "scout": "Ojeador",
    "physio": "Fisioterapeuta",
    "technical_director": "Director deportivo",
    "doctor": "Médico",
    "psychologist": "Psicólogo",
    "delegate": "Delegado",
    "additional": "Staff adicional",
}
STAFF_BASE_SALARY = {
    "head_coach": 60000,
    "assistant": 42000, "fitness_coach": 30000, "gk_coach": 24000,
    "performance_analyst": 26000, "scout": 20000, "physio": 28000,
    "technical_director": 45000,
    "doctor": 26000, "psychologist": 24000, "delegate": 12000, "additional": 15000,
}
STAFF_NAMES = [
    "Jordi Pons", "Marc Ferrer", "Laia Soler", "Pere Roca", "Núria Camps",
    "Xavier Puig", "Marta Vidal", "Oriol Serra", "Anna Bosch", "Pau Mas",
    "Carles Riera", "Elena Font", "Sergi Vidal", "Clara Pujol", "Toni Sala",
]


def market_window(state: GameState) -> str:
    if state.phase != "regular":
        return "cerrado"
    from datetime import date
    today = date.fromisoformat(state.date)
    year = int(state.season[:4])
    if date(year, 8, 1) <= today <= date(year, 9, 30):
        return "verano"
    if date(year + 1, 1, 1) <= today <= date(year + 1, 1, 31):
        return "invierno"
    return "cerrado"


def market_window_text(state: GameState) -> str:
    w = market_window(state)
    if w == "verano":
        return "Mercado de verano abierto"
    if w == "invierno":
        return "Mercado de invierno abierto"
    return "Mercado cerrado"


def _rng(state: GameState, salt: int = 0) -> random.Random:
    return random.Random(state.seed * 1000 + state.round * 71 + salt)


def market_players(state: GameState, limit: int = 40, max_value: int | None = None,
                   position: str | None = None) -> list[PlayerState]:
    pool = [p for t in state.teams.values() if t.league in ("DHA", "DHB")
            for p in t.players if t.id != state.club_id and p.age <= 34]
    pool += [p for p in state.free_agents if p.age <= 34]
    if max_value is not None:
        pool = [p for p in pool if p.value <= max_value]
    if position:
        pool = [p for p in pool if p.subposition == position]
    pool.sort(key=lambda p: (-p.overall, p.name))
    return pool[:limit]


def asking_price(player: PlayerState) -> int:
    return 0 if player.team_name == "Agente libre" else _club_value(player)


def scout_range(player: PlayerState, scout_rating: int) -> str:
    error = max(2, int(13 - scout_rating / 8))
    low = max(1, int(player.overall) - error)
    high = min(99, int(player.overall) + error)
    return f"{low}-{high}"


def _record_partial_career(player: PlayerState, club: TeamState, state: GameState) -> None:
    if not (player.apps or player.season_goals or player.season_assists):
        return
    entry = {
        "season": state.season, "club": club.name, "league": club.league,
        "apps": player.apps, "goals": player.season_goals,
        "assists": player.season_assists, "rating": round(player.rating, 2),
        "overall": round(player.overall, 1), "partial": True,
    }
    player.career = [e for e in player.career
                     if not (e.get("season") == state.season and e.get("club") == club.name)]
    player.career.append(entry)
    player.career = player.career[-30:]


def _contract_until(start_year: int, years: int) -> str:
    return f"{start_year + max(1, years)}-06-30"


def _club_value(player: PlayerState) -> int:
    age_factor = 1.25 if player.age <= 24 else (1.0 if player.age <= 29 else (0.70 if player.age <= 32 else (0.45 if player.age <= 34 else 0.25)))
    base = int((max(1, player.overall - 40) ** 2) * 180 * age_factor)
    return max(int(player.value * 1.10), base, 50000)


def make_transfer_offer(state: GameState, player_id: str, fee: int, salary: int, years: int,
                        rng: random.Random | None = None) -> dict[str, Any]:
    if market_window(state) == "cerrado":
        return {"ok": False, "message": "El mercado está cerrado."}
    buyer = state.user_team
    seller = None
    player = None
    for t in state.teams.values():
        for p in t.players:
            if p.id == player_id:
                seller, player = t, p
                break
        if player:
            break
    free_agent = False
    if not player:
        player = next((p for p in state.free_agents if p.id == player_id), None)
        free_agent = player is not None
    if not player:
        return {"ok": False, "message": "Jugador no encontrado."}
    if seller and seller.id == buyer.id:
        return {"ok": False, "message": "Ese jugador ya es tuyo."}
    if seller and len(seller.players) <= 16:
        return {"ok": False, "message": f"{seller.name} no quiere quedarse sin efectivos."}
    if fee < 0 or salary <= 0 or years < 1:
        return {"ok": False, "message": "Oferta no válida."}
    minimum_salary = int(max(5000, (player.overall - 45) * 900))
    if salary < minimum_salary and not free_agent:
        return {"ok": False, "message": f"{player.name} pide al menos {minimum_salary:,} € de salario.".replace(",", ".")}
    if fee > buyer.transfer_budget:
        return {"ok": False, "message": f"No tienes presupuesto de fichajes suficiente ({fee:,} €).".replace(",", ".")}
    rng = rng or _rng(state, zlib.crc32(player_id.encode("utf-8")) % 1000)
    if not free_agent:
        value = _club_value(player)
        key_threshold = sorted(seller.players, key=lambda p: p.overall, reverse=True)[:3]
        key = player in key_threshold
        seller_prob = 0.35 + (fee / max(1, value) - 1.0) * 0.85 - (0.22 if key else 0.0)
        seller_prob += (buyer.manager_rating - 50) / 250
        seller_prob = max(0.04, min(0.95, seller_prob))
        if rng.random() > seller_prob:
            return {"ok": False, "message": f"{seller.name} rechaza la oferta por {player.name}. Pide más dinero."}
    else:
        fee = 0
    raise_ratio = (salary - player.salary) / max(10000, player.salary)
    player_prob = 0.20 + raise_ratio * 0.55 + (buyer.manager_rating - 50) / 220
    if years >= 3:
        player_prob += 0.08
    if player.age > 31:
        player_prob -= 0.08
    player_prob = max(0.08, min(0.95, player_prob))
    if rng.random() > player_prob:
        return {"ok": False, "message": f"{player.name} rechaza el contrato. Quiere un salario mayor o más años."}
    # traspaso / firma de agente libre
    if free_agent:
        state.free_agents = [p for p in state.free_agents if p.id != player.id]
    else:
        seller.players.remove(player)
    buyer.players.append(player)
    player.team_name = buyer.name
    player.salary = int(salary)
    player.contract_until = _contract_until(int(state.season[:4]), years)
    if seller:
        _record_partial_career(player, seller, state)
    player.apps = player.season_goals = player.season_assists = 0
    player.rating_sum = 0.0
    player.fatigue = 0
    player.injury = 0
    player.suspension = 0
    buyer.transfer_budget -= int(fee)
    if seller:
        seller.budget += int(fee)
    entry = {
        "type": "transferencia", "round": state.round, "season": state.season,
        "player": player.name, "overall": round(player.overall, 1),
        "from": seller.name if seller else "Agente libre", "to": buyer.name, "fee": int(fee), "salary": int(salary),
    }
    state.market_history.append(entry)
    origin = seller.name if seller else "agente libre"
    return {"ok": True, "message": f"Fichado {player.name} ({origin}) por {fee:,} €.".replace(",", "."), "player": player, "entry": entry}


def _ai_market_activity(state: GameState, rng: random.Random) -> None:
    """Movimientos entre clubes IA con presupuesto y salario coherentes."""
    teams = [t for t in state.teams.values() if t.league in ("DHA", "DHB") and t.id != state.club_id]
    if len(teams) < 4:
        return
    for _ in range(3):
        buyer, seller = rng.sample(teams, 2)
        if len(seller.players) <= 17:
            continue
        candidates = [p for p in seller.players if p.overall < max(x.overall for x in seller.players) - 2]
        if not candidates:
            continue
        player = rng.choice(candidates)
        fee = int(_club_value(player) * rng.uniform(0.90, 1.20))
        if buyer.transfer_budget < fee:
            continue
        salary = int(max(player.salary * rng.uniform(1.10, 1.30), (player.overall - 45) * 900))
        seller.players.remove(player)
        buyer.players.append(player)
        player.team_name = buyer.name
        player.salary = salary
        player.contract_until = _contract_until(int(state.season[:4]), rng.randint(2, 4))
        _record_partial_career(player, seller, state)
        buyer.transfer_budget -= fee
        seller.budget += fee
        player.apps = player.season_goals = player.season_assists = 0
        player.rating_sum = 0.0
        player.fatigue = 0
        player.injury = 0
        player.suspension = 0
        state.market_history.append({
            "type": "IA", "round": state.round, "season": state.season,
            "player": player.name, "overall": round(player.overall, 1),
            "from": seller.name, "to": buyer.name, "fee": fee, "salary": salary,
        })


def generate_incoming_offers(state: GameState, rng: random.Random | None = None) -> list[dict]:
    if market_window(state) == "cerrado":
        return state.transfer_offers
    if (state.market_offers_round == state.round
            and state.market_offers_date == state.date
            and state.transfer_offers):
        return state.transfer_offers
    rng = rng or _rng(state, 7)
    if state.market_offers_round != state.round or state.market_offers_date != state.date:
        _ai_market_activity(state, rng)
    user = state.user_team
    candidates = [p for p in user.players if p.age <= 31 and p.perfil in ("Jugador", "Invitado")]
    candidates.sort(key=lambda p: p.overall, reverse=True)
    buyers = [t for t in state.teams.values() if t.league in ("DHA", "DHB") and t.id != user.id]
    offers = []
    for i, p in enumerate(candidates[:4]):
        if rng.random() < 0.35:
            continue
        buyer = rng.choice(buyers)
        fee = int(_club_value(p) * rng.uniform(0.85, 1.25))
        if buyer.transfer_budget < fee:
            continue
        salary = int(max(p.salary * rng.uniform(1.15, 1.55), (p.overall - 45) * 900))
        offers.append({
            "id": f"OF{state.round}-{i+1}", "player_id": p.id, "player_name": p.name,
            "from_club_id": buyer.id, "from_club_name": buyer.name,
            "fee": fee, "salary": salary, "years": rng.randint(2, 4), "status": "pendiente",
        })
    state.transfer_offers = offers
    state.market_offers_round = state.round
    state.market_offers_date = state.date
    return offers


def accept_incoming_offer(state: GameState, offer_id: str) -> dict[str, Any]:
    if market_window(state) == "cerrado":
        return {"ok": False, "message": "El mercado está cerrado."}
    offer = next((o for o in state.transfer_offers if o.get("id") == offer_id), None)
    if not offer:
        return {"ok": False, "message": "Oferta no encontrada."}
    user = state.user_team
    buyer = state.teams.get(offer["from_club_id"])
    player = next((p for p in user.players if p.id == offer["player_id"]), None)
    if not buyer or not player:
        return {"ok": False, "message": "La oferta ya no es válida."}
    if buyer.transfer_budget < int(offer["fee"]):
        return {"ok": False, "message": "El club comprador ya no tiene presupuesto suficiente."}
    user.players.remove(player)
    buyer.players.append(player)
    player.team_name = buyer.name
    player.salary = int(max(offer["salary"], (player.overall - 45) * 900))
    player.contract_until = _contract_until(int(state.season[:4]), int(offer["years"]))
    player.apps = player.season_goals = player.season_assists = 0
    player.rating_sum = 0.0
    buyer.transfer_budget -= int(offer["fee"])
    user.budget += int(offer["fee"])
    state.market_history.append({
        "type": "venta", "round": state.round, "season": state.season,
        "player": player.name, "overall": round(player.overall, 1),
        "from": user.name, "to": buyer.name, "fee": int(offer["fee"]), "salary": int(offer["salary"]),
    })
    state.transfer_offers = [o for o in state.transfer_offers if o.get("id") != offer_id]
    return {"ok": True, "message": f"Vendido {player.name} a {buyer.name} por {offer['fee']:,} €.".replace(",", ".")}


def reject_incoming_offer(state: GameState, offer_id: str) -> None:
    state.transfer_offers = [o for o in state.transfer_offers if o.get("id") != offer_id]


def renew_contract(state: GameState, player_id: str, salary: int, years: int,
                   rng: random.Random | None = None) -> dict[str, Any]:
    team = state.user_team
    player = next((p for p in team.players if p.id == player_id), None)
    if not player:
        return {"ok": False, "message": "Jugador no encontrado."}
    if salary <= 0 or years < 1:
        return {"ok": False, "message": "Contrato no válido."}
    rng = rng or _rng(state, 19)
    raise_ratio = (salary - player.salary) / max(10000, player.salary)
    prob = 0.25 + raise_ratio * 0.65 + (team.morale - 10) / 60
    if years >= 3:
        prob += 0.08
    if player.age > 32:
        prob -= 0.12
    prob = max(0.05, min(0.95, prob))
    if rng.random() > prob:
        return {"ok": False, "message": f"{player.name} rechaza la renovación. Pide más salario o años."}
    player.salary = int(salary)
    player.contract_until = _contract_until(int(state.season[:4]), years)
    state.market_history.append({
        "type": "renovacion", "round": state.round, "season": state.season,
        "player": player.name, "overall": round(player.overall, 1),
        "from": team.name, "to": team.name, "fee": 0, "salary": int(salary),
    })
    return {"ok": True, "message": f"{player.name} renueva hasta {player.contract_until}."}


def staff_candidates(team: TeamState, role: str, rng: random.Random | None = None, count: int = 4) -> list[StaffMember]:
    rng = rng or random.Random(0)
    base = STAFF_BASE_SALARY.get(role, 25000)
    out = []
    for i in range(count):
        rating = max(50, min(85, team.assistant_rating + rng.randint(-9, 9)))
        salary = int(base * (0.75 + rating / 180))
        out.append(StaffMember(role=role, name=rng.choice(STAFF_NAMES), rating=rating,
                               salary=salary, contract_until="2028-06-30",
                               source="modelo", confidence="baja"))
    return out


def hire_staff(state: GameState, candidate: StaffMember) -> dict[str, Any]:
    team = state.user_team
    if any(m.role == candidate.role for m in team.staff):
        return {"ok": False, "message": f"Ya tienes {STAFF_LABELS.get(candidate.role, candidate.role)}."}
    bonus = int(candidate.salary * 0.20)
    if team.budget < bonus:
        return {"ok": False, "message": "No hay caja suficiente para la prima de contratación."}
    team.staff.append(candidate)
    team.budget -= bonus
    if candidate.role == "assistant":
        team.assistant_rating = candidate.rating
    state.market_history.append({
        "type": "staff", "round": state.round, "player": candidate.name,
        "from": "mercado", "to": team.name, "fee": bonus, "salary": candidate.salary,
    })
    return {"ok": True, "message": f"Contratado {candidate.name} como {STAFF_LABELS.get(candidate.role, candidate.role)}."}


def fire_staff(state: GameState, role: str) -> dict[str, Any]:
    team = state.user_team
    member = next((m for m in team.staff if m.role == role), None)
    if not member:
        return {"ok": False, "message": "No hay nadie en ese rol."}
    compensation = int(member.salary * 0.50)
    if team.budget < compensation:
        return {"ok": False, "message": "No hay caja suficiente para la indemnización."}
    team.staff.remove(member)
    team.budget -= compensation
    if role == "assistant":
        team.assistant_rating = 55
    state.market_history.append({
        "type": "despido", "round": state.round, "player": member.name,
        "from": team.name, "to": "libre", "fee": compensation, "salary": 0,
    })
    return {"ok": True, "message": f"Despedido {member.name}. Indemnización: {compensation:,} €.".replace(",", ".")}
