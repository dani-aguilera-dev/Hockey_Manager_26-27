# Hockey Manager España 2026-27

Diseño y prototipo de un juego de **entrenador y gestión de club** de hockey hierba, solo texto, inspirado en la arquitectura de Football Manager y adaptado a la DHA, la DHB y la Primera Andaluza.

## Estado

- **Diseño:** completo en `docs/`.
- **Datos:** 29 clubes, 16 ciudades, 976 perfiles, 37 atributos.
- **Fase 1 (vertical slice):** implementada. Una temporada DHA jugable, con partidos en directo, gestión interna, logística, clasificación, Final Four, playout y guardado/carga.
- **Fases 2–4:** pendientes (entrenamiento, mercado, staff, multi-temporada, DHB completa).

## Inicio rápido

Juego de terminal:

```bash
cd /home/daniel/hockey_espana/manager
python3 run.py
```

Alpha web local:

```bash
cd /home/daniel/hockey_espana/manager
python3 run_web.py
```

Abre `http://127.0.0.1:5000`.

Modo interactivo con una base de datos alternativa:

```bash
python3 run.py --db /ruta/mi_partida.db
```

Simular una temporada completa sin interacción:

```bash
python3 run.py --auto --club cd-terrassa --seed 7
```

Pruebas:

```bash
python3 -m pytest src/tests -q
```

La Fase 1 incluye:

- selección de club y dossier;
- dashboard;
- plantilla y ficha de jugador;
- táctica, once automático y once manual;
- calendario DHA de 22 jornadas y 132 partidos;
- motor de partido por fases con comentario de texto;
- **modo directo**: cuarto a cuarto o minuto a minuto, con estadísticas, jugadores, cambios y táctica en vivo;
- **charla de vestuario** al descanso, con opción de delegar en el segundo entrenador;
- **IA reactiva** que ajusta táctica y cambios según el marcador, la fatiga y tu planteamiento;
- **sistema de gestión**: moral, cohesión, fatiga, confianza, encaje posicional y rating del mánager que otorgan un bonus de hasta ±7 puntos;
- **entrenamiento semanal**: plan automático del segundo entrenador, editor de sesiones, recuperación y preparación del rival;
- **staff y finanzas**: siete roles de staff, junta directiva, salarios, patrocinio, taquilla, viajes y caja;
- **mercado y contratos**: ventanas de verano/invierno, ofertas, renovaciones, contratación de staff y mercado IA;
- **multi-temporada**: ascensos, descensos, DHA/DHB, contratos, canteranos y nueva temporada;
- **Copa del Rey**, cantera, rueda de prensa y junta directiva dinámica;
- **DHA y DHB jugables desde el inicio**, DHB real de dos fases, **agentes libres** procedentes de 1ª Andaluza, **Copa del Rey de 8 equipos DHA** y **EHL**;
- logística con bus/tren/avión, coste y fatiga;
- clasificación, Final Four y playout;
- guardado/carga SQLite.

No incluye todavía:

- entrenamiento semanal;
- mercado de fichajes;
- cantera;
- staff;
- prensa compleja;
- finanzas completas con salarios;
- liga DHB completa;
- multi-temporada.

## Estructura

```
manager/
  README.md
  docs/
    00_VISION_Y_ARQUITECTURA.md
    01_MOTOR_PARTIDO.md
    02_LOGISTICA.md
    03_CLUBES_Y_ESTADIOS.md
    04_UI_TEXTO.md
    05_ROADMAP_Y_MVP.md
  data/
    clubs.json
    cities.json
    competitions.json
    tactical_roles.json
    staff_roles.json
    events.json
  schema/
    schema.sql
  src/
    main.py
    ui.py
    models.py
    data_loader.py
    calendar.py
    match_engine.py
    logistics.py
    season.py
    persistence.py
    tests/
    prototype.py        # prototipo legado, se conserva como referencia
  saves/
```

## Documentación

1. [`docs/00_VISION_Y_ARQUITECTURA.md`](docs/00_VISION_Y_ARQUITECTURA.md) — visión, referencia de Football Manager, capas y módulos.
2. [`docs/01_MOTOR_PARTIDO.md`](docs/01_MOTOR_PARTIDO.md) — motor de texto, fases, atributos, set pieces y calibración.
3. [`docs/02_LOGISTICA.md`](docs/02_LOGISTICA.md) — viajes, costes, fatiga, clima y superficie.
4. [`docs/03_CLUBES_Y_ESTADIOS.md`](docs/03_CLUBES_Y_ESTADIOS.md) — los 29 clubes, historia, estadio y logística.
5. [`docs/04_UI_TEXTO.md`](docs/04_UI_TEXTO.md) — pantallas, comandos y flujo de interfaz.
6. [`docs/05_ROADMAP_Y_MVP.md`](docs/05_ROADMAP_Y_MVP.md) — fases, backlog y criterios de aceptación.
7. [`docs/06_MODELO_DATOS.md`](docs/06_MODELO_DATOS.md) — tablas, atributos, eventos y guardado.
8. [`docs/07_FASE1_IMPLEMENTACION.md`](docs/07_FASE1_IMPLEMENTACION.md) — implementación, comandos, motor, pruebas y limitaciones de la Fase 1.
9. [`docs/08_MODO_DIRECTO_Y_GESTION.md`](docs/08_MODO_DIRECTO_Y_GESTION.md) — partido en directo y recompensa a la buena gestión.
10. [`docs/09_ENTRENAMIENTO_SEMANAL.md`](docs/09_ENTRENAMIENTO_SEMANAL.md) — entrenamiento semanal, plan automático y preparación del rival.
11. [`docs/10_STAFF_Y_FINANZAS.md`](docs/10_STAFF_Y_FINANZAS.md) — staff, junta directiva, salarios y finanzas.
12. [`docs/11_FASE3_MERCADO_Y_MULTITEMPORADA.md`](docs/11_FASE3_MERCADO_Y_MULTITEMPORADA.md) — mercado, contratos, staff y multi-temporada.
13. [`docs/12_FASE4_COPA_CANTERA_PRENSA_JUNTA.md`](docs/12_FASE4_COPA_CANTERA_PRENSA_JUNTA.md) — Copa, cantera, prensa y junta.
14. [`docs/13_FASE5A_DHB_REAL_Y_AGENTES_LIBRES.md`](docs/13_FASE5A_DHB_REAL_Y_AGENTES_LIBRES.md) — DHB de dos fases y agentes libres.
15. [`docs/14_TEST_ESTRESS_10_TEMPORADAS.md`](docs/14_TEST_ESTRESS_10_TEMPORADAS.md) — test de 10 temporadas con mercado y retiros.
16. [`docs/15_WEB_ALPHA.md`](docs/15_WEB_ALPHA.md) — alpha web local con Flask.

## Datos

- `data/clubs.json`: 29 clubes con historia, estadio, instalaciones, finanzas, junta y logística.
- `data/cities.json`: coordenadas, aeropuertos y tren.
- `data/competitions.json`: formatos DHA/DHB/1ª.
- `data/tactical_roles.json`: formaciones, roles e instrucciones.
- `data/staff_roles.json`: 13 roles de cuerpo técnico.
- `data/events.json`: plantillas de eventos de partido y mundo.
- `schema/schema.sql`: 41 tablas SQLite.

## Fuentes y calidad

- Plantillas, goles y atributos: RFEH/iSquad y modelo propio.
- Posiciones: 175 oficiales, 801 estimadas.
- Historias y estadios: webs oficiales, Wikipedia, iSquad y prensa local.
- Capacidades y presupuestos: estimaciones de diseño, marcadas como `estimada` o `modelo`.

## Próximo paso

Fase 2 del roadmap:

1. Entrenamiento semanal y desarrollo.
2. Moral y dinámica de grupo.
3. Junta, objetivos y finanzas completas.
4. Logística avanzada.
5. Simulación de DHB para playout y ascensos reales.

## Aviso

Proyecto personal/educativo. No es una fuente oficial de datos ni una evaluación profesional.
