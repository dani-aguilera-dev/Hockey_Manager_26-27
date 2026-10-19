# Hockey Manager España 2026-27

Diseño y prototipo de un juego de **entrenador y gestión de club** de hockey hierba, solo texto, inspirado en la arquitectura de Football Manager y adaptado a la DHA, la DHB y la Primera Andaluza.

## Estado

- **Diseño:** completo en `docs/`.
- **Datos:** 29 clubes, 16 ciudades, 976 perfiles, 37 atributos.
- **Prototipo:** vertical slice en `src/prototype.py`.
- **Juego completo:** pendiente de implementación por fases.

## Inicio rápido

```bash
cd /home/daniel/hockey_espana/manager/src
python3 prototype.py --demo
```

Modo interactivo:

```bash
python3 prototype.py
```

Simular una temporada con un club:

```bash
python3 prototype.py --club "CD TERRASSA HOCKEY" --auto
```

El prototipo:

- carga clubes, ciudades y jugadores;
- muestra el dossier del club;
- genera un calendario DHA;
- simula partidos con comentario de texto;
- muestra la clasificación;
- calcula la logística del próximo desplazamiento.

No incluye todavía:

- mercado de fichajes;
- entrenamiento;
- moral;
- junta;
- finanzas completas;
- DHB;
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
    prototype.py
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

Implementar la Fase 1 del roadmap:

1. `models.py` y `data_loader.py`.
2. Dashboard y navegación.
3. Calendario DHA.
4. Motor de partido por fases.
5. Guardado/carga.

## Aviso

Proyecto personal/educativo. No es una fuente oficial de datos ni una evaluación profesional.
