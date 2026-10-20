from src.data_loader import load_teams
from src.models import FORMATION_SLOTS, Tactics


def test_auto_lineup_and_tactics():
    teams, _, _ = load_teams()
    t = teams["cd-terrassa"]
    line, bench = t.auto_lineup()
    assert len(line) == 11
    assert len({p.id for p in line}) == 11
    assert all(p.available for p in line)
    for formation in FORMATION_SLOTS:
        t.tactics.formation = formation
        line, _ = t.auto_lineup()
        assert len(line) == 11
    t.tactics = Tactics(mentality="ofensiva", press="alta", tempo="rapido")
    assert t.tactics.attack_mod() > 0
    assert t.tactics.fatigue_mod() > 0
    assert Tactics(block="bajo").defense_mod() > 0
    assert Tactics(block="alto").attack_mod() > 0
    assert Tactics(passing="directo").attack_mod() > 0
    assert Tactics(width="estrecha").defense_mod() > 0
