# Los lectores enmudecen y el ciclo no se entera

Instalación, 27/10/2026. La persona que está en la sala avisa de que «cuando ayer me fui
dejó de leer durante toda la tarde y la noche». Lo medido contradice la primera lectura
del síntoma, y de ahí sale un fallo real del orquestador.

Continuación de `lectores-mqtt.md` (23/10) y `diagnostico-lectores-2026-10-26.md`.

## El ciclo no paró: los lectores callaron

`traza.ventana_lectura` por horas, 36 h:

```
26/10 10:00 - 15:00   ventanas ~115/h   lecturas 130.000-250.000/h   <- con gente delante
26/10 16:00 - 27/10 08:00   ventanas 120/h   lecturas 0              <- 17 horas mudas
27/10 09:00 en adelante     ventanas ~100/h  lecturas 90.000-250.000/h
```

**120 ventanas por hora, las dos lectoras, toda la noche, y cero lecturas.** El
orquestador encendió y apagó sin parar; fueron los lectores los que no publicaron. La
noche del 25 al 26 también salió muda. Sólo publican después de que alguien los reinicie
a mano, que es exactamente el síntoma «se para solo» que `lectores-mqtt.md` atribuye a
habilitar el `MQTTService` en caliente sin `confSave` y sin apagar y encender.

**Las ventanas vacías no estropearon el inventario.** El ciclo con cobertura 0% se
descarta por inválido y `_cerrar_ciclo_invalido` no toca `traza.elemento`. El corte
funcionó: 997 elementos intactos tras 17 horas de silencio.

## Por qué nadie protestó

Tres motivos que se suman:

1. **`/device/start` responde `OK` aunque el lector no vaya a publicar** (ya documentado
   el 23/10). El `fallos: {}` del orquestador sólo dice que la llamada HTTP contestó.
2. **Una ventana válida con 0 lecturas se registra como buena.** No hay ninguna regla que
   mire «arrancó bien y no produjo nada», que es el estado en el que estuvo 17 horas.
3. La salud por antena (`traza.lector_antena`) acumula totales desde siempre, así que un
   lector mudo sigue luciendo millones de lecturas históricas.

## El martilleo: 3.504 encendidos para nada

Duración real de las ventanas, 36 h:

| | n | duración media |
|---|---|---|
| con lecturas | 682 | 59,7 s |
| **mudas (0 lecturas)** | **3.504** | **30,7 s** |

30,7 s es el suelo exacto de `IRFID_ORQ_VENTANA_MIN_S=30`. La causa está en
`_esperar_ventana`: el cierre anticipado por `sin_nuevos_s` compara el contador de EPC
distintos con el de hace un instante, y **con el lector mudo ese contador se queda clavado
en cero**. «No veo nada nuevo» se cumple desde el primer muestreo, así que la ventana
cierra en el suelo y, con `IRFID_ORQ_PERIODO_S=60`, el ciclo vuelve a encender un minuto
después. Toda la noche.

**Cero lecturas no es «ya está todo leído», es «no llega nada».** El arreglo es exigir
haber visto algo antes de poder cerrar antes de tiempo:

```python
if visto > 0 and t >= minimo and t - sin_cambio_desde >= self.t.sin_nuevos_s:
```

Está en `orquestador/ciclo.py` con test de regresión
(`test_un_lector_mudo_agota_la_ventana_y_no_martillea`), comprobado que falla sin el
arreglo. Reduce el trajín a la cuarta parte, y además **es el candidato a causa** de que
los lectores enmudezcan: encaja con lo que la persona receptora recordaba del desarrollo
anterior, *«se pegó con muchos problemas al encender y apagar, y el receptor se
desesperaba»*.

> Desplegado en caliente con `docker cp` sobre
> `/usr/local/lib/python3.12/site-packages/irfid/orquestador/ciclo.py`. **Eso vive en la
> capa de escritura del contenedor**: sobrevive a `restart`, lo borra un `up -d` que
> recree. Para que sea permanente hay que reconstruir la imagen.

## Por qué la API y el visor dan números distintos

No es un fallo: cuentan cosas distintas.

| | cuenta | criterio |
|---|---|---|
| API (legacy `EPC_readings`) | 939 | `Stock = 1` |
| Visor (`traza.elemento`) | 951 | `estado = 'stock'`, dudosas incluidas |

De las 12 de diferencia, **9 son exactamente las dudosas** (`temporal`, con
`ciclos_sin_leer` de 1 o 2) y 2 no tienen ni fila en `EPC_readings`. El espejo pone
`Stock = 0` en cuanto irfid sospecha de una etiqueta, así que **la API resta la duda al
instante** y su número baila; el visor la mantiene en stock y señala la duda aparte.

## Las antenas: tres hipótesis descartadas con datos

Veníamos de dar por buena una antena defectuosa en el `.158`. **Es falso.**

1. **No hay antena floja.** Lecturas por etiqueta distinta, que no depende de cuántas
   cubre cada una: 1.693, 1.848, 1.984 y 2.341. Y RSSI medio **de −62 a −67 en las seis**.
   Una antena floja hundiría ambas medidas. El desequilibrio 205.447 contra 708.954 del
   `.158` es el reparto de etiquetas: sus dos antenas miran a lados opuestos desde el
   centro de la sala y **a la izquierda hay muchas más etiquetas**.
2. **No falta solape.** Sumando las etiquetas distintas por antena salen 2.885 sobre 944
   existentes: cada etiqueta la ven unas **tres** antenas. La UHF rebota y la orientación
   física no impide la redundancia.
3. **Las etiquetas sin respaldo no son las que fallan.** Un 11-13% depende de una sola
   antena (70 de ellas sólo del `.158` antena 2), pero de ésas sólo el 2,5% está dudosa
   frente al 5,6% de las que sí tienen respaldo. *Con una salvedad honesta*: la lista de
   «sin respaldo» sólo puede contener etiquetas que se leyeron, así que está sesgada y la
   comparación no es concluyente.

**Y un fallo de configuración:** `traza.lector` sigue declarando cuatro antenas en el
`.158`, que sólo tiene dos. Cada ventana válida apunta dos fantasmas como mudas (154 ya).
Se corrige con `python -m irfid bootstrap`, que sincroniza `topologia.json` (ya dice
`[1,2]`) y que en esta base **no hace nada más**: comprobado que los responsables son
idénticos, que ningún elemento encaja con la guarda de «virgen» y que no hay nada del
catálogo sin elemento.

## El espía del broker

`irfid/servicio/tools/espia.py`. Suscriptor de sólo lectura que responde a lo que la base
no puede: **cuántas etiquetas distintas ve cada antena de cada lector**. `ContadorAntenas`
sólo cuenta lecturas, y el espejo legacy apelmaza los dos lectores de inventario bajo
`devid='Almacen-1'`, así que ahí las antenas 1 de dos aparatos distintos son
indistinguibles. En el payload sí viene el `devmac`.

Reutiliza `model.ReaderMessage` y `model.flatten`; no publica nada y no toca la base.

```bash
docker cp ~/roomfid/espia.py banco-irfid-almacen:/tmp/espia.py
docker exec banco-irfid-almacen python /tmp/espia.py --segundos 150 --epcs
docker exec banco-irfid-almacen python /tmp/espia.py --epc 000385      # seguir una
```

Con `--epcs` sale el reparto del solape y con `--volcar` la lista de las que dependen de
una sola antena, para cruzarla con `traza.elemento`.

## Pendiente

- **Hacer durable el `MQTTService` de `.157` y `.158`**: habilitar **desde la web**,
  `confSave`, y apagar y encender. Es lo que decide si el miércoles hay lecturas. La API
  del lector miente sobre el estado de sus servicios.
- **Vigilante de lector mudo**: N ventanas válidas seguidas con 0 lecturas deberían
  generar alerta por la vía de `alertas.py`, igual que `lector_inactivo`. Hoy ese estado
  es invisible y puede durar 17 horas.
- **Reconstruir la imagen** para que el arreglo del martilleo deje de ser un parche en
  caliente.
- **Umbrales**: se quedan en `MINUTOS=5` / `CICLOS=3` por decisión expresa, para que la
  demostración detecte una etiqueta sacada en unos tres minutos. Queda acordado
  **intentar bajarlos** más adelante. Con sombras medidas de 312 s, el margen es estrecho.
- **Pausa por presencia**: escrita y probada (`presencia_carnet`, apagada por defecto),
  sin desplegar. El ciclo ya pasa de forma continua, que era la otra mitad de lo pedido.

---

## Nota aparte: la API no pide Bearer, y dentro de la red no pide nada

Comprobado el 27/10 encadenando las tres peticiones desde un portátil de la red:

```
GET /api/config                      -> HTTP 200, devuelve la apiKey completa
GET /api/epc-master  (sin cabecera)  -> HTTP 401
GET /api/epc-master  (con esa clave) -> HTTP 200
```

La autenticación es `x-api-key`, **no** Bearer. Las cinco rutas de datos
(`epc-master`, `epc-readings`, `user-readings`, `user-room`, `bin`) la exigen, pero
`/api/config` (`gestion-rfid-api/src/index.js:55`) es la única sin `validateApiKey` y
**reparte la clave** a quien la pida. Su control es que la IP del cliente empiece por
`192.168.`, `10.` o `172.16.`, o sea cualquiera enchufado a la red de la instalación.

Existe por un motivo, no por descuido: el comentario dice *«solo para el cliente web»*, y
la página de la API necesita la clave desde el navegador. El problema es el cómo.

**Lo que sí protege:** no hay `trust proxy`, así que `req.ip` es la IP real de la conexión
y **no se puede falsear** con un `X-Forwarded-For`. Una IP pública se lleva un 403.

**Decidido dejarlo así de momento:** la API es de solo lectura, el miércoles no depende de
ella, y tocar ahora la web que sirve es más riesgo que beneficio. Queda asumido que dentro
de la red la protección es decorativa.

> **La condición que lo rompería:** si el 3000 se abre por **redirección de puertos en el
> router** o se pone detrás de un proxy, las peticiones llegarían con la IP privada del
> router como origen, la comprobación las daría por locales y la clave saldría a internet.
> Mientras se llegue directo a la máquina, no pasa. Conviene confirmar que la redirección
> que se abrió para el 3000 está quitada.

Para cuando se arregle: lo pequeño es limitar la comprobación a `127.0.0.1`; lo bueno es
que el servidor inyecte la clave en la página y la ruta no exista. Las dos obligan a
**rotar la clave**, que además está en claro en `banco/api/app.json`.
