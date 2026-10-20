import tempfile
from pathlib import Path

from src.season import new_game, play_round, ensure_week_training
from src.persistence import save_game, load_game, list_saves, export_json, import_json


def test_sqlite_roundtrip():
    state = new_game("cd-terrassa", "Test", seed=42)
    play_round(state)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        name = save_game(state, "partida-test", db)
        assert list_saves(db)[0]["name"] == name
        loaded = load_game(name, db)
        assert loaded.club_id == state.club_id
        assert loaded.round == state.round
        assert loaded.user_team.points == state.user_team.points
        assert loaded.user_team.players[0].overall == state.user_team.players[0].overall
        assert loaded.last_result["home_goals"] == state.last_result["home_goals"]
        assert len(loaded.fixtures) == len(state.fixtures)


def test_training_state_roundtrip():
    state = new_game("cd-terrassa", "Test", seed=88)
    ensure_week_training(state)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "training.db"
        name = save_game(state, "training-test", db)
        loaded = load_game(name, db)
        assert loaded.week_trained is True
        assert loaded.weekly_plan == state.weekly_plan
        assert loaded.user_team.prep_bonus == state.user_team.prep_bonus
        assert loaded.training_report["plan_name"] == state.training_report["plan_name"]


def test_json_roundtrip():
    state = new_game("club-egara", "Test", seed=7)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "save.json"
        export_json(state, path)
        loaded = import_json(path)
        assert loaded.club_id == "club-egara"
        assert loaded.round == state.round
        assert len(loaded.teams) == len(state.teams)
