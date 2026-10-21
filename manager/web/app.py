"""Alpha web local del Hockey Manager (Flask + Jinja).

La lógica sigue en manager/src. Esta capa solo orquesta GameState y MatchEngine.
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import date
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)

from src.calendar import league_table
from src.cup import cup_round_fixtures, cup_status_text, cup_next_user_fixture
from src.data_loader import load_teams
from src.finance import financial_summary
from src.market import (STAFF_LABELS, accept_incoming_offer, asking_price,
                        fire_staff, generate_incoming_offers, hire_staff,
                        make_transfer_offer, market_players, market_window,
                        market_window_text, reject_incoming_offer,
                        renew_contract, scout_range, staff_candidates)
from src.models import FORMATION_SLOTS
from src.news import news_feed
from src.persistence import list_saves, load_game, save_game
from src.press import answer_press, mark_press_done, press_questions
from src.season import (advance_to_next_season, ensure_week_training,
                        finish_live_round, make_lineup, new_game, play_round,
                        prepare_live_round, season_summary, simulate_cup_remaining,
                        simulate_cup_round)
from src.training import (DAYS, PLAN_PRESETS, SESSION_ORDER, SESSION_TYPES,
                          apply_training_plan, auto_plan, format_plan, plan_name)
from src.youth import CATEGORY_AGES, CATEGORY_LABELS, YOUTH_CATEGORIES, promote_youth, release_youth

BASE = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BASE.parent
PHOTOS = PROJECT_ROOT / "jugadores"
WEB_DB = Path(os.environ.get("HOCKEY_WEB_DB", BASE / "saves" / "web.db"))
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("HOCKEY_WEB_SECRET", "hockey-manager-alpha-local")

GAMES: dict[str, object] = {}
LIVE: dict[str, object] = {}


def get_state():
    gid = session.get("game_id")
    if not gid:
        return None
    state = GAMES.get(gid)
    if state is None:
        name = session.get("save_name")
        if not name:
            return None
        try:
            state = load_game(name, WEB_DB)
        except Exception:
            return None
        GAMES[gid] = state
    return state


def save_state(state):
    name = session.get("save_name")
    if not name:
        name = f"web-{session.get('game_id', uuid.uuid4().hex)}"
        session["save_name"] = name
    save_game(state, name, WEB_DB)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if get_state() is None:
            flash("Primero crea o carga una partida.", "warning")
            return redirect(url_for("index"))
        return fn(*args, **kwargs)
    return wrapper


LINE_LAYOUTS = {
    "4-3-3": [1, 4, 3, 3],
    "3-4-3": [1, 3, 4, 3],
    "3-3-3-1": [1, 3, 4, 1, 2],
    "4-4-2": [1, 4, 4, 2],
    "5-3-2": [1, 5, 3, 2],
    "3-2-1-4": [1, 3, 2, 1, 4],
}
ROW_LABELS = {
    4: ["Portería", "Defensa", "Medio", "Ataque"],
    5: ["Portería", "Defensa", "Medio", "Mediapunta", "Ataque"],
}
SLOT_GROUP = {"POR": "Portero", "CEN": "Defensa", "LAT": "Defensa", "MED": "Medio", "DEL": "Delantero"}


def lineup_rows(team, line):
    slots = FORMATION_SLOTS.get(team.tactics.formation, FORMATION_SLOTS["4-3-3"])
    counts = LINE_LAYOUTS.get(team.tactics.formation, [1, 4, 3, 3])
    labels = ROW_LABELS.get(len(counts), ROW_LABELS[4])
    rows = []
    cursor = 0
    for count, label in zip(counts, labels):
        row = []
        for _ in range(count):
            if cursor >= len(slots):
                break
            code = slots[cursor]
            player = line[cursor] if cursor < len(line) else None
            row.append({
                "index": cursor, "code": code, "player": player,
                "group": SLOT_GROUP.get(code, ""),
                "mismatch": bool(player and player.position_group != SLOT_GROUP.get(code, player.position_group)),
            })
            cursor += 1
        rows.append({"label": label, "slots": row})
    return rows


def team_form(state, team_id):
    played = [f for f in state.fixtures if f.phase == "regular" and f.played and team_id in (f.home_id, f.away_id)]
    played.sort(key=lambda f: f.round)
    out = []
    for f in played[-5:]:
        gf = f.home_goals if f.home_id == team_id else f.away_goals
        ga = f.away_goals if f.home_id == team_id else f.home_goals
        out.append("V" if gf > ga else ("E" if gf == ga else "D"))
    return " ".join(out) if out else "—"


def state_context(state):
    team = state.user_team
    table = state.table()
    pos = next((i for i, t in enumerate(table, 1) if t.id == team.id), 0)
    return {
        "state": state,
        "team": team,
        "table": table,
        "positions": {t.id: i for i, t in enumerate(table, 1)},
        "position": pos,
        "competition": state.competition,
        "finance": financial_summary(team),
        "cup_status": cup_status_text(state),
        "market_status": market_window_text(state),
        "next_fixture": state.next_user_fixture(),
        "live_active": session.get("game_id") in LIVE,
    }


def fmt_money(n):
    return f"{int(round(n or 0)):,}".replace(",", ".") + " €"


def fmt_date(iso):
    try:
        d = date.fromisoformat(iso)
        return d.strftime("%d/%m/%Y")
    except Exception:
        return iso


app.jinja_env.filters["money"] = fmt_money
app.jinja_env.filters["fdate"] = fmt_date


def photo_src(player):
    if getattr(player, "photo", ""):
        return url_for("player_photo", filename=player.photo)
    if getattr(player, "photo_remote", ""):
        return player.photo_remote
    return url_for("static", filename="avatar.svg")


def initials(name):
    parts = [p for p in str(name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def crest_src(team):
    tid = getattr(team, "id", team)
    for ext in ("png", "webp", "jpg", "jpeg", "svg"):
        if (BASE / "web" / "static" / "crests" / f"{tid}.{ext}").exists():
            return url_for("static", filename=f"crests/{tid}.{ext}")
    return url_for("static", filename=f"crests/{tid}.svg")


app.jinja_env.globals["photo_src"] = photo_src
app.jinja_env.globals["crest_src"] = crest_src
app.jinja_env.globals["initials"] = initials


@app.context_processor
def inject_globals():
    state = get_state()
    return {
        "current_state": state,
        "current_team": state.user_team if state else None,
        "current_table": state.table() if state else [],
    }


@app.route("/photo/<path:filename>")
def player_photo(filename):
    try:
        return send_from_directory(PHOTOS, filename)
    except Exception:
        abort(404)


@app.route("/")
def index():
    state = get_state()
    if state:
        if state.phase == "season_end":
            return redirect(url_for("season_end"))
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/new", methods=["GET", "POST"])
def new_game_page():
    teams, clubs, _ = load_teams()
    clubs_list = sorted([t for t in teams.values() if t.league in ("DHA", "DHB")], key=lambda t: (t.league, t.name))

    def difficulty(expectation):
        e = (expectation or "").lower()
        if "título" in e or "final four" in e:
            return "Muy alta"
        if "top 4" in e:
            return "Alta"
        if "top 6" in e or "consolidar" in e:
            return "Media"
        if "permanencia" in e or "salvación" in e:
            return "Baja"
        if "ascenso" in e:
            return "Alta"
        return "Media"

    club_cards = []
    for t in clubs_list:
        c = clubs.get(t.id, {})
        st = c.get("stadium", {})
        club_cards.append({
            "team": t, "stadium": st.get("name", t.stadium_name),
            "expectation": t.board_expectation,
            "difficulty": difficulty(t.board_expectation),
        })
    if request.method == "POST":
        club_id = request.form.get("club_id", "")
        manager = request.form.get("manager", "Entrenador").strip() or "Entrenador"
        seed_raw = request.form.get("seed", "").strip()
        seed = int(seed_raw) if seed_raw.isdigit() else None
        if club_id not in teams or teams[club_id].league not in ("DHA", "DHB"):
            flash("Elige un club DHA o DHB válido.", "danger")
            return redirect(url_for("new_game_page"))
        state = new_game(club_id, manager, seed)
        gid = uuid.uuid4().hex
        GAMES[gid] = state
        session["game_id"] = gid
        session["save_name"] = f"web-{gid}"
        save_state(state)
        flash(f"Partida creada con {state.user_team.name}.", "success")
        return redirect(url_for("dashboard"))
    return render_template("new_game.html", clubs=clubs_list, club_cards=club_cards, clubs_by_id=clubs)


@app.route("/load", methods=["GET", "POST"])
def load_page():
    saves = list_saves(WEB_DB)
    if request.method == "POST":
        name = request.form.get("name", "")
        try:
            state = load_game(name, WEB_DB)
        except Exception as exc:
            flash(f"No se pudo cargar: {exc}", "danger")
            return redirect(url_for("load_page"))
        gid = uuid.uuid4().hex
        GAMES[gid] = state
        session["game_id"] = gid
        session["save_name"] = name
        flash(f"Partida cargada: {state.user_team.name}.", "success")
        return redirect(url_for("season_end") if state.phase == "season_end" else url_for("dashboard"))
    return render_template("load.html", saves=saves)


@app.route("/save", methods=["POST"])
@login_required
def save_page():
    state = get_state()
    name = request.form.get("name", "").strip()
    if name:
        session["save_name"] = name
    save_state(state)
    flash("Partida guardada.", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    state = get_state()
    if state.phase == "season_end":
        return redirect(url_for("season_end"))
    ctx = state_context(state)
    ctx["inbox"] = state.inbox[-4:]
    ctx["news"] = news_feed(state, 4)
    ctx["key_players"] = sorted(state.user_team.players, key=lambda p: p.overall, reverse=True)[:3]
    ctx["live_ctx"] = LIVE.get(session.get("game_id"))
    return render_template("dashboard.html", **ctx)


@app.route("/news")
@login_required
def news():
    state = get_state()
    ctx = state_context(state)
    ctx["news"] = news_feed(state, 12)
    return render_template("news.html", **ctx)


@app.route("/squad")
@login_required
def squad():
    ctx = state_context(get_state())
    ctx["players"] = sorted(ctx["team"].players, key=lambda p: (p.subposition, -p.overall))
    groups = []
    for group in ("Portero", "Defensa", "Medio", "Delantero"):
        members = [p for p in ctx["players"] if p.position_group == group]
        if members:
            groups.append((group, members))
    ctx["groups"] = groups
    return render_template("squad.html", **ctx)


@app.route("/player/<player_id>")
@login_required
def player_detail(player_id):
    state = get_state()
    player = next((p for p in state.user_team.players if p.id == player_id), None)
    if not player:
        flash("Jugador no encontrado.", "danger")
        return redirect(url_for("squad"))
    ctx = state_context(state)
    ctx["player"] = player
    return render_template("player.html", **ctx)


@app.route("/tactics", methods=["GET", "POST"])
@login_required
def tactics():
    state = get_state()
    team = state.user_team
    if request.method == "POST":
        old_formation = team.tactics.formation
        for field in ("formation", "mentality", "press", "block", "width", "tempo", "passing", "pc_routine"):
            value = request.form.get(field)
            if value:
                setattr(team.tactics, field, value)
        if team.tactics.formation != old_formation:
            state.manual_lineup = []
            flash("Formación cambiada. Once autoalineado.", "success")
        elif request.form.get("auto"):
            state.manual_lineup = []
            flash("Autoalineación activada.", "success")
        else:
            slots = FORMATION_SLOTS.get(team.tactics.formation, FORMATION_SLOTS["4-3-3"])
            selected = [request.form.get(f"slot_{i}", "") for i in range(len(slots))]
            selected = [x for x in selected if x]
            if len(selected) == 11 and len(set(selected)) == 11:
                state.manual_lineup = selected
                flash("Once guardado.", "success")
            else:
                flash("El once debe tener 11 jugadores distintos. Se mantiene el anterior.", "danger")
        save_state(state)
        return redirect(url_for("tactics"))
    ctx = state_context(state)
    line, bench = make_lineup(team, state.manual_lineup or None)
    slots = FORMATION_SLOTS.get(team.tactics.formation, FORMATION_SLOTS["4-3-3"])
    slot_options = []
    for i, slot in enumerate(slots):
        candidates = sorted(team.available_players, key=lambda p: p.selection_score(slot), reverse=True)[:14]
        if i < len(line) and line[i] not in candidates:
            candidates.append(line[i])
        slot_options.append(candidates)
    slot_rows = lineup_rows(team, line)
    ctx.update({"line": line, "bench": bench, "slots": slots, "slot_rows": slot_rows,
                "available": sorted(team.available_players, key=lambda p: (p.subposition, -p.overall)),
                "slot_options": slot_options,
                "formations": list(FORMATION_SLOTS), "selected": set(state.manual_lineup)})
    return render_template("tactics.html", **ctx)


@app.route("/training", methods=["GET", "POST"])
@login_required
def training():
    state = get_state()
    team = state.user_team
    if request.method == "POST" and not state.week_trained:
        action = request.form.get("action", "auto")
        if action == "recovery":
            plan = list(PLAN_PRESETS["recuperacion"])
            delegated = False
        elif action == "edit":
            plan = [request.form.get(f"session{i}", "recuperacion") for i in range(5)]
            plan = [p if p in SESSION_TYPES else "recuperacion" for p in plan]
            delegated = False
        else:
            plan = auto_plan(team, _opponent(state), random.Random(state.seed + state.round * 53 + 11))
            delegated = True
        report = apply_training_plan(team, plan, _opponent(state), random.Random(state.seed + state.round * 53 + 17), delegated=delegated)
        state.weekly_plan = plan
        state.training_report = report
        state.week_trained = True
        save_state(state)
        flash("Entrenamiento semanal aplicado.", "success")
        return redirect(url_for("training"))
    ctx = state_context(state)
    default_plan = auto_plan(team, _opponent(state), random.Random(state.seed + state.round * 53 + 11))
    ctx.update({"sessions": SESSION_TYPES, "session_order": SESSION_ORDER, "days": DAYS,
                "default_plan": default_plan, "plan_name": plan_name,
                "opponent": _opponent(state)})
    return render_template("training.html", **ctx)


def _opponent(state):
    fx = state.next_user_fixture()
    if not fx:
        return None
    oid = fx.away_id if fx.home_id == state.club_id else fx.home_id
    return state.teams.get(oid)


@app.route("/market")
@login_required
def market():
    state = get_state()
    ctx = state_context(state)
    max_value = request.args.get("max_value", "").strip()
    max_value = int(max_value) if max_value.isdigit() else max(100000, int(state.user_team.transfer_budget / 0.70))
    position = request.args.get("position", "")
    query = request.args.get("q", "").strip()
    players = market_players(state, limit=30, max_value=max_value, position=position or None)
    owners = {p.id: t.name for t in state.teams.values() for p in t.players}
    owner_teams = {p.id: t for t in state.teams.values() for p in t.players}
    for p in state.free_agents:
        owners[p.id] = "Agente libre"
    if query:
        needle = query.lower()
        players = [
            p for p in players
            if needle in p.name.lower()
            or needle in p.archetype.lower()
            or needle in owners.get(p.id, "").lower()
        ]
    ctx.update({"players": players, "max_value": max_value, "position": position, "query": query,
                "asking_price": asking_price, "scout_range": scout_range,
                "window": market_window(state), "offers": state.transfer_offers,
                "owners": owners, "owner_teams": owner_teams})
    return render_template("market.html", **ctx)


@app.route("/market/player/<player_id>", methods=["GET", "POST"])
@login_required
def market_player(player_id):
    state = get_state()
    player = next((p for p in state.user_team.players if p.id == player_id), None)
    if player:
        flash("Ese jugador ya es tuyo.", "warning")
        return redirect(url_for("market"))
    player = next((p for t in state.teams.values() for p in t.players if p.id == player_id), None)
    if not player:
        player = next((p for p in state.free_agents if p.id == player_id), None)
    if not player:
        flash("Jugador no encontrado.", "danger")
        return redirect(url_for("market"))
    if request.method == "POST":
        fee = int(request.form.get("fee", 0) or 0)
        salary = int(request.form.get("salary", 0) or 0)
        years = int(request.form.get("years", 3) or 3)
        result = make_transfer_offer(state, player.id, fee, salary, years)
        flash(result["message"], "success" if result.get("ok") else "danger")
        if result.get("ok"):
            save_state(state)
        return redirect(url_for("market"))
    ctx = state_context(state)
    owner_team = next((t for t in state.teams.values() if any(p.id == player.id for p in t.players)), None)
    owner = owner_team.name if owner_team else "Agente libre"
    ctx.update({"player": player, "owner": owner, "owner_team": owner_team, "asking": asking_price(player),
                "scout": scout_range(player, state.user_team.staff_rating("scout"))})
    return render_template("market_player.html", **ctx)


@app.route("/market/offers", methods=["GET", "POST"])
@login_required
def market_offers():
    state = get_state()
    offers = generate_incoming_offers(state)
    if request.method == "POST":
        offer_id = request.form.get("offer_id", "")
        action = request.form.get("action", "")
        if action == "accept":
            result = accept_incoming_offer(state, offer_id)
            flash(result["message"], "success" if result.get("ok") else "danger")
        else:
            reject_incoming_offer(state, offer_id)
            flash("Oferta rechazada.", "warning")
        save_state(state)
        return redirect(url_for("market_offers"))
    ctx = state_context(state)
    ctx["offers"] = offers
    return render_template("market_offers.html", **ctx)


@app.route("/market/renew")
@login_required
def market_renew():
    ctx = state_context(get_state())
    ctx["players"] = sorted(ctx["team"].players, key=lambda p: (p.contract_until, -p.overall))
    return render_template("market_renew.html", **ctx)


@app.route("/market/renew/<player_id>", methods=["POST"])
@login_required
def market_renew_player(player_id):
    state = get_state()
    salary = int(request.form.get("salary", 0) or 0)
    years = int(request.form.get("years", 3) or 3)
    result = renew_contract(state, player_id, salary, years)
    flash(result["message"], "success" if result.get("ok") else "danger")
    if result.get("ok"):
        save_state(state)
    return redirect(url_for("market_renew"))


@app.route("/staff")
@login_required
def staff():
    state = get_state()
    ctx = state_context(state)
    ctx["staff_labels"] = STAFF_LABELS
    ctx["free_roles"] = [r for r in STAFF_LABELS if not any(m.role == r for m in state.user_team.staff)]
    return render_template("staff.html", **ctx)


@app.route("/staff/hire/<role>", methods=["GET", "POST"])
@login_required
def staff_hire(role):
    state = get_state()
    if role not in STAFF_LABELS:
        flash("Rol no válido.", "danger")
        return redirect(url_for("staff"))
    if any(m.role == role for m in state.user_team.staff):
        flash("Ese rol ya está cubierto.", "warning")
        return redirect(url_for("staff"))
    rng = random.Random(state.seed * 1000 + state.round * 61 + len(state.user_team.staff))
    candidates = staff_candidates(state.user_team, role, rng)
    if request.method == "POST":
        idx = int(request.form.get("candidate", -1))
        if 0 <= idx < len(candidates):
            result = hire_staff(state, candidates[idx])
            flash(result["message"], "success" if result.get("ok") else "danger")
            if result.get("ok"):
                save_state(state)
            return redirect(url_for("staff"))
    ctx = state_context(state)
    ctx.update({"role": role, "candidates": candidates, "staff_labels": STAFF_LABELS})
    return render_template("staff_hire.html", **ctx)


@app.route("/staff/fire/<role>", methods=["POST"])
@login_required
def staff_fire(role):
    state = get_state()
    result = fire_staff(state, role)
    flash(result["message"], "success" if result.get("ok") else "danger")
    if result.get("ok"):
        save_state(state)
    return redirect(url_for("staff"))


@app.route("/youth")
@login_required
def youth():
    state = get_state()
    ctx = state_context(state)
    groups = []
    for category in YOUTH_CATEGORIES:
        members = [p for p in state.user_team.youth if p.youth_category == category]
        if members:
            groups.append((category, CATEGORY_LABELS[category], members))
    ctx["youth_groups"] = groups
    ctx["category_ages"] = CATEGORY_AGES
    return render_template("youth.html", **ctx)


@app.route("/youth/promote/<player_id>", methods=["POST"])
@login_required
def youth_promote(player_id):
    state = get_state()
    ok, msg = promote_youth(state.user_team, player_id)
    flash(msg, "success" if ok else "danger")
    if ok:
        save_state(state)
    return redirect(url_for("youth"))


@app.route("/youth/release/<player_id>", methods=["POST"])
@login_required
def youth_release(player_id):
    state = get_state()
    ok, msg = release_youth(state.user_team, player_id)
    flash(msg, "success" if ok else "danger")
    if ok:
        save_state(state)
    return redirect(url_for("youth"))


@app.route("/press", methods=["GET", "POST"])
@login_required
def press():
    state = get_state()
    if request.method == "POST":
        questions = press_questions(state)
        for q in questions:
            raw = request.form.get(f"answer_{q['id']}", "0")
            try:
                idx = int(raw)
            except ValueError:
                idx = 0
            answer_press(state, q["id"], idx)
        mark_press_done(state)
        save_state(state)
        flash("Rueda de prensa completada.", "success")
        return redirect(url_for("press"))
    ctx = state_context(state)
    ctx["questions"] = press_questions(state)
    ctx["done"] = state.press_done_round == state.round
    return render_template("press.html", **ctx)


@app.route("/cup", methods=["GET", "POST"])
@login_required
def cup():
    state = get_state()
    if request.method == "POST":
        action = request.form.get("action", "round")
        if action == "all":
            simulate_cup_remaining(state)
        else:
            simulate_cup_round(state, state.manual_lineup or None)
        save_state(state)
        flash("Copa actualizada.", "success")
        return redirect(url_for("cup"))
    ctx = state_context(state)
    ctx.update({"fixtures": cup_round_fixtures(state), "next_cup": cup_next_user_fixture(state)})
    return render_template("cup.html", **ctx)


@app.route("/table")
@login_required
def table():
    ctx = state_context(get_state())
    regular = [f for f in ctx["state"].fixtures if f.phase == "regular"]
    ctx["fixtures"] = sorted(regular, key=lambda f: (f.round, f.date))
    return render_template("table.html", **ctx)


@app.route("/match")
@login_required
def match_page():
    state = get_state()
    gid = session.get("game_id")
    if gid in LIVE:
        return redirect(url_for("match_live"))
    fx = state.next_user_fixture()
    if not fx:
        return redirect(url_for("season_end") if state.phase == "season_end" else url_for("dashboard"))
    home, away = state.teams[fx.home_id], state.teams[fx.away_id]
    user = state.user_team
    line, bench = make_lineup(user, state.manual_lineup or None)
    travel = []
    if fx.away_id == user.id:
        from src.data_loader import load_clubs
        from src.logistics import travel_options
        _, cities = load_clubs()
        travel = travel_options(user, home, cities, squad_size=18)
    ctx = state_context(state)
    def top_scorer(t):
        return max(t.players, key=lambda p: (p.season_goals, p.overall), default=None)
    def absences(t):
        return [p for p in t.players if p.injury or p.suspension]
    ctx.update({
        "fixture": fx, "home": home, "away": away, "line": line, "bench": bench, "travel": travel,
        "home_top": top_scorer(home), "away_top": top_scorer(away),
        "home_absences": absences(home), "away_absences": absences(away),
        "home_form": team_form(state, home.id), "away_form": team_form(state, away.id),
        "slot_rows": lineup_rows(user, line),
    })
    return render_template("match_preview.html", **ctx)


@app.route("/match/quick", methods=["POST"])
@login_required
def match_quick():
    state = get_state()
    travel_id = request.form.get("travel") or None
    payload = play_round(state, state.manual_lineup or None, travel_id)
    if not payload:
        flash("No se pudo simular el partido.", "danger")
        return redirect(url_for("dashboard"))
    save_state(state)
    return redirect(url_for("match_report"))


@app.route("/match/live/start", methods=["POST"])
@login_required
def match_live_start():
    state = get_state()
    gid = session.get("game_id")
    if gid in LIVE:
        return redirect(url_for("match_live"))
    travel_id = request.form.get("travel") or None
    try:
        ctx = prepare_live_round(state, state.manual_lineup or None, travel_id)
    except Exception as exc:
        flash(f"No se pudo iniciar el directo: {exc}", "danger")
        return redirect(url_for("match_page"))
    LIVE[gid] = ctx
    return redirect(url_for("match_live"))


@app.route("/match/live")
@login_required
def match_live():
    state = get_state()
    gid = session.get("game_id")
    ctx = LIVE.get(gid)
    if not ctx:
        flash("No hay partido en directo.", "warning")
        return redirect(url_for("match_page"))
    engine = ctx.engine
    ctx_state = state_context(state)
    events = [e for e in engine.events if e.get("type") in ("goal", "pc", "stroke", "save", "card", "injury", "substitution", "chance", "circle_entry", "talk", "tactic")]
    ctx_state.update({"engine": engine, "live": ctx, "fixture": ctx.fixture, "events": events[-40:],
                      "user_side": ctx.user_side,
                      "home": state.teams[ctx.fixture.home_id],
                      "away": state.teams[ctx.fixture.away_id],
                      "line": engine._lineup(ctx.user_side),
                      "bench": engine._bench(ctx.user_side),
                      "player_rows": engine.player_live_rows(ctx.user_side),
                      "players_by_id": {p.id: p for p in state.user_team.players}})
    return render_template("match_live.html", **ctx_state)


@app.route("/match/live/advance", methods=["POST"])
@login_required
def match_live_advance():
    state = get_state()
    gid = session.get("game_id")
    ctx = LIVE.get(gid)
    if not ctx:
        return redirect(url_for("match_page"))
    mode = request.form.get("mode", "quarter")
    engine = ctx.engine
    if mode == "moment":
        engine.advance_moment()
    elif mode == "rest":
        while not engine.finished:
            engine.advance_quarter()
    else:
        engine.advance_quarter()
    return redirect(url_for("match_live"))


@app.route("/match/live/tactics", methods=["POST"])
@login_required
def match_live_tactics():
    state = get_state()
    gid = session.get("game_id")
    ctx = LIVE.get(gid)
    if not ctx:
        return redirect(url_for("match_page"))
    for field in ("mentality", "press", "block", "width", "tempo", "passing", "pc_routine"):
        value = request.form.get(field)
        if value:
            setattr(state.user_team.tactics, field, value)
    return redirect(url_for("match_live"))


@app.route("/match/live/sub", methods=["POST"])
@login_required
def match_live_sub():
    state = get_state()
    gid = session.get("game_id")
    ctx = LIVE.get(gid)
    if not ctx:
        return redirect(url_for("match_page"))
    out_id = request.form.get("out_id", "")
    in_id = request.form.get("in_id", "")
    ok, msg = ctx.engine.manual_substitute(ctx.user_side, out_id, in_id, coaching=True)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("match_live"))


@app.route("/match/live/finish", methods=["POST"])
@login_required
def match_live_finish():
    state = get_state()
    gid = session.get("game_id")
    ctx = LIVE.get(gid)
    if not ctx:
        return redirect(url_for("match_page"))
    if not ctx.engine.finished:
        ctx.engine.simulate()
    payload = finish_live_round(state, ctx)
    LIVE.pop(gid, None)
    save_state(state)
    return redirect(url_for("match_report"))


@app.route("/match/report")
@login_required
def match_report():
    state = get_state()
    payload = state.last_result
    if not payload:
        flash("No hay parte de partido.", "warning")
        return redirect(url_for("dashboard"))
    ctx = state_context(state)
    ctx["p"] = payload
    return render_template("match_report.html", **ctx)


@app.route("/season/end")
@login_required
def season_end():
    state = get_state()
    if state.phase != "season_end":
        return redirect(url_for("dashboard"))
    ctx = state_context(state)
    ctx["summary"] = season_summary(state)
    return render_template("season_end.html", **ctx)


@app.route("/season/continue", methods=["POST"])
@login_required
def season_continue():
    state = get_state()
    if state.phase != "season_end":
        return redirect(url_for("dashboard"))
    advance_to_next_season(state)
    save_state(state)
    flash(f"Nueva temporada: {state.season} · {state.competition}.", "success")
    return redirect(url_for("dashboard"))


@app.route("/new-season")
@login_required
def new_season_redirect():
    return redirect(url_for("season_end"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False, threaded=False)
