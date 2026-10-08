# Agente de monitorización (uno por máquina)

Cada máquina de la instalación lleva un **agente** en Docker que alimenta el **monitor** (el
nodo, puerto `:8080` del servidor).

| Máquina | Qué informa | Dónde está su compose |
|---|---|---|
| Servidor | Su sistema y sus contenedores, **más la salud RFID** leída de irfid `/estado` | servicio `rfid-monitor-agente` (réplica), `monitor-agente` (banco y sombra) |
| Raspberry | Su sistema, sus contenedores y las **tablets** que dependen de ella (por sondeo) | este directorio |
| Tablet | Nada: no se instala nada en ella. La sondea su Raspberry | — |

Así se ve la instalación en el monitor:

```
SERVIDOR                      cpu, memoria, temperatura, disco, contenedores
└─ ALMACEN-1                  último ciclo válido, cobertura, stock
   ├─ LECTOR-157 ─ ANT1..4    publica / responde al start / lecturas por antena
   ├─ PUERTA-1 ─ LECTOR-159
   └─ QUIROFANO-1 ─ PAPELERA-1 ─ LECTOR-205
RASPBERRY-01                  cpu, temperatura, disco, contenedores
└─ TABLET-01                  responde al ping
```

## Instalar en una Raspberry

1. **Da de alta la máquina en el nodo.** En el `node.yaml` del servidor, añade un
   dispositivo con `remoto: true`. Si no está dado de alta, el nodo rechaza sus informes.
   ```yaml
   - device_code: RASPBERRY-01
     label: Raspberry sala 1
     type: raspberry
     remoto: true
   ```
   Después reinicia el nodo: `docker compose restart rfid-monitor`.
2. **En la Raspberry**, dentro de `rep_server/agente/` (llega con `scripts/empaquetar.sh`):
   ```bash
   cp .env.ejemplo .env               # ROOMFID_AGENTES_TOKEN = el del servidor
   cp agente.yaml.ejemplo agente.yaml # device_code, nodo_url, tablets
   ./instalar.sh                      # construye, arranca y comprueba que el nodo lo acepta
   ```

El contenedor usa la red del host (para que las sondas salgan por la red de la máquina) y
monta en solo lectura `/` (disco) y el socket de Docker (contenedores). La CPU, la memoria
y la temperatura se leen de `/proc` y `/sys`, que son los del host.

## Qué alarma y por qué

| En el monitor | Causa |
|---|---|
| Máquina DEGRADED `SERVICE_DOWN` | Un contenedor que debería estar corriendo no lo está, o está `unhealthy` |
| Máquina DEGRADED `E_AGENTE_SIN_INFORME` | El agente nunca ha informado (no está instalado, o el token es incorrecto) |
| Máquina DEGRADED y luego OFFLINE (`STALE`) | El agente ha dejado de informar |
| Lector OFFLINE | No responde a la sonda TCP desde el servidor |
| Lector `E_LECTOR_NO_RESPONDE` | El orquestador no consigue hacerle start (3 intentos seguidos) |
| Lector `E_LECTOR_NO_PUBLICA` | Es de inventario y no publica lecturas por MQTT desde hace 15 min |
| Antena `E_ANTENA_SIN_LECTURAS` | Lleva 3 ventanas válidas sin leer mientras las demás antenas del lector sí leían. Solo se evalúa en lectores de inventario: los de puerta y papelera solo leen cuando pasa algo |
| Antenas UNKNOWN | Su lector está caído: sin él no se puede saber cómo están |
| Almacén `E_SIN_CICLOS` / `E_CICLO_COBERTURA` | No hay ciclos de inventario válidos, o el último vio menos de la mitad del stock |
| Tablet OFFLINE | No responde al ping desde su Raspberry. Si la que cae es la Raspberry, la tablet sale UNKNOWN |

Los umbrales de irfid se ajustan en su `.env`: `IRFID_ANTENA_VENTANAS_FALLO`,
`IRFID_ESTADO_LECTOR_SILENCIO_S` e `IRFID_ESTADO_CICLO_MAX_S`.

## Diagnóstico

```bash
docker compose exec agente roomfid-agent --config /etc/roomfid/agente.yaml --una-vez   # qué mide ahora
docker compose logs -f agente
```

En el simulador de la réplica se pueden provocar averías:

- Antena muerta: `curl --digest -u admin:admin "http://127.0.0.1:8157/sim/antena?muerta=3"`, y `?viva=3` para devolverla.
- Lector apagado: `docker stop rfid-lector-158`.
