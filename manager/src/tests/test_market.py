from src.season import new_game, play_round, season_summary, advance_to_next_season
from src.market import (market_window, market_players, asking_price, make_transfer_offer,
                        generate_incoming_offers, renew_contract, staff_candidates,
                        hire_staff, fire_staff)


def test_market_window():
    state = new_game("cd-terrassa", "Test", seed=501)
    assert market_window(state) == "verano"
    play_round(state, None, "equilibrado")
    assert market_window(state) == "cerrado"
    # avanzar hasta la ventana de invierno (ronda 12)
    for _ in range(10):
        play_round(state, None, "equilibrado")
    assert state.round == 12
    assert market_window(state) == "invierno"


def test_transfer_and_contracts():
    state = new_game("cd-terrassa", "Test", seed=502)
    state.user_team.transfer_budget = 2_000_000
    players = market_players(state, limit=30, max_value=1_000_000)
    assert players
    player = min(players, key=lambda p: p.value)
    old_team = next(t for t in state.teams.values() if any(p.id == player.id for p in t.players))
    result = make_transfer_offer(state, player.id, max(asking_price(player), 1), player.salary * 2, 3)
    if result["ok"]:
        assert any(p.id == player.id for p in state.user_team.players)
        assert not any(p.id == player.id for p in old_team.players)
        assert state.market_history
    # renovación de un jugador propio
    own = max(state.user_team.players, key=lambda p: p.overall)
    renewed = renew_contract(state, own.id, own.salary * 2, 3)
    assert "message" in renewed
    if renewed["ok"]:
        assert own.contract_until.endswith("-06-30")


def test_incoming_offers_shape():
    state = new_game("cd-terrassa", "Test", seed=503)
    offers = generate_incoming_offers(state)
    for offer in offers:
        assert offer["player_id"]
        assert offer["from_club_id"] != state.club_id
        assert offer["fee"] >= 0


def test_staff_hire_and_fire():
    state = new_game("cd-terrassa", "Test", seed=504)
    team = state.user_team
    fired = fire_staff(state, "scout")
    assert fired["ok"]
    candidates = staff_candidates(team, "scout", __import__("random").Random(1))
    hired = hire_staff(state, candidates[0])
    assert hired["ok"]
    assert any(m.role == "scout" for m in team.staff)


def test_multi_season_transition():
    state = new_game("cd-terrassa", "Test", seed=505)
    for _ in range(22):
        play_round(state, None, "equilibrado")
    assert state.phase == "season_end"
    old_season = state.season
    advance_to_next_season(state)
    assert state.phase == "regular"
    assert state.season != old_season
    assert state.round == 1
    assert len([t for t in state.teams.values() if t.league == "DHA"]) == 12
    assert len([t for t in state.teams.values() if t.league == "DHB"]) == 16
    assert len(state.fixtures) == (132 if state.competition == "DHA" else 240)
    assert state.total_rounds == (22 if state.competition == "DHA" else 30)
    assert all(len(t.players) >= 18 for t in state.teams.values() if t.league in ("DHA", "DHB"))
