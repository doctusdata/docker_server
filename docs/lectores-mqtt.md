# Los lectores de inventario no publicaban: diagnóstico completo

Sala demo, 23/10/2026. Los lectores `192.168.1.157` y `.158` (AdvanReader-m4-160) leían
etiquetas pero **no publicaban nada** en `TAG_readings`, así que el inventario no se
movía. Costó una jornada entera. Esto es lo que era, lo que no era, y cómo se arregló.

## La causa

Dos condiciones que se reforzaban, y que había que cumplir **las dos a la vez**:

1. **El `MQTTService` estaba deshabilitado** en los dos lectores.
2. **Ese servicio solo se levanta al arrancar el aparato.** Habilitarlo en caliente no
   sirve: produce el síntoma de «se para solo» una y otra vez.

La secuencia que lo resuelve:

```
habilitar MQTTService en la web del lector
   ->  confSave            (si no, la habilitación se pierde al reiniciar)
   ->  apagar y encender   (los servicios solo arrancan al iniciarse el equipo)
```

Hecho eso, los dos lectores publicaron de inmediato y de forma sostenida: 42 y 44 tramas
en cinco minutos, con ventanas de 822 y 863 EPC distintos en la primera pasada.

## La trampa que nos costó el día

> **La API del lector miente sobre el estado de sus servicios.** Con el `MQTTService`
> deshabilitado, `GET /system/services/byId/MQTTService` devolvía `enabled: true`, y
> `GET /system/services/status` devolvía `true` para su índice. **Solo la web del lector
> dice la verdad.**

Cualquier diagnóstico que se fíe del REST para saber si un servicio está corriendo va a
dar vueltas en falso. Lo descubrimos mirando la interfaz, no la API.

## Lo que NO era

Todo esto se midió y se descartó. No merece la pena volver a mirarlo:

| Descartado | Comprobación |
|---|---|
| Credenciales del broker | `CONNACK = 0` conectando en crudo con `gestion_rfid` / `rfid_room@` |
| Red y alcance | Los lectores responden; la Pi los enciende sin fallo cada ciclo |
| Colisión de `clientId` | `lector1` y `lector2`, distintos |
| Potencia y sensibilidad | `31.5` dBm (máximo) y `-85` dBm en todas las antenas |
| Antenas y colocación | `/inventory` devolvía 85-130 etiquetas: el lector leía |
| `generateReadEvents` | Puesto en `true`: sin efecto. Y `.158` leía con él en `false` |
| `onlyMute` | Puesto en `false` en los dos: sin efecto |
| `keepAlivePeriodMs = -1` | Sospechoso principal durante horas; no era (y el REST lo ignora) |
| DNS | Los lectores tienen `dns = 192.168.1.1`; el broker va por IP, no se resuelve nada |
| ACL del broker | `mosquitto.conf` no tiene fichero de ACL |

## Otras trampas verificadas de este firmware

- **`/device/start` responde `status OK`** aunque el lector no vaya a publicar nada. El
  `fallos: {}` del orquestador solo dice que la llamada HTTP respondió.
- **Devuelve HTTP 200 en rutas inexistentes**, con el error dentro del cuerpo XML
  (`status=ERROR`, `UNKNOWN_OPERATION`). Hay que mirar el cuerpo, no el código HTTP.
- **Reenviar el campo `config` completo por REST puede tumbarle la web.** Pasó con
  `.158`; se recupera apagando y encendiendo.
- **Sin `confSave`, cualquier cambio se pierde al reiniciar.** Esto invalidó varias de
  nuestras pruebas antes de darnos cuenta.
- **No hay registro accesible** en la web de estos lectores: solo *Monitor* y *Tag read
  analysis*. Activar `debug` y `verbose` en el servicio no sirve de nada si no se puede
  leer lo que escribe.

## Umbrales para demostraciones

Por defecto, una etiqueta que no se lee durante **30 minutos** sale del stock y pasa a
`circulante` (`reglas._escalar`, criterio por tiempo). Cada corte de red mueve inventario
de verdad: en una tarde con varios cortes, el stock bajó de 995 a 798 y hubo que
recuperarlo.

Para una demostración conviene subirlos en `~/roomfid/.env`:

```
IRFID_MINUTOS_PARA_CIRCULANTE=600
IRFID_CICLOS_PARA_CIRCULANTE=100
```

Y recrear el contenedor, **no reiniciarlo**, porque las variables se fijan al crearlo:

```bash
cd ~/roomfid && docker compose up -d irfid-almacen
```

Se nota que las ha tomado porque el contador `observaciones` de `:8090/health` vuelve a
empezar.

## El simulador como plan B

`rep_server/simuladores/keonn-sim` publica tramas igual que el hardware y sostuvo la
demo mientras los lectores no funcionaban. Dos cosas que hay que acertar:

- **`POOL_SIZE` debe cubrir el catálogo completo.** Su consulta es
  `SELECT "EPC" FROM "EPC_master" WHERE "Almacen" = $1 ORDER BY random() LIMIT $2`: con
  `POOL_SIZE=950` sobre 997 catalogados, los 47 que el sorteo deja fuera nunca se leen y
  acaban en `circulante` para siempre. Con `POOL_SIZE=997` el inventario cuadró solo.
- **`DEVMAC` debe ser la del lector real** al que se quiere suplantar, o irfid no sabrá a
  qué ventana atribuir las lecturas y aparecerán en `lectores_desconocidos`.

> **En macOS reciente el permiso de Red Local es por aplicación.** El simulador fallaba
> con `EHOSTUNREACH` inmediato lanzado desde iTerm y funcionó desde Warp. El mismo
> binario de Node, la misma máquina, el mismo destino. Si una conexión al LAN falla con
> `EHOSTUNREACH` mientras `ping` funciona, es esto.
