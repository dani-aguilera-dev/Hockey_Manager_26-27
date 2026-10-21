"""Persistencia SQLite de la partida (Fase 1).

El estado completo se guarda como JSON en una tabla `saves`. Es una solución
pragmática para el MVP: permite guardar/cargar sin acoplar la UI al esquema
completo de 41 tablas, que se irá normalizando en fases posteriores.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import GameState, StaffMember

DEFAULT_DB = Path(__file__).resolve().parents[1] / "saves" / "manager.db"


def _connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS saves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            club_id TEXT NOT NULL,
            season TEXT NOT NULL,
            round INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            state_json TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_game(state: GameState, name: str | None = None, path: Path | str = DEFAULT_DB) -> str:
    name = name or f"{state.user_team.name} · {state.season} · J{state.round}"
    payload = json.dumps(state.to_dict(), ensure_ascii=False, separators=(",", ":"))
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connect(path)
    try:
        conn.execute("""
            INSERT INTO saves (name, club_id, season, round, updated_at, state_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                club_id=excluded.club_id, season=excluded.season, round=excluded.round,
                updated_at=excluded.updated_at, state_json=excluded.state_json
        """, (name, state.club_id, state.season, state.round, now, payload))
        conn.commit()
    finally:
        conn.close()
    return name


def list_saves(path: Path | str = DEFAULT_DB) -> list[dict]:
    conn = _connect(path)
    try:
        rows = conn.execute("SELECT id, name, club_id, season, round, updated_at FROM saves ORDER BY updated_at DESC").fetchall()
    finally:
        conn.close()
    keys = ["id", "name", "club_id", "season", "round", "updated_at"]
    return [dict(zip(keys, r)) for r in rows]


def _backfill_communities(state: GameState) -> None:
    """Rellena la comunidad en partidas antiguas sin reescribir sus datos."""
    if all(team.community for team in state.teams.values()):
        return
    try:
        from .data_loader import load_clubs
        clubs, _ = load_clubs()
    except Exception:
        return
    for team_id, team in state.teams.items():
        if not team.community:
            team.community = clubs.get(team_id, {}).get("community", "")


def _backfill_media(state: GameState) -> None:
    """Rellena fotos en partidas antiguas creadas antes de guardar media."""
    if not any(not p.photo for t in state.teams.values() for p in t.players) and not any(not p.photo for p in state.free_agents):
        return
    try:
        from .data_loader import load_teams
        teams, _, _ = load_teams()
    except Exception:
        return
    by_id: dict[str, tuple[str, str]] = {}
    by_name: dict[tuple[str, str], tuple[str, str]] = {}
    for team in teams.values():
        for player in team.players:
            media = (player.photo, player.photo_remote)
            by_id[player.id] = media
            by_name[(team.name.casefold(), player.name.casefold())] = media
    for team in state.teams.values():
        for player in team.players + team.youth:
            if player.photo:
                continue
            media = by_id.get(player.id) or by_name.get((team.name.casefold(), player.name.casefold()))
            if media:
                player.photo, player.photo_remote = media
    for player in state.free_agents:
        if player.photo:
            continue
        media = by_id.get(player.id) or by_name.get((player.team_name.casefold(), player.name.casefold()))
        if media:
            player.photo, player.photo_remote = media


def _backfill_staff(state: GameState) -> None:
    """Añade el cuerpo técnico de iSquad a partidas antiguas."""
    if all(team.staff and any(m.role == "head_coach" for m in team.staff)
           for team in state.teams.values()):
        return
    path = Path(__file__).resolve().parents[1] / "data" / "staff_isquad.json"
    if not path.exists():
        return
    try:
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    for team in state.teams.values():
        scraped = data.get(team.id, {}).get("staff", [])
        if not scraped:
            continue
        if not any(m.role == "head_coach" for m in team.staff):
            head = next((row for row in scraped if row.get("role") == "head_coach"), None)
            if head:
                team.staff.append(StaffMember(**{k: v for k, v in head.items()
                                                 if k in StaffMember.__dataclass_fields__}))
        if not team.staff:
            team.staff = [StaffMember(**{k: v for k, v in row.items()
                                         if k in StaffMember.__dataclass_fields__})
                          for row in scraped]


def backfill_state(state: GameState) -> GameState:
    """Compatibilidad con partidas guardadas antes de comunidad/fotos."""
    _backfill_communities(state)
    _backfill_media(state)
    _backfill_staff(state)
    return state


def load_game(name_or_id: str | int, path: Path | str = DEFAULT_DB) -> GameState:
    conn = _connect(path)
    try:
        if isinstance(name_or_id, int) or str(name_or_id).isdigit():
            row = conn.execute("SELECT state_json FROM saves WHERE id=?", (int(name_or_id),)).fetchone()
        else:
            row = conn.execute("SELECT state_json FROM saves WHERE name=?", (str(name_or_id),)).fetchone()
    finally:
        conn.close()
    if not row:
        raise KeyError(f"No existe la partida: {name_or_id}")
    state = GameState.from_dict(json.loads(row[0]))
    _backfill_communities(state)
    _backfill_media(state)
    _backfill_staff(state)
    return state


def delete_save(name_or_id: str | int, path: Path | str = DEFAULT_DB) -> bool:
    conn = _connect(path)
    try:
        if isinstance(name_or_id, int) or str(name_or_id).isdigit():
            cur = conn.execute("DELETE FROM saves WHERE id=?", (int(name_or_id),))
        else:
            cur = conn.execute("DELETE FROM saves WHERE name=?", (str(name_or_id),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def export_json(state: GameState, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def import_json(path: Path | str) -> GameState:
    state = GameState.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    _backfill_communities(state)
    _backfill_media(state)
    _backfill_staff(state)
    return state
