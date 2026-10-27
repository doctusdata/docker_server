# Diagnóstico de los lectores, 26/10/2026 por la noche (en remoto)

Hecho desde la oficina con SSH a la Pi de la instalación (puerto 2015 del router) y **solo
con lectura**: no se ha reiniciado ni cambiado nada. Todas las cifras salen de
`clon/diagnostico-lectores.sh` o de las consultas que aparecen aquí, y se pueden repetir.
Es la continuación de `instalacion-26-10.md`.

Hay tres problemas distintos que, vistos desde el visor, se confunden en uno solo ("no se
lee bien"):

| | Qué pasa | Gravedad |
|---|---|---|
| 1 | **Desde las 15:03 los lectores no entregan ninguna lectura** | Lo para todo |
| 2 | La antena floja del `.158` sigue sin cambiar | Causa de las sombras |
| 3 | Sombras de hasta 21 minutos en etiquetas presentes: **todas las salidas de hoy han sido falsas** | Acusaciones falsas |

---

## 1 · Los lectores no entregan: conexiones MQTT expulsándose en bucle

**Desde las 15:03 (`.157`) y las 14:48 (`.158`) no ha llegado ninguna lectura de
inventario.** Lo demás funciona: los lectores responden al ping, el orquestador los
enciende y apaga sin fallos (`control ok hace 20 s`), y su propia API dice `RF_ON`. Leen,
pero lo que leen no llega a nadie.

El broker deja claro por qué:

```
New client connected from 192.168.1.157:42562 as lector1 (p4, c1, k60, u'gestion_rfid').
Client lector1 [192.168.1.157:42562] disconnected: session taken over.
New client connected from 192.168.1.157:42560 as lector1 ...
Client lector1 [192.168.1.157:42560] disconnected: session taken over.
```

Cada lector tiene **más de una conexión abierta con el mismo client id** (`lector1` el
`.157`, `lector2` el `.158`). Cada conexión nueva expulsa a la anterior, la expulsada se
reconecta y expulsa a la nueva, y así continuamente. Medido:

- unas **95 conexiones por segundo** entre los dos lectores, sin parar;
- unos 5.900 sockets en `TIME_WAIT` dentro del contenedor del broker en un minuto;
- **0 mensajes** de `.157` y `.158` en 15 s escuchando `TAG_readings`. En esos mismos
  15 s, el lector de puerta sí publicó.

### Cuándo empezó: con el reinicio de las 14:01

| Hora (Madrid) | Ventanas válidas/h | EPC por ventana | Ciclos válidos |
|---|---|---|---|
| 11–13 h | 29 por lector, de 120 s | ~830 | 29/h, ~945 presentes |
| **14:01** | **reinicio de la Pi y los contenedores** (`StartedAt 13:01:42Z`) | | |
| 14 h | 57, de 37 s | 28–37 | 3 |
| 15 h en adelante | 60, de 30 s | **0** | **0** |

Antes del reinicio funcionaba con la misma configuración en los lectores. Lo más
probable es que, al caer el broker, el cliente MQTT del lector se reconectara dejando la
sesión vieja viva, o que tenga dos salidas MQTT (datos y eventos) con el mismo id que
antes convivían por casualidad. **No está verificado.** La configuración MQTT del lector
no aparece en su REST (`/devices/<id>` no la incluye) y hay que mirarla en su web.

> **Si se confirma que pasa en cada reinicio del broker, cualquier corte de luz de la Pi
> deja la instalación sin inventario hasta que alguien reinicie los lectores.**

### Lo que ha funcionado bien

El **corte de cobertura** ha protegido el stock: con 0 lecturas, todos los ciclos se han
descartado por `cobertura` y en 8 horas **no se ha marcado nada como fuera**. Sin ese
corte, el primer ciclo vacío habría dado por salido todo el almacén.

### Por qué nadie se ha enterado en 8 horas

- La alerta `lector_inactivo` solo salta cuando el orquestador **no consigue manejar** el
  lector (`orquestador/runner.py:160`). Aquí lo maneja sin problema, así que no salta.
- `/estado` sí lo detecta (`E_LECTOR_NO_PUBLICA`), pero eso solo se ve en el monitor.
- Y el monitor no recibe nada: el `monitor-agente` envía sus datos a `127.0.0.1:8080`,
  que desde el cambio de esta tarde es la API (`sala-demo-api-publica.md`). Está
  `unhealthy`.

### Efecto secundario: el log del broker

Cada conexión deja 2 o 3 líneas. Tres millones de líneas solo cubren 2,9 horas. El log de
Docker no tiene límite de tamaño y crece del orden de **1–2 GB al día** (estimado, no
medido: el fichero es de root). Ahora hay 95 GB libres, así que no corre prisa, pero
desgasta la tarjeta SD.

---

## 2 · La antena del `.158`, sin cambios

| Lector | Reparto acumulado por antena |
|---|---|
| `.157` | 33 / 22 / 18 / 27 % (sano) |
| `.158` | **22 / 78 %** |

Es lo mismo que midió `instalacion-26-10.md`: la antena no se ha cambiado. Las filas de
las antenas 3 y 4 del `.158` siguen en la tabla, a cero, como se explica en esa memoria.

---

## 3 · Sombras: todas las salidas de hoy han sido falsas

Tiempo que pasa una etiqueta **presente** sin leerse (`salida_temporal` hasta su
siguiente `retorno`), con los datos de hoy:

| Sombras | Etiquetas distintas | p50 | p90 | p99 | Máximo |
|---|---|---|---|---|---|
| 984 | 339 (36 % del stock) | 29 s | 159 s | 639 s | **1.298 s (21,6 min)** |

La memoria anterior hablaba de un máximo de 312 s; hoy se han medido **cuatro veces más**.

**35 etiquetas pasaron a circulante y 31 volvieron a leerse después: estaban en la
estantería.** Las otras 4 pasaron a las 14:02–14:09, justo cuando empezó el corte, así
que no se han podido volver a leer. Lo más probable es que también estén. Con
`MINUTOS_PARA_CIRCULANTE=5` (lo que tiene el proceso), **el 100 % de las salidas de hoy
son acusaciones falsas**.

Dos detalles del código que lo explican:

- **El tiempo escala solo, sin esperar a los ciclos.** `_escalar` (`almacen/repo.py:532`)
  pasa a circulante todo lo que lleve `minutos_para_circulante` como temporal, haya
  habido los ciclos que haya. Es "lo que antes ocurra" (`config.py:53`), y con parpadeo
  siempre llega antes el tiempo.
- **Un ciclo con 294 faltantes contó como válido** (13:33: 663 presentes de 957, un 69 %).
  `cobertura_minima` es 0.5 por defecto. Ese ciclo pudo marcar como temporales hasta 294
  etiquetas de golpe; no se ha medido cuántas eran nuevas.

---

## Qué se puede hacer, por orden

### Ahora, para recuperar la lectura (no hecho: requiere tu visto bueno)

1. **Reiniciar los dos lectores** desde su web (túnel por la Pi) o desconectándolos de la
   corriente. Después, `./diagnostico-lectores.sh` tiene que mostrar **0 expulsiones** y
   mensajes de los dos lectores.
2. Ya en su web, **revisar la configuración MQTT**: si hay dos salidas, darles client ids
   distintos (`lector1-datos`, `lector1-eventos`…).
3. **Probar que no se repite**: reiniciar solo el broker (`docker compose restart
   mosquitto`) y comprobar que vuelven sin expulsiones. Si se repite, hay que resolverlo
   en el lector antes de poner esto en producción.

### Para que no vuelva a pasar en silencio

4. Monitor: cambiar `nodo_url` a `:8081` en `~/roomfid/agente.yaml` y recrear el agente.
5. irfid: una alerta **`lector_sin_lecturas`** cuando el orquestador lo maneja bien pero
   haya N ventanas seguidas sin lecturas. Hoy ese caso no avisa a nadie. *(Propuesta; el
   código no se ha tocado.)*
6. Broker: añadir `logging: {options: {max-size: "50m", max-file: "3"}}` a `mosquitto` en
   `clon/docker-compose.yml`.

### Para las acusaciones falsas

7. **Cambiar la antena del `.158`** (lo que ya estaba pendiente) y volver a medir las
   sombras con el script.
8. Hasta entonces, **`IRFID_MINUTOS_PARA_CIRCULANTE=30`** (el valor por defecto). Con 15
   habría seguido acusando: el máximo de hoy pasa de 21 minutos. Recordar que hay que
   **recrear** el contenedor (`up -d`), no reiniciarlo.
9. A estudiar en irfid: que el tiempo solo cuente **después** de los ciclos (Y en vez de
   O), y subir `cobertura_minima` a 0.9, la misma que ya usa el canal hacia la gestión.

---

## Cómo repetirlo

```bash
ssh -p 2015 andy@<IP pública> 'bash -s' < clon/diagnostico-lectores.sh       # o en la Pi: ./diagnostico-lectores.sh 3
```

Es solo de lectura: consulta `/estado`, el log del broker, escucha 15 s de
`TAG_readings`, hace SELECT en la base y lee el `env` de los procesos.
