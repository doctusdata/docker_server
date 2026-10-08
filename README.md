# Réplica virtualizada del sistema RoomFID

Réplica del sistema RFID hospitalario: **la Raspberry es real** (192.168.0.64,
hardware conectado) y orquesta un servidor y unos lectores virtualizados en
esta máquina (192.168.0.4).

```
  Raspberry Pi REAL                 Esta máquina (192.168.0.4)
  192.168.0.64                      ┌──────────────────────────────┐
  Node-RED :1880      ─── LAN ───▶  │ Mosquitto :1883              │
  (GPIO real)                       │ PostgreSQL :15432            │
                                    │ API + UI :3000               │
                                    │ batch :8081                  │
                                    │ lectores :8157 8158 8159 8205│
                                    └──────────────────────────────┘
```

Material de referencia original en `RoomFID Máquina/` (entrega del cliente,
**no se modifica**). Los servicios de `servicios/` son copias editables.

## Arranque

```bash
./scripts/up.sh                 # levanta todo (build incluido)
docker compose ps               # todos deben estar healthy
./scripts/down.sh               # para (con -v borra tambien la base)
```

| Servicio | URL desde el host | Credenciales |
|---|---|---|
| API REST + UI | http://192.168.0.4:3000/ | header `x-api-key: rfid_api_2025_f8e7d6c5b4a3210987654321abcdef98` |
| Node-RED (editor) | http://192.168.0.64:1880/ (**la Pi real**) | las suyas |
| Dashboard | http://192.168.0.64:1880/ui/ | — |
| PostgreSQL | `localhost:15432` | `rfidroom` / `rfidroom@2025`, db `gestion_rfid` |
| Mosquitto | `localhost:1883` | `gestion_rfid` / `rfid_room@` |

> El 5432 del host ya estaba ocupado, por eso PostgreSQL se publica en 15432.
> La contraseña del editor de Node-RED se cambió a `roomfid` porque el hash
> entregado en `settings.js` correspondía a una contraseña que no tenemos.

## Mapa de la réplica

Se conserva la subred original `192.168.1.0/24` con las mismas IPs, para no
tener que reescribir ninguna configuración ni los flows.

| Contenedor | IP | Rol |
|---|---|---|
| `rfid-postgres` | .155 | PostgreSQL 14 |
| `rfid-mosquitto` | .155 | Mosquitto 2 (comparte namespace de red) |
| `rfid-api` | .155 | API Express :3000 (comparte namespace) |
| `rfid-nodered` | .156 | Node-RED de respaldo (**parado**, perfil `backup`) |
| `rfid-lector-157` | .157 | Lector almacén A |
| `rfid-lector-158` | .158 | Lector almacén B |
| `rfid-lector-159` | .159 | Lector de puerta (alarma EAS) |
| `rfid-almacen-mqtt` | .160 | Puente MQTT → PostgreSQL |
| `rfid-servicio-pg` | .163 | Los 7 procesos batch |
| `rfid-lector-205` | .205 | Lector de papeleras (arranca **parado**) |

Flujo: los lectores publican tramas `TAG_readings` por MQTT → `almacen_mqtt`
enruta **por `devmac`** y escribe en PostgreSQL → la **Raspberry real** orquesta
las ventanas de RF (ciclo de 300 s) y dispara el batch → la API expone los datos.

### Puertos publicados en la LAN (lo que ve la Raspberry)

Como la Pi está en `192.168.0.x` y no ve la subred interna `192.168.1.0/24`,
los servicios se publican en `192.168.0.4`:

| Puerto | Servicio | Equivale en el sistema real a |
|---|---|---|
| 1883 | Mosquitto | `192.168.1.155:1883` |
| 15432 | PostgreSQL | `192.168.1.155:5432` |
| 3000 | API + UI | `192.168.1.155:3000` |
| 8081 | batch (`/run`) | el `ssh ... node index.js` |
| 8157 / 8158 | lectores de almacén | `192.168.1.157` / `.158` |
| 8159 | lector de puerta | `192.168.1.159` |
| 8205 / 8206 | papeleras / API AdvanNet | `192.168.1.205:80` / `:3161` |

## Monitor de la instalación

El monitor local está en **http://192.168.0.4:8080**. Lo alimentan los **agentes**, uno por
máquina: el contenedor `rfid-monitor-agente` en el servidor y `rep_server/agente/` en cada
Raspberry. Cada agente informa al nodo con el token `ROOMFID_AGENTES_TOKEN` del `.env`.

El agente del servidor lee además `irfid /estado`. Con eso, el monitor enseña la
instalación tal como es: almacén → lectores → antenas, puerta, y quirófanos → papeleras →
lector. Las papeleras se declaran en `irfid/servicio/topologia.json` con su `almacen` y su
`quirofano`; un quirófano puede tener varias.

Qué alarma y cómo provocar averías en el simulador: [agente/README.md](agente/README.md).

## La Raspberry real

`raspberry/flows.json` es el flow de la entrega reapuntado a esta máquina
(14 sustituciones: URLs de lectores, las dos conexiones PostgreSQL y el batch).
**Los nodos `rpi-gpio` se conservan**: en la Pi real sí hay GPIO, al contrario
que en el contenedor.

```bash
./scripts/make-pi-flows.py          # regenera el flow desde la entrega
./scripts/deploy-pi.sh <usuario>    # lo despliega en la Pi
```

`deploy-pi.sh` **hace copia de seguridad antes de sustituir nada** (en
`raspberry/backup-<fecha>/` y en `/tmp` de la propia Pi), para y arranca
Node-RED, y comprueba que estén instalados los 5 módulos necesarios. Al
terminar imprime el comando exacto para revertir.

> El Node-RED en contenedor (`rfid-nodered`) queda en el perfil `backup` y **no
> arranca por defecto**: encendería los mismos lectores que la Pi. Si alguna vez
> lo necesitas aislado: `docker compose --profile backup up -d rfid-nodered`.

## Uso habitual

```bash
./scripts/lector.sh 157 start      # enciende un lector (start|stop|status)
./scripts/run-batch.sh             # ejecuta los 7 procesos batch
./scripts/psql.sh -c 'SELECT count(*) FROM "EPC_readings";'
./scripts/snapshot.sh              # guarda un volcado antes de experimentar
./scripts/gen-mosquitto-passwd.sh  # regenera el fichero de passwords MQTT
```

Restaurar un snapshot:
```bash
docker compose down -v && ./scripts/up.sh      # vuelve al dump original
```

## Qué se cambió respecto al original, y por qué

Solo lo imprescindible por no haber hardware. Todo lo demás es la entrega tal cual.

1. **`exec ssh` → HTTP.** Node-RED lanzaba el batch con
   `ssh rfidroom@192.168.1.155 "node /opt/Servicio_postgresql/index.js"`.
   Se sustituye por una llamada a `http://192.168.1.163:8081/run`, servida por
   `servicios/servicio_postgresql/server.js` (fichero **nuevo**). El `index.js`
   original no se toca: sigue siendo el one-shot, y cada llamada es un proceso
   nuevo, igual que el SSH.
2. **`rpi-gpio in` → `inject`.** No hay GPIO en un contenedor. Los dos nodos de
   entrada (pin 21 `Puerta-1`, pin 16 `sensor-1`) pasan a inject manuales con
   **payload numérico** — `function 10` compara `msg.payload === 1` de forma
   estricta y un string no dispararía el reset de los triggers.
3. **`flows_cred.json`: 6 entradas añadidas.** El fichero entregado tenía 4.
   Faltaban la contraseña de PostgreSQL de los dos `postgreSQLConfig` (sin ella
   los 10 nodos `postgresql` fallan de forma silenciosa) y las credenciales
   digest de 4 `http request` de stop que declaraban `authType: "digest"` sin
   tenerlas (habrían devuelto 401 al cortar RF desde los sensores).
4. **`www/api.html`:** `API_BASE_URL` pasa de la IP pública hardcodeada a
   `${window.location.origin}/api`. Además de funcionar desde cualquier origen,
   evita que el CSP de helmet bloquee las llamadas.

El script `scripts/patch-flows.py` aplica 1 y 2 de forma reproducible.
`docker/nodered/flows.json.orig` conserva el flow sin parchear.

## Verificado end-to-end

- Base restaurada con los datos reales: 960 EPC_master, 921 EPC_readings, 40 Bin, 11 User_readings, 2 user_room
- MQTT rechaza anónimos y acepta `gestion_rfid`
- Digest de los lectores: 401 sin credenciales, 200 con `admin/admin`
- Trama MQTT → `EPC_readings` con `Stock=1`, `Tmp=0` y `Local_time` actualizado
- Ciclo automático de Node-RED: enciende .157 ~2 min, lo para, enciende .158
- API: ping, `/api/config`, 401 sin key, consultas con datos, UI en `/`
- Batch: los 7 procesos en orden (47 foráneas borradas, 920 asignadas, 657 a `Stock=0`)
- Alarma de puerta: autoriza `state=1`, alarma con `state=0` y con EPC desconocido
- Papeleras: inserta en `Bin` y la API AdvanNet responde en :3161

## ⚠️ PENDIENTE DE REVISAR — lector de papeleras

`processMasterDelete` da de baja en `EPC_master` **todo EPC que aparezca en
`Bin`**, y `Bin` solo crece (nada la vacía salvo `DELETE /api/bin`). Cada pasada
del batch erosiona el catálogo de productos.

En un sistema de consumibles puede ser lo deseado (el producto se consume y se
da de baja), pero **conviene confirmarlo con el cliente**.

Mientras tanto, `rfid-lector-205` arranca **parado**. Para probarlo:
`./scripts/lector.sh 205 start`, y pararlo después. Haz `./scripts/snapshot.sh`
antes de experimentar.

## Comportamientos del sistema original que se conservan

No son fallos de la réplica: están así en el sistema entregado.

- **Cada trama se procesa 4 veces.** `almacen_mqtt` suscribe `TAG_readings/#`
  *y además* `TAG_readings/scenario1..3`, y el broker entrega una copia por
  suscripción coincidente. Son upserts idempotentes, así que no corrompe datos,
  pero cuadruplica la carga.
- **`Bin.Local_time` queda NULL** en las filas nuevas: la columna no está en los
  `fields` de `config/app.json` y no tiene default.
- **Credenciales en claro** en `flows_cred.json`, en los configs de los tres
  servicios y en los lectores (`admin`/`admin`), con `credentialSecret: false`.
- **Rama MySQL huérfana** en los flows (6 nodos deshabilitados apuntando a
  `Almacen_hospital`), resto de la versión anterior a la migración a PostgreSQL.
- En los lectores reales, los de almacén están en región **FCC** y el de puerta
  en **ETSI**. FCC no es legal en la UE — a comentar con el cliente.

## Notas de mantenimiento

- **El volumen `nodered-data` enmascara cambios del Dockerfile**: un `COPY` a
  `/data` no sobrescribe un volumen ya poblado. Tras editar `flows.json` hay que
  `docker compose down -v`, o los cambios no se ven.
- El pwfile de Mosquitto debe pertenecer al uid 1883 y ser `0700`, o el broker
  arranca y muere con `Unable to open pwfile`. Lo gestiona
  `scripts/gen-mosquitto-passwd.sh`.
- Mientras el compose esté levantado, la subred `192.168.1.0/24` queda capturada
  por el bridge y no es alcanzable desde el host.
