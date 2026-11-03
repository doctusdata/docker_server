# Cuándo damos algo por salido: medido, y decidido con Y

Instalación y clon, 31/10/2026. La sala pidió revisar cómo decide el sistema que un
artículo ha salido, porque **el software actual en producción parece dar mejores
resultados que irfid**. Se midió sobre los **85.174 movimientos reales** de la instalación
(restaurados en el clon `192.168.0.17` desde el volcado del 30/10) y se leyó el software de
producción entero, Node-RED incluido (`doctus_data/soft_octubre`).

El resultado invierte la pregunta de partida. Esto es lo que se encontró, lo que se decidió
y lo que queda por hacer.

> **Cómo se llama cada estado depende de la rama, y este documento usa los nombres de
> `main`**, que es lo que corre hoy en la sala y en el clon: `creado · stock · circulante ·
> consumido`. En las ramas `topologia-papelera` / `inventario-estable`, tras la migración
> `018`, los mismos estados se llaman `creado · almacen · en_transito · usado · retirado`,
> y están descritos en **`estados-inventario.md`**. **La regla que se decide aquí es la
> misma en los dos casos**; sólo cambia el nombre del estado de destino. Donde este
> documento dice `circulante`, allí se lee `en_transito`.

---

## 1 · El sistema antiguo no hace cinco pasadas

Lo que se recordaba: lanzar un lector 90 s, luego el otro 90 s, consolidar, marcar dudosas
las que faltan, repetir **cinco pasadas** y sólo entonces dar algo por salido.

Lo que hace de verdad:

| pieza | qué hace |
|---|---|
| `.node-red/flows.json` | `Disparo-L1` **90 s**, `Disparo-L2` **90 s**, `Timer General` cada **240 s** |
| `opt/Servicio_postgresql` (marzo 2025) | `Stock = 0` cuando `Local_time` tiene más de **5 minutos** |
| `opt/Servicio_postgresql/config/app.json` | `Scan_time_nofound = 5` |

**Las ventanas de 90 s en serie sí son exactas.** El conteo de pasadas no existe:

- `grep -riE "pasada|observacion|intentos|contador"` sobre todo el árbol (`opt/`,
  `gestion-rfid-api/`, los flujos): **cero resultados**.
- Y la tabla de producción **no tiene dónde contar**. Esquema real de `EPC_readings`:
  `id, devid, devip, devmac, EPC, Antenna, RSSI, Stock, Local_time, Used, EPC_User,
  Time_User, Tmp`. Ni una columna de recuento; el único dato temporal es `Local_time`.

**El «5» es `Scan_time_nofound`: cinco minutos, no cinco pasadas.** Y con un ciclo de
240 s, cinco minutos son algo más de **una** pasada de tolerancia — el sistema antiguo es,
si acaso, **más precipitado** que irfid con sus tres ciclos.

> Que el algoritmo recordado no esté implementado no es un reproche a nadie: es *lo que se
> quiere que haga*. Y resulta que **irfid es el único de los dos que puede hacerlo**,
> porque ya tiene `ciclos_sin_leer` en `traza.elemento`. El antiguo no tiene dónde
> guardarlo.

## 2 · Entonces por qué parece mejor: porque no apunta sus errores

Node-RED sólo pinta dos contadores —`COUNT(*) WHERE Stock=1` y `Stock=0`— y además **borra
filas en cada vuelta** (`Borrado Usadas`, `Borrado Foraneas`). Una etiqueta que desaparece
y vuelve pasa de `Stock=1` a `0` y a `1` otra vez, **en la misma columna**: sin movimiento,
sin histórico, sin atribución a una persona y sin alerta.

irfid hace lo mismo **y lo escribe**:

| movimiento | veces |
|---|---|
| `salida_temporal` (se marca dudosa) | **39.810** |
| `retorno` (reaparece) | **39.699** |
| `circulante` (pasa a tránsito) | **4.564** |

**El 99,7% de las dudosas volvieron.** La fluctuación es de los dos sistemas; el expediente
es sólo de uno. Por eso uno «se ve mal» y el otro no.

## 3 · Lo que el histórico dice de los umbrales

De las 4.564 escaladas a tránsito, cuántas habrían ocurrido según las pasadas exigidas:

| pasadas | escalarían | se evitarían |
|---|---|---|
| 2 | 4.069 | 495 |
| 3 *(valor que estaba puesto)* | 3.668 | 896 |
| **4** | **56** | **4.508** |
| 5 | 44 | 4.520 |
| 6 | 44 | 4.520 |

**Hay un acantilado entre 3 y 4**, y a partir de ahí da igual el número. Eso hace que 4 sea
un punto de diseño robusto y no un umbral al filo.

Dos datos más del mismo histórico:

- **601 escaladas fueron por el criterio de tiempo**, y la mínima ocurrió con **un solo
  ciclo sin leer**: una etiqueta que falla una pasada y sale a tránsito porque lo dice el
  reloj.
- **666 EPC distintos** pasaron a tránsito y **reaparecieron después**: falsos positivos
  demostrados, no sospechas.

---

## 4 · Lo que pide el cliente, y cómo se traduce

Dos datos distintos en el visor (la pantalla se rehará después):

| el cliente dice | en irfid es | estado |
|---|---|---|
| **«las que da como fuera»**, claras tras los 5 minutos | `estado = 'circulante'` | existe |
| **«guadiana»**: aparecen y desaparecen, **cuentan como dentro**, se ven sólo como observaciones | `estado = 'stock'` **+** `temporal = true` | existe, pero **sin memoria** |
| atribución **al último que entró** | `usuario_tarjeta` en `faltante_en_ciclo` | existe |

El modelo del cliente **ya es el de irfid**. Las guadiana hoy ya cuentan como dentro y ya
no escalan: al reaparecer, `_localizado()` pone a cero el contador **y el reloj**.

## 5 · La decisión: 4 pasadas **Y** 5 minutos

**Decidido el 31/10.** `_escalar` (`almacen/reglas.py:227`) hoy escala con **cualquiera** de
los dos criterios:

```python
if not (por_ciclos or por_tiempo):   # <- como estaba
    return
```

Pasa a exigir **los dos**. Es lo que hace que «lo tenga claro», y es lo que mata el caso
medido: fallar **una** pasada e irse a tránsito por reloj.

| ajuste | antes | ahora |
|---|---|---|
| `IRFID_CICLOS_PARA_CIRCULANTE` | 3 | **4** |
| `IRFID_MINUTOS_PARA_CIRCULANTE` | 5 | **5** (coincide con `Scan_time_nofound`) |
| `IRFID_ORQ_PARALELO` | `true` | **`false`**, lectores en serie 90 s como Node-RED |

> **Trampa que hay que dejar escrita:** cuál de los dos criterios manda **depende del
> periodo del ciclo**. Con `ORQ_PERIODO_S=60`, cinco minutos son cinco ciclos y las 4
> pasadas se cumplen antes, así que gobierna el tiempo. Con el periodo en 240 s, al revés.
> **Quien cambie el periodo está cambiando la regla sin darse cuenta.**

### Un peligro que el Y cierra de paso

Existe una segunda vía, `escalar_por_tiempo` (`reglas.py:275`), cuyo docstring dice que
está para escalar *«aunque no se cierren ciclos (p. ej. lectores parados)»*. Con el `Y` esa
vía **deja de escalar cuando los lectores están muertos**, que es exactamente lo que debe
pasar: las **17 horas mudas** del 26/10 (ver `lectores-mudos-2026-10-27.md`) no deben
declarar nada fuera. Hay que **reescribir ese docstring**: su propósito declarado ya no se
sostiene.

## 6 · Las guadiana hay que recordarlas

`_localizado()` (`reglas.py:122`) **borra la memoria** al reaparecer una etiqueta:

```python
e.temporal = False
e.temporal_desde = None
e.ciclos_sin_leer = 0
```

Así una etiqueta con cincuenta idas y venidas queda **idéntica** a una impecable, y no hay
de dónde sacar la lista de observaciones que el cliente pide. Con 39.699 retornos en el
histórico, el ir y venir es la norma, no la excepción.

Hace falta un contador que **no** se reinicie (`veces_dudosa` en `traza.elemento`, en su
propio fichero SQL numerado e idempotente). «Guadiana» es un **dato derivado**, no un valor
nuevo del ENUM —eso obligaría a un fichero aparte por la trampa del `ALTER TYPE`— igual que
ya lo es `temporal`. Y su estado **no se toca**: siguen contando como dentro, que es lo que
mantiene estable la cifra de cabecera.

## 7 · El corte contra la acusación en masa

La atribución va **al último que entró**, como pide el cliente, y `faltante_en_ciclo` ya lo
hace —con la mejora de calificar la firmeza en `ventana` (el carnet pasó entre la última
lectura y la detección) o `ultimo` (sólo es el último que entró), que el sistema antiguo no
tiene: su `processUsuarios` asigna el último carnet a todo lo que esté fuera, sin comprobar
franja.

El riesgo con los 5 minutos es el que ya ocurrió el 26/10 con la etiqueta `...176`: si un
lector enmudece caen cientos de faltantes en el mismo ciclo y **todas** se atribuyen a la
misma persona.

**Si en un mismo ciclo se marcan más de N faltantes, eso no es un robo: es un fallo de
lectura.** Se registra la ausencia, **no se atribuye a nadie** y se levanta alerta de
lector. El tope ya existe para la gestión (`gestion_max_faltantes = 100`); falta el
equivalente para la atribución.

---

## Cómo se repite la medida

```sql
-- Reparto: cuantas dudosas y cuantas volvieron
SELECT tipo::text, count(*) FROM traza.movimiento GROUP BY 1 ORDER BY 2 DESC;

-- El acantilado: que pasaria con cada umbral de pasadas
SELECT umbral,
       count(*) FILTER (WHERE c >= umbral) AS escalarian,
       count(*) FILTER (WHERE c <  umbral) AS se_evitarian
  FROM (SELECT (detalle->>'ciclos_sin_leer')::int AS c
          FROM traza.movimiento WHERE tipo='circulante') m,
       (VALUES (2),(3),(4),(5),(6)) AS u(umbral)
 GROUP BY umbral ORDER BY umbral;

-- Con que criterio escalo cada transito
SELECT detalle->>'criterio' AS criterio, count(*),
       min((detalle->>'ciclos_sin_leer')::int) AS ciclos_min,
       max((detalle->>'ciclos_sin_leer')::int) AS ciclos_max
  FROM traza.movimiento WHERE tipo='circulante' GROUP BY 1;

-- Falsos positivos demostrados: paso a transito y luego reaparecio
WITH esc AS (SELECT epc, at FROM traza.movimiento WHERE tipo='circulante')
SELECT count(DISTINCT e.epc) FROM esc e
 WHERE EXISTS (SELECT 1 FROM traza.movimiento r
                WHERE r.epc = e.epc AND r.tipo='retorno' AND r.at > e.at);
```

**Todo esto se puede medir porque `_escalar` guarda en cada movimiento
`detalle = {"criterio": "ciclos"|"tiempo", "ciclos_sin_leer": N}`.** Sin ese detalle no
habría forma de reconstruir con qué regla se tomó cada decisión. **No quitarlo.**

## Verificación y despliegue

1. **Tests de tabla en `reglas.py`**, que es pura (sin base ni reloj): una etiqueta con 3
   pasadas y 6 minutos **no** sale; con 4 pasadas y 5 minutos **sí**; una que falta, vuelve
   y falta cincuenta veces **nunca** sale y acaba marcada guadiana.
2. **Repetir la medida** tras el cambio: la predicción es pasar de 3.668 escaladas a del
   orden de 56.
3. **Lectores parados**: con el `Y`, 17 horas de silencio deben declarar **cero** fuera.
4. **Primero el clon, después producción** (acordado el 31/10): se prueba en
   `192.168.0.17` —que lleva el volcado real, 997 artículos y 85.174 movimientos— y sólo
   después se sube a la `.155`, por `scp` y `ssh` en el puerto **2015**. El camino está
   validado de ida y vuelta, con punto de restauración por etiqueta de imagen
   (`roomfid/irfid:hoy-20261030`): unos 40 s cada sentido.

## Serie frente a paralelo: demostrado el 3/11/2026

Era la única hipótesis que quedaba abierta, y **era cierta**. Los dos lectores de la misma
sala **se estaban cegando mutuamente**.

Lo que lo destapó no fue una medida nuestra, fue acordarse de cómo trabajaba el sistema
antiguo: `90 s un lector → parar → 90 s el otro → parar → ~30 s de procesado → repetir`, y
**la que no estaba, estaba fuera**. Una sola pasada, sin histéresis ni contador. Eso sólo se
sostiene con cobertura casi perfecta, y la nuestra no lo era.

Medido con `ORQ_PARALELO` en `false`, ventana de 90 s, sobre las mismas 957 etiquetas:

| | paralelo | **serie** |
|---|---|---|
| EPCs que ve `.157` leyendo **solo** | 814 (791-833) | **910 (877-936)** |
| EPCs que ve `.158` leyendo **solo** | 795 (778-814) | **914 (893-930)** |
| faltantes por pasada, estantería completa | **24,5** (8-44) | **2-5** |
| cobertura | 97,4% | **99,5-99,8%** |
| ciclo | 122 s | 190 s |
| umbral que lo aguanta | 3 | **1** |
| detección de una retirada | ~6,5 min | **una pasada, 3,2-6,3 min** |

**Cien etiquetas más por lector, sólo por no encenderlos juntos.** El sistema antiguo no
acertaba por el umbral: acertaba por esto.

### La prueba a ciegas

Se retiraron 27 etiquetas **sin decir el número**. La pasada de las 11:57:55 dio `vistas
929, faltantes 28`, y el visor 28 en tránsito:

```
...253 a ...276    24 etiquetas    12,8 - 13,3 min sin leerse
...602 a ...604     3 etiquetas    12,8 - 13,1 min
                   ─────────────
                   27  ← las retiradas, con el reloj subiendo junto
...513              1 etiqueta      5,3 min   ← el unico falso positivo
```

Ninguna de menos. Y el error residual **no es aleatorio**: con todo devuelto a la
estantería quedan cuatro en tránsito —`...333`, `...428`, `...514`, `...516`— y son **las
mismas que llevaban fallando toda la mañana**. Cuatro etiquetas crónicas de 957, que es un
problema físico de esas cuatro y va al estudio de cobertura, no al umbral.

### El arreglo que lo hizo posible, y que sin él la serie parecía un fracaso

Una ventana inválida por `corta` **ya no invalida el ciclo** (`almacen/repo.py`,
`_ventana()`). Tras cada `stop` siguen llegando observaciones del agregador —la cola de la
ráfaga, en vuelo cuando se apagó el lector— y abren una ventana de 0 a 2 s con decenas de
EPC. `_cerrar_ciclo_invalido()` asigna **todas** las ventanas pendientes al ciclo
descartado, así que ese artefacto se llevaba por delante los 90 s del lector que esperaba
pareja: **una sola pasada válida en once minutos**, con las dos ventanas reales impecables.

No hace falta que invalide para estar protegido: un ciclo sólo se cierra cuando todos los
lectores requeridos tienen ventana pendiente **y válida**. Un `abort` sí sigue matando el
ciclo — ahí alguien ha entrado.

### La configuración que queda

```
IRFID_ORQ_PARALELO=false
IRFID_ORQ_VENTANA_S=90
IRFID_ORQ_PAUSA_S=5
IRFID_ORQ_PERIODO_S=190          # 90+5+90=185: ciclos encadenados, sin hueco muerto
IRFID_CICLOS_PARA_CIRCULANTE=1
IRFID_MINUTOS_PARA_CIRCULANTE=60 # no interviene; queda de tope
```

**`IRFID_ORQ_PARALELO` hubo que declararlo en el compose.** El bloque `irfid-orquestador`
**enumera** las `IRFID_ORQ_*`, no las hereda del ancla, así que ponerlo sólo en el `.env`
no hacía nada y el síntoma era «lo he cambiado y sigue en paralelo».

### Tres cosas que falsearon medidas antes de entenderlas

1. **No promediar dos configuraciones.** Las primeras cifras tras cada cambio mezclaban
   pasadas viejas con nuevas y daban un número que no describía ninguna: una «cadencia de
   126,8 s» que en realidad eran 74,6, y una «ventana de 106,5 s» con el tope en 60.
   **Esperar 10 minutos tras cada cambio y filtrar por ese intervalo.**
2. **El ciclo abarca sus dos ventanas** (~190 s en serie). Un ciclo que *empieza* antes de
   la retirada cuenta las etiquetas como presentes: de ahí un «5 faltantes» con 27 fuera.
   No era contaminación de las ventanas `corta` —se sospechó y era falso—, era el tramo
   solapando el momento de sacarlas.
3. **Cada `up -d` del orquestador cuesta un ciclo**: la primera ventana tras arrancar es
   `arranque` e invalida su ciclo. Reiniciando seguido, el contador no avanza nunca y
   parece que el sistema no detecta nada. Pasó tres veces.

### Y con umbral 1 no hay red de seguridad

Es asumido, no un descuido. Lo que lo hace defendible son dos cosas **medidas**: la
cobertura (2-5 faltantes de 957) y que un falso positivo se quita con un clic desde
**«Devolver al almacén»**, dejando su `ajuste_manual` en el historial. Sin ese botón, el
umbral 1 no sería defendible.

---

## Cómo se enseña la política en pantalla (1/11/2026)

La política —**X pasadas sin leer y entonces fuera**— sólo convence si se ve. Y lo que se
veía era el resultado, no el criterio: la tarjeta «En observación» con su cifra, y una
tabla con «en almacén» y una hora, que no explica por qué esa etiqueta está en esa lista.

Ahora la pestaña «En observación» lleva su propia tabla, con la columna que lo dice todo:

| columna | qué enseña |
|---|---|
| **Pasadas sin leer** | `1 de 15` · «faltan 14 para darla por salida» |
| Última lectura | con segundos, de la pasada en que se vio por última vez |
| Dudando desde | cuándo empezó a fallar |

**El denominador es el de verdad, no uno escrito a mano.** `/resumen` devuelve
`umbral_ciclos`, que sale de `IRFID_CICLOS_PARA_CIRCULANTE` (hoy **15**). Si alguien
ajusta el umbral, la tabla lo refleja sola; un 15 incrustado en el frontend habría acabado
mintiendo el día que se cambie.

Con eso, las dos listas se explican la una a la otra: **las de observación llevan 1 o 2
pasadas de 15** —todavía lejos—, y **las dos de tránsito agotaron las 15**. Es la
demostración de que el sistema no da nada por salido a la primera.

### Y va detrás del modo técnico

**Con `?tecnico=0` —lo normal— «En observación» no existe en la pantalla**: ni tarjeta, ni
pestaña, ni el aviso «no visto en esta pasada» en las filas de «En almacén». Quedan las
cuatro cifras de siempre. Con `?tecnico=1` aparece la quinta y su tabla.

La razón: **la cifra no resta del total.** Observación está *dentro* de «En almacén», así
que fuera de un diagnóstico no informa de nada y sí invita a preguntar si el sistema pierde
etiquetas. Enseñarla exige saber que fallar una pasada es normal, y eso no cabe en el pie
de una tarjeta.

**Esconder la pestaña no bastaba.** El grupo elegido vivía en el estado del componente: al
apagar el modo técnico con esa pestaña abierta, la tabla seguía sirviendo sus filas bajo el
rótulo de otra, que es peor que enseñarlas. Ahora el grupo se fuerza a `inventario` y la
consulta no se hace siquiera.

Y los tres sitios se esconden juntos a propósito: el aviso por fila dice lo mismo que la
cifra, así que dejar uno puesto habría vaciado de sentido al modo técnico.

Ver `clon/parches/LEEME.md`: hasta que haya imagen nueva, los dos ficheros van **montados**
desde el disco de la Pi, no copiados dentro.

---

## El botón de reiniciar pasadas (3/11/2026)

En la pestaña «En observación» —modo técnico— hay ahora un botón por fila y otro para
todas: **pone el contador de pasadas a cero**. Es para el caso real de «he comprobado la
estantería, está completa, lo que falla es la lectura».

**Hace exactamente lo que una reaparición**, que es lo único defendible: `temporal=false`,
`temporal_desde=NULL`, `ciclos_sin_leer=0` y **se borra la atribución de usuario**. Eso
último no es un extra: reiniciar el contador y dejar el nombre puesto sería declarar que la
etiqueta está donde debe y conservar a quien supuestamente se la llevó.

Por eso el elemento **sale** de la lista: el grupo es `estado='almacen' AND temporal`. Si la
siguiente pasada tampoco lo ve, vuelve con 1 de 15. No se pierde nada.

**Queda registrado.** Cada reinicio escribe un movimiento `ajuste_manual` con
`temporal_origen=true`, `temporal_destino=false` y
`detalle={"accion":"reiniciar_pasadas","origen":"visor","alcance":...}`. Un contador que se
puede poner a cero sin rastro no sirve de nada en un sistema de trazabilidad.

### Dos cosas que había que decidir, y por qué así

**`ajuste_manual` ya existía en el ENUM** (`010_traza.sql`), así que no hace falta
migración. Importa porque `ALTER TYPE ... ADD VALUE` no se puede usar en el mismo fichero
que lo introduce, y un valor nuevo de ENUM el día de una demostración es exactamente lo que
no se hace.

**Esta API ya no es de sólo lectura.** El `SET TRANSACTION READ ONLY` de `_leer_sync` se
puso para que no pudiera escribir por descuido; la excepción **no se cuela por ahí**, va por
un `_escribir_sync` propio que se ve en el `grep` y que sólo usa esta ruta. Sigue **sin
autenticación**, como `/estado`: escucha en la red interna de la Pi. Si algún día hace falta
una segunda escritura, es el momento de replantear eso.

**Y el `post()` del cliente del visor vacía la caché entera.** Con `CACHE_TTL_SECONDS=10`,
sin eso quien pulsa el botón ve diez segundos las cifras de antes y concluye que no ha
funcionado.
