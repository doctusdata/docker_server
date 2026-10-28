# Instalar la sincronización en la sala demo, desde cero

Una página. El detalle está en `gestion/docs/pi-cambios-sincronizacion.md`, pero para
hacerlo basta con esto y en este orden.

**La idea:** borrar lo que hay y empezar limpio. Los datos actuales son de prueba, y
arrastrarlos traería el estado del sistema antiguo —vocabulario viejo, altas por
lectura— a un sistema que ya no funciona así. Lo que queda después es una Pi que sabe
exactamente de dónde viene cada cosa: de la plataforma de gestión.

---

## 0. Antes de empezar

```bash
cd ~/roomfid
git -C ~/irfid log --oneline -1        # debe decir "Archivado del historico..."
grep -i LEGACY_MIRROR .env             # si está a true, el servicio ya no arranca
```

El código tiene que ser el de la rama `sincronizacion-c` en los tres repositorios
(`gestion`, `irfid`, `rep_server`).

### Construir y llevar las imágenes (desde el Mac)

La Pi solo ejecuta: no compila. Las imágenes se construyen aquí y allí solo se
cargan. **En un Mac con Apple Silicon esto es nativo**, no emulado, así que tarda
minutos y no horas.

```bash
open -a OrbStack                      # el motor, primero: sin él nada funciona
cd rep_server/clon
./construir-arm64.sh                  # las cinco, arm64 nativo
./empaquetar.sh                       # ~192 MB, SIN volcado
scp roomfid-pi-*.tar.gz andy@IP_PI:~/
ssh andy@IP_PI 'tar xzf roomfid-pi-*.tar.gz && cd roomfid-pi && ./instalar.sh'
```

Verificado en un M3: las cinco imágenes salen arm64 y el paquete son 192 MB.

**Si dice «el builder no puede construir arm64»**, lo primero que hay que mirar es
si el motor está arrancado — en un Mac es la causa en casi todos los casos. El
script ya lo comprueba antes y lo dice con esas palabras.

**Qué corre dónde.** Lo de `clon/` (construir, empaquetar) en el Mac; todo lo demás
—`instalar.sh`, `empezar-de-cero.sh`, `verificar-sincronizacion.sh`,
`simular-ciclo.sh`— **en la Pi**, porque usan `docker compose exec` contra sus
propios contenedores.

## 1. Borrar y rehacer la Pi

```bash
./scripts/empezar-de-cero.sh
```

Hace copia de seguridad, borra el esquema `traza`, aplica `sql/010…020`, carga la
topología y arranca. Pide escribir `borrar` para confirmar. **No toca el esquema
`public` legacy**, que ya nadie alimenta pero que `raspi_visor` y la API Node siguen
leyendo.

## 2. Limpiar también la operación de gestión

Una sola vez, no por Pi:

```bash
cd backend && python -m scripts.limpiar_operacion --borrar
```

No toca `cima_nomenclator` —son 30.500 presentaciones de un XML de 192 MB—, ni
catálogos, ni licencias, ni usuarios.

## 3. Vincular

```
En gestión:  Almacenes → <el almacén> → Vincular Pi      (anota el código)
```

```bash
docker compose exec irfid-almacen \
  python -m irfid vincular --gestion https://TU-GESTION --codigo XXXX-XXXX
```

El código es de un solo uso y caduca en 24 h. **Es la Pi quien llama**: gestión no
necesita alcanzar esta máquina, y por eso funciona desde la red interna.

Sin código a mano, la Pi puede presentarse con su número de serie y esperar
aprobación: el mismo comando sin `--codigo`.

## 4. Saber qué funciona y qué no

```bash
./scripts/verificar-sincronizacion.sh
```

Comprueba las piezas **en orden de dependencia** y dice de cada una si está, con el
sitio donde mirar cuando no. Si hay varios ✗, empieza por el primero: los de abajo
suelen ser consecuencia.

Solo el esquema, sin lo demás: `./scripts/verificar-sincronizacion.sh --esquema`.

## 5. Probar que el circuito funciona

Los lectores de inventario están en otra red y son inalcanzables desde la sala. El
**503 del orquestador es esperable**, no un fallo. Para probar sin ellos:

```bash
# Da de alta material en gestión (pantalla de escaneo). En menos de un intervalo
# debe aparecer en la Pi CON SU NOMBRE:
docker compose exec -T pg psql -U rfidroom -d gestion_rfid -c \
  "SELECT epc, nombre, estado FROM traza.elemento LIMIT 5"

./scripts/simular-ciclo.sh                      # ciclo completo
./scripts/simular-ciclo.sh --faltan 2           # provoca temporales
./scripts/simular-ciclo.sh --desconocido        # debe ir solo a epc_desconocido
./scripts/simular-ciclo.sh --papelera <EPC>     # consumo → usado
./scripts/simular-ciclo.sh --papelera <EPC> --incidencia "envase roto"   # → retirado
```

**Lo que hay que ver, y es la prueba de que esto funciona:**

| Prueba | Resultado correcto |
|---|---|
| Alta en gestión | aparece en la Pi con su nombre real, no solo el EPC |
| Ciclo completo | `valido=t`, 0 faltantes |
| `--faltan 2` | 2 temporales, **y ningún `en_transito`** al primer fallo |
| Repetirlo hasta agotar reintentos | entonces sí `en_transito`, motivo `anomalia` |
| `--desconocido` | solo en `epc_desconocido`, **nada** en `traza.elemento` |
| `--papelera` sin incidencia | `usado` |
| `--papelera --incidencia` | `retirado` |
| `--papelera --incidencia anulada` | `usado` (el criterio del operario gana) |
| Tras la papelera | la fila sale de `envio_estado` y `local_pendiente` vuelve a `false` |

Y en gestión: la etiqueta `usado`/`retirado` con su movimiento de consumo, con el
paciente y la incidencia.

## 6. Los tests que nadie ha ejecutado todavía

**219 tests de integración.** Es lo que más conviene correr aquí, porque cubren
justo lo que no se puede probar a ojo: la reconstrucción del ENUM, la regla de
autoridad de `local_pendiente`, el marcar-y-barrer de la foto completa, la
idempotencia de los dos canales y el archivado.

```bash
# irfid — crea y destruye sus propias bases
cd servicio && IRFID_TEST_PG="host=127.0.0.1 port=5432 user=rfidroom password=<pass>" \
  python -m pytest tests/integracion -q

# gestión — base APARTE. NUNCA gestion_rfid: el fixture hace drop_all.
docker compose exec -T pg psql -U rfidroom -d postgres \
  -c 'CREATE DATABASE roomfid_test TEMPLATE template0;'
cd backend && TEST_DATABASE_URL=postgresql+psycopg://rfidroom:<pass>@127.0.0.1:5432/roomfid_test \
  python -m pytest -m integration -q
```

---

## Si algo va mal

| Síntoma | Dónde mirar |
|---|---|
| La Pi no recibe nada | `traza.gestion.ultimo_error`, y `/health` → `bajada` |
| Llegan etiquetas sin nombre | la vista `v_etiqueta_sync` de gestión no resuelve el arco |
| Rechazos `estado_desconocido` | falta aplicar `sql/018`: el ENUM sigue con el vocabulario viejo |
| `local_pendiente` crece y no baja | el canal de subida no entrega. **Es una fuga real**: esos elementos se quedan sordos al estado de gestión |
| Cola `agotado` en `envio_gestion` | casi siempre el token o el `store_id` |
| `rechazado` en `envio_estado` | gestión no conoce esas etiquetas. No se reintenta a propósito |
| El orquestador en 503 | **esperable.** Los lectores están en otra red |

Volver atrás: la copia que hizo el paso 1 está en `~/antes-de-cero-*.sql.gz`.

```bash
docker compose stop irfid-almacen irfid-orquestador
gunzip -c ~/antes-de-cero-AAAAMMDD-HHMM.sql.gz | \
  docker compose exec -T pg psql -U rfidroom -d gestion_rfid
docker compose up -d
```

## Lo que queda pendiente, y conviene saberlo antes de la demo

- **El terminal papelerIA lleva un puente temporal.** El `/catalogo` que la Pi le
  sirve traduce los estados al vocabulario viejo, porque el terminal mira ese campo
  para decir "ya estaba" y vive fuera del repositorio. El valor real va en
  `estado_gestion`. Funciona, pero hay que retirarlo cuando se toque papelerIA.
- **`alerta_sanitaria` se sirve `false`** en el catálogo de papeleras. La decide
  gestión, que cruza las alertas de la AEMPS, y todavía no baja por el canal.
- **Un almacén no puede tener dos Pi activas** (índice único parcial). Para mover una
  Pi de almacén, hay que revocar primero — y revocar **rota el token**.
