#!/bin/bash
# Simula un ciclo de inventario publicando por MQTT, sin lectores reales.
#
# **Por que hace falta.** Los lectores de inventario (192.168.1.157 y .158) estan en
# OTRA red y son inalcanzables desde la sala demo: el orquestador los marca fallidos y
# queda unhealthy, que es esperable y no un fallo. Sin este script no hay forma de
# probar un ciclo sin desplazarse a la instalacion real.
#
# Publica lo mismo que publicaria un lector Keonn: lecturas en TAG_readings/<devid> y
# el stop de ventana en RFID_control/<devid>. El servicio no distingue esto de un
# lector de verdad, que es justo lo que se quiere.
#
# Uso:
#   simular-ciclo.sh                       todo el stock del almacen (ciclo completo)
#   simular-ciclo.sh --faltan 2            todo menos 2 (para provocar temporales)
#   simular-ciclo.sh --epcs a,b,c          exactamente esos
#   simular-ciclo.sh --papelera EPC        tira un EPC a la papelera
#   simular-ciclo.sh --papelera EPC --incidencia "envase roto"
#   simular-ciclo.sh --desconocido         un EPC inventado (debe ir a epc_desconocido)
#
# Opciones: --devid, --paciente, --esperar
set -e
. "$(dirname "$0")/_comun.sh"

# Los dos lectores de inventario del almacen y la papelera, de topologia.json. Se
# publica con el devmac real porque es por ahi por donde el servicio resuelve el
# lector; un devmac desconocido acabaria en `macs_desconocidas` y no se procesaria.
MAC_A="3c:e4:b0:dc:ca:d7"
MAC_B="3c:e4:b0:dc:dc:47"
MAC_PAPELERA="18:2c:65:11:a9:a6"
DEVID="Almacen-1"
DEVID_PAPELERA="Papelera-1"

FALTAN=0
EPCS=""
PAPELERA=""
INCIDENCIA=""
PACIENTE="NHC104233"
DESCONOCIDO=0
ESPERAR="${ESPERAR:-8}"

while [ $# -gt 0 ]; do
    case "$1" in
        --faltan)       FALTAN="$2"; shift 2 ;;
        --epcs)         EPCS="$2"; shift 2 ;;
        --papelera)     PAPELERA="$2"; shift 2 ;;
        --incidencia)   INCIDENCIA="$2"; shift 2 ;;
        --paciente)     PACIENTE="$2"; shift 2 ;;
        --desconocido)  DESCONOCIDO=1; shift ;;
        --devid)        DEVID="$2"; shift 2 ;;
        --esperar)      ESPERAR="$2"; shift 2 ;;
        *) echo "opcion desconocida: $1" >&2; exit 2 ;;
    esac
done

psql() { docker compose exec -T pg psql -U rfidroom -d gestion_rfid -tAc "$1" | tr -d '\r'; }

publicar() {
    # mosquitto_pub dentro del contenedor del broker: asi no hace falta tenerlo
    # instalado en la Pi ni exponer el puerto.
    docker compose exec -T mosquitto mosquitto_pub \
        -h localhost -p 1883 \
        ${MQTT_USER:+-u "$MQTT_USER"} ${MQTT_PASS:+-P "$MQTT_PASS"} \
        -q 1 -t "$1" -m "$2"
}

# --- que EPC se van a leer ----------------------------------------------------------
if [ "$DESCONOCIDO" = "1" ]; then
    # Uno que la gestion no ha dado nunca: tiene que acabar SOLO en epc_desconocido.
    EPCS="e2801160600002$(printf '%010d' $RANDOM$RANDOM | cut -c1-10)"
    echo "EPC inventado: $EPCS"
elif [ -n "$PAPELERA" ]; then
    EPCS="$PAPELERA"
elif [ -z "$EPCS" ]; then
    EPCS=$(psql "SELECT string_agg(epc, ',') FROM (
                   SELECT epc FROM traza.elemento
                    WHERE estado = 'almacen' AND baja_at IS NULL
                    ORDER BY epc OFFSET $FALTAN) t")
    if [ -z "$EPCS" ]; then
        echo "No hay nada en estado 'almacen'." >&2
        echo "Si la Pi acaba de arrancar, primero hay que vincularla y dejar que" >&2
        echo "la gestion le baje su inventario:  python -m irfid vincular --help" >&2
        exit 1
    fi
fi

IFS=',' read -ra LISTA <<< "$EPCS"
TOTAL=${#LISTA[@]}

# --- papelera -----------------------------------------------------------------------
if [ -n "$PAPELERA" ]; then
    echo "== Tirando $PAPELERA a la papelera =="
    LECTURA="{\"EPC\":\"${LISTA[0]}\",\"Antenna\":1,\"RSSI\":-52"
    [ -n "$INCIDENCIA" ] && LECTURA="$LECTURA,\"incidencia\":\"$INCIDENCIA\""
    LECTURA="$LECTURA}"
    publicar "TAG_readings/$DEVID_PAPELERA" \
        "{\"devid\":\"$DEVID_PAPELERA\",\"devip\":\"192.168.0.159\",\"devmac\":\"$MAC_PAPELERA\",\"patient\":\"$PACIENTE\",\"operating_room\":\"Quirofano-1\",\"reads\":[$LECTURA]}"
    echo "  publicado. Esperando $ESPERAR s a que se procese..."
    sleep "$ESPERAR"
    echo
    echo "Estado:"
    psql "SELECT epc||'  '||estado||'  incidencia='||coalesce((SELECT detalle->>'incidencia' FROM traza.movimiento WHERE epc=e.epc AND tipo='consumo' ORDER BY at DESC LIMIT 1),'-')
            FROM traza.elemento e WHERE epc = '${LISTA[0]}'"
    echo "Cola de subida a gestion:"
    psql "SELECT estado||' -> '||estado_envio||'  intentos='||intentos
            FROM traza.envio_estado WHERE epc = '${LISTA[0]}' ORDER BY at DESC LIMIT 3"
    exit 0
fi

# --- ciclo de inventario -------------------------------------------------------------
echo "== Ciclo con $TOTAL EPC =="
[ "$FALTAN" != "0" ] && echo "   (faltan $FALTAN a proposito, para provocar temporales)"

# Dos lectores que se reparten el stock, como en la instalacion real: el primero lee
# la mitad y cierra su ventana, el segundo la otra mitad. Un ciclo con un solo lector
# no ejercita la cobertura igual.
MITAD=$(( TOTAL / 2 ))
[ "$MITAD" = "0" ] && MITAD=$TOTAL

publicar "RFID_control/$DEVID" "{\"devmac\":\"$MAC_A\",\"evento\":\"start\"}"
i=0
LOTE=""
for epc in "${LISTA[@]}"; do
    [ -n "$LOTE" ] && LOTE="$LOTE,"
    LOTE="$LOTE{\"EPC\":\"$epc\",\"Antenna\":$(( (i % 4) + 1 )),\"RSSI\":-$(( 45 + i % 20 ))}"
    i=$(( i + 1 ))
    if [ "$i" = "$MITAD" ]; then
        publicar "TAG_readings/$DEVID" \
            "{\"devid\":\"$DEVID\",\"devip\":\"192.168.1.157\",\"devmac\":\"$MAC_A\",\"reads\":[$LOTE]}"
        publicar "RFID_control/$DEVID" "{\"devmac\":\"$MAC_A\",\"evento\":\"stop\"}"
        publicar "RFID_control/$DEVID" "{\"devmac\":\"$MAC_B\",\"evento\":\"start\"}"
        LOTE=""
    fi
done
if [ -n "$LOTE" ]; then
    publicar "TAG_readings/$DEVID" \
        "{\"devid\":\"$DEVID\",\"devip\":\"192.168.1.158\",\"devmac\":\"$MAC_B\",\"reads\":[$LOTE]}"
fi
publicar "RFID_control/$DEVID" "{\"devmac\":\"$MAC_B\",\"evento\":\"stop\"}"

echo "  publicado. Esperando $ESPERAR s a que cierre el ciclo..."
sleep "$ESPERAR"
echo
echo "Ultimo ciclo:"
psql "SELECT 'valido='||valido||'  presentes='||coalesce(presentes::text,'-')||'  faltantes='||coalesce(faltantes::text,'-')||'  nuevos_temporales='||coalesce(nuevos_temporales::text,'-')||coalesce('  motivo='||motivo_invalido,'')
        FROM traza.ciclo ORDER BY inicio DESC LIMIT 1"
echo "Recuento por estado:"
psql "SELECT estado||' temporal='||temporal||': '||count(*) FROM traza.elemento GROUP BY 1,2 ORDER BY 1"
if [ "$DESCONOCIDO" = "1" ]; then
    echo "EPC desconocidos (debe estar el inventado, y NO en traza.elemento):"
    psql "SELECT epc||'  lecturas='||lecturas FROM traza.epc_desconocido ORDER BY ultima DESC LIMIT 3"
    psql "SELECT 'EN ELEMENTO (MAL): '||epc FROM traza.elemento WHERE epc = '$EPCS'"
fi
