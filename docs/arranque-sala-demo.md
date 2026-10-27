# Arranque del sistema en la sala demo

Orden de encendido y comprobaciones, para llegar y tenerlo en marcha sin pensar.
Escrito el 23/10/2026, después del montaje.

## Orden de encendido

> **REGLA DE ORO, descubierta a base de perder la tarde del 23/10:**
> **La Raspberry se enciende primero y se apaga la última.** Los lectores, al contrario.
>
> Los lectores **no se recuperan de perder el broker**. Si al arrancar la Pi no está, o
> si la Pi se cae mientras publican, su cliente MQTT se queda mudo para siempre:
> `keepAlivePeriodMs = -1` significa que no hay latido que detecte la caída ni reintento
> que la arregle. Y es traicionero, porque desde fuera parecen sanos — responden al
> `ping`, su web va, siguen leyendo y acumulando etiquetas en su buffer. Lo único que lo
> delata es que **no llegan tramas al broker**.
>
> Por eso: **después de cualquier corte de corriente, de red o del router, hay que
> reiniciar los dos lectores**, aunque no parezca que les pase nada.
>
> El arreglo definitivo es poner el **keep-alive a 60** en la configuración del
> `MQTTService` desde la web del lector. Por REST el aparato ignora ese campo.

### Qué pasa si no se respeta

El 23/10, al volver de comer con los lectores encendidos antes que la Pi, un ciclo cogió
a `.157` mudo y a `.158` a medias. El ciclo se dio por válido —`cobertura_minima` está en
`0.5`, media foto basta— y marcó **293 etiquetas como ausentes** estando en la
estantería. No se perdió nada porque los umbrales altas lo frenaron, pero el visor las
habría mostrado como salidas delante del cliente.

**1. El router**, y esperar a que dé red.

**2. La Raspberry.** Tiene que responder en `192.168.1.155`. Si no:

```bash
ip -4 -br addr show          # deben salir 192.168.1.155/24 y 192.168.0.60/24
nmcli con up "<conexion>"    # o desde nmtui: desactivar y reactivar
```

> La `.155` se perdió al reiniciar el router. Es lo primero que hay que mirar si algo no
> va: **todo depende de esa dirección** — el broker, la base, el visor y la cadena JDBC
> que lleva grabada el lector de puerta.

**3. Los dos lectores de inventario**, `192.168.1.157` y `.158`.

Su `MQTTService` está habilitado y guardado con `confSave`, así que **al arrancar se
levanta solo y publican**. Si no publicaran, ver `docs/lectores-mqtt.md`: el servicio solo
arranca al iniciarse el equipo, y la API miente sobre su estado.

## Comprobación, en orden

```bash
# los nueve servicios
curl -s 192.168.1.155:8090/health        # ok:true, mqtt:true, db:true
curl -s 192.168.1.155:8091/health        # el orquestador, fallos vacio
```

En `:8090/health`, los dos campos que de verdad importan:

- **`ultimo_ok_hace_s`** por debajo de unos segundos: están entrando lecturas.
- **`lectores_desconocidos`** vacío: las tramas se atribuyen a lectores conocidos. Si
  aparece una MAC ahí, ese lector no está en `traza.lector`.

Y que las ventanas traigan etiquetas:

```sql
SELECT to_char(v.inicio,'HH24:MI:SS'), l.devip, v.epcs_distintos, v.lecturas
  FROM traza.ventana_lectura v JOIN traza.lector l ON l.id = v.lector_id
 WHERE v.fin IS NOT NULL ORDER BY v.inicio DESC LIMIT 6;
```

Con los lectores bien, la primera ventana de cada uno barre el almacén completo
(~820-880 EPC distintos) y las siguientes traen solo las novedades. Un ciclo válido da
unos **952 presentes y 4 faltantes**.

## Lo que se abre en la demostración

| | |
|---|---|
| **Visor del almacén** | http://192.168.1.155:8020 |
| **Panel de monitorización** | http://192.168.1.155:8080 |
| **Bandeja de correo** | http://192.168.1.155:8025 |

El resto son interfaces de máquina. Un **401 en la API legacy (`:3000`) y en la de
papeleras (`:8092`) es correcto**: significa que están protegidas.

## Umbrales: PENDIENTE DE AJUSTAR

Esto quedó a medias el 23/10 y hay que terminarlo. En `~/roomfid/.env` se pusieron:

```
IRFID_MINUTOS_PARA_CIRCULANTE=600
IRFID_CICLOS_PARA_CIRCULANTE=100
```

**El de minutos funciona** (no hubo ninguna escalada con criterio `tiempo`). **El de
ciclos no tomó efecto**: se midieron 40 elementos pasando a `circulante` con criterio
`ciclos` y `ciclos_sin_leer = 2`, así que el valor en vigor es 2 o menos, no 100. Hay que
revisar el `.env` —nombre exacto de la variable, que no esté duplicada más abajo— y
**recrear el contenedor, no reiniciarlo**:

```bash
cd ~/roomfid && docker compose up -d irfid-almacen
```

Se nota que tomó las variables porque el contador `observaciones` de `:8090/health`
vuelve a empezar desde cero.

Para comprobar por qué un elemento se fue a circulante, el movimiento lo guarda:

```sql
SELECT at, detalle->>'criterio', detalle->>'ciclos_sin_leer'
  FROM traza.movimiento WHERE tipo = 'circulante'
 ORDER BY at DESC LIMIT 10;
```

## Si hay que recurrir al simulador

Solo si los lectores fallan. Desde **Warp** (iTerm no tiene permiso de Red Local y falla
con `EHOSTUNREACH`):

```bash
cd ~/Documents/doctus_data/desarrollo/rep_server/simuladores/keonn-sim
MODE=warehouse DEVID=Almacen-1 DEVIP=192.168.1.157 \
DEVMAC=3c:e4:b0:dc:ca:d7 HTTP_PORT=8157 \
MQTT_URL=mqtt://192.168.1.155:1883 \
MQTT_USER=gestion_rfid MQTT_PASS='rfid_room@' \
MQTT_TOPIC=TAG_readings/scenario1 MQTT_CLIENT_ID=keonn-sim-157 \
EPC_SOURCE=db PGHOST=192.168.1.155 \
POOL_SIZE=997 SWEEP=true TAGS_PER_CYCLE=120 RF_PERIOD_MS=1000 \
ANTENNAS=1,2,3,4 START_AUTO=true node index.js
```

`POOL_SIZE=997` es importante: con 950 sobre 997 catalogados, los 47 que el sorteo deja
fuera acaban en `circulante` y no vuelven nunca.

**Los lectores reales tienen que estar encendidos igualmente**, aunque se use el
simulador: son ellos los que responden al `start`/`stop` del orquestador y por tanto los
que abren las ventanas. Con ellos apagados, las lecturas llegan sin ventana en la que
caer.

## Estado al cerrar el 23/10

- Los dos lectores reales **publicando** en `TAG_readings`, 42 y 44 tramas en 5 minutos.
- Un ciclo válido con 952 presentes y 4 faltantes.
- Inventario: 997 catalogados, 2 consumidos (están en una mochila, fuera del campo).
- Pendiente: el umbral de ciclos, y que el lector de puerta (`Puerta-1`, MAC
  `64:8c:bb:f0:b9:28`) sigue en la base como `Papelera-1` en `192.168.0.159`. Al montarlo
  en `.1.159`, `bootstrap` lo reconcilia por MAC — ver `docs/lector-puerta.md`.

## Quién hay en la red de la sala

| Dirección | Qué es |
|---|---|
| `192.168.1.1` | Router TP-Link Archer MR550 (4G). **Sin contraseña conocida**: no resetear, se perdería el APN del SIM y el WiFi |
| `192.168.1.53` | El portátil, por cable, con IP manual **sin puerta de enlace** (así internet sigue por el móvil) |
| `192.168.1.101` y `.103` | **Las cámaras de la sala.** Servidor web en el 8086 con Digest. No tienen nada que ver con el sistema |
| `192.168.1.155` | La Raspberry |
| `192.168.1.157` y `.158` | Los lectores de inventario |

## Pendiente (23/10, al cerrar)

**El visor y las dos contabilidades.** El visor lee de la API Node heredada, o sea de
`EPC_readings`, no de `traza`. Las dos cuentan lo mismo pero con semánticas distintas:

| | |
|---|---|
| `traza.elemento` estado `stock` | incluye los marcados `temporal` — sospechosos sin confirmar |
| `EPC_readings."Stock"=1` | ya excluye lo que no se ha visto en el último ciclo |

Medido el 23/10: legacy 948, `traza` presentes (stock y no temporal) 948 — **coinciden**;
`traza.stock` bruto 958, con 11 temporales dentro. Las 8 discrepancias puntuales son esos
mismos temporales en tránsito entre una contabilidad y otra.

No es un error, pero **confunde a quien mira el visor**. Lo que pide el visor es enseñar
las tres cifras por separado: presentes, sospechosos y fuera.

**Indicador de estado de los lectores en el visor.** Los datos ya existen y no hay que
tocar irfid: `GET :8090/estado` devuelve el árbol completo, con esto por lector:

```
codigo    LECTOR-157
estado    ok
metricas  publica_hace_s, control_ok_hace_s, control_fallos, antenas_en_fallo
antenas   [{antena, estado, ultima_lectura_hace_s, lecturas_total}, ...]
```

**`publica_hace_s` es el campo clave**: es el único que detecta el fallo del 23/10, en el
que los lectores respondían al ping, su web iba y seguían leyendo, pero no publicaban. Un
punto ámbar por encima de 90 s (el ciclo es de 60 s) y rojo por encima de 300 convierte un
fallo invisible en algo que se ve de un vistazo.

El trabajo va en el repositorio `raspi_visor`: un router que haga de proxy a ese endpoint
—siguiendo el patrón de `backend/app/rfid_client.py`— y un componente en el frontend.

**Keep-alive de los lectores.** Ponerlo a `60` en el `MQTTService` de los dos, desde su
web. Por REST el aparato ignora ese campo. Mientras siga en `-1`, cada corte de red o de
corriente los deja mudos hasta que se reinicien.
