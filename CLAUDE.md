# CLAUDE.md — RoomFID

> Copia en el repositorio de la guía que vive en la raíz de `desarrollo/`. Está aquí
> para que viaje al clonar; si cambias una, actualiza la otra.

Guía para Claude Code en el árbol completo de RoomFID. Cubre el sistema entero; cada
subproyecto con su propio `CLAUDE.md` (`gestion/`, `raspi_visor/`, `roomfid/`) manda
sobre el suyo.

**Idioma: todo en castellano.** Comentarios, docstrings, mensajes de log, UI y
documentos. El código Python existente **omite las tildes en comentarios y docstrings**
(no en cadenas de presentación): seguir esa convención. Los identificadores van en
castellano sin tildes (`ubicacion_id`, `volcar_antenas`, `faltante_en_ciclo`).

---

## Qué es RoomFID

Convierte un almacén sanitario existente en un sistema de **inventario automático y
trazabilidad** por RFID UHF, sin obras ni cambiar la forma de trabajar. Lectores Keonn
barren las estanterías por ciclos; cada etiqueta leída alimenta la traza de su elemento.

Hay **dos sistemas que se hablan pero no son el mismo**:

| | Quién | Qué hace |
|---|---|---|
| **El almacén** (`irfid/`) | Raspberry en el hospital | Lee etiquetas, decide estados, guarda la traza, orquesta lectores |
| **La gestión** (`gestion/`) | Servidor | Plataforma B2B multi-tenant: catálogos, stock, alertas sanitarias AEMPS |

**La dirección importa:** es la gestión quien **consulta** la API del almacén. El almacén
no escribe en la gestión salvo por el canal que se diseñe explícitamente (ver *Trabajo
pendiente*).

---

## El árbol

| Directorio | Qué es | Git |
|---|---|---|
| `irfid/` | **El núcleo.** Servicio Python del almacén + API Node heredada | sí (main) |
| `gestion/` | Plataforma de gestión: FastAPI + Next.js | sí (rama `redistribucion`) |
| `rep_server/` | **Réplica y despliegue.** Compose del banco, Dockerfiles, scripts de clonado | sí (main) |
| `monitor/` | Monitorización: nodo central + agente por instalación | sí (main) |
| `raspi_visor/` | Visor de solo lectura del almacén (React + FastAPI proxy) | sí (main) |
| `roomfid/` | Web corporativa (Next.js). Nada que ver con el sistema | sí (main) |
| `Papelera_2026/papelerIA/` | Terminal de la papelera (Python + UI en kiosco). Se trabaja en sesión aparte | — |
| `almacen_mqtt/`, `api/`, `Servicio_postgresql/` | **Sistema antiguo**, solo referencia histórica | — |

**La raíz no es un repositorio.** Cada proyecto lleva el suyo; no hay superproyecto.

---

## irfid — el servicio del almacén

`irfid/servicio/`, Python 3.11+, asyncio, psycopg3, pydantic-settings. Un paquete,
varios procesos:

```
python -m irfid [almacen]      ingesta + trazabilidad + espejo legacy + alertas
python -m irfid orquestador    ciclo de lectores (sustituye a Node-RED)
python -m irfid migrar         aplica el esquema traza (idempotente)
python -m irfid bootstrap      topologia + elementos desde el estado legacy
python -m irfid archivo <ord>  archivado mensual / backup / consulta
python -m irfid comparar       modo sombra: legacy frente a traza
```

### El camino de una lectura

```
Lector Keonn ──MQTT──> ingest.py ──> WindowAggregator ──> Spool ──> Procesador ──> traza.*
   (TAG_readings)         │           (dedup 5 s)        (SQLite    (reglas.py)      │
                          │                               durable)                   └──> espejo legacy
                          └──> ContadorAntenas (salud por antena)
```

**Piezas clave:**

- `aggregate.py` — colapsa las decenas de lecturas por segundo de una misma etiqueta en
  una observación. Clave `(devid, epc)`. **Es la razón de que el sistema escale**: no
  tocar sin entender las consecuencias.
- `spool.py` — cola durable SQLite (WAL), semántica "al menos una vez". **Monotipo**: el
  payload es siempre una `Observation`, no hay discriminador de destino.
- `reglas.py` — **PURA**: sin base de datos ni reloj. Decide estados y movimientos. Es
  donde vive la lógica de negocio y donde es trivial escribir tests.
- `almacen/repo.py` — toda la E/S. `Procesador` es la clase central.
- `orquestador/ciclo.py` — enciende y apaga lectores por ventanas. Los de un mismo
  almacén leen **en paralelo** (antes era en serie, como Node-RED).
- `almacen/alertas.py` — alertas con responsables por ubicación, agrupación por persona,
  reintentos (`MAX_INTENTOS=20`) y reaviso diario.
- `papelera/api.py` — FastAPI que recibe las sesiones de los terminales papelerIA,
  firmadas con HMAC-SHA256.

### Configuración

Todo por entorno, prefijo `IRFID_`, en `config.py` (pydantic-settings). Dos valores con
criterio detrás:

- **`MQTT_CLIENT_ID` debe ser estable.** Con `clean_session=False` el broker retiene los
  QoS 1 mientras el servicio está caído; si cambia el id, se pierden.
- **`LEGACY_MIRROR`** controla si se escribe también en las tablas antiguas. Con él
  apagado, el RSSI se descarta por completo (hoy solo acaba ahí).

---

## Las dos bases de datos conviviendo

**Una sola base**, dos esquemas. El antiguo sigue intacto y funcionando; el nuevo añade
lo que el antiguo no podía expresar.

### `public` — el legacy (5 tablas, no tocar su forma)

`EPC_master` (catálogo), `EPC_readings` (**estado**: una fila por artículo y almacén, se
sobrescribe), `Bin` (consumos), `User_readings` (carnets), `user_room` (permisos).

Sin claves foráneas, fechas en `varchar`, y la API Node y Node-RED siguen leyendo de
aquí. **Lo único que se le ha añadido**: `creado_at`/`modificado_at`, tres índices y los
triggers de sincronización — todo transparente porque ningún controlador hace `SELECT *`.

### `traza` — el nuevo (16 tablas)

El cambio de fondo: el legacy guarda **dónde está cada cosa ahora**; `traza` guarda
**qué le ha ocurrido**. Nada se borra.

- `elemento` — estado vivo de cada EPC, con restricciones que impiden estados imposibles
  (un elemento en stock **tiene** que tener ubicación).
- `movimiento` — cada cambio con hora, estados de origen y destino, ubicaciones, lector
  y usuario. **Particionada por mes.**
- `ubicacion` / `lector` — topología real (almacenes, puertas, quirófanos, papeleras).
- `acceso` — cada paso de carnet por una puerta. **Particionada.**
- `alerta` / `responsable` — avisos con reintentos y destinatarios por ubicación.
- `ventana_lectura` / `ciclo` — qué leyó cada lector y cuándo. **Particionadas.**

7 tipos ENUM, 24 claves foráneas, 14 índices, 6 funciones, 3 triggers.

### El hallazgo que importa

`EPC_readings` **no tenía índice único** sobre `(EPC, devid)`, aunque todo el sistema
depende de esa unicidad. Está en `sql/001_indice_unico.sql`, con `CONCURRENTLY`.
**Comprobar duplicados antes de aplicarlo en producción** (la consulta está en el
fichero).

### Los SQL

`irfid/servicio/sql/0NN_*.sql`, idempotentes, aplicados en orden por
`python -m irfid migrar`. **Cada fichero se envía en un solo `execute`** con
`autocommit=True` (`bootstrap.py:32-39`).

> **Trampa verificada:** `ALTER TYPE ... ADD VALUE` y el uso de ese valor **no pueden ir
> en el mismo fichero** (`New enum values must be committed before they can be used`).
> Si hace falta un valor nuevo de ENUM, va en su propio fichero numerado, antes del que
> lo usa. Reaplicarlo es inocuo.

En gestión, en cambio, las migraciones son **Alembic**, con `upgrade` **y** `downgrade`.

---

## El banco de pruebas y el despliegue

`rep_server/banco/` — Docker Compose con el sistema completo. Nueve servicios:

| Servicio | URL (Pi del banco: `192.168.0.60`) | Qué |
|---|---|---|
| `visor` | **http://192.168.0.60:8020** | Visor de almacén. Se abre en el navegador |
| `monitor` | **http://192.168.0.60:8080** | Panel de monitorización |
| `mailpit` | **http://192.168.0.60:8025** | Bandeja de correo de pruebas |
| `api` | http://192.168.0.60:3000/api | API Node heredada. Exige `x-api-key` (401 sin ella) |
| `irfid-almacen` | http://192.168.0.60:8090/health | Salud de la trazabilidad (JSON) |
| `irfid-almacen` | http://192.168.0.60:8092/api/papelera/v1 | API de papeleras. Exige firma HMAC (401 sin ella) |
| `irfid-orquestador` | http://192.168.0.60:8091/health | Salud del ciclo de lectores |
| `pg` | `192.168.0.60:5432` | PostgreSQL 18. Base `gestion_rfid`, usuario `rfidroom` |
| `mosquitto` | `192.168.0.60:1883` | Broker MQTT |
| `monitor-agente` | — | Agente local, sin puerto propio (red de host) |

Las tres primeras son las que se abren en el navegador; el resto son interfaces de
máquina. Un **401 en la API legacy y en la de papeleras es correcto**: significa que
están protegidas. El orquestador puede dar **503 cuando no alcanza sus lectores**, que
es lo que pasa fuera de la instalación real.

Desde la propia Pi, las mismas rutas en `127.0.0.1`. Para ver los registros:
`cd ~/roomfid && docker compose logs -f <servicio>`.

**PostgreSQL 18 es obligatorio**: el esquema usa `uuidv7()`, que no existe en la 17.

### Las otras máquinas de la sala

| Equipo | Dirección | Qué es |
|---|---|---|
| Terminal papelerIA | `192.168.0.15` | Pantalla en kiosco. Local: http://127.0.0.1:8085 · config con **Ctrl+Shift+S** (teclado USB) · `/etc/papeleria/papeleria.env` |
| Lector Keonn papelera | `192.168.0.159` | Web en el 80 (Digest `admin`), AdvanNet en 3177, API en 3161. MAC `64:8c:bb:f0:b9:28` |
| Lectores de inventario | `192.168.1.157` / `.158` | **Otra red**: inalcanzables desde la sala. Por eso el orquestador da 503 |
| Gestión | esta máquina | Apunta al lector por `licencias.lector_url` (licencia **Demo**), no por el `.env` |

**El terminal no usa MQTT**: habla con su lector por AdvanNet y REST, y con el servidor
por HTTP firmado. El broker solo interviene en las lecturas de inventario.

**El lector de puerta** (quién entra al almacén, para la trazabilidad de usuario) está
documentado en `rep_server/docs/lector-puerta.md`: payload, filtro de EPC y la consulta
JDBC con la que valida el carnet él mismo. Hoy **ese aparato hace de papelera** — es el
mismo, y con uno solo no se pueden tener las dos funciones.

### Clonar a otra Raspberry — `rep_server/clon/`

La Raspberry **solo ejecuta**: no lleva código fuente ni compila. Las imágenes se
construyen aquí (x86_64) para ARM y allí solo se cargan.

```bash
./construir-arm64.sh                        # 5 imágenes arm64 (emulación, tarda)
./empaquetar.sh --desde andy@IP_ORIGEN      # imágenes + config + volcado (~183 MB)
scp roomfid-pi-*.tar.gz andy@IP_NUEVA:~/
ssh andy@IP_NUEVA 'tar xzf roomfid-pi-*.tar.gz && cd roomfid-pi && ./instalar.sh'
```

El `docker-compose.yml` de `clon/` es el del banco **sin un solo `build:`** — cada
servicio arranca de su imagen. `ETIQUETA` permite versionar y volver atrás.

**Requisitos de la Raspberry:** Pi OS **64 bits** (con 32 no arrancan las imágenes),
usuario `andy`, Docker + plugin compose, y `usermod -aG docker andy`.

### Cuatro trampas del despliegue (todas resueltas en los scripts)

1. **El `passwd` de Mosquitto no se copia.** Es del uid 1883 con permisos 0700; copiado
   de otra máquina el broker falla con `Unable to open pwfile`. Se regenera en destino.
   Además, `mosquitto_passwd -c` **no sobrescribe**: hay que borrar el fichero antes.
2. **La base se vuelca con `pg_dump`, nunca copiando el volumen** (en caliente saldría
   corrupta). El paquete lleva el recuento de origen para verificar que llegó entero.
3. **El `initdb` espera `/volcado/produccion.sql` sin comprimir**, con ese nombre exacto.
4. **El `.env` no viaja** (credenciales en claro): va la plantilla.

---

## Estado actual (19/10/2026)

- **`192.168.0.60`** — Raspberry de 128 GB, **sistema completo arrancado y verificado**.
  997 elementos y 1.003 movimientos, idéntico al origen. Los nueve servicios arriba.
- **`192.168.0.59`** — la Raspberry anterior (15 GB, al 60%). Desconectada tras el
  clonado.
- **Lectores `192.168.1.157` y `.158`** — en **otra instalación**, inaccesibles desde la
  red de desarrollo. El orquestador los marca como fallidos y queda `unhealthy`: es
  **esperable**, no es un fallo del sistema. Las pruebas reales de ciclo requieren
  desplazarse.

---

## Trabajo pendiente

- **Detección de manipulación por RSSI** — plan completo y PDF en
  `rep_server/manipulacion-rssi-plan.pdf`. Diseñado, **no implementado**. El hallazgo
  central: *un acceso autorizado reciente exculpa; la ausencia de acceso acusa*. Requiere
  línea base por antena, porque el `rssi_max` actual es el `max()` de dBm negativos (la
  señal **más fuerte**) y mezcla antenas.
- **Canal irfid → gestión: existe para el inventario** (`almacen/gestion.py`). Al cerrar
  un ciclo válido se encola en `traza.envio_gestion` y una tarea lo manda a
  `POST /api/v1/products-scan`; allí lo que está en stock y no se ha leído pasa a
  `en_transito`. **Apagado por defecto** (`IRFID_GESTION_ACTIVO`): encenderlo mueve
  estados en gestión y deshacerlo es manual. Tres cortes lo protegen — ciclo válido,
  cobertura propia (0.9, más estricta que `cobertura_minima`) y tope de salidas de golpe
  (100): un ciclo sin lecturas marcaría como salido **todo** el stock.
- **Incidencias (RSSI) hacia gestión**: sigue sin existir. Decidido:
  `POST /api/v1/incidencias` con `require_almacen_bearer`.
- **Caducados y defectuosos** desde gestión (alertas AEMPS) hacia el almacén: pendiente
  de diseño.
- **Rastreo entre hospitales.** Hoy imposible: `traza.instalacion` tiene
  `CHECK (unica)` — una instalación por base.
- **Credenciales en claro** en `banco/api/app.json` y en los `.env`. Deuda conocida.

---

## Normas de trabajo

**Verificar antes de afirmar.** Este sistema tiene hardware real detrás y varias capas
heredadas. Medir en el banco antes de dar por bueno un diagnóstico; varias hipótesis
razonables han resultado falsas al comprobarlas.

**Reutilizar antes que crear.** Hay mucho ya resuelto: `_ultimo_acceso()` para saber
quién entró, `alertas.py` para avisar por correo, `ContadorAntenas` como patrón de
acumulador con volcado periódico, `Spool` para durabilidad.

**Los comentarios explican el porqué, no el qué.** El código existente lo hace así y es
lo que lo hace mantenible.

**Tests:** irfid usa pytest con dobles (`tests/`) e integración con contenedor
`postgres:18` (`tests/integracion/`). Gestión tiene su suite. Ninguna debe bajar de su
cobertura actual.

**Git:** commits cuando se pidan, nunca automáticos. `rep_server` tiene un **token de
GitHub en claro** en el remoto (`.git/config`) — pendiente de revocar; no hacer `push`
hasta resolverlo.
