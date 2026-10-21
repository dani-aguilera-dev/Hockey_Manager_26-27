# Test de estrés: 10 temporadas con mercado

**Fecha:** 2026-10-21.
**Club:** CD Terrassa Hockey.
**Semilla:** 9182.
**Motor:** Python + SQLite, sin servidor.
**Alcance:** 10 temporadas completas, entrenamiento automático, mercado de verano e invierno, agentes libres, Copa, EHL, DHB de dos fases y multi-temporada.

---

## 1. Resultado general

- **10 temporadas simuladas:** 2026-27 → 2035-36.
- **Sin errores ni excepciones.**
- **40 movimientos de mercado registrados.**
- DHA y DHB mantuvieron **12 y 16 equipos**.
- Ningún equipo quedó por debajo de 18 jugadores.
- El club del usuario pasó de DHA a DHB en la última temporada.
- Tiempo de ejecución: **104,4 segundos**.

### Trayectoria del usuario

| Temporada | Liga | Posición |
|---|---|---:|
| 2026-27 | DHA | 10º |
| 2027-28 | DHA | 4º |
| 2028-29 | DHA | 6º |
| 2029-30 | DHA | 10º |
| 2030-31 | DHA | 6º |
| 2031-32 | DHA | 5º |
| 2032-33 | DHA | 10º |
| 2033-34 | DHA | 6º |
| 2034-35 | DHA | 11º |
| 2035-36 | DHB | 8º |

### Campeones

- DHA: Real Club de Campo (2), UD Taburiente, CH Carpesa, RS Tenis, Sanse Complutense (2), CD Giner de los Ríos, Club Hockey Madrid - Las Rozas.
- DHB: Pedralbes HC en la última temporada.
- Copa: Pozuelo (2), RC Polo, Junior FC, Real Sociedad 1927 (2), RC Jolaseta, Real Club de Campo y RS Tenis.
- EHL: THC Hurley, Rot-Weiss Köln (3), SV Kampong (2), HC Bloemendaal (2), Royal Léopold.

---

## 2. Fichajes más caros

| Temporada | Jornada | Jugador | OVR | Desde | Hacia | Precio |
|---|---:|---|---:|---|---|---:|
| 2026-27 | 12 | Lucas Gabriel Martini Menazzi | 85,3 | RC Jolaseta | Atlètic Terrassa | 297.500 € |
| 2026-27 | 1 | Alejandro Peña Martín | 85,9 | SPV | Club Egara | 272.000 € |
| 2026-27 | 1 | Marco Moretto | 81,5 | Junior FC | Real Club de Campo | 263.464 € |
| 2026-27 | 1 | Ángel Sáenz de Santa María | 72,0 | RS Tenis | CD Terrassa | 255.000 € |
| 2026-27 | 1 | Biel Roca Durán | 71,0 | AD Rimas | RC Polo | 255.000 € |
| 2027-28 | 1 | Alejandro Peña Martín | 85,9 | Club Egara | Junior FC | 212.500 € |
| 2028-29 | 1 | Borja Valcárcel-Resalt | 72,9 | CD Giner | Real Club de Campo | 158.555 € |
| 2028-29 | 1 | Pablo Usóz Díaz | 85,9 | Real Club de Campo | Sanse Complutense | 102.000 € |
| 2026-27 | 12 | Mario Álvarez-Villabol Navarro | 90,4 | Pozuelo | UD Taburiente | 76.500 € |
| 2028-29 | 1 | Leandro Martínez-Zurita Arpa | 67,5 | Pedralbes HC | RS Tenis | 68.000 € |

### Lectura

- El mercado mueve estrellas entre clubes DHA y también pesca en DHB.
- Alejandro Peña Martín se movió dos veces en dos temporadas: SPV → Egara → Junior.
- Mario Álvarez-Villabol, con 90,4 de overall, salió muy barato (76.500 €): la valoración de estrellas y la negociación IA necesitan ajuste.
- El club del usuario fichó a Ángel Sáenz de Santa María por 255.000 € en la primera temporada.

---

## 3. Agentes libres relevantes

| Temporada | Jugador | OVR | Destino |
|---|---|---:|---|
| 2026-27 | Álvaro Romero Cornejo | 80,8 | Real Club de Campo |
| 2026-27 | José María Arriaza Olvera | 78,1 | Sanse Complutense |
| 2027-28 | Jaime Arrieta Fuentes | 77,5 | CH Carpesa |
| 2027-28 | Álvaro Migueles Jiménez | 76,8 | Real Club de Campo |
| 2028-29 | Gonzalo Fernández Pérez-Arellano | 76,6 | CD Giner |
| 2028-29 | Isaac Molina Gallego | 73,6 | RS Tenis |
| 2029-30 | Carlos Martínez García | 72,6 | Sanse Complutense |
| 2029-30 | Diego Adrián Fernández Aragón | 72,3 | Sanse Complutense |

Los jugadores de 1ª Andaluza entran al mercado como agentes libres y varios acaban siendo titulares en DHA.

---

## 4. Observaciones

### Lo que funciona

- El mercado no rompe plantillas ni presupuestos.
- Hay ascensos, descensos y cambios de liga sin errores.
- La Copa y la EHL se resuelven cada temporada.
- Los agentes libres de 1ª Andaluza tienen impacto real.
- La cantera y los contratos mantienen los equipos con al menos 18 jugadores.

### Lo que hay que ajustar

1. **Valoración de estrellas:** jugadores de 90+ pueden salir por menos de 100.000 €.
2. **Salarios:** algunos fichajes llegan con salarios muy altos y otros demasiado bajos.
3. **Mercado IA:** los movimientos son directos y no negocian de verdad; es una simulación de estrés.
4. **DHA/DHB:** el club del usuario puede bajar a DHB y seguir jugando, pero no hay descenso DHB → 1ª Andaluza.
5. **EHL:** se simula, pero no se juega en directo.

---

## 5. Conclusión

El núcleo aguanta **10 temporadas con mercado, contratos, copa, EHL, cantera y DHB**. No hay errores de ejecución.

El siguiente ajuste recomendado es económico: **valoración de jugadores, salarios y presupuesto de fichajes** para que las estrellas no se muevan por debajo de su valor.
