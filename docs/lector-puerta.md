# Lector de puerta — configuración original

Transcrito del PDF de Keonn (`RoomFID Máquina/Configuracion _lectores_keon/`) para poder
consultarlo y buscar en él sin abrir el documento.

**Es el mismo aparato que ahora hace de papelera** (MAC `64:8c:bb:f0:b9:28`): se trajo al
banco y se le cambió la IP y el rol. Para devolverlo a puerta hay que revertir lo de
abajo. Con un solo lector no se pueden tener las dos funciones a la vez.

## Para qué sirve

Lee los **carnets** de quien entra al almacén, no los artículos. Eso es lo que permite
decir *quién* se llevó algo: al cerrar un ciclo con faltantes, se les atribuye el último
usuario que pasó la puerta.

## Red y MQTT

| | |
|---|---|
| IP | `192.168.1.159` |
| Broker | `tcp://192.168.1.155:1883` |
| Usuario / clave | `gestion_rfid` / `rfid_room@` |
| Topic | `TAG_readings` |

## Payload

Idéntico al de los lectores de almacén salvo en una línea, que es la que determina todo:

```js
body += '"devid": "Puerta-1",';
```

El `devid` es lo que hace que irfid trate sus lecturas como accesos y no como inventario.
Completo:

```js
var body = '{';
body += '"devid": "Puerta-1",';
body += '"devip": "' + ctx_devip + '",';
body += '"devmac": "' + ctx_devmac + '",';
body += '"reads": [';
for(i = 0; i < ctx_tagno; i++) {
  body += '{';
  body += '"EPC": "' + ctx_tags[i].getEPC() + '",';
  body += '"Antenna": "' + ctx_tags[i].getAntenna() + '",';
  body += '"RSSI": "' + ctx_tags[i].getRSSI() + '"';
  body += '}';
  if(i < ctx_tagno - 1) { body += ','; }
}
body += ']';
body += '}';
```

## Opciones de envío

| Opción | Valor |
|---|---|
| Send one by one | desactivado |
| Inventory tag TTL | **15 s** |
| Keep-alive period | −1 (deshabilitado) |
| Use antenna in tagTTL | **activado** |
| Re-send on COMM error | desactivado |

## Filtro EPC — solo carnets

Sin esto leería también los artículos que pasan por la puerta y los tomaría por personas.

| | |
|---|---|
| Mask offset | 32 bits |
| Filter mask | `0xce002812` |
| Mask length | 16 bits |
| Use SW filter only | desactivado (degrada el rendimiento) |
| Allow Extended EPC Filter | desactivado |

Encaja con los carnets de `user_room`, que empiezan por `ce0028…` — por ejemplo
`ce0028121900000000002f68`, el de Carlos Garcia.

## Alarma con consulta a base

El lector **valida el carnet él mismo**, entrando directamente a PostgreSQL por JDBC. Por
eso el compose publica el puerto 5432: no es para administrar, es para esto.

| | |
|---|---|
| Driver | `org.postgresql.Driver` |
| Cadena | `jdbc:postgresql://192.168.1.155:5432/gestion_rfid` |
| Usuario / clave | `rfidroom` / `rfidroom@2025` |
| Invert query result | desactivado |
| Query cache TTL | 1500 ms |

```sql
SELECT "state"
  FROM "user_room"
 WHERE "epc"  = ${epc}
   AND "state" = 1
   AND "door"  = 'Puerta-1';
```

> El driver JDBC de este lector puede no entender SCRAM, que es el método por defecto de
> PostgreSQL 18. Por eso la clave de `rfidroom` se guarda en `md5` y `pg_hba` usa `md5`
> (`POSTGRES_HOST_AUTH_METHOD=md5` en el compose), que acepta clientes nuevos y antiguos.

## Al montarlo en la sala

Con `./sala-demo.sh on` la Raspberry toma la `192.168.1.155`, así que **el broker y la
cadena JDBC vuelven a ser válidos sin tocarlos**. Lo que sí hay que revertir en el lector:
su IP, el `devid` del payload, el filtro EPC y la configuración de alarma.

En la topología, `Puerta-1` ya existe como ubicación y está vinculada a `Almacen-1`; los
carnets ya están en `user_room`. Falta dar de alta el lector con `rol='puerta'`.

## Credenciales

Este documento las lleva en claro porque así vienen en el PDF original y hacen falta para
configurar el aparato. Son las mismas del sistema de producción: tratar el fichero en
consecuencia.

---

# El mismo aparato como papelera

Decidido el 23/10 en la sala: este lector (`AdvanReader-m1-70-b928`, MAC
`64:8c:bb:f0:b9:28`) se usa como **papelera**, no como puerta. Con uno solo hay que
elegir, y la papelera es lo que se quiere enseñar.

## Configuración objetivo

| Parámetro | Valor | Por qué |
|---|---|---|
| IP | `192.168.1.159/24`, gw `192.168.1.1` | La red de la sala |
| Modo dispositivo | `Autonomous` | Papelera, no puerta |
| Modo lectura | `AUTONOMOUS` | Idem |
| **Filtro EPC** | **vacío** | **Lo más fácil de olvidar.** Con `0xce002812` solo lee carnets (`ce0028…`) y **no ve el material**: como papelera sería inútil |
| Potencia antena | **15** | Los 5 de fábrica no alcanzan |
| Sensibilidad | **−70 dBm** | Con −40 solo leía etiquetas pegadas |
| Alarma / JDBC | desactivada | Era del rol de puerta |

El respaldo del 5/10 guarda los valores **de fábrica** de antena (`power 5`,
sensibilidad `-40`). Si se restaura desde él, hay que volver a subirlos a 15 y −70 a
mano.

## No necesita MQTT

Como papelera, este lector **no publica en el broker**. El terminal papelerIA habla con
él por AdvanNet y REST, y es el terminal quien manda las sesiones al servidor por HTTP
firmado con HMAC. Así que el problema del `MQTTService` que afectó a los lectores de
inventario (ver `docs/lectores-mqtt.md`) **no le afecta**.

## Lo que necesita el terminal

En `/etc/papeleria/papeleria.env`:

```
PAPELERIA_API_URL=http://192.168.1.155:8092/api/papelera/v1
```

Encuentra el lector por MAC; si no, indicárselo con
`PAPELERIA_READER_HOST=192.168.1.159`. Su configuración también se abre con
**Ctrl+Shift+S** desde el teclado USB.

El servidor ya está preparado: la API responde `401` sin firma en
`:8092/api/papelera/v1`, y `traza.dispositivo` tiene `papelera-1` activo con su secreto.
Había 6 sesiones registradas de pruebas anteriores, así que el circuito completo ya
funcionó alguna vez.
