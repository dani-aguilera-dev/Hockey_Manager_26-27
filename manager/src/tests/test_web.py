from urllib.parse import quote

import pytest


@pytest.fixture()
def client(tmp_path):
    import web.app as web
    web.WEB_DB = tmp_path / "web.db"
    web.GAMES.clear()
    web.LIVE.clear()
    web.app.config.update(TESTING=True)
    with web.app.test_client() as c:
        yield c


def _new(client, club="cd-terrassa", seed="10"):
    r = client.post("/new", data={"club_id": club, "manager": "WebTest", "seed": seed}, follow_redirects=True)
    assert r.status_code == 200
    return r


def test_web_new_and_main_routes(client):
    assert client.get("/").status_code == 200
    r = _new(client)
    assert "Dashboard".encode() in r.data
    for path in ("/dashboard", "/squad", "/tactics", "/training", "/market", "/staff", "/youth", "/press", "/cup", "/table", "/match"):
        rr = client.get(path)
        assert rr.status_code == 200, path


def test_web_player_photo_and_cards(client):
    import web.app as web
    _new(client, seed="14")
    state = list(web.GAMES.values())[-1]
    player = next((p for p in state.user_team.players if p.photo), None)
    assert player is not None
    r = client.get("/photo/" + quote(player.photo))
    assert r.status_code == 200
    assert r.mimetype.startswith("image/")
    html = client.get("/squad").get_data(as_text=True)
    assert "avatar" in html
    assert "archetype" in html or "Central" in html


def test_web_training_and_quick_match(client):
    import web.app as web
    _new(client, seed="11")
    state = list(web.GAMES.values())[-1]
    line, _ = state.user_team.auto_lineup()
    r = client.post("/training", data={"action": "auto"}, follow_redirects=True)
    assert r.status_code == 200
    data = {
        "formation": "4-3-3", "mentality": "equilibrada", "press": "media",
        "block": "medio", "width": "normal", "tempo": "normal",
        "passing": "mixto", "pc_routine": "directa",
    }
    data.update({f"slot_{i}": p.id for i, p in enumerate(line)})
    r = client.post("/tactics", data=data, follow_redirects=True)
    assert r.status_code == 200
    assert len(state.manual_lineup) == 11
    r = client.post("/tactics", data={"formation": "4-4-2"}, follow_redirects=True)
    assert r.status_code == 200
    assert state.manual_lineup == []
    assert state.user_team.tactics.formation == "4-4-2"
    r = client.post("/match/quick", data={"travel": "equilibrado"}, follow_redirects=True)
    assert r.status_code == 200
    assert client.get("/match/report").status_code == 200


def test_web_crests_and_news(client):
    _new(client, seed="15")
    r = client.get("/new")
    assert r.status_code == 200
    assert b"crests/cd-terrassa.png" in r.data
    assert client.get("/static/crests/cd-terrassa.png").status_code == 200
    assert client.get("/static/crests/cd-terrassa.png").mimetype == "image/png"
    r = client.get("/news")
    assert r.status_code == 200
    assert "Actualidad".encode() in r.data
    assert "Noticias".encode() in r.data


def test_web_live_match(client):
    _new(client, seed="12")
    r = client.post("/match/live/start", data={"travel": "equilibrado"}, follow_redirects=True)
    assert r.status_code == 200
    assert client.get("/match/live").status_code == 200
    assert client.post("/match/live/advance", data={"mode": "quarter"}, follow_redirects=True).status_code == 200
    assert client.post("/match/live/advance", data={"mode": "rest"}, follow_redirects=True).status_code == 200
    r = client.post("/match/live/finish", follow_redirects=True)
    assert r.status_code == 200
    assert client.get("/match/report").status_code == 200


def test_web_save_and_load(client):
    _new(client, seed="13")
    r = client.post("/save", data={"name": "web-test-save"}, follow_redirects=True)
    assert r.status_code == 200
    r = client.get("/load")
    assert b"web-test-save" in r.data
