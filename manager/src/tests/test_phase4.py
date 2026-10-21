from src.season import new_game, play_round, simulate_cup_round, simulate_cup_remaining, season_summary, _process_age_and_retirements
from src.cup import new_cup, cup_round_fixtures, cup_status_text
from src.youth import promote_youth, develop_youth, intake
from src.press import press_questions, answer_press, mark_press_done
from src.ehl import create_ehl, simulate_ehl
import random


def test_cup_bracket_and_rounds():
    state = new_game("cd-terrassa", "Test", seed=601)
    new_cup(state)
    assert state.cup_active
    assert state.cup_round == 1
    assert len(cup_round_fixtures(state)) == 4
    simulate_cup_round(state)
    assert state.cup_round == 2
    assert len(cup_round_fixtures(state)) == 2
    simulate_cup_remaining(state)
    assert not state.cup_active
    assert state.cup_winner_id in state.teams
    assert "Campeón" in cup_status_text(state)


def test_youth_promotion_and_development():
    state = new_game("cd-terrassa", "Test", seed=602)
    team = state.user_team
    assert len(team.youth) >= 3
    before_players = len(team.players)
    before_youth = len(team.youth)
    ok, _ = promote_youth(team, team.youth[0].id)
    assert ok
    assert len(team.players) == before_players + 1
    assert len(team.youth) == before_youth - 1
    develop_youth(team, random.Random(1), 2027)
    intake(team, random.Random(2), 2027)
    assert len(team.youth) >= 3


def test_press_conference():
    state = new_game("cd-terrassa", "Test", seed=603)
    qs = press_questions(state)
    assert len(qs) >= 2
    result = answer_press(state, qs[0]["id"], 0)
    assert result["ok"]
    mark_press_done(state)
    assert state.press_done_round == state.round
    assert state.press_history


def test_ehl_tournament():
    state = new_game("cd-terrassa", "Test", seed=605)
    create_ehl(state)
    assert len(state.ehl["participants"]) == 8
    simulate_ehl(state)
    assert not state.ehl["active"]
    assert state.ehl["winner_name"]


def test_retirements():
    state = new_game("cd-terrassa", "Test", seed=606)
    player = state.user_team.players[0]
    player.age = 39
    _process_age_and_retirements(state)
    assert state.retirements
    assert all(p.id != player.id for p in state.user_team.players)


def test_board_review_after_season():
    state = new_game("cd-terrassa", "Test", seed=604)
    for _ in range(22):
        play_round(state, None, "equilibrado")
    assert state.phase == "season_end"
    summary = season_summary(state)
    review = summary.get("board_review") or {}
    assert review
    assert "target" in review and "position" in review
    assert 0 <= state.user_team.board_confidence <= 100
