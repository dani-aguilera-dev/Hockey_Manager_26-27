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

from .models import GameState

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
    return GameState.from_dict(json.loads(row[0]))


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
    return GameState.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
