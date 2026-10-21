# Alpha web local

**Estado:** primera versión funcional (2026-10-21).

La alpha web es una capa Flask + Jinja sobre el motor existente. No reescribe la lógica: usa `GameState`, `MatchEngine`, mercado, entrenamiento, Copa, EHL, cantera y persistencia.

Para la investigación de color, usabilidad, escudos y componentes, ver [`16_DISENO_UI.md`](16_DISENO_UI.md).

---

## 1. Arrancar

```bash
cd /home/daniel/hockey_espana/manager
python3 run_web.py
```

Abrir:

```text
http://127.0.0.1:5000
```

También se puede usar otra base de datos:

```bash
HOCKEY_WEB_DB=/ruta/web.db python3 run_web.py
```

---

## 2. Qué incluye

- Nueva partida con club DHA o DHB.
- Carga y guardado de partidas en SQLite.
- Dashboard con ticker de última hora, próximo partido, clasificación, caja, entrenamiento, Copa e inbox.
- **Escudos oficiales de club** descargados de iSquad en `web/static/crests/` (29/29), con SVG estilizado como respaldo.
- **Noticias generadas** desde el estado: previa, resultado, liga, mercado, enfermería, cantera, scouting, afición, junta y Copa.
- **Fotos de los jugadores** servidas desde `jugadores/` con fallback a avatar.
- Plantilla en fichas por posición, con foto, posición y arquetipo destacados.
- Ficha de jugador con foto grande, badges y barras de atributos.
- Táctica y once: pizarrón de slots con foto, posición, arquetipo, OVR y selector por puesto.
- Mercado en fichas de jugador con foto, club, posición, arquetipo y escudo del propietario.
- Entrenamiento semanal: automático, recuperación o plan editado.
- Mercado: búsqueda, agentes libres, ofertas de traspaso, ofertas recibidas y renovaciones.
- Staff: contratar y despedir; junta directiva.
- Cantera: categorías Sub-16, Sub-18 y Sub-21; promover y liberar juveniles.
- Prensa.
- Copa del Rey de 8 equipos DHA.
- Clasificación y calendario.
- Partido rápido.
- Partido en directo: marcador con escudos, cuartos, momento a momento, estadísticas, cambios y táctica.
- Fin de temporada y multi-temporada.

---

## 3. Estructura

```text
manager/
  web/
    app.py
    templates/
    static/style.css
    static/crests/*.svg
    static/avatar.svg
  src/news.py
  run_web.py
```

- `app.py` mantiene `GameState` en memoria por sesión y guarda en SQLite.
- Las plantillas son HTML server-rendered.
- El partido en directo vive en memoria mientras se juega.
- Al terminar el partido se actualiza el estado y se guarda.

---

## 4. Persistencia

- Base por defecto: `manager/saves/web.db`.
- Cada partida se guarda como un blob JSON dentro de SQLite.
- El nombre de guardado se puede cambiar desde la barra superior.
- La alpha no guarda en mitad de un partido: si se reinicia el servidor, ese partido en directo se pierde.

---

## 5. Limitaciones

- Es una alpha local, sin login ni multiusuario.
- No hay guardado en mitad del partido.
- El partido en directo no tiene animación; es texto y tablas.
- Algunas pantallas son más simples que la CLI.
- El servidor de desarrollo de Flask no debe exponerse a Internet.
- La DHB no desciende a 1ª Andaluza porque esa liga no se simula.

---

## 6. Pruebas

```bash
cd manager
python3 -m pytest src/tests -q
```

Incluye pruebas de rutas web, nueva partida, fotos, escudos, noticias, entrenamiento, partido rápido, partido en directo y guardado/carga.

Resultado actual: **52 tests superados**.
