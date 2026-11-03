# Las 31 etiquetas que fallan estando en la estantería

> Hoja de trabajo para la sesión de recolocación. Medido el 3/11/2026 a las 19:30 en la Pi
> de la sala. **Son las candidatas físicas, no un problema de software.**

## Por qué esta lista y no otra

Hoy se confirmó que **las etiquetas que fallan no son etiquetas malas: es el sitio donde
están.** Por la mañana el conjunto crónico era `333`, `428`, `514`, `516`; tras **mover
físicamente** las etiquetas aparecieron `824` y `674`. Si el fallo viajara con la etiqueta
serían las mismas. No lo son.

Y «aparece a veces» —palabras del usuario sobre la `674`— es **la firma de un margen justo
en el límite de sensibilidad** (−85 dBm). Una etiqueta con margen de sobra no tiene «a
veces»: se lee siempre. Por eso ningún umbral lo arregla y moverla sí.

## Cómo se ha filtrado, que es la parte que importa

Se cuentan los episodios de `salida_temporal` **sólo desde las 11:29:44**, cuando se pasó a
lectura en serie. Antes el ruido era **seis veces mayor** (464 episodios/hora frente a 54) y
mezclar los dos tramos da un número que no describe ninguno.

Y **se excluyen los bloques `253`–`276` y `602`–`604`**: ésas son las 27 que se sacaron
físicamente a las 14:10. Fallaron porque no estaban, que es el sistema funcionando. Tienen
exactamente 2 episodios cada una, así que el corte en **3 o más** las deja fuera solo.

## La lista

`fallos` = veces que entró en observación · `fuera` = veces que llegó a tránsito ·
`sin leer` = segundos desde su última lectura, a las 19:30

| EPC (últimos dígitos) | fallos | fuera | sin leer |
|---|---|---|---|
| **…177** | **34** | 15 | 34 s |
| **…674** | **28** | 20 | **2.376 s** |
| **…687** | **23** | 11 | 48 s |
| **…224** | **22** | 3 | 62 s |
| …680 | 17 | 7 | 191 s |
| …686 | 17 | 4 | 415 s |
| …217 | 16 | 2 | 51 s |
| **…824** | 16 | 3 | 26 s |
| …428 | 13 | 11 | 10 s |
| …830 | 13 | 5 | 62 s |
| …176 | 12 | 3 | 8 s |
| …823 | 12 | 1 | 71 s |
| …514 | 10 | 9 | 22 s |
| …182 | 9 | 2 | 132 s |
| …333 | 9 | 8 | 20 s |
| …669 | 9 | 0 | 442 s |
| …178 | 8 | 2 | 8 s |
| …385 | 8 | 6 | 16 s |
| …513 | 8 | 7 | 18 s |
| …334 | 7 | 5 | 14 s |
| …442 | 7 | 4 | 18 s |
| …681 | 7 | 4 | 113 s |
| …675 | 6 | 5 | 34 s |
| …032 | 5 | 0 | 48 s |
| …679 | 4 | 3 | 18 s |
| …028 · …386 · …488 · …489 · …516 · …864 | 3 | 0-3 | — |

En negrita las cuatro peores y las dos que aparecieron al mover.

**Prefijo completo:** `9999009900000000000000NN`, p. ej. `…177` es
`999900990000000000000177`.

## Dos lecturas de la tabla que no son obvias

**`fuera` alto con `fallos` parecido = se lee casi nunca.** La `674` (28 fallos, 20 fuera) y
la `428` (13/11) llegan al umbral casi siempre que fallan: están peor que la `224`, que
falla 22 veces pero sólo escala 3 porque reaparece enseguida. **Para recolocar, ordenar por
`fuera`, no por `fallos`.**

**Y `sin leer` alto ahora mismo señala a las que hay que mirar primero**: la `674` llevaba
**40 minutos** sin una sola lectura estando en la estantería. La `686` y la `669`, 7 minutos.
Las que están a 10-30 s se leen bien en este momento y su problema es intermitente.

## Qué hacer mañana, y en este orden

**1 · Medir antes de mover.** `tools/espia.py` se suscribe al broker y **no toca nada**. Hoy
agrega RSSI medio por antena pero no lo saca por etiqueta; ampliarlo para que dé, de cada
EPC, **cuántas antenas la oyen y con cuánto margen cada una** es el único trozo que falta
del estudio de cobertura (`estudio-cobertura-2026-11-01.md`).

Con eso se sabe **hacia dónde** mover cada una —acercarla a la antena que ya la oye, o
girarla— en vez de probar sitios y esperar media hora a ver qué pasa.

**2 · Mover, de una en una y anotando de dónde a dónde.** Si se mueven varias a la vez no se
sabe cuál mejoró. Y anotar **orientación**, no sólo posición: con un dipolo de ~9 cm, los 3
dB de desajuste de polarización que modela el simulador son la mitad de la potencia.

**3 · Volver a medir el mismo rato.** La comparación válida es episodios/hora en una ventana
limpia, nunca «parece que va mejor».

## Una trampa al usar el botón «Devolver» con éstas

Se vio en vivo a las 19:15 con la `674`: llevaba **34 minutos sin leerse**, escaló
correctamente a tránsito, se pulsó «Devolver»… y **80 segundos después volvía a contar**.
Dos veces seguidas.

La devolución pone el contador a cero y la pasada siguiente la vuelve a marcar. **El
periodo de gracia arregla eso** (`irfid 37b2815`, probado en la `.17`) pero **no está
desplegado en la sala**. Mientras no lo esté, devolver una crónica no sirve de nada: hay que
moverla.

## El objetivo de fondo

De **«330 etiquetas que parpadean»** —la cifra de la mañana, con los dos lectores
cegándose— a **31 con nombre y apellidos**, y de ellas 6 que explican la mitad del ruido.
Eso ya no es una nube: es un caso de estudio reproducible, que es lo que el estudio de
cobertura necesitaba para empezar.
