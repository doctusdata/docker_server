#!/bin/bash
# Prepara el paquete que se lleva a la Raspberry nueva: imagenes, configuracion y datos.
#
# No incluye codigo fuente: la Pi solo ejecuta. Las imagenes tienen que estar ya
# construidas para arm64 (./construir-arm64.sh).
#
#   ./empaquetar.sh                sin datos (base vacia, se crea el esquema)
#   ./empaquetar.sh --desde PI     ademas vuelca la base de esa Pi (usuario@ip)
#
# Resultado: roomfid-pi-AAAAMMDD.tar.gz, listo para copiar y para instalar.sh.
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
ETIQUETA="${ETIQUETA:-latest}"
ORIGEN=""
[ "${1:-}" = "--desde" ] && { ORIGEN="${2:?falta usuario@ip}"; }

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
aviso() { printf '\033[33m%s\033[0m\n' "$*"; }

TRABAJO=$(mktemp -d)
trap 'rm -rf "$TRABAJO"' EXIT
PAQ="$TRABAJO/roomfid-pi"
mkdir -p "$PAQ"/{imagenes,config,datos}

IMAGENES=(roomfid/irfid roomfid/api roomfid/visor roomfid/monitor roomfid/agente)

# --- 1. Imagenes: se comprueba que son arm64 ANTES de exportar nada ----------------
echo "== Comprobando imagenes =="
for i in "${IMAGENES[@]}"; do
    arq=$(docker image inspect "$i:$ETIQUETA" --format '{{.Architecture}}' 2>/dev/null || true)
    if [ -z "$arq" ]; then
        rojo "falta $i:$ETIQUETA — lanza antes ./construir-arm64.sh"; exit 1
    fi
    if [ "$arq" != "arm64" ]; then
        rojo "$i:$ETIQUETA es $arq, no arm64. En la Pi no arrancaria."; exit 1
    fi
    printf '  %-24s arm64 OK\n' "$i"
done

echo "== Exportando imagenes (tarda) =="
# Todas en un solo archivo: comparten capas base y asi no se duplican.
docker save "${IMAGENES[@]/%/:$ETIQUETA}" | gzip -1 > "$PAQ/imagenes/roomfid.tar.gz"
verde "  $(du -h "$PAQ/imagenes/roomfid.tar.gz" | cut -f1)"

# --- 2. Configuracion y compose ------------------------------------------------------
echo "== Configuracion =="
cp "$AQUI/docker-compose.yml" "$PAQ/"
cp "$AQUI/instalar.sh" "$PAQ/" 2>/dev/null || true

BANCO="$AQUI/../banco"
for f in topologia.json node.yaml agente.yaml; do
    [ -f "$BANCO/$f" ] && cp "$BANCO/$f" "$PAQ/config/"
done
mkdir -p "$PAQ/config/mosquitto" "$PAQ/config/api" "$PAQ/config/initdb"
# El passwd NO se copia: es del uid 1883 y se regenera en destino (instalar.sh).
[ -f "$BANCO/mosquitto/mosquitto.conf" ] && cp "$BANCO/mosquitto/mosquitto.conf" "$PAQ/config/mosquitto/"
[ -f "$BANCO/api/app.json" ] && cp "$BANCO/api/app.json" "$PAQ/config/api/"
cp "$BANCO"/initdb/* "$PAQ/config/initdb/" 2>/dev/null || true
# El .env lleva credenciales: va la plantilla, no el real.
[ -f "$BANCO/.env.ejemplo" ] && cp "$BANCO/.env.ejemplo" "$PAQ/config/env.ejemplo"
echo "  compose, topologia, mosquitto.conf, app.json, initdb"

# --- 3. Datos: volcado consistente de la Pi de origen --------------------------------
if [ -n "$ORIGEN" ]; then
    echo "== Volcando la base de $ORIGEN =="
    # pg_dump dentro del contenedor: version identica a la del servidor y sin exponer
    # el puerto. Copiar el volumen en caliente daria una base corrupta.
    ssh "$ORIGEN" 'docker exec banco-pg pg_dump -U rfidroom --no-owner --clean --if-exists gestion_rfid' \
        | gzip -1 > "$PAQ/datos/gestion_rfid.sql.gz"
    tam=$(du -h "$PAQ/datos/gestion_rfid.sql.gz" | cut -f1)
    # Un volcado vacio o truncado no se detecta hasta que falla la restauracion.
    if ! gzip -dc "$PAQ/datos/gestion_rfid.sql.gz" | grep -q "PostgreSQL database dump complete"; then
        rojo "el volcado parece incompleto: no termina como deberia"; exit 1
    fi
    verde "  gestion_rfid.sql.gz ($tam) — volcado integro"
    # Comillas: el SQL necesita simples para el literal, asi que la orden remota va
    # entre dobles. Con simples fuera, psql veia " " como nombre de columna.
    ssh "$ORIGEN" "docker exec banco-pg psql -U rfidroom -d gestion_rfid -tAc \"SELECT (SELECT count(*) FROM traza.elemento)||' '||(SELECT count(*) FROM traza.movimiento)\"" \
        2>/dev/null | tr -d '\r' > "$PAQ/datos/recuento.txt" || true
    if [ -s "$PAQ/datos/recuento.txt" ]; then
        echo "  esperado (elementos movimientos): $(cat "$PAQ/datos/recuento.txt")"
    else
        aviso "  no se pudo leer el recuento del origen; la instalacion no podra compararlo"
    fi
else
    # **Este es el camino normal desde el enfoque C.** Una Pi nueva no necesita el
    # inventario de otra: lo pide a la gestion al vincularse, y asi no arrastra el
    # esquema legacy ni los datos de otro hospital. `--desde` queda para mudar una
    # instalacion que ya estaba funcionando con el sistema antiguo.
    echo "== Sin volcado: la Pi arrancara vacia y pedira su inventario a la gestion =="
fi

# --- 4. Empaquetar ------------------------------------------------------------------
SALIDA="$AQUI/roomfid-pi-$(date +%Y%m%d).tar.gz"
tar -C "$TRABAJO" -czf "$SALIDA" roomfid-pi
echo
verde "Paquete: $SALIDA  ($(du -h "$SALIDA" | cut -f1))"
echo
if [ -z "$ORIGEN" ]; then
    echo "Recuerda: tras instalar hay que vincular la Pi con la gestion."
    echo "El propio instalar.sh explica como."
    echo
fi
echo "En la Raspberry nueva:"
echo "  scp $(basename "$SALIDA") andy@IP:~/"
echo "  ssh andy@IP 'tar xzf $(basename "$SALIDA") && cd roomfid-pi && ./instalar.sh'"
