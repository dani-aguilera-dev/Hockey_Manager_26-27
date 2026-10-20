"""Interfaz de texto del Hockey Manager (Fase 1).

Sin gráficos: tablas, decisiones y comentario textual. El motor y la
persistencia son independientes de esta capa.
"""
from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

from .models import GameState, PlayerState, TeamState, FORMATION_SLOTS
from .data_loader import load_clubs, load_teams, dha_teams
from .calendar import dha_table
from .logistics import travel_options
from .season import new_game, play_round, make_lineup, season_summary, _best_dhb_team
from .persistence import DEFAULT_DB, save_game, load_game, list_saves

W = 100
WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
POS_ORDER = {"Portero": 0, "Central": 1, "Lateral": 2, "Medio": 3, "Delantero": 4, "Polivalente": 5}


def header(title: str):
    print("\n" + "=" * W)
    print(title.center(W))
    print("=" * W)


def section(title: str):
    print("\n" + title)
    print("-" * W)


def line():
    print("-" * W)


def money(n: int | float) -> str:
    return f"{int(round(n)):,}".replace(",", ".") + " €"


def fmt_date(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except Exception:
        return iso
    return f"{WEEKDAYS[d.weekday()].capitalize()} {d.day:02d}/{d.month:02d}/{d.year}"


def short(s: str, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 3] + "..."


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)


def pause(msg: str = "Pulsa Enter para continuar..."):
    ask(msg)


def wrap(text: str, width: int = W, indent: str = "") -> str:
    return "\n".join(textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent))


def status(p: PlayerState) -> str:
    if p.injury > 0:
        return f"Lesionado ({p.injury})"
    if p.suspension > 0:
        return f"Sancionado ({p.suspension})"
    return "Disponible"


def difficulty(expectation: str) -> str:
    e = expectation.lower()
    if "título" in e or "final four" in e:
        return "Muy alta"
    if "top 4" in e:
        return "Alta"
    if "top 6" in e or "consolidar" in e:
        return "Media"
    if "permanencia" in e or "salvación" in e:
        return "Baja"
    return "Media"


class GameUI:
    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.clubs_by_id, self.cities = load_clubs()
        self.state: GameState | None = None

    # ------------------------------------------------------------------ inicio
    def run(self):
        while True:
            header("HOCKEY MANAGER ESPAÑA 2026-27")
            print("  Liga IATI · DHA · DHB · Primera Andaluza")
            print("\n  1. Nueva partida")
            print("  2. Cargar partida")
            print("  3. Salir")
            op = ask("\n  > ")
            if op == "1":
                self.new_game_flow()
            elif op == "2":
                self.load_flow()
            elif op == "3":
                print("\nHasta la próxima temporada.")
                return

    def new_game_flow(self):
        manager = ask("Nombre del entrenador (Enter = Entrenador): ") or "Entrenador"
        team = self.choose_club()
        if not team:
            return
        raw_seed = ask("\nSemilla aleatoria (Enter = aleatoria): ")
        seed = int(raw_seed) if raw_seed.isdigit() else None
        print(f"\nCreando partida con {team.name}...")
        self.state = new_game(team.id, manager, seed)
        self.dashboard()

    def load_flow(self):
        saves = list_saves(self.db_path)
        if not saves:
            print("\nNo hay partidas guardadas.")
            pause()
            return
        section("PARTIDAS GUARDADAS")
        print(f"{'#':>3}  {'Nombre':<44} {'Club':<30} {'J':>3}  Actualizado")
        for s in saves:
            print(f"{s['id']:>3}  {short(s['name'],44):<44} {short(s['club_id'],30):<30} {s['round']:>3}  {s['updated_at']}")
        raw = ask("\nNúmero o nombre de la partida (Enter = volver): ")
        if not raw:
            return
        try:
            self.state = load_game(raw, self.db_path)
        except Exception as e:
            print(f"\nNo se pudo cargar: {e}")
            pause()
            return
        print(f"\nPartida cargada: {self.state.user_team.name} · J{self.state.round}")
        if self.state.phase == "season_end":
            self.season_end_screen()
        else:
            self.dashboard()

    # ------------------------------------------------------------- club
    def choose_club(self) -> TeamState | None:
        teams, _, _ = load_teams()
        dha = sorted([t for t in teams.values() if t.league == "DHA"], key=lambda t: t.name)
        while True:
            section("ELIGE TU CLUB · DHA")
            print(f"{'#':>3}  {'Club':<36} {'Ciudad':<18} {'Estadio':<30} {'Exigencia':<10}")
            line()
            for i, t in enumerate(dha, 1):
                club = self.clubs_by_id.get(t.id, {})
                stadium = club.get("stadium", {}).get("name", t.stadium_name)
                print(f"{i:>3}  {short(t.name,36):<36} {short(t.city,18):<18} {short(stadium,30):<30} {difficulty(t.board_expectation):<10}")
            raw = ask("\nNúmero de club (Enter = volver): ")
            if not raw:
                return None
            if not raw.isdigit() or not (1 <= int(raw) <= len(dha)):
                print("Opción no válida.")
                continue
            team = dha[int(raw) - 1]
            self.show_dossier(team)
            ok = ask("\n[Enter] aceptar el puesto   [V] volver: ").lower()
            if ok in ("", "s", "enter"):
                return team

    def show_dossier(self, team: TeamState):
        club = self.clubs_by_id.get(team.id, {})
        st = club.get("stadium", {})
        fin = club.get("finances", {})
        board = club.get("board", {})
        logi = club.get("logistics", {})
        line, _ = team.auto_lineup()
        attack, defense = team.lineup_strength(line)
        top = sorted(team.players, key=lambda p: p.overall, reverse=True)[:3]
        header(team.name.upper())
        print(f"{club.get('full_name', team.name)} · Fundado en {club.get('founded', '?')} · {team.city}")
        print(f"Colores: {', '.join(club.get('colors', [])) or '—'} · Liga: {team.league}")
        print(f"Estadio: {st.get('name', team.stadium_name)} · {st.get('capacity', team.stadium_capacity)} espectadores · {st.get('surface', '—')}")
        section("HISTORIA")
        print(wrap(club.get("history", "Sin historia registrada.")))
        section("JUNTA DIRECTIVA")
        print(f"Objetivo: {board.get('expectation', team.board_expectation)}")
        print(f"Presión: {board.get('pressure', '—')} · Paciencia: {board.get('patience', '—')}/5")
        print(f"Presupuesto de fichajes: {money(fin.get('transfer_budget', team.budget))} · Masa salarial: {money(fin.get('wage_budget', team.wage_budget))}")
        section("LOGÍSTICA")
        print(f"Aeropuerto: {logi.get('airport', '—')} · Tren: {logi.get('train', '—')} · Modo habitual: {logi.get('preferred_mode', '—')}")
        print(wrap(logi.get("notes", ""), indent="  "))
        section("PLANTILLA")
        print(f"{len(team.players)} fichas · {len(team.squad)} jugadores de plantilla · Fuerza estimada: ataque {attack:.1f} / defensa {defense:.1f}")
        print("Jugadores clave:")
        for p in top:
            print(f"  · {p.name:<34} {p.subposition:<10} OVR {p.overall:>4.1f} · {p.archetype}")
        if club.get("rivalries"):
            print(f"Rivalidades: {', '.join(club['rivalries'])}")

    # ------------------------------------------------------------- dashboard
    def dashboard(self):
        while self.state and self.state.phase == "regular":
            self.print_dashboard()
            print("\n  1. Jugar próximo partido")
            print("  2. Plantilla y ficha de jugador")
            print("  3. Táctica y once inicial")
            print("  4. Calendario y clasificación")
            print("  5. Club y estadio")
            print("  6. Finanzas")
            print("  7. Logística")
            print("  8. Guardar partida")
            print("  9. Salir")
            print("  A. Simular jornada (auto)")
            op = ask("\n  > ").lower()
            if op == "1":
                self.matchday()
            elif op == "2":
                self.squad_screen()
            elif op == "3":
                self.tactics_screen()
            elif op == "4":
                self.calendar_screen()
            elif op == "5":
                self.club_screen()
            elif op == "6":
                self.finances_screen()
            elif op == "7":
                self.logistics_screen()
            elif op == "8":
                self.save_flow()
            elif op == "9":
                self.exit_flow()
                return
            elif op == "a":
                self.auto_round()
            else:
                print("Opción no válida.")
        if self.state and self.state.phase == "season_end":
            self.season_end_screen()

    def print_dashboard(self):
        s = self.state
        t = s.user_team
        header(f"DASHBOARD · {fmt_date(s.date)} · {t.name.upper()} · DHA")
        fx = s.next_user_fixture()
        if fx:
            home = s.teams[fx.home_id]
            away = s.teams[fx.away_id]
            rival = away if home.id == t.id else home
            venue = "casa" if home.id == t.id else "fuera"
            print(f"Próximo partido:  {home.name} vs {away.name}")
            print(f"Jornada {fx.round} · {fmt_date(fx.date)} · {venue} · {rival.stadium_name if venue == 'fuera' else t.stadium_name}")
        else:
            print("Próximo partido:  temporada regular finalizada")
        table = dha_table(s.teams)
        pos = next((i for i, x in enumerate(table, 1) if x.id == t.id), 0)
        print(f"Posición: {pos}º/12 · {t.points} pts · {t.played} PJ · {t.won}G {t.drawn}E {t.lost}P · GF {t.goals_for} / GC {t.goals_against}")
        print(f"Forma: {self.form_string()} · Moral: {t.morale}/20 · Junta: {t.board_confidence}/100 · Afición: {t.fan_confidence}/100")
        print(f"Presupuesto: {money(t.budget)} · Masa salarial: {money(t.wage_budget)}")
        inj = sum(1 for p in t.players if p.injury > 0)
        sus = sum(1 for p in t.players if p.suspension > 0)
        print(f"Bajas: {inj} lesionados · {sus} sancionados · Fatiga media: {sum(p.fatigue for p in t.players)/max(1,len(t.players)):.1f}%")
        section("INBOX")
        for msg in s.inbox[-3:]:
            print(f"  [{msg.get('date', '')}] {msg.get('from', '')}: {msg.get('subject', '')}")
            print(f"      {short(msg.get('body', ''), 110)}")

    def form_string(self) -> str:
        s = self.state
        played = [f for f in s.fixtures if f.phase == "regular" and f.played and s.club_id in (f.home_id, f.away_id)]
        played.sort(key=lambda f: f.round)
        out = []
        for f in played[-5:]:
            gf = f.home_goals if f.home_id == s.club_id else f.away_goals
            ga = f.away_goals if f.home_id == s.club_id else f.home_goals
            out.append("V" if gf > ga else ("E" if gf == ga else "D"))
        return " ".join(out) if out else "—"

    # ------------------------------------------------------------- plantilla
    def squad_screen(self):
        s = self.state
        t = s.user_team
        while True:
            header(f"PLANTILLA · {t.name.upper()}")
            players = sorted(t.players, key=lambda p: (POS_ORDER.get(p.subposition, 9), -p.overall))
            print(f"{'#':>3}  {'Jugador':<34} {'Pos':<10} {'Edad':>4} {'OVR':>5} {'Forma':>5} {'Fatiga':>6} {'Moral':>5}  Estado")
            line()
            for i, p in enumerate(players, 1):
                print(f"{i:>3}  {short(p.name,34):<34} {p.subposition:<10} {p.age:>4} {p.overall:>5.1f} {p.form:>5.1f} {p.fatigue:>5.0f}% {p.morale:>5}  {status(p)}")
            raw = ask("\nNúmero para ficha · V volver: ").lower()
            if raw in ("v", ""):
                return
            if raw.isdigit() and 1 <= int(raw) <= len(players):
                self.player_detail(players[int(raw) - 1])
            else:
                print("Opción no válida.")

    def player_detail(self, p: PlayerState):
        t = self.state.user_team
        header(f"FICHA · {p.name.upper()}")
        print(f"{p.subposition} · {p.age} años · {t.name} · {p.perfil} · {p.archetype}")
        print(f"Overall: {p.overall:.1f} · Potencial: {p.potential:.1f} · Valor: {money(p.value)} · Polivalencia: {p.polivalencia:.1f}")
        if p.overalls:
            print("Overalls por posición: " + " · ".join(f"{k} {v:.1f}" for k, v in p.overalls.items()))
        print(f"Temporada: {p.apps} PJ · {p.season_goals} goles · {p.season_assists} asistencias · Rating {p.rating:.2f}")
        print(f"Estado: {status(p)} · Fatiga: {p.fatigue:.0f}% · Moral: {p.morale}/20 · Forma: {p.form:.1f}")
        groups = [
            ("TÉCNICA", ["control", "pase", "conduccion", "golpeo", "flick", "regate_3d", "definicion"]),
            ("AÉREA / SET PIECES", ["aerial", "pc_injection", "pc_trap", "pc_flick", "pc_deflection", "pc_first_runner", "pc_gk_save", "stroke_shot", "stroke_save", "free_hit"]),
            ("TÁCTICA", ["posicionamiento", "pressing", "cobertura", "transicion", "desmarque"]),
            ("FÍSICA", ["velocidad", "resistencia", "fuerza", "agilidad", "coordinacion"]),
            ("MENTAL", ["decisiones", "concentracion", "competitividad", "liderazgo"]),
            ("PORTERO", ["reflejos", "blocaje", "distribucion", "uno_vs_uno", "alto", "rebote_gk"]),
        ]
        for title, keys in groups:
            vals = [f"{k.replace('_', ' ').title()} {p.attributes.get(k, 0)}" for k in keys if k in p.attributes]
            if vals:
                section(title)
                print(wrap(" · ".join(vals)))
        pause()

    # ------------------------------------------------------------- táctica
    def tactics_screen(self):
        s = self.state
        t = s.user_team
        while True:
            header(f"TÁCTICA · {t.name.upper()}")
            tac = t.tactics
            print(f"Formación: {tac.formation} · Mentalidad: {tac.mentality.replace('_', ' ')} · Presión: {tac.press.replace('_', ' ')}")
            print(f"Bloque: {tac.block.replace('_', ' ')} · Anchura: {tac.width.replace('_', ' ')} · Tempo: {tac.tempo.replace('_', ' ')} · Pase: {tac.passing.replace('_', ' ')} · PC: {tac.pc_routine.replace('_', ' ')}")
            line, bench = make_lineup(t, s.manual_lineup or None)
            section("ONCE INICIAL")
            slots = FORMATION_SLOTS.get(tac.formation, FORMATION_SLOTS["4-3-3"])
            for i, slot in enumerate(slots):
                p = line[i] if i < len(line) else None
                if p:
                    print(f"  {slot:<4} {p.name:<36} OVR {p.overall:>4.1f} · Fatiga {p.fatigue:>3.0f}% · {status(p)}")
            print("\nBANQUILLO: " + ", ".join(p.name for p in bench[:7]))
            spec = t.specialists(line)
            section("ESPECIALISTAS")
            labels = {
                "pc_injector": "Inyector PC", "pc_stopper": "Stopper PC", "pc_flicker": "Drag flicker",
                "pc_deflector": "Desviador PC", "pc_first_runner": "Primer runner", "pc_goalkeeper": "Portero PC",
                "stroke_taker": "Stroke", "stroke_goalkeeper": "Portero stroke", "free_hit_taker": "Faltas",
            }
            for k, label in labels.items():
                p = spec.get(k)
                print(f"  {label:<16}: {p.name if p else '—'}")
            print("\n  1. Formación   2. Mentalidad   3. Presión   4. Bloque   5. Anchura")
            print("  6. Tempo       7. Pase         8. Rutina PC  9. Autoalineación  10. Elegir once manual")
            print("  V. Volver")
            op = ask("\n  > ").lower()
            if op == "1":
                tac.formation = self.choose_option("Formación", list(FORMATION_SLOTS), tac.formation)
            elif op == "2":
                tac.mentality = self.choose_option("Mentalidad", ["muy_defensiva", "defensiva", "equilibrada", "ofensiva", "muy_ofensiva"], tac.mentality)
            elif op == "3":
                tac.press = self.choose_option("Presión", ["baja", "media", "alta", "muy_alta"], tac.press)
            elif op == "4":
                tac.block = self.choose_option("Bloque", ["bajo", "medio", "alto"], tac.block)
            elif op == "5":
                tac.width = self.choose_option("Anchura", ["estrecha", "normal", "ancha"], tac.width)
            elif op == "6":
                tac.tempo = self.choose_option("Tempo", ["lento", "normal", "rapido"], tac.tempo)
            elif op == "7":
                tac.passing = self.choose_option("Pase", ["corto", "mixto", "directo"], tac.passing)
            elif op == "8":
                tac.pc_routine = self.choose_option("Rutina PC", ["directa", "slip_izquierda", "slip_derecha", "desvio", "rebote"], tac.pc_routine)
            elif op == "9":
                s.manual_lineup = []
                print("Once automático activado.")
            elif op == "10":
                ids = self.choose_lineup(t, s.manual_lineup)
                if ids:
                    s.manual_lineup = ids
                    print("Once manual guardado para el próximo partido.")
            elif op in ("v", ""):
                return

    def choose_option(self, title: str, options: list[str], current: str) -> str:
        section(title.upper())
        for i, opt in enumerate(options, 1):
            mark = "  <-- actual" if opt == current else ""
            print(f"  {i}. {opt.replace('_', ' ')}{mark}")
        raw = ask("Opción (Enter = mantener): ")
        if not raw:
            return current
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("Opción no válida.")
        return current

    def choose_lineup(self, team: TeamState, current_ids: list[str] | None = None) -> list[str] | None:
        available = team.available_players
        if len(available) < 11:
            print(f"\nSolo hay {len(available)} jugadores disponibles. Se usará la autoalineación.")
            pause()
            return None
        players = sorted(available, key=lambda p: (POS_ORDER.get(p.subposition, 9), -p.overall))
        current = set(current_ids or [])
        section("ELIGE EL ONCE INICIAL")
        print(f"{'#':>3}  {'Jugador':<34} {'Pos':<10} {'OVR':>5} {'Fatiga':>6}  Estado")
        line()
        for i, p in enumerate(players, 1):
            mark = "*" if p.id in current else " "
            print(f"{mark}{i:>2}  {short(p.name,34):<34} {p.subposition:<10} {p.overall:>5.1f} {p.fatigue:>5.0f}%  {status(p)}")
        raw = ask("\nEscribe 11 números separados por comas (A = auto, V = volver): ").strip()
        if raw.lower() in ("v", "", "a"):
            return None
        try:
            nums = [int(x.strip()) for x in raw.split(",") if x.strip()]
        except ValueError:
            print("Formato no válido.")
            pause()
            return None
        if len(nums) != 11 or len(set(nums)) != 11 or any(n < 1 or n > len(players) for n in nums):
            print("Debes elegir exactamente 11 jugadores distintos de la lista.")
            pause()
            return None
        return [players[n - 1].id for n in nums]

    # ------------------------------------------------------------- calendario
    def calendar_screen(self):
        s = self.state
        t = s.user_team
        header(f"CALENDARIO Y CLASIFICACIÓN · {t.name.upper()}")
        section("CLASIFICACIÓN DHA")
        table = dha_table(s.teams)
        print(f"{'#':>3}  {'Equipo':<38} {'PJ':>3} {'G':>3} {'E':>3} {'P':>3} {'GF':>3} {'GC':>3} {'DG':>4} {'PTS':>4}")
        line()
        for i, x in enumerate(table, 1):
            print(f"{i:>3}  {short(x.name,38):<38} {x.played:>3} {x.won:>3} {x.drawn:>3} {x.lost:>3} {x.goals_for:>3} {x.goals_against:>3} {x.goals_for-x.goals_against:>+4} {x.points:>4}")
        section("CALENDARIO DEL EQUIPO")
        user_fx = [f for f in s.fixtures if f.phase == "regular" and t.id in (f.home_id, f.away_id)]
        user_fx.sort(key=lambda f: f.round)
        for f in user_fx:
            home = s.teams[f.home_id].name
            away = s.teams[f.away_id].name
            if f.played:
                res = f"{f.home_goals}-{f.away_goals}"
            else:
                res = "vs"
            marker = " <<< próximo" if not f.played and s.next_user_fixture() and f.id == s.next_user_fixture().id else ""
            print(f"  J{f.round:>2}  {fmt_date(f.date):<24} {short(home,30):<30} {res:^7} {short(away,30):<30}{marker}")
        pause()

    def club_screen(self):
        self.show_dossier(self.state.user_team)
        pause()

    # ------------------------------------------------------------- finanzas
    def finances_screen(self):
        s = self.state
        t = s.user_team
        header(f"FINANZAS · {t.name.upper()} · {s.season}")
        gate = sum(int(f.home_stats.get("gate_revenue", 0)) for f in s.fixtures if f.phase == "regular" and f.home_id == t.id and f.played)
        travel = sum(int(f.travel.get("cost", 0)) for f in s.fixtures if f.phase == "regular" and f.away_id == t.id and f.travel)
        print(f"Presupuesto actual:      {money(t.budget)}")
        print(f"Masa salarial anual:     {money(t.wage_budget)}")
        print(f"Taquilla acumulada:      {money(gate)}")
        print(f"Viajes acumulados:       {money(travel)}")
        print(f"Balance de explotación:  {money(gate - travel)}  (taquilla - viajes; sin salarios en Fase 1)")
        print(f"Objetivo de la junta:    {t.board_expectation}")
        print(f"Confianza de la junta:   {t.board_confidence}/100")
        print(f"Confianza de la afición: {t.fan_confidence}/100")
        if t.budget < 0:
            print("\nALERTA: el presupuesto está en negativo. La junta puede perder la paciencia.")
        last = s.last_result
        if last:
            section("ÚLTIMO PARTIDO")
            print(f"{last.get('home_name')} {last.get('home_goals')}-{last.get('away_goals')} {last.get('away_name')}")
            print(f"Asistencia: {last.get('attendance', 0)} · Taquilla: {money(last.get('home_stats', {}).get('gate_revenue', 0))}")
            tr = last.get("travel") or {}
            if tr:
                print(f"Viaje: {tr.get('mode', '—')} · {tr.get('distance_km', '—')} km · coste {money(tr.get('cost', 0))} · fatiga +{tr.get('fatigue_add', 0)}")
        pause()

    # ------------------------------------------------------------- logística
    def logistics_screen(self):
        s = self.state
        t = s.user_team
        header(f"LOGÍSTICA · {t.name.upper()}")
        fx = s.next_user_fixture()
        if not fx:
            print("No hay próximo partido.")
            pause()
            return
        if fx.home_id == t.id:
            print(f"Próximo partido en casa: {t.name} vs {s.teams[fx.away_id].name}")
            print(f"Estadio: {t.stadium_name} · Sin desplazamiento.")
        else:
            rival = s.teams[fx.home_id]
            print(f"Próximo partido fuera: {rival.name} vs {t.name}")
            print(f"Estadio rival: {rival.stadium_name} · {rival.city}")
            opts = travel_options(t, rival, self.cities, squad_size=18)
            print("\nOpciones de viaje:")
            for i, o in enumerate(opts, 1):
                print(f"  {i}. {o['label']:<26} {o['mode']:<7} {o['distance_km']:>5} km · {o['hours']:>4} h · {money(o['cost']):>10} · fatiga +{o['fatigue']*100:.0f}% · {o['hotel_nights']} noche(s)")
                print(f"     {o['notes']}")
        section("ESTADO FÍSICO")
        players = sorted(t.players, key=lambda p: p.fatigue, reverse=True)[:6]
        for p in players:
            print(f"  {p.name:<36} fatiga {p.fatigue:>5.1f}% · {status(p)}")
        print(f"\nModo habitual del club: {t.preferred_mode or '—'}")
        pause()

    # ------------------------------------------------------------- partido
    def matchday(self):
        s = self.state
        t = s.user_team
        fx = s.next_user_fixture()
        if not fx:
            print("No hay partido pendiente.")
            pause()
            return
        while True:
            home = s.teams[fx.home_id]
            away = s.teams[fx.away_id]
            rival = away if home.id == t.id else home
            header(f"PREVIA · JORNADA {fx.round} · {fmt_date(fx.date)}")
            print(f"{home.name} vs {away.name}")
            print(f"Estadio: {home.stadium_name} · {home.city}")
            pos = next((i for i, x in enumerate(dha_table(s.teams), 1) if x.id == rival.id), 0)
            print(f"Rival: {rival.name} · {pos}º · {rival.points} pts · GF {rival.goals_for} / GC {rival.goals_against} · Moral {rival.morale}/20")
            line, bench = make_lineup(t, s.manual_lineup or None)
            section("ONCE INICIAL")
            slots = FORMATION_SLOTS.get(t.tactics.formation, FORMATION_SLOTS["4-3-3"])
            for i, slot in enumerate(slots):
                p = line[i] if i < len(line) else None
                print(f"  {slot:<4} {p.name if p else '—':<36} " + (f"OVR {p.overall:>4.1f} · Fatiga {p.fatigue:>3.0f}%" if p else ""))
            print("\nBANQUILLO: " + ", ".join(p.name for p in bench[:7]))
            print("\n[Enter] jugar   [M] elegir once manual   [T] táctica   [V] volver")
            op = ask("  > ").lower()
            if op in ("v",):
                return
            if op == "t":
                self.tactics_screen()
                continue
            if op == "m":
                ids = self.choose_lineup(t, s.manual_lineup)
                if ids:
                    s.manual_lineup = ids
                continue
            if op not in ("", "j"):
                print("Opción no válida.")
                continue
            break
        # viaje
        travel_id = None
        if fx.away_id == t.id:
            opts = travel_options(t, home, self.cities, squad_size=18)
            section("VIAJE")
            for i, o in enumerate(opts, 1):
                print(f"  {i}. {o['label']:<26} {o['mode']:<7} {o['distance_km']:>5} km · {money(o['cost']):>10} · fatiga +{o['fatigue']*100:.0f}% · {o['hotel_nights']} noche(s)")
                print(f"     {o['notes']}")
            default = next((i for i, o in enumerate(opts, 1) if o["id"] == "equilibrado"), 1)
            raw = ask(f"\nElige viaje (Enter = {default}): ")
            idx = int(raw) if raw.isdigit() and 1 <= int(raw) <= len(opts) else default
            chosen = opts[idx - 1]
            if chosen["cost"] > t.budget:
                print(f"\nAviso: el viaje cuesta {money(chosen['cost'])} y el presupuesto es {money(t.budget)}. Se elegirá la opción más barata.")
                chosen = min(opts, key=lambda o: o["cost"])
            travel_id = chosen["id"]
            print(f"Viaje elegido: {chosen['label']} · {money(chosen['cost'])} · fatiga +{chosen['fatigue']*100:.0f}%")
        else:
            print("\nPartido en casa: sin desplazamiento.")
        confirm = ask("\n¿Jugar el partido? (s/n): ").lower()
        if confirm not in ("s", "si", "sí", ""):
            return
        payload = play_round(s, user_lineup_ids=s.manual_lineup or None, travel_option_id=travel_id)
        if not payload:
            print("No se pudo simular el partido.")
            pause()
            return
        self.print_match_report(payload)
        pause()

    def print_match_report(self, p: dict):
        header(f"RESULTADO · {p['home_name'].upper()} {p['home_goals']}-{p['away_goals']} {p['away_name'].upper()}")
        print(f"{fmt_date(p['date'])} · Jornada {p['round']} · Asistencia: {p.get('attendance', 0)}")
        print(f"Perspectiva: {p['result']} ({p['user_goals']}-{p['user_against']})")
        section("COMENTARIO")
        key_types = {"goal", "pc", "stroke", "save", "card", "injury", "substitution", "chance", "circle_entry"}
        events = [e for e in p.get("events", []) if e.get("type") in key_types]
        current_q = None
        for e in events:
            if e.get("quarter") != current_q:
                current_q = e.get("quarter")
                print(f"\n  --- Cuarto {current_q} ---")
            prefix = {"goal": ">>> ", "save": "  ! ", "card": "  # ", "injury": "  + ", "substitution": "  -> ", "pc": "  PC ", "stroke": "  ST "}.get(e.get("type"), "  · ")
            print(f"  {e.get('minute', 0):02d}' {prefix}{e.get('text', '')}")
        if not events:
            print("  Partido sin incidencias destacadas.")
        if p.get("shootout"):
            so = p["shootout"]
            print(f"\n  Shootout: {so.get('home_score')}-{so.get('away_score')} · Ganador: {self.state.teams[so['winner_id']].name}")
        section("ESTADÍSTICAS")
        hs, as_ = p.get("home_stats", {}), p.get("away_stats", {})
        rows = [
            ("Posesión", f"{hs.get('possession', 0)}%", f"{as_.get('possession', 0)}%"),
            ("Tiros", hs.get("shots", 0), as_.get("shots", 0)),
            ("Tiros a puerta", hs.get("shots_on_target", 0), as_.get("shots_on_target", 0)),
            ("Penalty corners", hs.get("pc", 0), as_.get("pc", 0)),
            ("Goles de PC", hs.get("pc_goals", 0), as_.get("pc_goals", 0)),
            ("Strokes", hs.get("strokes", 0), as_.get("strokes", 0)),
            ("Paradas", hs.get("saves", 0), as_.get("saves", 0)),
            ("Tarjetas V/A/R", f"{hs.get('green',0)}/{hs.get('yellow',0)}/{hs.get('red',0)}", f"{as_.get('green',0)}/{as_.get('yellow',0)}/{as_.get('red',0)}"),
            ("Entradas al círculo", hs.get("circle_entries", 0), as_.get("circle_entries", 0)),
            ("Pases completados", f"{hs.get('passes_completed',0)}/{hs.get('passes',0)}", f"{as_.get('passes_completed',0)}/{as_.get('passes',0)}"),
        ]
        print(f"{'Estadística':<24} {short(p['home_name'],28):>28} {short(p['away_name'],28):>28}")
        for label, hv, av in rows:
            print(f"{label:<24} {str(hv):>28} {str(av):>28}")
        section("RATINGS DEL EQUIPO")
        ratings = p.get("ratings", {})
        for name, r in sorted(ratings.items(), key=lambda x: -x[1])[:8]:
            print(f"  {name:<38} {r:>5.2f}")
        section("INCIDENCIAS")
        inc = [e for e in p.get("events", []) if e.get("type") in ("injury", "card")]
        if inc:
            for e in inc:
                print(f"  {e.get('minute', 0):02d}' {e.get('text', '')}")
        else:
            print("  Sin lesiones ni tarjetas.")
        tr = p.get("travel") or {}
        if tr:
            section("VIAJE")
            print(f"  {tr.get('from')} → {tr.get('to')} · {tr.get('mode')} · {tr.get('distance_km')} km · {tr.get('hotel_nights')} noche(s) · coste {money(tr.get('cost', 0))} · fatiga +{tr.get('fatigue_add', 0)}")
        section("OTROS RESULTADOS")
        for f in self.state.fixtures:
            if f.phase == "regular" and f.round == p["round"] and f.played and self.state.club_id not in (f.home_id, f.away_id):
                print(f"  {short(self.state.teams[f.home_id].name,34):<34} {f.home_goals}-{f.away_goals} {short(self.state.teams[f.away_id].name,34)}")
        nxt = self.state.next_user_fixture()
        if nxt:
            print(f"\nPróximo partido: {self.state.teams[nxt.home_id].name} vs {self.state.teams[nxt.away_id].name} · {fmt_date(nxt.date)}")
        else:
            print("\nTemporada regular finalizada.")

    def auto_round(self):
        s = self.state
        s.manual_lineup = []
        payload = play_round(s, user_lineup_ids=None, travel_option_id="equilibrado")
        if payload:
            print(f"\nJ{payload['round']}: {payload['home_name']} {payload['home_goals']}-{payload['away_goals']} {payload['away_name']} · {payload['result']}")
            table = dha_table(s.teams)
            pos = next((i for i, t in enumerate(table, 1) if t.id == s.club_id), 0)
            print(f"Posición: {pos}º · {s.user_team.points} pts")
        pause()

    # ------------------------------------------------------------- guardar / salir
    def save_flow(self):
        default = f"{self.state.user_team.name} · {self.state.season} · J{self.state.round}"
        name = ask(f"Nombre de la partida (Enter = {default}): ") or default
        try:
            save_game(self.state, name, self.db_path)
            print(f"Partida guardada: {name}")
        except Exception as e:
            print(f"No se pudo guardar: {e}")
        pause()

    def exit_flow(self):
        raw = ask("¿Guardar antes de salir? (s/n): ").lower()
        if raw in ("s", "si", "sí"):
            self.save_flow()

    # ------------------------------------------------------------- fin de temporada
    def season_end_screen(self):
        s = self.state
        summ = season_summary(s)
        header(f"FIN DE TEMPORADA · {s.season}")
        print(f"Campeón de DHA: {summ.get('champion') or '—'}")
        print(f"Tu club: {s.user_team.name} · Posición: {summ.get('user_position')}º/12")
        section("CLASIFICACIÓN FINAL")
        print(f"{'#':>3}  {'Equipo':<40} {'PJ':>3} {'G':>3} {'E':>3} {'P':>3} {'GF':>3} {'GC':>3} {'DG':>4} {'PTS':>4}")
        for row in summ.get("table", []):
            print(f"{row['position']:>3}  {short(row['team'],40):<40} {row['played']:>3} {row['won']:>3} {row['drawn']:>3} {row['lost']:>3} {row['gf']:>3} {row['ga']:>3} {row['gd']:>+4} {row['points']:>4}")
        section("FINAL FOUR")
        f4 = summ.get("final4") or {}
        for i, sf in enumerate(f4.get("semifinals", []), 1):
            h = s.teams.get(sf.get("home_id"), None)
            a = s.teams.get(sf.get("away_id"), None)
            print(f"  SF{i}: {h.name if h else '—'} {sf.get('home_goals')}-{sf.get('away_goals')} {a.name if a else '—'} · pasa {s.teams[sf['winner_id']].name if sf.get('winner_id') in s.teams else '—'}")
        fin = f4.get("final") or {}
        if fin:
            h = s.teams.get(fin.get("home_id"), None)
            a = s.teams.get(fin.get("away_id"), None)
            print(f"  FINAL: {h.name if h else '—'} {fin.get('home_goals')}-{fin.get('away_goals')} {a.name if a else '—'} · campeón {s.teams[f4['champion_id']].name if f4.get('champion_id') in s.teams else '—'}")
        p = summ.get("playout") or {}
        if p:
            h = s.teams.get(p.get("home_id"), None)
            a = s.teams.get(p.get("away_id"), None)
            print(f"  PLAYOUT: {h.name if h else '—'} {p.get('home_goals')}-{p.get('away_goals')} {a.name if a else '—'}")
            if p.get("stays_id"):
                print(f"    El 11º clasificado mantiene la plaza; desciende el 12º: {summ.get('direct_relegated') or '—'}.")
            else:
                promoted = s.teams.get(p.get("promoted_id"), None)
                relegated = s.teams.get(p.get("relegated_id"), None)
                print(f"    Asciende {promoted.name if promoted else '—'}; desciende {relegated.name if relegated else '—'}. El 12º también baja: {summ.get('direct_relegated') or '—'}.")
            print(f"    {p.get('note','')}")
        section("MÁXIMOS GOLEADORES")
        for i, sc in enumerate(summ.get("top_scorers", [])[:10], 1):
            print(f"  {i:>2}. {sc['player']:<38} {sc['team']:<34} {sc['goals']:>3} goles · {sc['assists']:>2} asistencias")
        print("\n  [G] Guardar partida   [N] Nueva partida   [S] Salir")
        op = ask("  > ").lower()
        if op == "g":
            self.save_flow()
            self.season_end_screen()
        elif op == "n":
            self.new_game_flow()
        else:
            print("\nFin de la Fase 1. Gracias por jugar.")
            raise SystemExit(0)
