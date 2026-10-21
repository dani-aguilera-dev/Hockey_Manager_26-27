from datetime import date

from src.daily import simulate_days
from src.season import new_game, record_season_career
from src.market import market_players


def test_daily_simulation_stops_at_next_match():
    state = new_game("cd-terrassa", "Test", seed=801)
    assert state.date == "2026-08-01"
    fixture = state.next_user_fixture()
    assert fixture
    result = simulate_days(state, target_date=fixture.date, stop_at_match=True)
    assert result["ok"]
    assert result["stopped_at_match"]
    assert state.date == fixture.date
    assert state.daily_events
    assert any(e["category"] == "Partido" for e in state.daily_events)


def test_daily_simulation_to_exact_date():
    state = new_game("cd-terrassa", "Test", seed=802)
    result = simulate_days(state, target_date="2026-08-10", stop_at_match=False)
    assert result["days"] == 9
    assert state.date == "2026-08-10"
    assert state.daily_events


def test_market_players_include_other_teams_and_stats():
    state = new_game("cd-terrassa", "Test", seed=803)
    players = market_players(state, limit=500)
    assert players
    other = [p for p in players if p.team_name != state.user_team.name]
    assert other
    assert all(p.team_name for p in other)


def test_player_career_is_recorded():
    state = new_game("cd-terrassa", "Test", seed=804)
    player = state.user_team.players[0]
    player.apps = 12
    player.season_goals = 7
    player.season_assists = 4
    player.rating_sum = 84.0
    record_season_career(state)
    assert player.career
    row = player.career[-1]
    assert row["season"] == state.season
    assert row["club"] == state.user_team.name
    assert row["goals"] == 7
    assert date.fromisoformat(state.date).year == 2026
