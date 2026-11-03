# Estudio de cobertura: por qué 330 etiquetas parpadean y qué se puede tocar

> 1/11/2026. Plan de trabajo, no resultados todavía. Se irá ampliando con lo que salga del
> simulador y de las capturas. Lo medido hasta ahora está en
> `criterio-salida-2026-10-31.md` y `limpieza-2026-11-01.md`.

## Por qué hace falta

Con el umbral en 15 pasadas la pantalla ya dice la verdad: dos etiquetas fuera, y son las
dos que de verdad están fuera. Pero eso **tapa el síntoma, no lo cura**. Debajo sigue
habiendo un problema físico, y está medido:

```
330 de 957 etiquetas entraron y salieron de la duda en 6 horas
2.468 episodios · media 7,5 por etiqueta · la peor 48 veces
cobertura por ciclo: 97-99 %
```

El 1-3% que falta en cada pasada **no es aleatorio: son siempre las mismas**. Hay un
conjunto fijo e identificable de etiquetas que las antenas ven mal.

El objetivo es saber **cuál de las tres palancas —posición de antenas, potencia, formato y
colocación de la etiqueta— puede mover eso, y cuánto**.

## Lo que ya se sabe, y acota el trabajo

**La potencia no es una palanca.** Medido el 23/10 (`lectores-mqtt.md`): los lectores están
a **31,5 dBm, que es su máximo**, con sensibilidad −85 dBm en todas las antenas. El catálogo
del simulador lo confirma desde la ficha (`potencia_max_dbm: 31.5`). No hay margen hacia
arriba. **Descartada.**

**El RSSI se está tirando.** Sólo viaja por `aggregate.py` —como `rssi_max`, en memoria— y
acaba en `legacy.py`, el espejo legacy. Con `IRFID_LEGACY_MIRROR=false`, que es como está y
como debe seguir, **se calcula y se descarta**. No hay histórico que consultar: hay que
capturarlo del flujo MQTT.

**La herramienta ya existe.** `irfid/servicio/tools/espia.py` se suscribe al broker,
reutiliza `model.ReaderMessage` y `model.flatten`, y **no toca nada**: ni base, ni lectores,
ni servicio. Hoy agrega RSSI medio por antena y sabe cuántas antenas ven cada etiqueta.

---

## 1 · La métrica: margen sobre la sensibilidad

```
margen = RSSI_mejor − (−85)
```

Una etiqueta cuyo mejor RSSI sea −80 tiene **5 dB** y parpadeará siempre. Una a −55 tiene
**30 dB** y no fallará nunca. Todo el estudio gira alrededor de ese número.

El espía guarda hoy `por_epc[epc] = {(devmac, antena), …}`: sólo el conjunto, sin RSSI ni
recuento. Hay que ampliarlo a:

```python
por_epc[epc][(devmac, antena)] = {lecturas, rssi_max, rssi_min, rssi_suma}
```

Es el mismo bucle de `Espia.lectura`, guardando más. Con eso, de cada etiqueta salen tres
números: **cuántas antenas la ven, su mejor RSSI y su margen**.

## 2 · El cruce que contesta la pregunta de fondo

La otra mitad ya la tenemos: **la lista de las 330 que parpadean, con cuántas veces cada
una**, sacada de `traza.movimiento` con las consultas de `limpieza-2026-11-01.md`.

Cruzando margen contra parpadeo, con 957 puntos, sale una nube que se lee directamente:

- **Si las que parpadean son las de margen bajo** → es cobertura, y la posición de las
  antenas es la palanca. Además dirá **cuántos dB** faltan, que es lo que permite decidir
  sin comprar a ciegas.
- **Si parpadean etiquetas con buen margen** → no es cobertura: es colisión o tiempo de
  inventario, y la palanca es otra —menos etiquetas por ventana, o ventana más larga—.

No es una hipótesis que haya que creerse: es una medida.

## 3 · Las dos palancas que quedan

### Posición de las antenas

Agregando por antena: cuántas etiquetas dependen de una sola y cuál es el margen medio de
cada una. Eso señala la zona concreta donde falta una antena o sobra un ángulo.

Hubo una medida previa el 31/10 —**11-13% dependían de una sola antena, 70 de ellas sólo
del `.158` antena 2**— pero sin RSSI, así que no se supo si era grave. Con el margen sí.

### Formato y colocación de la etiqueta

**El simulador ya ha detectado que pegarlas contra el cartón, donde están, no es la mejor
solución.** No modela el cartón por su nombre, pero sí lleva lo que lo explica:

```
etiqueta real: Trace-ID TER17S · PET · sensibilidad de lectura −24 dBm
               inlay 92 × 14 mm, dipolo 88 × 11 mm   (textual del catálogo)
               chip Impinj M750 (EPC 96 + User 32) o M730 (EPC 128)
pol: 3         pérdida por polarización, en dB
kShelf: 0,55   atenuación de la estantería
atten: 4
```

Con un dipolo de unos nueve centímetros, **lo que decide no es el cartón sino la orientación
respecto a la polarización de la antena y lo que hay inmediatamente detrás** — el contenido
de la caja, no su pared. Tres decibelios de desajuste de polarización son **la mitad de la
potencia**, y en una etiqueta que ya va al límite eso es exactamente la diferencia entre
leerse y no leerse.

**Y es la más barata de las tres**: reorientar o separar etiquetas no cuesta hardware. Por
eso conviene medirla **antes** de cualquier compra, no después.

---

## 4 · El simulador

`http://192.168.0.7:8000/` responde desde esta red. Es **una sola página autocontenida**
servida por un `BaseHTTP` de Python; el código (`sim/rfid_sim.py`, `catalogo.json`, en
`~/Documents/roomfid-antenas` de esa máquina) no está expuesto por HTTP, pero **el modelo
entero va embebido en el HTML**, y su propio comentario dice que el cálculo es *«igual que
sim/rfid_sim.py»*. Para estudiarlo no hace falta acceso.

**Por qué merece crédito:**

```
"6 SP12 en dos AdvanReader-160 (arriba 4 en R1, abajo 2 en R2; R2·P3 y P4 libres)"
sala 3×3×3 m · puerta 0,8 × 2 en x=0 · rack en x=0,92, alto 1,05
A1 en [1.5, 0.04, 2.72] con boresight y ejes
freq 866 · sens −24 · modLoss 6 · pol 3 · atten 4 · kShelf 0,55 · erpMax 33 · sigma 4
```

**Coincide con lo que se midió a ciegas el 31/10**: el `.157` con cuatro antenas, el `.158`
con dos y **dos puertos libres**. Un modelo que acierta en lo comprobable es un modelo del
que fiarse en lo que no.

Trae catálogo de hardware con fichas reales —AdvanReader-160 y 70, y un **AdvanTrack-600 de
techo con antenas integradas y PoE**— con ganancias, HPBW y relación delante-detrás. Y su
función **«Comparar montajes»** es literalmente la pregunta de este estudio.

### Se puede calibrar sin saber dónde está cada etiqueta

Era la duda de partida: el simulador predice cobertura del **espacio**, y nuestras medidas
son de **etiquetas cuya posición no conocemos**. Tiene solución, y no hace falta esa clave:

> El simulador predice una **distribución de margen** sobre el volumen del rack. La captura
> mide una **distribución de margen** sobre las etiquetas repartidas por ese mismo rack.
> **Si las dos coinciden, el modelo está calibrado** — y entonces sus comparaciones entre
> montajes son creíbles aunque no se sepa qué caja es cuál.

Si no coinciden, el desajuste dice qué corregir: `kShelf` si lo medido es peor en el fondo
de la estantería, `sigma` si no cuadra la dispersión.

### El candidato que señalan los dos lados

**Los dos puertos libres de R2.** El simulador los declara (`R2·P3 y P4 libres`) y nosotros
medimos que el `.158` tiene dos antenas para 70 etiquetas que dependen de una sola. Es el
cambio más barato que existe —dos antenas y dos cables, sin mover nada— y **se puede
predecir antes de comprarlas**.

### Qué aportaría el acceso al código

La página permite comparar montajes **a mano, pinchando**. El código permitiría **barrer
decenas de montajes en lote** y ordenarlos por cuántas etiquetas quedan por debajo de X dB.
Es la diferencia entre probar cuatro ideas y explorar el espacio entero. Útil, **no
bloqueante**.

---

## Cuántas etiquetas hay: es un resultado, no un dato

Se empezó con 997 y tras la limpieza del 1/11 quedan **957** en la base. Pero **cuántas
existen físicamente no se sabe**, y averiguarlo es uno de los objetivos.

La captura lo contesta sola: **lo que el espía no vea en 15 minutos con los dos lectores
sanos, no está en la sala.** Esa lista de ausentes es un entregable, y hay que separarla
antes de calcular distribuciones: un EPC que no existe sale siempre con margen nulo y
ensucia justo la cola baja, que es la que interesa.

## Ficheros

- `irfid/servicio/tools/espia.py` — ampliar `Espia.lectura` y el volcado para guardar RSSI
  por `(EPC, antena)`. **Sólo lee del broker**: se puede correr en la sala sin riesgo.
- El volcado se cruza con `traza.movimiento` usando las consultas de
  `limpieza-2026-11-01.md`.
- **Nada del servicio cambia.** Esto es instrumentación, no una modificación.

## Verificación

1. **Captura de 15 minutos en la sala** (varios ciclos completos). Debe producir el margen
   de cada etiqueta vista; las que falten son las interesantes.
2. **Control de cordura**: las dos que están fuera de verdad (`…000001` y
   `726474726a7173676972796d`) **no deben aparecer**. Si aparecen, están dentro y el
   inventario miente.
3. **La nube margen-contra-parpadeo debe mostrar correlación.** Si no la muestra, la
   hipótesis de cobertura es falsa y hay que mirar colisión — y eso también es un resultado.
4. **Antes y después de tocar algo**: repetir la misma captura. La mejora se mide en dB de
   margen y en número de etiquetas con una sola antena, **no en impresiones**.

---

## Actualización 3/11/2026: la primera palanca no era ninguna de las tres

El estudio planteaba tres palancas —potencia (descartada), posición de antenas, colocación
de la etiqueta— y daba por buena la cobertura de partida del 97-99%. **Faltaba una, y era
la que más pesaba: cuántos lectores emiten a la vez.**

Los dos lectores de la sala leían **en paralelo**, y se estaban cegando mutuamente.
Pasándolos a serie —90 s uno, 90 s el otro, como hacía el sistema antiguo— cada uno ve
**unas cien etiquetas más leyendo solo**:

```
.157   814 -> 910       faltantes por pasada:  24,5  ->  2-5
.158   795 -> 914       cobertura:            97,4% -> 99,5-99,8%
```

Detalle completo y prueba a ciegas en `criterio-salida-2026-10-31.md`.

**Qué significa para este estudio.** Las dos palancas que quedaban siguen en pie, pero el
terreno ha cambiado:

- **El parpadeo era en buena parte interferencia.** Los 2.468 episodios en 6 h y las 330
  etiquetas que entraban y salían de la duda se midieron **con los dos lectores emitiendo
  juntos**. Esa cifra hay que volver a tomarla en serie antes de usarla para nada: el punto
  de partida ya no es un 2,6% de fallo por pasada, es un **0,2-0,5%**.
- **Y el objetivo se estrecha, que es mejor.** Con todo devuelto a la estantería quedan
  **cuatro** etiquetas crónicas en tránsito —`...333`, `...428`, `...514`, `...516`— y son
  siempre las mismas. De «330 que parpadean» a «cuatro que no se leen». Esas cuatro son el
  caso de estudio perfecto para la captura de RSSI: pocas, identificadas y reproducibles.
- **La medida de margen sigue siendo la que decide**, pero ahora con una pregunta mucho más
  concreta: *¿qué tienen esas cuatro?* Si su margen es bajo, es posición o colocación. Si no
  lo es, es colisión y hay que mirar el tiempo de inventario.

**Lo que no cambia:** la potencia sigue descartada (31,5 dBm es el máximo), el RSSI sigue
sin guardarse, y `tools/espia.py` sigue siendo la herramienta. Lo que cambia es que ya no
hace falta una captura de 957 etiquetas para empezar: con las cuatro crónicas hay caso.

**Y el hallazgo del día que no es de cobertura sino de método:** «fuera pero cerca» no se
distingue de «dentro». Con los lectores a 31,5 dBm en 3×3 m, una etiqueta en la mesa de al
lado se lee igual que una en su sitio. Ninguna palanca de este estudio arregla eso; lo que
hay que hacer es no confundirlo con un fallo del sistema cuando se prueba.
