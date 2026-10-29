# Instalar la sincronización en la sala demo

Procedimiento completo, desde cero. Pensado para seguirlo de pie en la sala.

**Qué se instala:** el rediseño de la sincronización entre la plataforma de gestión
y la Pi del almacén. Gestión pasa a ser la única fuente del catálogo y de los
estados; la Pi arranca vacía y pide lo suyo.

**Por qué desde cero y no migrando:** los datos que hay son de prueba. Migrarlos
arrastraría el estado del sistema antiguo —vocabulario viejo, altas por lectura— a
uno que ya no funciona así. Después, la Pi sabe de dónde viene cada cosa.

---

## Antes de salir de casa

Esto no se puede arreglar en la sala. Compruébalo aquí.

### 1. El código, en las tres ramas

```bash
for r in gestion irfid rep_server; do
  echo "$r: $(git -C ~/desarrollo/$r branch --show-current)"
done
# los tres deben decir: sincronizacion-c
```

### 2. ⚠️ El `external_id` del almacén tiene que cuadrar

**Es el error más caro de todos**, porque la Pi se vincula bien, todo parece
correcto y aun así **no reporta ningún inventario**.

En gestión, `Almacen.external_id` tiene que ser **exactamente** el `codigo` de una
ubicación de `topologia.json`. Es el mismo identificador por los dos lados —el
devid del lector— solo que cada uno lo llama a su manera.

| Gestión | Pi (`topologia.json`) |
|---|---|
| `Almacen.external_id` = `Almacen-1` | `ubicacion.codigo` = `Almacen-1` |

```bash
# en gestión
psql -c "SELECT nombre, external_id FROM almacenes"
# en la Pi
python3 -c "import json;print([u['codigo'] for u in json.load(open('topologia.json'))['ubicaciones']])"
```

Si no coinciden, corrige el `external_id` en gestión **antes de ir**.

### 3. Material dado de alta en gestión

La Pi no inventa inventario: lo pide. Si en gestión no hay etiquetas con su
almacén asignado, la Pi se quedará vacía y todo lo que lea irá a
`epc_desconocido` — el almacén aparecerá vacío aunque esté lleno.

Da de alta unas cuantas unidades por la pantalla de escaneo antes de ir.

### 4. Decide cómo llevas las imágenes

| | Dónde compila | Cuándo |
|---|---|---|
| **`banco/`** | **en la propia Pi** | lo de siempre. No necesitas el Mac |
| `clon/` | en el Mac, la Pi solo carga | Pi nueva sin código, o no querer compilar allí |

**Con `banco/` (lo normal):** la Pi necesita **internet** para `construir.sh` —
descarga las imágenes base. 15-30 min la primera vez. Después opera sin conexión.

**Con `clon/` (desde el Mac):**

```bash
open -a OrbStack                      # primero el motor; sin él, nada
cd rep_server/clon
./construir-arm64.sh                  # arm64 NATIVO en Apple Silicon: minutos
./empaquetar.sh                       # ~192 MB, sin volcado
scp roomfid-pi-*.tar.gz andy@IP_PI:~/
```

> Si dice *«el builder no puede construir arm64»*, lo primero es si el motor está
> arrancado. En un Mac es la causa en casi todos los casos.

---

## En la sala

### Paso 1 · Dejar la Pi vacía

```bash
cd ~/roomfid
./scripts/construir.sh         # solo si usas banco/ y hay código nuevo
./scripts/empezar-de-cero.sh
```

Hace copia de seguridad **verificada** (si el volcado sale truncado, no sigue),
borra el esquema `traza`, aplica `sql/010…020`, carga la topología y arranca. Pide
escribir `borrar` para confirmar.

No toca el esquema `public` legacy: ya nadie lo alimenta, pero `raspi_visor` y la
API Node lo siguen leyendo.

### Paso 2 · Limpiar la operación de gestión

Una sola vez, no por Pi:

```bash
cd backend && python -m scripts.limpiar_operacion --borrar
```

No toca `cima_nomenclator` —30.500 presentaciones de un XML de 192 MB—, ni
catálogos, ni licencias, ni usuarios.

### Paso 3 · Vincular

```
En gestión:  Almacenes → <el almacén> → Vincular Pi
```

Anota el código `XXXX-XXXX`. **Un solo uso, caduca en 24 h.**

```bash
docker compose exec irfid-almacen \
  python -m irfid vincular --gestion https://TU-GESTION --codigo XXXX-XXXX
```

Esto deja configurado **todo**: la URL, el token de cada almacén, el enlace con la
ubicación local y los parámetros. No hay que editar ningún `.env`.

**Es la Pi quien llama.** Gestión no necesita alcanzar esta máquina, y por eso esto
funciona desde la red interna del hospital.

> Sin código a mano, la Pi puede presentarse con su número de serie y esperar
> aprobación: el mismo comando sin `--codigo`. Queda en una cola en gestión
> (*Almacenes → Pi pendientes*) y sondea hasta que alguien la apruebe.

### Paso 4 · Saber dónde estás

```bash
./scripts/verificar-sincronizacion.sh
```

Comprueba las piezas **en orden de dependencia** y dice de cada una ✓ o ✗ con dónde
mirar. **Si hay varios ✗, empieza por el primero:** los de abajo suelen ser
consecuencia.

Solo el esquema: `--esquema`.

### Paso 5 · Probar el circuito

Los lectores de inventario están en otra red y son inalcanzables desde la sala. El
**503 del orquestador es esperable**, no un fallo. Para probar sin ellos:

```bash
./scripts/simular-ciclo.sh                    # ciclo completo
./scripts/simular-ciclo.sh --faltan 2         # provoca temporales
./scripts/simular-ciclo.sh --desconocido      # un EPC que gestión no dio
./scripts/simular-ciclo.sh --papelera <EPC>
./scripts/simular-ciclo.sh --papelera <EPC> --incidencia "envase roto"
```

Publica exactamente lo que publicaría un Keonn, con los `devmac` reales: el
servicio no lo distingue de un lector de verdad.

**Lo que tiene que pasar:**

| Prueba | Correcto |
|---|---|
| Alta en gestión | aparece en la Pi **con su nombre real**, no solo el EPC |
| Ciclo completo | `valido=t`, 0 faltantes |
| `--faltan 2` | 2 temporales, **y ningún `en_transito`** al primer fallo |
| Repetir hasta agotar reintentos | entonces sí `en_transito`, motivo `anomalia` |
| `--desconocido` | solo en `epc_desconocido`, **nada** en `traza.elemento` |
| `--papelera` sin incidencia | `usado` |
| `--papelera --incidencia "roto"` | `retirado` |
| `--papelera --incidencia "anulada"` | `usado` — el criterio del operario gana |
| Tras la papelera | sale de `envio_estado` y `local_pendiente` vuelve a `false` |

Y en gestión: la etiqueta `usado`/`retirado`, con su movimiento de consumo llevando
el paciente y la incidencia.

### Paso 6 · Los 219 tests que nadie ha ejecutado

**Es lo más valioso que puedes hacer allí.** Cubren justo lo que no se ve a ojo: la
reconstrucción del ENUM de estados, la regla de autoridad de `local_pendiente`, el
marcar-y-barrer de la foto completa, la idempotencia de los dos canales y el
archivado.

```bash
# irfid — crea y destruye sus propias bases
cd servicio && IRFID_TEST_PG="host=127.0.0.1 port=5432 user=rfidroom password=<pass>" \
  python -m pytest tests/integracion -q

# gestión — base APARTE
docker compose exec -T pg psql -U rfidroom -d postgres \
  -c 'CREATE DATABASE roomfid_test TEMPLATE template0;'
cd backend && TEST_DATABASE_URL=postgresql+psycopg://rfidroom:<pass>@127.0.0.1:5432/roomfid_test \
  python -m pytest -m integration -q
```

> ⚠️ **Nunca apuntes `TEST_DATABASE_URL` a `gestion_rfid`.** El fixture hace
> `drop_all`: destruiría la base del banco.

### Paso 7 · Antes de irte

```bash
./scripts/verificar-sincronizacion.sh --demo
```

Dice si la Pi puede sobrevivir sin gestión y cuántos consumos y ciclos le quedan
por entregar.

---

## La gestión no estará siempre encendida

**Hace falta una vez, al instalar.** Sin la primera bajada la Pi no tiene nada, y
todo lo que lea acabará en `epc_desconocido`.

A partir de ahí es autónoma: *sin red guarda y sincroniza en cuanto puede, misma
política siempre*.

| Con gestión apagada | |
|---|---|
| Ciclos de inventario | **funciona** |
| Papelera (consumo y retirada) | **funciona** |
| Trazabilidad y movimientos | **funciona** |
| Alertas por correo | **funciona** |
| Visor | **funciona** |
| Material **nuevo** dado de alta en gestión | no llega hasta que vuelva |
| Consumos hacia gestión | se acumulan en cola, se entregan al reconectar |

> Con gestión apagada, **`local_pendiente` creciendo es normal**: son hechos que la
> Pi ha decidido y aún no ha podido contar. Solo es un problema con gestión
> encendida, y el verificador distingue los dos casos.

---

## Si algo va mal

| Síntoma | Dónde mirar |
|---|---|
| **El almacén aparece vacío aunque esté lleno** | la Pi no tiene inventario: falta la primera bajada. `verificar-sincronizacion.sh --demo` |
| **Vinculada pero no reporta ningún ciclo** | el `external_id` no cuadra con ningún `codigo` de `topologia.json`. Ver *Antes de salir*, punto 2 |
| La Pi no recibe nada | `traza.gestion.ultimo_error`, y `/health` → `bajada` |
| Llegan etiquetas sin nombre | la vista `v_etiqueta_sync` de gestión no resuelve el arco |
| Rechazos `estado_desconocido` | falta aplicar `sql/018`: el ENUM sigue con el vocabulario viejo |
| `local_pendiente` crece | con gestión apagada es **normal**. Con gestión encendida es una fuga: esos elementos se quedan sordos a su estado |
| Cola `agotado` en `envio_gestion` | casi siempre el token o el `store_id` |
| `rechazado` en `envio_estado` | gestión no conoce esas etiquetas. **No se reintenta a propósito** |
| El orquestador en 503 | **esperable.** Los lectores están en otra red |
| `IRFID_LEGACY_MIRROR=true` | el servicio **no arranca**, a propósito. Ponlo a `false` |

### Volver atrás

**Los dos lados se deshacen de forma distinta, y conviene saberlo antes de empezar.**

| | Cómo se vuelve | Qué se pierde |
|---|---|---|
| **Gestión** (Alembic) | `alembic downgrade <revisión>` | nada, salvo en `l4` |
| **La Pi** (ficheros SQL) | **solo restaurando un volcado** | lo ocurrido desde la copia |

#### Gestión: hay `downgrade` y funciona

Probado de verdad contra PostgreSQL 18: las cinco migraciones nuevas suben y bajan.

```bash
cd backend
alembic downgrade k2_implantable_precio_origen   # deshace l1, l2, l4, l5 y m1
alembic current                                  # comprobar dónde quedó
```

La única que **pierde datos** es `l4`: borró los productos con GTIN sintético, y su
`downgrade` quita el CHECK pero no los resucita. No se puede inventar lo que se
borró, y fingir que sí sería peor que no poder volver.

#### La Pi: no hay `downgrade`, y `018` no tiene vuelta

`python -m irfid migrar` **solo va hacia delante**: aplica `sql/010…020` y no existe
ningún mecanismo inverso. Y `018` reconstruye el ENUM de estados —crea el nuevo,
convierte las columnas, borra el viejo—, así que después no queda ni el tipo
anterior.

**La copia no es opcional aquí. Es el único camino de vuelta.**

El paso 1 ya la hace y la verifica (si el volcado sale truncado, no sigue). Queda
en `~/antes-de-cero-*.sql.gz`.

```bash
docker compose stop irfid-almacen irfid-orquestador
docker compose exec -T pg psql -U rfidroom -d postgres \
  -c 'DROP DATABASE gestion_rfid' -c 'CREATE DATABASE gestion_rfid'
gzip -dc ~/antes-de-cero-AAAAMMDD-HHMM.sql.gz | \
  docker compose exec -T pg psql -U rfidroom -d gestion_rfid
docker compose up -d
./scripts/verificar-sincronizacion.sh --esquema
```

> El `DROP`/`CREATE` antes de restaurar **importa**: restaurar encima de una base ya
> migrada deja las tablas nuevas conviviendo con el esquema viejo, y el resultado no
> es ni lo uno ni lo otro. El ciclo completo —copiar, migrar, restaurar— está
> probado: vuelven los estados `stock` y el ENUM anterior.

#### Si vas a tocar la base a mano

Haz la copia tú, con el mismo criterio que el script:

```bash
docker compose exec -T pg pg_dump -U rfidroom -d gestion_rfid \
  | gzip > ~/antes-de-$(date +%Y%m%d-%H%M).sql.gz
# y COMPRUÉBALA, que un volcado truncado no se nota hasta que hace falta:
gzip -dc ~/antes-de-*.sql.gz | grep -c "PostgreSQL database dump complete"
```

**Siempre `pg_dump`, nunca copiando el volumen de Docker**: en caliente sale
corrupto, y es un error que no se descubre hasta el día que intentas restaurar.

---

## Qué saber antes de enseñarlo

**Lo que no está verificado.** Nada de esto se ha ejecutado nunca contra una base
real: no hay PostgreSQL 18 fuera de esa Pi. En concreto, el SQL `018` —que
reconstruye el ENUM de estados— se ha leído con cuidado pero no se ha corrido. Por
eso el paso 1 hace copia antes de nada, y por eso el paso 6 importa.

**Deudas conocidas, por si sale la pregunta:**

- **El terminal papelerIA lleva un puente temporal.** El `/catalogo` que la Pi le
  sirve traduce los estados al vocabulario viejo, porque el terminal mira ese campo
  para decir «ya estaba» y vive fuera del repositorio. El valor real va en
  `estado_gestion`. Funciona; hay que retirarlo cuando se toque papelerIA.
- **`alerta_sanitaria` se sirve `false`** en el catálogo de papeleras. La decide
  gestión, que cruza las alertas de la AEMPS, y todavía no baja por el canal.
- **Un almacén no puede tener dos Pi activas.** Para mover una Pi de almacén hay que
  revocar primero — y revocar **rota el token**, que es lo que hace que signifique
  algo.
- **Credenciales en claro** en `banco/api/app.json` y en los `.env`.

---

## Resumen en una pantalla

```
EN CASA     ramas = sincronizacion-c
            external_id de gestión == codigo de topologia.json   ← el caro
            material dado de alta en gestión

EN LA SALA  1. ./scripts/empezar-de-cero.sh
            2. python -m scripts.limpiar_operacion --borrar      (en gestión)
            3. generar código → python -m irfid vincular
            4. ./scripts/verificar-sincronizacion.sh             ← aquí sabes dónde estás
            5. ./scripts/simular-ciclo.sh
            6. los 219 tests de integración                      ← lo más valioso
            7. ./scripts/verificar-sincronizacion.sh --demo      ← antes de irte
```
