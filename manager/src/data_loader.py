"""Carga de clubes, ciudades y jugadores para el Hockey Manager."""
from __future__ import annotations

import csv, json, re, unicodedata
from pathlib import Path
from .models import PlayerState, TeamState, Tactics, StaffMember, BoardMember

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "manager" / "data"
TOOLS = BASE / "tools"


def norm(s: str) -> str:
    s = str(s or "").upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return " ".join(s.split())


def slug(s: str) -> str:
    s = norm(s).lower().replace(" ", "-")
    return re.sub(r"-+", "-", s).strip("-")


def load_json(name: str):
    return json.load(open(DATA / name, encoding="utf-8"))


def load_clubs() -> tuple[dict[str, dict], dict[str, dict]]:
    clubs = load_json("clubs.json")
    cities = load_json("cities.json")
    clubs_by_id = {c["id"]: c for c in clubs}
    cities_by_name = {norm(c["name"]): c for c in cities}
    return clubs_by_id, cities_by_name


def _club_for_team(team_name: str, clubs_by_id: dict[str, dict]) -> dict | None:
    target = norm(team_name)
    for c in clubs_by_id.values():
        if norm(c["name"]) == target or norm(c["full_name"]) == target:
            return c
    # alias manuales
    aliases = {
        "CD TERRASSA HOCKEY": "cd-terrassa",
        "REAL CLUB DE CAMPO VILLA DE MADRID": "rc-de-campo",
        "SANSE COMPLUTENSE": "sanse-complutense",
        "SARDINERO HOCKEY CLUB": "sardinero",
        "RS TENIS": "rs-tenis",
        "UD TABURIENTE": "ud-taburiente",
        "JUNIOR FC": "junior-fc",
        "CLUB EGARA": "club-egara",
        "RC POLO": "rc-polo",
        "ATLÈTIC TERRASSA HC": "atletic-terrassa",
        "CH CARPESA": "ch-carpesa",
        "FC BARCELONA": "fc-barcelona",
        "AD RIMAS": "ad-rimas",
        "CASTELLDEFELS HC": "castelldefels",
        "CD GINER DE LOS RÍOS": "cd-giner",
        "CLUB HOCKEY MADRID - LAS ROZAS": "ch-madrid-las-rozas",
        "EGARA 1935": "egara-1935",
        "HC SANT CUGAT": "hc-sant-cugat",
        "ILURO HC": "iluro",
        "LÍNIA 22 STERN MOTOR": "linia-22",
        "PEDRALBES HC": "pedralbes",
        "RC JOLASETA": "rc-jolaseta",
        "POZUELO": "pozuuelo",
        "REAL SOCIEDAD 1927": "real-sociedad-1927",
        "SPV": "spv",
        "UNIVERSITAT D'ALACANT - SAN VICENTE": "universitat-alacant",
        "VALLES ESPORTIU": "valles-esportiu",
        "ATICOS INMOBILIARIA CH SAN FERNANDO": "aticos-san-fernando",
        "CLUB DE HOCKEY SAN FERNANDO": "san-fernando-andaluza",
    }
    cid = aliases.get(target)
    return clubs_by_id.get(cid) if cid else None


def load_teams() -> tuple[dict[str, TeamState], dict[str, dict], dict[str, dict]]:
    clubs_by_id, cities_by_name = load_clubs()
    staff_path = DATA / "staff_dha.json"
    staff_by_club = json.load(open(staff_path, encoding="utf-8")) if staff_path.exists() else {}
    rows = list(csv.DictReader(open(TOOLS / "player_attributes_v2.csv", encoding="utf-8-sig")))
    by_team: dict[str, list[dict]] = {}
    for r in rows:
        by_team.setdefault(str(r.get("equipo", "")).strip(), []).append(r)
    teams: dict[str, TeamState] = {}
    for team_name, team_rows in by_team.items():
        club = _club_for_team(team_name, clubs_by_id)
        if not club:
            continue
        players: list[PlayerState] = []
        seen: dict[str, int] = {}
        for i, r in enumerate(team_rows):
            name = str(r.get("jugador", "")).strip()
            key = slug(name)
            seen[key] = seen.get(key, 0) + 1
            pid = f"{club['id']}-{key}-{seen[key]}"
            attrs = {}
            for k, v in r.items():
                if k.startswith("attr_"):
                    try:
                        attrs[k[5:]] = int(float(v or 50))
                    except Exception:
                        attrs[k[5:]] = 50
            try:
                overall = float(r.get("overall") or 0)
            except Exception:
                overall = 0.0
            try:
                potential = float(r.get("potential") or overall)
            except Exception:
                potential = overall
            try:
                value = int(float(r.get("value") or 0))
            except Exception:
                value = 0
            try:
                goals = int(float(r.get("goles") or 0))
            except Exception:
                goals = 0
            try:
                age = int(float(r.get("edad") or 0))
            except Exception:
                age = 0
            overalls = {}
            for pos, col in [("Portero", "overall_portero"), ("Central", "overall_central"), ("Lateral", "overall_lateral"), ("Medio", "overall_medio"), ("Delantero", "overall_delantero")]:
                try:
                    overalls[pos] = float(r.get(col) or 0)
                except Exception:
                    overalls[pos] = 0.0
            try:
                poly = float(r.get("polivalencia") or 0)
            except Exception:
                poly = 0.0
            players.append(PlayerState(
                id=pid, name=name, team_name=club["name"],
                position_group=str(r.get("position_group") or r.get("pos") or "Medio"),
                subposition=str(r.get("subposicion") or r.get("pos") or "Medio"),
                age=age, overall=overall, potential=potential, attributes=attrs,
                archetype=str(r.get("archetype") or "Jugador"),
                perfil=str(r.get("perfil") or "Jugador"),
                goals_isquad=goals, value=value, polivalencia=poly, overalls=overalls,
            ))
        fin = club.get("finances", {})
        stadium = club.get("stadium", {})
        fac = club.get("facilities", {})
        assistant_rating = 50 + int(fac.get("academy", 0) or 0) * 4
        assistant_rating += 5 if fac.get("video") else 0
        assistant_rating += 3 if fac.get("medical") else 0
        assistant_rating = max(45, min(85, assistant_rating))
        staff_rows = staff_by_club.get(club["id"], {}).get("staff", [])
        staff = [StaffMember(**{k: v for k, v in row.items() if k in StaffMember.__dataclass_fields__}) for row in staff_rows]
        board = [BoardMember(**{k: v for k, v in row.items() if k in BoardMember.__dataclass_fields__}) for row in staff_by_club.get(club["id"], {}).get("board", [])]
        if staff:
            assistant = next((m for m in staff if m.role == "assistant"), None)
            if assistant:
                assistant_rating = assistant.rating
        wage_budget = int(fin.get("wage_budget", 0) or 0)
        # Reparto salarial proporcional al nivel de los jugadores.
        if players and wage_budget:
            weights = [max(1.0, p.overall - 40.0) ** 2 for p in players]
            total_w = sum(weights)
            assigned = 0
            for i, (p, w) in enumerate(zip(players, weights)):
                if i == len(players) - 1:
                    p.salary = max(0, wage_budget - assigned)
                else:
                    p.salary = int(wage_budget * w / total_w)
                    assigned += p.salary
        transfer_budget = int(fin.get("transfer_budget", 0) or 0)
        cash = transfer_budget + int(wage_budget * 0.45)
        teams[club["id"]] = TeamState(
            id=club["id"], name=club["name"], league=club["league"], city=club["city"],
            players=players, tactics=Tactics(),
            stadium_name=stadium.get("name", ""),
            stadium_capacity=int(stadium.get("capacity", 1000) or 1000),
            board_expectation=club.get("board", {}).get("expectation", ""),
            preferred_mode=club.get("logistics", {}).get("preferred_mode", ""),
            assistant_rating=assistant_rating,
            staff=staff, board=board,
            transfer_budget=transfer_budget, club_tier=int(fin.get("tier", 3) or 3),
            budget=cash, wage_budget=wage_budget,
        )
    return teams, clubs_by_id, cities_by_name


def dha_teams(teams: dict[str, TeamState]) -> list[TeamState]:
    return [t for t in teams.values() if t.league == "DHA"]
