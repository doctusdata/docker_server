# Lector de puerta — configuración original

Transcrito del PDF de Keonn (`RoomFID Máquina/Configuracion _lectores_keon/`) para poder
consultarlo y buscar en él sin abrir el documento.

**Es el mismo aparato que ahora hace de papelera** (MAC `64:8c:bb:f0:b9:28`): se trajo al
banco y se le cambió la IP y el rol. Para devolverlo a puerta hay que revertir lo de
abajo. Con un solo lector no se pueden tener las dos funciones a la vez.

## Para qué sirve

**Desde el 14/11/2026 lee personas y material.** Antes solo leía carnets, y quién se
llevaba algo se deducía al cerrar un ciclo con faltantes: se le atribuía al último que
había pasado la puerta, varios minutos después. Ahora es el control de salida (irfid,
migración `023_bloqueo_puerta.sql`):

1. Pasa una **pulsera del personal** por la puerta: se registra el acceso y se **paran
   las antenas interiores**.
2. Durante **2 minutos desde el último paso de pulsera** (`IRFID_ORQ_PAUSA_ACCESO_S`), todo
   el material que lea la antena de la puerta **pasa a `en_transito` en el acto**,
   atribuido a esa persona. También una caja leída hasta 15 s antes que la pulsera.
3. **Sin pulsera alrededor no se hace nada**: material solo en la puerta es una lectura
   cruzada o algo que pasa cerca.
4. Lo que sale así queda **bloqueado**: una lectura suelta dentro no lo devuelve. Vuelve a
   `almacen` tras **3 ciclos válidos seguidos** en los que se lee dentro
   (`IRFID_CICLOS_CONFIRMAR_RETORNO`). Un ciclo válido sin verlo reinicia la cuenta; uno
   inválido (aborto, cobertura) no cuenta.
5. Pasados los 2 minutos se reanuda la lectura, y la ausencia se sigue detectando como
   siempre.

La salida y su vuelta se encolan hacia la gestión por el canal de estados
(`traza.envio_estado`), con la pulsera en el detalle. **Hasta que la gestión acepte
`en_transito` y `almacen` en `/sync/estados`, esos envíos esperan en la cola.**

**Lo que no pasa por la puerta sigue el proceso de siempre**: si un ciclo deja de verlo, a
los 3 ciclos pasa a `en_transito`, y una lectura dentro lo devuelve. A la gestión también
llega por el canal de estados, pero **solo cuando es estable** (irfid
`024_envio_diferido.sql`). La salida se encola tras `IRFID_CICLOS_ESTABLE_ENVIO` ciclos
válidos seguidos (3 por defecto) en los que sigue fuera. La vuelta se encola tras otros
tantos leyéndose dentro. Se envía con la hora real del cambio. Si oscila (sale y vuelve
antes de ser estable) se anula y no se manda nada: para la gestión no ha pasado nada.

No hay dirección: con una sola antena de puerta no se distingue entrar de salir. Una caja
que entra durante la sesión también queda bloqueada, y la liberan los ciclos.

### Las pulseras se configuran por instalación

Qué es persona y qué es material lo decide el **prefijo del EPC**. Cada hospital tiene sus
pulseras, así que va en el `.env` de la Pi, no en el código:

```
IRFID_PUERTA_PREFIJOS_PERSONA=["ce0028","<prefijo de las pulseras>"]
```

Por defecto solo `ce0028` (los carnets). **Una pulsera que no esté aquí se trata como
material desconocido**: no abre sesión y no saca nada. Un EPC que no es persona ni material
nuestro se apunta en `traza.epc_desconocido` y ya no aborta la pasada, como pasaba antes.

Tras cambiar el `.env`, **recrear** (no reiniciar) los dos procesos:
`docker compose up -d irfid-almacen irfid-orquestador`.

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

## Filtro EPC — HAY QUE QUITARLO

**Con el control de salida, el filtro del lector tiene que estar vacío.** Si no, la antena
de la puerta solo ve carnets y el material sale sin que nadie se entere. La distinción
entre persona y material la hace ahora el software, por prefijo (ver arriba).

Lo que tenía en la configuración original, por si hay que volver atrás:

| | |
|---|---|
| Mask offset | 32 bits |
| Filter mask | `0xce002812` |
| Mask length | 16 bits |
| Use SW filter only | desactivado (degrada el rendimiento) |
| Allow Extended EPC Filter | desactivado |

Encajaba con los carnets de `user_room`, que empiezan por `ce0028…` — por ejemplo
`ce0028121900000000002f68`, el de Carlos Garcia.

**Antes de dar el control por bueno, medir las lecturas cruzadas.** Sin filtro, la antena
de la puerta puede leer cajas de las estanterías cercanas. Fuera de una sesión no pasa
nada, pero durante los 2 minutos de una pulsera esas cajas saldrían a `en_transito` (y
volverían a los 3 ciclos). Se ajusta con la potencia y la sensibilidad de la antena de
puerta.

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
