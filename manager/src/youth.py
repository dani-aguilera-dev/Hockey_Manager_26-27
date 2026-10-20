"""Cantera: generación, desarrollo y promoción de juveniles."""
from __future__ import annotations

import random
import zlib

from .models import PlayerState, TeamState

YOUTH_NAMES = ["Aleix", "Pau", "Marc", "Nil", "Joan", "Biel", "Iker", "Hugo", "Adrià", "Pol",
               "Leo", "Arnau", "Jan", "Roc", "Oriol", "Dani", "Bruno", "Álex", "Gonzalo", "Mateo"]
YOUTH_SURNAMES = ["Serra", "Pujol", "Vidal", "Roca", "Camps", "Ferrer", "Soler", "Mas", "Bosch", "Riera",
                  "Font", "Puig", "Sala", "Vila", "Costa", "Moya", "Navarro", "García", "López", "Martín"]
KEYS = ["control", "pase", "conduccion", "golpeo", "flick", "regate_3d", "definicion",
        "aerial", "pc_injection", "pc_trap", "pc_flick", "pc_deflection", "pc_first_runner",
        "pc_gk_save", "stroke_shot", "stroke_save", "free_hit", "posicionamiento", "pressing",
        "cobertura", "transicion", "desmarque", "velocidad", "resistencia", "fuerza", "agilidad",
        "coordinacion", "decisiones", "concentracion", "competitividad", "liderazgo", "reflejos",
        "blocaje", "distribucion", "uno_vs_uno", "alto", "rebote_gk"]


def generate_youth(team: TeamState, rng: random.Random, year: int, seq: int, age: int | None = None) -> PlayerState:
    pos = rng.choice(["Portero", "Central", "Lateral", "Medio", "Delantero"])
    group = "Portero" if pos == "Portero" else ("Defensa" if pos in ("Central", "Lateral") else pos)
    academy = team.academy_rating
    base = 38 + int(academy / 8)
    attrs = {k: max(30, min(72, base + rng.randint(-8, 10))) for k in KEYS}
    overall = round(max(42.0, min(66.0, base + rng.uniform(-3, 6))), 1)
    potential = round(min(88.0, overall + rng.uniform(10, 24) + academy / 10), 1)
    name = f"{rng.choice(YOUTH_NAMES)} {rng.choice(YOUTH_SURNAMES)}"
    return PlayerState(
        id=f"{team.id}-youth-{year}-{seq}", name=name, team_name=team.name,
        position_group=group, subposition=pos, age=age or rng.randint(16, 18),
        overall=overall, potential=potential, attributes=attrs,
        archetype="Canterano", perfil="Canterano", goals_isquad=0,
        value=int(overall * 4000), polivalencia=0.0,
        salary=int(rng.uniform(5000, 10000)), contract_until=f"{year + 3}-06-30",
    )


def initial_youth(teams: dict[str, TeamState], seed: int, count: int = 4) -> None:
    for team in teams.values():
        if team.league not in ("DHA", "DHB"):
            continue
        rng = random.Random(seed + zlib.crc32(team.id.encode("utf-8")) % 10000)
        team.youth = [generate_youth(team, rng, 2026, i + 1) for i in range(count)]


def develop_youth(team: TeamState, rng: random.Random, new_year: int) -> None:
    kept = []
    for p in team.youth:
        p.age += 1
        if p.age >= 21:
            continue
        gains = 0
        for k in rng.sample(KEYS, 4):
            chance = 0.18 + (team.academy_rating - 50) / 250 + max(0, p.potential - p.overall) / 100
            if rng.random() < chance:
                p.attributes[k] = min(99, p.attributes.get(k, 40) + 1)
                gains += 1
        p.overall = round(min(p.potential, p.overall + gains * 0.04 + rng.uniform(0.0, 0.25)), 1)
        kept.append(p)
    team.youth = kept


def intake(team: TeamState, rng: random.Random, new_year: int, count: int = 3) -> None:
    for i in range(count):
        if len(team.youth) >= 9:
            break
        team.youth.append(generate_youth(team, rng, new_year, len(team.youth) + i + 1, age=rng.randint(16, 17)))


def promote_youth(team: TeamState, player_id: str) -> tuple[bool, str]:
    p = next((x for x in team.youth if x.id == player_id), None)
    if not p:
        return False, "Jugador no encontrado en la cantera."
    team.youth.remove(p)
    p.perfil = "Jugador"
    p.team_name = team.name
    team.players.append(p)
    return True, f"{p.name} sube al primer equipo."


def release_youth(team: TeamState, player_id: str) -> tuple[bool, str]:
    p = next((x for x in team.youth if x.id == player_id), None)
    if not p:
        return False, "Jugador no encontrado."
    team.youth.remove(p)
    return True, f"{p.name} deja la cantera."
