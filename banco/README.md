# Banco de pruebas con las antenas reales

Una Raspberry **toma la IP del servidor (192.168.1.155)** y hace de servidor para los
lectores reales, ya con el sistema nuevo:

- Los lectores publican en su Mosquitto (`:1883`, mismo usuario y clave).
- El lector de puerta consulta `user_room` en su PostgreSQL (`:5432`, `rfidroom`, clave en md5).
- El **orquestador** enciende y apaga los lectores en lugar de Node-RED.
- **irfid** calcula la trazabilidad y escribe el espejo en las tablas de siempre, que la
  API (`:3000`) y el visor leen como hasta ahora.
- Las alertas llegan a Mailpit (`:8025`).

El servidor y la Raspberry originales **no se tocan**: ni se apagan ni se configuran.


> **Para instalar la sincronización desde cero en la sala demo, ver
> [SALA-DEMO.md](SALA-DEMO.md).** Es una página con el orden exacto y los tres
> scripts nuevos:
>
> - `scripts/empezar-de-cero.sh` — borra el esquema `traza` y lo rehace (pide confirmación)
> - `scripts/verificar-sincronizacion.sh` — dice pieza por pieza qué funciona y qué no
> - `scripts/simular-ciclo.sh` — simula un ciclo por MQTT, porque los lectores de
>   inventario están en otra red y son inalcanzables desde la sala

## Lo más importante: red aislada

No puede haber dos equipos con la IP .155 en la misma red. Por eso **la prueba se hace
en una red aparte**, formada solo por la Pi del banco y los lectores:

```
  red del almacén (NO se toca)             red del banco (switch propio)
  ┌──────────────────────────┐            ┌─────────────────────────────┐
  │ servidor .155 original    │            │ Pi banco  = 192.168.1.155   │
  │ Raspberry Node-RED        │            │ lector .157  lector .158    │
  │ ...                       │            │ lector .159  lector .205    │
  └──────────────────────────┘            └─────────────────────────────┘
```

**Hay que mover los cables de los lectores** del switch del almacén al del banco, y
devolverlos al terminar.

- **Si los lectores se alimentan por PoE, el switch del banco tiene que ser PoE.**
  Compruébalo antes de ir.
- `scripts/ip.sh on` **se niega a poner la .155 si ya responde alguien con esa IP**.
  Es la protección contra enchufarse por error a la red real.

**Efecto en el sistema original mientras dura la prueba.** Sin lectores, el batch
original marcará todo como "no encontrado" (`Stock=0`) a los 5 minutos y lo asignará al
último carnet. Al devolver los lectores, las lecturas lo ponen otra vez en `Stock=1`, pero
`EPC_User` queda con el valor de la prueba. Hay que avisar al cliente, o pausar Node-RED
en la Raspberry original si lo autoriza.

## Qué llevar

- La Raspberry del banco: 64 bits, Docker, **con las imágenes ya construidas en casa**.
- Un switch (**PoE si hace falta**) y cables.
- Un portátil para ver el visor y el monitor. Se conecta al switch del banco con una IP
  libre de la 192.168.1.x (por ejemplo .200).
- El volcado de producción, si no se puede sacar allí (ver paso 2).

## Preparar en casa (con internet)

En la máquina de desarrollo:

```bash
rep_server/scripts/empaquetar.sh
scp roomfid-pi.tar.gz pi@<ip-pi>:
```

En la Pi:

```bash
mkdir -p ~/roomfid && cd ~/roomfid && tar xzf ~/roomfid-pi.tar.gz
cd rep_server/banco && cp .env.ejemplo .env          # revisar claves
./scripts/construir.sh                               # 15-30 min la primera vez; necesita internet
```

`arrancar.sh` no construye ni descarga nada: en la nave funciona sin internet. Si falta
alguna imagen, avisa y no arranca.

Opcional, para llegar con todo probado: copia un volcado cualquiera (`irfid/rfid.sql`) a
`volcado/produccion.sql` y lanza `scripts/arrancar.sh`. Sin lectores verás que el
orquestador no los alcanza, pero se comprueba que todo arranca. Después ejecuta
`scripts/parar.sh -v` y borra el volcado.

## El día de la prueba

1. **Pi en la red normal del almacén** (con su IP de siempre): no hace falta hacer nada todavía.
2. **Volcado de la base original**, en solo lectura:
   ```bash
   ./scripts/volcado.sh           # pide la clave de rfidroom
   ```
   Si el servidor no admite conexiones desde la Pi, sácalo en el propio servidor:
   `pg_dump -U rfidroom --exclude-schema=traza gestion_rfid > produccion.sql`, y copia el
   fichero a `volcado/produccion.sql`.
3. **Montar la red del banco:** switch aparte, la Pi y los 4 lectores. Desenchufa la Pi
   de la red del almacén.
4. **Dar a la Pi la IP del servidor:**
   ```bash
   ./scripts/ip.sh fijar          # permanente; comprueba antes que nadie tenga ya la .155
   ```
   Con la IP fija, tras un reinicio o un corte de luz todo vuelve solo: Docker arranca
   con el sistema y los contenedores tienen `restart: unless-stopped`. `ip.sh on` la
   pone solo hasta el siguiente reinicio.
5. **Arrancar** (solo la primera vez; despues arranca solo con la Pi):
   ```bash
   ./scripts/arrancar.sh          # restaura, arranca, bootstrap
   ./scripts/estado.sh
   ```

## Comprobaciones, en este orden

| Qué | Cómo | Si falla |
|---|---|---|
| Los lectores responden a la Pi | `scripts/lector.sh 157 status` | cableado, PoE o IP de la Pi |
| El orquestador los maneja | `:8091/health`: `ciclos` sube y `fallos` vacío | usuario y clave Digest (`LECTOR_USER`/`LECTOR_PASS`) |
| Publican en el broker de la Pi | `docker compose logs mosquitto`: conexiones de los lectores | los lectores deben apuntar a 192.168.1.155:1883 |
| irfid los reconoce | `:8090/health`: `lectores_desconocidos` vacío | corrige la MAC en `topologia.json` y `docker compose restart irfid-almacen` |
| Ventanas y ciclos válidos | `estado.sh`: ciclos con `valido = t` | ver la tabla de ajustes |
| Puerta | Pasa una tarjeta: `estado.sh`, apartado de accesos | que el lector de puerta publique en MQTT |
| Alarma EAS de la puerta | Una tarjeta autorizada no debe pitar | el lector entra por JDBC a :5432; mira `docker compose logs pg` |
| Visor | `http://192.168.1.155:8020` | `docker compose logs visor api` |

**Ajustes** (en `.env`, y después `./scripts/arrancar.sh`):

- Ciclos `INVALIDO (cobertura)`: los lectores ven menos de la mitad del stock. Anota el
  porcentaje (sale en `estado.sh`); es un dato del sistema real.
- Ventanas `corta`: ventanas reales de menos de 30 s. Baja `IRFID_VENTANA_MIN_S`.
- Para ver pasar un artículo por todos los estados sin esperar 3 ciclos de 5 minutos:
  `IRFID_ORQ_PERIODO_S=150`, `IRFID_ORQ_VENTANA_S=60`, `IRFID_CICLOS_PARA_CIRCULANTE=2`.

**Prueba de trazabilidad completa:**

1. Pasa una tarjeta por la puerta y saca un artículo del almacén.
2. En el siguiente ciclo sale como `salida_temporal`, asignado a esa tarjeta.
3. Pasados N ciclos, `circulante`.
4. Devuélvelo: `retorno`. O pásalo por la papelera: `consumo`.

Todo queda en `estado.sh`, apartado de movimientos.

## Terminar y dejarlo todo como estaba

```bash
./scripts/estado.sh > resultado-$(date +%F).txt      # guardar lo visto
./scripts/parar.sh                                   # conserva la base del banco
./scripts/ip.sh off                                  # quita la .155 (tambien la fija)
```

Devuelve los cables de los lectores al switch del almacén. El sistema original vuelve a
verlos en su siguiente ciclo de Node-RED.
