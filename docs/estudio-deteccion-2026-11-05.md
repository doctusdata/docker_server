# Por qué la detección tarda casi 7 minutos, y qué la acorta de verdad

> 5/11/2026, 16:57. Medido sobre la Pi de la sala con consultas de **sólo lectura**; no se
> tocó nada. Ventana analizada: desde el 3/11 a las 11:29:44 (paso a lectura en serie)
> hasta el 5/11 a las 16:55. Sustituye a la parte de `criterio-salida-2026-10-31.md` que
> estimaba la detección en «una pasada».

## La cifra, medida y no estimada

Cada movimiento `salida_temporal` guarda en su `detalle` la última lectura de la etiqueta,
así que la latencia real de detección está registrada: es `at − detalle.ultima_lectura_at`.

```
2.188 episodios
  minimo    180 s  (3,0 min)
  mediana   293 s  (4,9 min)
  media     289 s  (4,8 min)
  p90       358 s  (6,0 min)   <- los "casi 7 minutos"
  p99       701 s  (11,7 min)
  maximo  2.043 s  (34 min)
```

**Los 7 minutos son reales y son el p90.** No es una avería: es la estructura del ciclo.

## Por qué son 1,5 ciclos y no uno

La cadencia medida es **193 s** (`start` a `start` en el log: 11:38:16 → 11:41:29). Y la
detección no cuesta un ciclo, sino **entre uno y dos**:

Una etiqueta cuenta como presente si `ultima_lectura_at >= ciclo.inicio` (`repo.py:541`).
Si la retiras a mitad de pasada, **ya te leyó en esa pasada**, así que esa pasada la da por
presente. Hay que esperar a que termine *y* a que pase otra entera sin verla.

```
latencia = lo que le quede al ciclo en curso  +  un ciclo completo
         = uniforme entre 1 y 2 ciclos  ->  media 1,5 ciclos
```

1,5 × 193 s = **290 s**. Medido: **289 s**. El modelo cuadra al segundo, y de ahí sale la
consecuencia útil: **la latencia es 1,5 veces la cadencia, nada más.** Para bajarla hay que
bajar la cadencia; no hay otro sitio donde tocar.

En serie, `ciclo.py:244` aplica la pausa también tras el último lector:

```
cadencia = N × (ventana + pausa) + HTTP = 2 × (90 + 5) + ~3 = 193 s
```

> **Corrección a `criterio-salida-2026-10-31.md:288`:** allí se fijó `PERIODO_S=190` con la
> cuenta «90+5+90=185». La buena es 2×(90+5)=190, más el HTTP: 193. Da igual en la práctica
> —190 < 193, así que el periodo no gobierna y los ciclos van encadenados— pero importa al
> elegir el periodo nuevo.

## Las palancas, ordenadas por lo que dan

Latencia media = 1,5 × cadencia; p90 ≈ 1,85 × cadencia.

| Configuración | Cadencia | Latencia media | p90 | Qué cuesta |
|---|---|---|---|---|
| **Hoy** · serie, ventana 90, periodo 190 | 193 s | **4,8 min** | 6,0 min | — |
| Serie, ventana 60, **periodo 130** | 133 s | **3,3 min** | 4,1 min | cobertura, **sin medir** |
| Serie, ventana 45, periodo 100 | 103 s | 2,6 min | 3,2 min | más de lo mismo, peor |
| Paralelo, ventana 90, periodo 100 | ~98 s | **2,5 min** | 3,0 min | **cobertura 97,4 %**, medido el 3/11 |
| Un solo lector, ventana 90 | ~98 s | 2,5 min | 3,0 min | **13-43 faltantes/evaluación** |
| **Evaluar en cada cierre de ventana** | 193 s | **3,9 min** | 4,7 min | **ninguno, por construcción** |
| Ventana 60 **con el resto igual** | 190 s | 4,7 min | 5,9 min | **nada: no acelera** |

Dos lecturas de la tabla:

**La ventana sola no sirve.** `periodo_s` es inicio-a-inicio (`ciclo.py:254-260`): si la
pasada dura menos, se espera el resto. Con la ventana en 60 la pasada cae a 133 s, pero el
periodo de 190 se queda esperando 57 s y la cadencia apenas baja de 193 a 190. **Hay que
bajar los dos o no bajar ninguno.**

**El paralelo es la palanca más grande y ya se descartó, con razón.** Divide la cadencia por
dos porque los dos lectores leen a la vez, pero el 3/11 se midió que **se ciegan entre
ellos**: la cobertura cayó al 97,4 % frente al 99,5 % en serie, y eso son las 330 etiquetas
parpadeando de `estudio-cobertura-2026-11-01.md`. Volver al paralelo compra velocidad
pagando con el ruido que costó una semana quitar.

## Lo que cuesta acortar la ventana, y por qué no es gratis

Línea base por ventana, de 1.995 ventanas válidas:

| | `.157` | `.158` |
|---|---|---|
| EPC distintos (de 956) | **922,4** · peor 811 · mejor 961 | **917,6** · peor 805 · mejor 953 |
| Desviación | 18,4 | 9,2 |
| Lecturas | 4.316 | 4.178 |

Y por ciclo: **1.005 ciclos, 954,1 presentes, 2,58 faltantes de media**, peor 28, 164 ciclos
perfectos, **cobertura 99,730 %**.

**Un lector solo ve 922 de 956; la unión de los dos llega a 954.** Unos 68 artículos los oye
sólo uno de los dos: la unión no es un lujo, es lo que sostiene el 99,7 %.

**Y una ventana no son 90 segundos de observación, son ~4,7 oportunidades.** 4.316 lecturas
entre 922 etiquetas = una reaparición cada **19,2 s**, que es el TTL del lector
(`config.py:176-180` lo documenta en ~23 s). Bajar a 60 s deja **3,1 oportunidades** en vez
de 4,7, un tercio menos. Para una etiqueta con probabilidad `p` de ser oída en cada
oportunidad, perderla va como `(1−p)^n`, y las que fallan hoy son justo las de `p` bajo: las
31 crónicas de `etiquetas-a-recolocar-2026-11-03.md`, que fallan **por posición, no por ser
malas**.

El margen es estrecho: 2,58 faltantes por ciclo, y con `CICLOS_PARA_CIRCULANTE=1` cada uno
se va a tránsito **en el mismo ciclo** (`reglas.py:388`: `faltante_en_ciclo` llama a
`_escalar`). Son ~48 salidas falsas por hora que vuelven en la pasada siguiente. Acortar la
ventana las multiplica.

## Lo que no se puede responder con lo registrado

**¿A los 60 s se ha visto ya lo que se vería a los 90?** No hay dato, y está comprobado:

- **No existe ninguna relación (ventana, EPC).** `ventana_lectura` guarda sólo el recuento;
  el `set` de EPC se descarta al cerrar (`ventanas.py:99`).
- **`first_seen` y `read_count` se tiran** para etiquetas conocidas: de una `Observation`
  sólo persiste `last_seen`, en `elemento.ultima_lectura_at` (`repo.py:299`).
- **No hay ventanas de duración intermedia** de las que sacar la curva: hay un hueco entre
  3 s y 87 s. Todo lo corto son los artefactos de 0-3 s de la cola del agregador tras el
  `stop`.
- **El cierre anticipado nunca dispara.** Con `SIN_NUEVOS_S=25` (el defecto, activo) las
  ventanas deberían cerrarse al saturarse la lectura; hay **0 líneas `ventana cerrada a los`
  en 6 h** y las 1.995 ventanas agotan el techo de 90 s. No es un desajuste de MAC
  (`VistosPorLector` normaliza a minúsculas por los dos lados, `runner.py:26-50`). O siguen
  apareciendo etiquetas nuevas hasta el segundo 90 —y entonces acortar es claramente malo— o
  el contador no recibe. **Distinguirlo es la primera medida de la campaña.**

## El criterio de decisión, fijado antes de medir

Sea `R(t)` los EPC vistos por un lector a los `t` segundos de su ventana.

| Resultado | Decisión |
|---|---|
| `R(60) ≥ R(90) − 1` en los dos lectores | 60 s es gratis → ventana **y** periodo a 60/130 |
| `R(60)` pierde 2-5 | dobla las salidas falsas: sólo con `CICLOS_PARA_CIRCULANTE ≥ 2` |
| `R(60)` pierde >5, o hay EPC nuevos tras el segundo 85 | **dejar 90 s** y atacar por recolocación |

Fijarlo antes de medir es a propósito: evita elegir después el umbral que confirme lo que se
quería.

## La campaña, cuando la sala esté libre (cero escrituras)

El truco que la hace posible sin tocar nada: **`ultima_lectura_at` es un reloj.**
`count(*) WHERE ultima_lectura_at >= t0` a distintos momentos de la pasada da la curva
acumulada de descubrimiento.

Se ejecuta **desde la máquina de desarrollo**, por un túnel `ssh -L`, y sólo emite `SELECT`:

1. Tomar `t0` del `start` en el log del orquestador (lectura) o de la cadencia de 193 s.
2. Muestrear con **la misma holgura de drenaje** en los dos puntos (la cola del agregador va
   5-10 s por detrás: `window_seconds=5`):
   - `t0+70` → rendimiento del `.157` a 60 s · `t0+100` → a 90 s
   - `t0+165` y `t0+195` → lo mismo para el `.158`
3. **La diferencia es el conjunto en riesgo:** etiquetas cuyo primer avistamiento de la
   ventana llegó después del segundo ~60. Sacar la **lista de EPC**, no el recuento.
4. ~20 pasadas ≈ 65 min. **Cruzar la lista con las 31 crónicas.** Si coinciden, el coste de
   los 60 s recae sobre las que ya están al límite, y entonces **recolocar es la actuación
   correcta, no acortar.**

*Sesgo declarado:* el muestreo mide cuándo la base supo de la lectura, no cuándo la antena
oyó. Es conservador en la dirección segura —subestima los 60 s— y la holgura igual en los
dos puntos lo acota.

## Si sale bien, qué se cambia

```
IRFID_ORQ_VENTANA_S=60
IRFID_ORQ_PERIODO_S=130      # 2×(60+5) = 130; sin esto no se gana nada
```

Los dos a la vez y con **`docker compose up -d irfid-orquestador`, nunca `restart`**: las
variables de entorno se fijan al **crear** el contenedor. Y tienen que ir en el `compose`:
el bloque `irfid-orquestador` **enumera** las `IRFID_ORQ_*` en vez de heredarlas del ancla,
así que ponerlas sólo en el `.env` no hace nada — ya pasó una vez con `IRFID_ORQ_PARALELO`.

## La palanca que no se paga con cobertura

De los 289 s, **186 son irreducibles.** Es el tramo de evidencia: lo que tarda en completarse
una ventana de cada lector, y hace falta entera porque un lector solo ve 922 de 956. Pero el
otro término sí se puede atacar:

```
latencia = W + h/2     W = tramo de evidencia  = 186 s   (irreducible)
                       h = cada cuanto se evalua = 193 s  (hoy, el doble de lo necesario)
```

186 + 96,5 = 282 s frente a los 289 medidos. **Y `h` es el doble de lo que podría ser.** Las
ventanas de los dos lectores se alternan cada ~96 s, así que la evidencia se renueva cada
96 s; pero la evaluación de ausencias va pegada al cierre del *ciclo*, y un ciclo sólo cierra
cuando los dos lectores tienen ventana pendiente: cada 193 s.

Desacoplar las dos cosas —seguir cerrando **un ciclo por barrido**, igual que hoy, pero
**evaluar las ausencias también al cerrar una ventana intermedia**, contra la última ventana
válida de cada lector— lleva `h` de 193 a 96,5 s y la latencia media de **289 a ~234 s**, sin
leer más y sin relajar la evidencia.

Es la única palanca que **no paga cobertura por construcción** y la única reversible sin
tocar los lectores. Y compone con el resto: con 60/130 dejaría la latencia en ~158 s.

## Y por qué recolocar NO compra velocidad

La tentación es evidente: ~68 artículos los oye un solo lector; si estuvieran a la vista de
los dos bastaría un lector para cerrar ciclo y la cadencia caería a ~98 s. **No se sostiene,
y queda escrito para no volver a proponerlo.**

La unión de los dos lectores no sólo tapa esas 68: **amortigua la varianza.** Un lector solo
oscila entre **811 y 961** EPC por ventana; la unión se queda en **2,58 faltantes**, peor caso
28. Recolocar elimina la parte *estructural* del hueco —lo que está donde una antena no
llega— pero no la *aleatoria*, que es la que produce ese rango de 150 EPC. Incluso tras una
recolocación perfecta, un ciclo de un solo lector daría del orden de **13 a 43 faltantes por
evaluación** en vez de 2,58. Y `cobertura_minima=0,5` (`config.py:47`) no lo frenaría: no
llega a invalidar el ciclo.

Dicho de otro modo: con cobertura de unión, la evidencia para afirmar «no está» ocupa ~186 s
**de cualquier forma que se trocee**. Cerrar con un lector no es velocidad gratis: es el mismo
canje con el precio escondido.

**Recolocar sigue siendo lo correcto** —quita el parpadeo crónico y sube la unión por encima
del 99,73 %— pero por su propio mérito. Y antes de plantear el ciclo de un solo lector haría
falta un dato que hoy no existe: **la cobertura por ventana de cada lector restringida al
stock que ese lector puede oír.**
