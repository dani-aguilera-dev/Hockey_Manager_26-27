"""Mercado de fichajes, contratos y contratación de staff (Fase 3A)."""
from __future__ import annotations

import random
import zlib
from typing import Any

from .models import GameState, PlayerState, StaffMember, TeamState

STAFF_LABELS = {
    "assistant": "Segundo entrenador",
    "fitness_coach": "Preparador físico",
    "gk_coach": "Entrenador de porteros",
    "performance_analyst": "Analista de rendimiento",
    "scout": "Ojeador",
    "physio": "Fisioterapeuta",
    "technical_director": "Director deportivo",
}
STAFF_BASE_SALARY = {
    "assistant": 42000, "fitness_coach": 30000, "gk_coach": 24000,
    "performance_analyst": 26000, "scout": 20000, "physio": 28000,
    "technical_director": 45000,
}
STAFF_NAMES = [
    "Jordi Pons", "Marc Ferrer", "Laia Soler", "Pere Roca", "Núria Camps",
    "Xavier Puig", "Marta Vidal", "Oriol Serra", "Anna Bosch", "Pau Mas",
    "Carles Riera", "Elena Font", "Sergi Vidal", "Clara Pujol", "Toni Sala",
]


def market_window(state: GameState) -> str:
    if state.phase != "regular":
        return "cerrado"
    played = any(f.phase == "regular" and f.played for f in state.fixtures)
    if state.round == 1 and not played:
        return "verano"
    round_fixtures = [f for f in state.fixtures if f.phase == "regular" and f.round == state.round]
    if state.round == 12 and round_fixtures and not any(f.played for f in round_fixtures):
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
    if max_value is not None:
        pool = [p for p in pool if p.value <= max_value]
    if position:
        pool = [p for p in pool if p.subposition == position]
    pool.sort(key=lambda p: (-p.overall, p.name))
    return pool[:limit]


def asking_price(player: PlayerState) -> int:
    return _club_value(player)


def scout_range(player: PlayerState, scout_rating: int) -> str:
    error = max(2, int(13 - scout_rating / 8))
    low = max(1, int(player.overall) - error)
    high = min(99, int(player.overall) + error)
    return f"{low}-{high}"


def _contract_until(start_year: int, years: int) -> str:
    return f"{start_year + max(1, years)}-06-30"


def _club_value(player: PlayerState) -> int:
    return max(int(player.value * 0.70), int((max(1, player.overall - 40) ** 2) * 120))


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
    if not player or not seller:
        return {"ok": False, "message": "Jugador no encontrado."}
    if seller.id == buyer.id:
        return {"ok": False, "message": "Ese jugador ya es tuyo."}
    if len(seller.players) <= 16:
        return {"ok": False, "message": f"{seller.name} no quiere quedarse sin efectivos."}
    if fee < 0 or salary <= 0 or years < 1:
        return {"ok": False, "message": "Oferta no válida."}
    if fee > buyer.transfer_budget:
        return {"ok": False, "message": f"No tienes presupuesto de fichajes suficiente ({fee:,} €).".replace(",", ".")}
    value = _club_value(player)
    key_threshold = sorted(seller.players, key=lambda p: p.overall, reverse=True)[:3]
    key = player in key_threshold
    seller_prob = 0.35 + (fee / max(1, value) - 1.0) * 0.85 - (0.22 if key else 0.0)
    seller_prob += (buyer.manager_rating - 50) / 250
    seller_prob = max(0.04, min(0.95, seller_prob))
    rng = rng or _rng(state, zlib.crc32(player_id.encode("utf-8")) % 1000)
    if rng.random() > seller_prob:
        return {"ok": False, "message": f"{seller.name} rechaza la oferta por {player.name}. Pide más dinero."}
    raise_ratio = (salary - player.salary) / max(10000, player.salary)
    player_prob = 0.20 + raise_ratio * 0.55 + (buyer.manager_rating - 50) / 220
    if years >= 3:
        player_prob += 0.08
    if player.age > 31:
        player_prob -= 0.08
    player_prob = max(0.08, min(0.95, player_prob))
    if rng.random() > player_prob:
        return {"ok": False, "message": f"{player.name} rechaza el contrato. Quiere un salario mayor o más años."}
    # traspaso
    seller.players.remove(player)
    buyer.players.append(player)
    player.team_name = buyer.name
    player.salary = int(salary)
    player.contract_until = _contract_until(int(state.season[:4]), years)
    player.apps = player.season_goals = player.season_assists = 0
    player.rating_sum = 0.0
    player.fatigue = 0
    player.injury = 0
    player.suspension = 0
    buyer.transfer_budget -= int(fee)
    seller.budget += int(fee)
    entry = {
        "type": "transferencia", "round": state.round, "player": player.name,
        "from": seller.name, "to": buyer.name, "fee": int(fee), "salary": int(salary),
    }
    state.market_history.append(entry)
    return {"ok": True, "message": f"Fichado {player.name} de {seller.name} por {fee:,} €.".replace(",", "."), "player": player, "entry": entry}


def _ai_market_activity(state: GameState, rng: random.Random) -> None:
    """Movimientos sencillos entre clubes IA para que el mercado no sea solo del usuario."""
    teams = [t for t in state.teams.values() if t.league in ("DHA", "DHB") and t.id != state.club_id]
    if len(teams) < 4:
        return
    for _ in range(2):
        buyer, seller = rng.sample(teams, 2)
        if len(seller.players) <= 17:
            continue
        candidates = [p for p in seller.players if p.overall < max(x.overall for x in seller.players) - 2]
        if not candidates:
            continue
        player = rng.choice(candidates)
        fee = int(_club_value(player) * rng.uniform(0.75, 1.15))
        seller.players.remove(player)
        buyer.players.append(player)
        player.team_name = buyer.name
        player.salary = int(player.salary * rng.uniform(1.05, 1.25))
        seller.budget += fee
        player.apps = player.season_goals = player.season_assists = 0
        player.rating_sum = 0.0
        state.market_history.append({
            "type": "IA", "round": state.round, "player": player.name,
            "from": seller.name, "to": buyer.name, "fee": fee, "salary": player.salary,
        })


def generate_incoming_offers(state: GameState, rng: random.Random | None = None) -> list[dict]:
    if market_window(state) == "cerrado":
        return state.transfer_offers
    if state.market_offers_round == state.round and state.transfer_offers:
        return state.transfer_offers
    rng = rng or _rng(state, 7)
    if state.market_offers_round != state.round:
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
        salary = int(p.salary * rng.uniform(1.15, 1.55))
        offers.append({
            "id": f"OF{state.round}-{i+1}", "player_id": p.id, "player_name": p.name,
            "from_club_id": buyer.id, "from_club_name": buyer.name,
            "fee": fee, "salary": salary, "years": rng.randint(2, 4), "status": "pendiente",
        })
    state.transfer_offers = offers
    state.market_offers_round = state.round
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
    user.players.remove(player)
    buyer.players.append(player)
    player.team_name = buyer.name
    player.salary = int(offer["salary"])
    player.contract_until = _contract_until(int(state.season[:4]), int(offer["years"]))
    player.apps = player.season_goals = player.season_assists = 0
    player.rating_sum = 0.0
    user.budget += int(offer["fee"])
    state.market_history.append({
        "type": "venta", "round": state.round, "player": player.name,
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
        "type": "renovacion", "round": state.round, "player": player.name,
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
