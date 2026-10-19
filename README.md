# Hockey España Masculino 2026-27

Proyecto de datos, scouting y simulación del hockey hierba masculino español: **DHA**, **DHB** y **Primera Andaluza**.

## Inicio rápido

```bash
# Abrir el juego
xdg-open /home/daniel/hockey_espana/juego_hockey/index.html

# Regenerar datos, juego y Excel
cd /home/daniel/hockey_espana/tools
python3 build_attributes_v2.py
python3 generate_game.py
python3 build_excel_attributes.py
```

## Qué incluye

- **29 equipos**: 12 DHA, 16 DHB y 1 Primera Andaluza.
- **976 perfiles**: 509 jugadores y 467 invitados.
- **Posiciones**: 175 oficiales y 801 estimadas; 75 porteros.
- **37 atributos** por jugador: técnica, 3D y set pieces, táctica, física, mental y portero.
- **5 overalls posicionales**: portero, central, lateral, medio y delantero.
- **Especialistas de set pieces**: inyector, stopper, drag flicker, desviador, primer runner, portero de PC, tirador de stroke, portero de stroke, aéreo y faltas.
- **Editor** para corregir posición y atributos en el navegador.
- **Trazabilidad**: la ficha muestra la fuente de la posición, su URL y la fecha cuando está disponible.
- **Simulador** con formato real DHA/DHB, Final Four, playout, ascensos y descensos.
- **Excel** con atributos, especialistas, diccionario y cobertura.
- **Documentación** completa para continuar el proyecto.

## Archivos principales

| Archivo | Descripción |
|---|---|
| `juego_hockey/index.html` | Juego completo y autocontenido. |
| `juego_hockey/README.md` | Manual resumido del juego. |
| `equipos_hockey_hierba_espana_masculino_2026_27_con_atributos.xlsx` | Excel ampliado con atributos. |
| `jugadores_atributos_2026_27.csv` | CSV completo de jugadores y atributos. |
| `equipos_hockey_hierba_espana_masculino_2026_27_con_posiciones.xlsx` | Excel base con posiciones. |
| `jugadores_posiciones_2026_27.csv` | CSV base de posiciones. |
| `informe_sistema_ligas_DHA_DHB_2026_27.md` / `.pdf` | Informe del sistema de ligas. |
| `informe_posiciones_DHA_DHB_2026_27.md` / `.pdf` | Informe de posiciones. |
| `tools/` | Scripts y datos reproducibles. |
| `docs/` | Documentación maestra. |
| `manager/` | Diseño y prototipo del juego de gestión/entrenador (solo texto). |

## Manager (juego de gestión)

El proyecto incluye un diseño completo y un prototipo de juego de entrenador/gestión, solo texto, inspirado en Football Manager:

- [`manager/README.md`](manager/README.md) — índice y cómo ejecutar el prototipo.
- [`manager/docs/00_VISION_Y_ARQUITECTURA.md`](manager/docs/00_VISION_Y_ARQUITECTURA.md) — arquitectura.
- [`manager/docs/01_MOTOR_PARTIDO.md`](manager/docs/01_MOTOR_PARTIDO.md) — motor de partido.
- [`manager/docs/02_LOGISTICA.md`](manager/docs/02_LOGISTICA.md) — viajes, costes y fatiga.
- [`manager/docs/03_CLUBES_Y_ESTADIOS.md`](manager/docs/03_CLUBES_Y_ESTADIOS.md) — los 29 clubes.
- [`manager/docs/04_UI_TEXTO.md`](manager/docs/04_UI_TEXTO.md) — interfaz de texto.
- [`manager/docs/05_ROADMAP_Y_MVP.md`](manager/docs/05_ROADMAP_Y_MVP.md) — roadmap.
- [`manager/docs/06_MODELO_DATOS.md`](manager/docs/06_MODELO_DATOS.md) — modelo de datos y guardado.

```bash
cd manager/src && python3 prototype.py --demo
```

## Documentación

- [`docs/00_PROYECTO.md`](docs/00_PROYECTO.md) — visión general, estado y arquitectura.
- [`docs/01_SISTEMA_LIGAS.md`](docs/01_SISTEMA_LIGAS.md) — formato DHA/DHB, ascensos y descensos.
- [`docs/02_MODELO_ATRIBUTOS.md`](docs/02_MODELO_ATRIBUTOS.md) — 37 atributos, pesos y especialistas.
- [`docs/03_COMO_SE_JUEGA_HOCKEY.md`](docs/03_COMO_SE_JUEGA_HOCKEY.md) — reglas, fases y set pieces.
- [`docs/04_DATOS_Y_FUENTES.md`](docs/04_DATOS_Y_FUENTES.md) — fuentes, cobertura y calidad.
- [`docs/05_ROADMAP.md`](docs/05_ROADMAP.md) — próximos pasos.
- [`docs/06_CHANGELOG.md`](docs/06_CHANGELOG.md) — historial de cambios.
- [`docs/07_GUIA_JUEGO.md`](docs/07_GUIA_JUEGO.md) — manual de uso del HTML.

Versiones PDF: [`docs/00_PROYECTO.pdf`](docs/00_PROYECTO.pdf), [`docs/02_MODELO_ATRIBUTOS.pdf`](docs/02_MODELO_ATRIBUTOS.pdf), [`docs/03_COMO_SE_JUEGA_HOCKEY.pdf`](docs/03_COMO_SE_JUEGA_HOCKEY.pdf), [`docs/07_GUIA_JUEGO.pdf`](docs/07_GUIA_JUEGO.pdf).

## Pipeline

```
iSquad / RFEH / clubes / prensa
              │
              ▼
tools/todos_manifest_positions.csv
              │
              ▼
tools/build_attributes_v2.py
              │
              ▼
tools/player_attributes_v2.csv
        ┌─────┴─────┐
        ▼           ▼
generate_game.py  build_excel_attributes.py
        │           │
        ▼           ▼
index.html      Excel + CSV
```

## Estado y limitaciones

- Los **37 atributos** y el **82,1 % de las posiciones** son estimaciones del modelo, no datos oficiales.
- 399 subposiciones Central/Lateral son estimadas.
- San Fernando 1ª Andaluza no tiene portero identificado.
- No hay datos oficiales de asistencias, PC, strokes, paradas, minutos o lesiones.
- El simulador es lúdico y educativo; no predice resultados reales.
- Fecha de corte: octubre de 2026.

## Aviso

Proyecto personal/educativo. No es una evaluación profesional ni una fuente oficial de datos. Las imágenes y datos pertenecen a sus fuentes originales.
