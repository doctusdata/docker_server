# Prueba en campo: modo sombra en una Raspberry

El sistema nuevo (irfid) corre en una Raspberry conectada a la LAN del almacén y **escucha**
el sistema real sin tocarlo:

- Tiene **su propia base** (PostgreSQL 18), cargada con un volcado de producción.
- Se suscribe al **broker MQTT real** sin sesión persistente: al desconectarse no deja
  nada encolado en el broker.
- **No escribe nada en producción.** Node-RED, `almacen_mqtt` y el batch siguen como
  están. El orquestador no se arranca.
- El visor y el monitor apuntan a los equipos reales.

Al cabo de unos días, `scripts/comparar.sh` enfrenta lo que dice producción con lo que ha
calculado irfid.

**Vuelta atrás:** apagar la Pi. No hay nada más que deshacer.

## Requisitos de la Raspberry

- Pi 4 con 4 GB o más, o Pi 5.
- **Sistema de 64 bits** (Raspberry Pi OS 64-bit / arm64).
- Docker y el plugin compose: `curl -fsSL https://get.docker.com | sh`.
- Mejor con un SSD por USB. En tarjeta SD vale para unos días.
- IP en la red del almacén (192.168.1.x), fija o reservada.
- **Primera construcción: 15-30 minutos** en la Pi, porque compila los frontales. Mejor
  hacerla en casa, con internet, antes de ir.

## Llevar el código

En la máquina de desarrollo:

```bash
rep_server/scripts/empaquetar.sh              # -> desarrollo/roomfid-pi.tar.gz
scp roomfid-pi.tar.gz pi@<ip-pi>:
```

En la Pi:

```bash
mkdir roomfid && cd roomfid && tar xzf ~/roomfid-pi.tar.gz
cd rep_server/campo
cp .env.ejemplo .env && nano .env              # credenciales reales
docker compose build                           # con internet, antes de ir
```

## El día de la prueba

```bash
cd ~/roomfid/rep_server/campo
./scripts/volcado.sh       # pg_dump de produccion (solo lectura) -> volcado/produccion.sql
./scripts/arrancar.sh      # restaura el volcado, arranca y hace el bootstrap
./scripts/estado.sh        # salud, ultimos ciclos, recuento por estado
```

| URL (en la IP de la Pi) | Qué es |
|---|---|
| `:8020` | Visor (datos de la API real) |
| `:8080` | Monitor: la Pi, el servidor .155, la API, MQTT y los 4 lectores |
| `:8090/health` | Estado de irfid: MQTT, base, cola, contadores, **lectores desconocidos** |

## Comprobaciones en los primeros minutos

1. **`/health` → `mqtt: true`.** Si no conecta, revisa `MQTT_USER`/`MQTT_PASS` y que el
   broker admita conexiones desde la IP de la Pi.
2. **`/health` → `lectores_desconocidos` vacío.** Si aparece alguna MAC, un lector real
   publica con una MAC distinta de `topologia.json`. Corrígela y reinicia con
   `docker compose restart irfid-almacen`. Las MAC salen del `app.json` de producción, y
   el lector de papelera es el menos seguro.
3. **Ventanas.** Tras el primer ciclo de Node-RED, `docker compose logs -f irfid-almacen`
   debe mostrar `ventana cerrada ... valida`. Lo esperado:
   - La primera ventana de cada lector sale `INVALIDA (arranque)`. Es normal.
   - `INVALIDA (corta)` en todas: las ventanas reales duran menos de 30 s. Baja
     `IRFID_VENTANA_MIN_S` en `.env`.
   - Ventanas partidas en varias: el lector deja huecos de más de 20 s sin publicar.
     Sube `IRFID_VENTANA_GAP_S` en `.env`.
4. **Ciclos.** `estado.sh` debe mostrar ciclos `valido = t`. Si salen
   `motivo_invalido = cobertura`, los lectores reales ven menos de la mitad del stock por
   ciclo. Anota el porcentaje: es un dato valioso sobre el sistema real.
5. **Puerta.** Pasa una tarjeta por la puerta y comprueba:
   `SELECT * FROM traza.acceso ORDER BY at DESC LIMIT 5;` (`psql` en `-p 15432`).

## Durante los días de prueba

```bash
./scripts/comparar.sh          # produccion frente a sombra, con las diferencias caso a caso
./scripts/estado.sh
```

Las diferencias esperables no son errores:

- **Ritmo distinto.** El sistema actual marca "no encontrado" a los 5 minutos sin lectura.
  irfid marca "temporal" solo al cerrar un ciclo completo y válido.
- **Usuario distinto.** El sistema actual asigna al último carnet leído en la puerta, sin
  límite de tiempo. irfid asigna el acceso anterior a la detección y lo marca con
  confianza `ventana` o `ultimo`.

Lo que hay que mirar con lupa:

- Elementos que irfid da por `temporal` y que producción ve en stock durante horas.
- Lo contrario: producción los da por salidos e irfid los sigue viendo.

## Si algo falla

- **`volcado.sh` no conecta a la base de producción.** El `pg_hba.conf` del .155 puede no
  admitir la IP de la Pi. No lo toques; saca el volcado en el propio servidor:
  `pg_dump -U rfidroom --exclude-schema=traza gestion_rfid > produccion.sql`.
  Cópialo a `campo/volcado/`. `comparar.sh` tampoco funcionará en ese caso: repite el
  volcado al final de la prueba y compáralo a mano.
- **Empezar de cero con un volcado nuevo:**
  `./scripts/parar.sh -v && ./scripts/volcado.sh && ./scripts/arrancar.sh`.
- **Logs:** `docker compose logs -f irfid-almacen`.

## Parar

```bash
./scripts/parar.sh         # conserva la base de la sombra
./scripts/parar.sh -v      # la borra
```
