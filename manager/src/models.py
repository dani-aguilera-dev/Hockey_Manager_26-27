"""Modelos de datos del Hockey Manager (Fase 1)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

SLOT_TO_SUB = {
    "POR": "Portero",
    "CEN": "Central",
    "LAT": "Lateral",
    "MED": "Medio",
    "DEL": "Delantero",
}

FORMATION_SLOTS = {
    "4-3-3": ["POR", "LAT", "CEN", "CEN", "LAT", "MED", "MED", "MED", "DEL", "DEL", "DEL"],
    "3-4-3": ["POR", "CEN", "CEN", "CEN", "LAT", "MED", "MED", "LAT", "DEL", "DEL", "DEL"],
    "3-3-3-1": ["POR", "CEN", "CEN", "CEN", "LAT", "MED", "MED", "LAT", "MED", "DEL", "DEL"],
    "4-4-2": ["POR", "LAT", "CEN", "CEN", "LAT", "MED", "MED", "MED", "MED", "DEL", "DEL"],
    "5-3-2": ["POR", "LAT", "CEN", "CEN", "CEN", "LAT", "MED", "MED", "MED", "DEL", "DEL"],
    "3-2-1-4": ["POR", "CEN", "CEN", "CEN", "MED", "MED", "MED", "DEL", "DEL", "DEL", "DEL"],
}

TACTIC_MODS = {
    "mentality": {
        "muy_defensiva": (-0.15, 0.15),
        "defensiva": (-0.08, 0.08),
        "equilibrada": (0.0, 0.0),
        "ofensiva": (0.08, -0.08),
        "muy_ofensiva": (0.15, -0.15),
    },
    "press": {
        "baja": (-0.05, -0.10, -0.05),
        "media": (0.0, 0.0, 0.0),
        "alta": (0.05, 0.08, 0.08),
        "muy_alta": (0.10, 0.12, 0.15),
    },
    "tempo": {
        "lento": (-0.05, 0.03, -0.03),
        "normal": (0.0, 0.0, 0.0),
        "rapido": (0.08, -0.03, 0.05),
    },
    "block": {
        "bajo": (-0.03, 0.05),
        "medio": (0.0, 0.0),
        "alto": (0.04, -0.03),
    },
    "width": {
        "estrecha": (-0.01, 0.02),
        "normal": (0.0, 0.0),
        "ancha": (0.02, -0.01),
    },
    "passing": {
        "corto": (-0.02, 0.02),
        "mixto": (0.0, 0.0),
        "directo": (0.03, -0.02),
    },
}


@dataclass
class Tactics:
    formation: str = "4-3-3"
    mentality: str = "equilibrada"
    press: str = "media"
    block: str = "medio"
    width: str = "normal"
    tempo: str = "normal"
    passing: str = "mixto"
    pc_routine: str = "directa"

    def attack_mod(self) -> float:
        return (
            TACTIC_MODS["mentality"].get(self.mentality, (0, 0))[0]
            + TACTIC_MODS["press"].get(self.press, (0, 0, 0))[0]
            + TACTIC_MODS["tempo"].get(self.tempo, (0, 0, 0))[0]
            + TACTIC_MODS["block"].get(self.block, (0, 0))[0]
            + TACTIC_MODS["width"].get(self.width, (0, 0))[0]
            + TACTIC_MODS["passing"].get(self.passing, (0, 0))[0]
        )

    def defense_mod(self) -> float:
        return (
            TACTIC_MODS["mentality"].get(self.mentality, (0, 0))[1]
            + TACTIC_MODS["press"].get(self.press, (0, 0, 0))[1]
            + TACTIC_MODS["tempo"].get(self.tempo, (0, 0, 0))[1]
            + TACTIC_MODS["block"].get(self.block, (0, 0))[1]
            + TACTIC_MODS["width"].get(self.width, (0, 0))[1]
            + TACTIC_MODS["passing"].get(self.passing, (0, 0))[1]
        )

    def fatigue_mod(self) -> float:
        return TACTIC_MODS["press"].get(self.press, (0, 0, 0))[2] + TACTIC_MODS["tempo"].get(self.tempo, (0, 0, 0))[2]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Tactics":
        return cls(**{k: d.get(k, getattr(cls(), k)) for k in cls().__dict__})


@dataclass
class PlayerState:
    id: str
    name: str
    team_name: str
    position_group: str
    subposition: str
    age: int
    overall: float
    potential: float
    attributes: dict[str, int]
    archetype: str
    perfil: str
    goals_isquad: int
    value: int = 0
    polivalencia: float = 0.0
    overalls: dict[str, float] = field(default_factory=dict)
    fatigue: float = 0.0          # 0-100
    morale: int = 12              # 1-20
    form: float = 6.5             # 1-10
    injury: int = 0               # partidos de baja
    suspension: int = 0           # partidos de sanción
    season_goals: int = 0
    season_assists: int = 0
    apps: int = 0
    rating_sum: float = 0.0

    @property
    def available(self) -> bool:
        return self.injury <= 0 and self.suspension <= 0

    @property
    def rating(self) -> float:
        return round(self.rating_sum / self.apps, 2) if self.apps else 0.0

    def slot_fit(self, slot: str) -> float:
        target = SLOT_TO_SUB.get(slot)
        if not target:
            return 0.0
        if self.subposition == target:
            return 6.0
        if self.position_group == target:
            return 3.0
        if target in ("Central", "Lateral") and self.position_group == "Defensa":
            return 3.0
        if self.subposition == "Polivalente":
            return 2.0
        # Portero solo puede jugar de portero; los demás tienen penalización.
        if self.subposition == "Portero" or target == "Portero":
            return -40.0
        return -3.0

    def selection_score(self, slot: str) -> float:
        fatigue_pen = self.fatigue * 0.20
        form_bonus = (self.form - 5) * 1.2
        morale_bonus = (self.morale - 10) * 0.3
        return self.overall + self.slot_fit(slot) + form_bonus + morale_bonus - fatigue_pen

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PlayerState":
        return cls(**d)


@dataclass
class TeamState:
    id: str
    name: str
    league: str
    city: str
    players: list[PlayerState]
    tactics: Tactics = field(default_factory=Tactics)
    stadium_name: str = ""
    stadium_capacity: int = 1000
    board_expectation: str = ""
    preferred_mode: str = ""
    budget: int = 0
    wage_budget: int = 0
    board_confidence: int = 60
    fan_confidence: int = 60
    morale: int = 12
    cohesion: int = 12
    manager_rating: int = 60
    assistant_rating: int = 60
    prep_bonus: float = 0.0
    last_lineup: list[str] = field(default_factory=list)
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0

    @property
    def squad(self) -> list[PlayerState]:
        return [p for p in self.players if p.perfil == "Jugador"]

    @property
    def available_players(self) -> list[PlayerState]:
        return [p for p in self.players if p.available]

    def auto_lineup(self) -> tuple[list[PlayerState], list[PlayerState]]:
        slots = FORMATION_SLOTS.get(self.tactics.formation, FORMATION_SLOTS["4-3-3"])
        # Si las bajas dejan menos de 11 disponibles, completar con jugadores no disponibles
        # (situación de emergencia; el motor lo refleja como equipo muy justo).
        all_available = self.available_players
        # Rotación: si hay 11 jugadores por debajo del 80% de fatiga, priorizarlos.
        rotation = [p for p in all_available if p.fatigue < 80]
        if len(rotation) < 11:
            rest = sorted([p for p in all_available if p.id not in {x.id for x in rotation}],
                          key=lambda p: (p.fatigue, -p.overall))
            rotation = rotation + rest[: 11 - len(rotation)]
        if len(rotation) < 11:
            rotation = sorted(self.players, key=lambda p: (p.available, p.fatigue, -p.overall), reverse=True)
        pool = [p for p in rotation if p.subposition != "Portero" or "POR" in slots]
        chosen: list[PlayerState] = []
        used: set[str] = set()
        # Primero porteros, luego el resto por slot.
        priority = sorted(slots, key=lambda s: (s != "POR", s))
        for slot in priority:
            # Prioridad: jugador natural del puesto > mismo grupo > cualquier otro.
            natural = [p for p in pool if p.id not in used and p.slot_fit(slot) >= 6]
            group = [p for p in pool if p.id not in used and p.slot_fit(slot) >= 3]
            candidates = natural or group or [p for p in pool if p.id not in used and p.slot_fit(slot) > -20]
            if not candidates:
                candidates = [p for p in rotation if p.id not in used]
            if not candidates:
                break
            best = max(candidates, key=lambda p: p.selection_score(slot))
            chosen.append(best)
            used.add(best.id)
        # Completar hasta 11 si faltan.
        for p in sorted(rotation, key=lambda x: x.overall, reverse=True):
            if len(chosen) >= 11:
                break
            if p.id not in used:
                chosen.append(p)
                used.add(p.id)
        bench = [p for p in sorted(all_available, key=lambda x: (x.fatigue, -x.overall)) if p.id not in used][:7]
        return chosen[:11], bench

    def lineup_strength(self, lineup: list[PlayerState]) -> tuple[float, float]:
        if not lineup:
            return 50.0, 50.0
        def mean_attr(keys, players):
            vals = []
            for p in players:
                vals.append(sum(p.attributes.get(k, 50) for k in keys) / len(keys))
            return sum(vals) / len(vals) if vals else 50.0
        attack = mean_attr(["definicion", "pc_flick", "regate_3d", "pase", "velocidad"], lineup)
        defense = mean_attr(["cobertura", "posicionamiento", "pc_first_runner", "pressing", "fuerza"], lineup)
        # Portero
        gk = next((p for p in lineup if p.subposition == "Portero"), None)
        if gk:
            defense = 0.75 * defense + 0.25 * (gk.attributes.get("reflejos", 50) + gk.attributes.get("blocaje", 50)) / 2
        fatigue = sum(p.fatigue for p in lineup) / len(lineup)
        attack -= fatigue * 0.08
        defense -= fatigue * 0.08
        attack += self.tactics.attack_mod() * 100
        defense += self.tactics.defense_mod() * 100
        return max(25.0, attack), max(25.0, defense)

    def management_profile(self, lineup: list[PlayerState] | None = None) -> dict:
        """Puntuación interna de gestión (0-100) y sus componentes.

        Premia moral, cohesión, descanso, confianza, encaje posicional y
        trayectoria del entrenador. Se aplica como pequeño modificador de
        ataque/defensa en el motor, para que una buena gestión pueda competir
        contra plantillas superiores.
        """
        if lineup is None:
            lineup = self.auto_lineup()[0]
        if not lineup:
            lineup = self.players[:11]
        slots = FORMATION_SLOTS.get(self.tactics.formation, FORMATION_SLOTS["4-3-3"])
        avg_fatigue = sum(p.fatigue for p in lineup) / max(1, len(lineup))
        fits = [p.slot_fit(slots[i] if i < len(slots) else "MED") for i, p in enumerate(lineup)]
        avg_fit = sum(fits) / len(fits) if fits else 0.0
        comps = {
            "moral": (self.morale - 10) * 2.0,
            "cohesion": (self.cohesion - 10) * 1.5,
            "fatiga": -avg_fatigue * 0.30,
            "confianza": (((self.board_confidence + self.fan_confidence) / 2) - 50) * 0.15,
            "encaje": (avg_fit - 2.0) * 1.5,
            "entrenador": (self.manager_rating - 50) * 0.10,
        }
        score = max(0.0, min(100.0, 50.0 + sum(comps.values())))
        bonus = max(-7.0, min(7.0, (score - 50.0) / 8.0))
        comps["score"] = round(score, 1)
        comps["bonus"] = round(bonus, 2)
        comps["avg_fatigue"] = round(avg_fatigue, 1)
        comps["avg_fit"] = round(avg_fit, 2)
        return comps

    def management_score(self, lineup: list[PlayerState] | None = None) -> float:
        return self.management_profile(lineup)["score"]

    def management_bonus(self, lineup: list[PlayerState] | None = None) -> float:
        return self.management_profile(lineup)["bonus"]

    def specialists(self, lineup: list[PlayerState] | None = None) -> dict[str, PlayerState]:
        pool = lineup or self.auto_lineup()[0]
        if not pool:
            pool = self.players
        def best(attr: str) -> PlayerState:
            return max(pool, key=lambda p: p.attributes.get(attr, 0)) if pool else None
        return {
            "pc_injector": best("pc_injection"),
            "pc_stopper": best("pc_trap"),
            "pc_flicker": best("pc_flick"),
            "pc_deflector": best("pc_deflection"),
            "pc_first_runner": best("pc_first_runner"),
            "pc_goalkeeper": max([p for p in pool if p.subposition == "Portero"] or pool, key=lambda p: p.attributes.get("pc_gk_save", 0)),
            "stroke_taker": best("stroke_shot"),
            "stroke_goalkeeper": max([p for p in pool if p.subposition == "Portero"] or pool, key=lambda p: p.attributes.get("stroke_save", 0)),
            "free_hit_taker": best("free_hit"),
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "league": self.league,
            "city": self.city,
            "players": [p.to_dict() for p in self.players],
            "tactics": self.tactics.to_dict(),
            "stadium_name": self.stadium_name,
            "stadium_capacity": self.stadium_capacity,
            "board_expectation": self.board_expectation,
            "preferred_mode": self.preferred_mode,
            "budget": self.budget,
            "wage_budget": self.wage_budget,
            "board_confidence": self.board_confidence,
            "fan_confidence": self.fan_confidence,
            "morale": self.morale,
            "cohesion": self.cohesion,
            "manager_rating": self.manager_rating,
            "assistant_rating": self.assistant_rating,
            "prep_bonus": self.prep_bonus,
            "last_lineup": self.last_lineup,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
            "points": self.points,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TeamState":
        return cls(
            id=d["id"], name=d["name"], league=d["league"], city=d["city"],
            players=[PlayerState.from_dict(p) for p in d["players"]],
            tactics=Tactics.from_dict(d.get("tactics", {})),
            stadium_name=d.get("stadium_name", ""), stadium_capacity=d.get("stadium_capacity", 1000),
            board_expectation=d.get("board_expectation", ""), preferred_mode=d.get("preferred_mode", ""),
            budget=d.get("budget", 0), wage_budget=d.get("wage_budget", 0),
            board_confidence=d.get("board_confidence", 60), fan_confidence=d.get("fan_confidence", 60),
            morale=d.get("morale", 12), cohesion=d.get("cohesion", 12),
            manager_rating=d.get("manager_rating", 60),
            assistant_rating=d.get("assistant_rating", 60),
            prep_bonus=d.get("prep_bonus", 0.0), last_lineup=d.get("last_lineup", []),
            played=d.get("played", 0), won=d.get("won", 0),
            drawn=d.get("drawn", 0), lost=d.get("lost", 0),
            goals_for=d.get("goals_for", 0), goals_against=d.get("goals_against", 0),
            points=d.get("points", 0),
        )


@dataclass
class Fixture:
    id: str
    round: int
    date: str
    home_id: str
    away_id: str
    phase: str = "regular"
    played: bool = False
    home_goals: int = 0
    away_goals: int = 0
    home_stats: dict[str, Any] = field(default_factory=dict)
    away_stats: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    attendance: int = 0
    travel: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Fixture":
        return cls(**d)


@dataclass
class GameState:
    manager_name: str
    club_id: str
    season: str
    seed: int
    round: int
    date: str
    fixtures: list[Fixture]
    teams: dict[str, TeamState]
    phase: str = "regular"
    final4: dict[str, Any] = field(default_factory=dict)
    playout: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    inbox: list[dict[str, Any]] = field(default_factory=list)
    last_result: dict[str, Any] = field(default_factory=dict)
    manual_lineup: list[str] = field(default_factory=list)
    week_trained: bool = False
    weekly_plan: list[str] = field(default_factory=list)
    training_report: dict[str, Any] = field(default_factory=dict)
    ai_training_round: int = 0

    @property
    def user_team(self) -> TeamState:
        return self.teams[self.club_id]

    def table(self) -> list[TeamState]:
        teams = [t for t in self.teams.values() if t.league == "DHA"]
        return sorted(teams, key=lambda t: (-t.points, -(t.goals_for - t.goals_against), -t.goals_for, t.name))

    def user_position(self) -> int:
        table = self.table()
        for i, t in enumerate(table, 1):
            if t.id == self.club_id:
                return i
        return 0

    def next_user_fixture(self) -> Fixture | None:
        for f in self.fixtures:
            if f.phase == "regular" and not f.played and self.club_id in (f.home_id, f.away_id):
                return f
        return None

    def to_dict(self) -> dict:
        return {
            "manager_name": self.manager_name,
            "club_id": self.club_id,
            "season": self.season,
            "seed": self.seed,
            "round": self.round,
            "date": self.date,
            "fixtures": [f.to_dict() for f in self.fixtures],
            "teams": {k: v.to_dict() for k, v in self.teams.items()},
            "phase": self.phase,
            "final4": self.final4,
            "playout": self.playout,
            "history": self.history,
            "inbox": self.inbox,
            "last_result": self.last_result,
            "manual_lineup": self.manual_lineup,
            "week_trained": self.week_trained,
            "weekly_plan": self.weekly_plan,
            "training_report": self.training_report,
            "ai_training_round": self.ai_training_round,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        return cls(
            manager_name=d["manager_name"], club_id=d["club_id"], season=d["season"],
            seed=d["seed"], round=d["round"], date=d["date"],
            fixtures=[Fixture.from_dict(f) for f in d["fixtures"]],
            teams={k: TeamState.from_dict(v) for k, v in d["teams"].items()},
            phase=d.get("phase", "regular"), final4=d.get("final4", {}),
            playout=d.get("playout", {}), history=d.get("history", []),
            inbox=d.get("inbox", []), last_result=d.get("last_result", {}),
            manual_lineup=d.get("manual_lineup", []),
            week_trained=d.get("week_trained", False),
            weekly_plan=d.get("weekly_plan", []),
            training_report=d.get("training_report", {}),
            ai_training_round=d.get("ai_training_round", 0),
        )
