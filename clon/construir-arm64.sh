#!/bin/bash
# Construye las cinco imagenes propias para la Raspberry (arm64) DESDE ESTA MAQUINA.
#
# La Pi solo ejecuta: no lleva codigo fuente ni compila nada. Aqui se construye,
# alli se carga la imagen ya hecha. Para actualizar algo en el futuro basta con
# volver a lanzar esto y copiar el paquete.
#
#   ./construir-arm64.sh            las cinco
#   ./construir-arm64.sh irfid      solo una (irfid|api|visor|monitor|agente)
#
# Requisitos (se comprueban): docker buildx y emulacion arm64 registrada.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"     # .../desarrollo
REP="$RAIZ/rep_server"
ETIQUETA="${ETIQUETA:-latest}"
BUILDER="roomfid-arm"

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }

# --- comprobaciones previas: fallar aqui es barato, a mitad de build no -------------
docker buildx version >/dev/null 2>&1 || { rojo "falta docker buildx"; exit 1; }

if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
    echo "creando el builder $BUILDER..."
    docker buildx create --name "$BUILDER" --driver docker-container >/dev/null
fi
# El arranque del builder tarda la primera vez; se consulta despues de arrancarlo,
# porque recien creado todavia no informa de las plataformas que soporta.
docker buildx inspect "$BUILDER" --bootstrap >/dev/null 2>&1 || true
if ! docker buildx inspect "$BUILDER" 2>&1 | grep -q "linux/arm64"; then
    rojo "el builder no puede construir arm64. Registra la emulacion con:"
    echo "  docker run --privileged --rm tonistiigi/binfmt --install arm64"
    exit 1
fi

# nombre|contexto|dockerfile|imagen
IMAGENES=(
  "irfid|$RAIZ/irfid/servicio|$REP/docker/irfid/Dockerfile|roomfid/irfid:$ETIQUETA"
  "api|$RAIZ/irfid/gestion-rfid-api|$REP/banco/api/Dockerfile|roomfid/api:$ETIQUETA"
  "visor|$RAIZ/raspi_visor|$REP/docker/visor/Dockerfile|roomfid/visor:$ETIQUETA"
  "monitor|$RAIZ/monitor|$REP/docker/monitor/Dockerfile|roomfid/monitor:$ETIQUETA"
  "agente|$RAIZ/monitor|$REP/docker/agente/Dockerfile|roomfid/agente:$ETIQUETA"
)

pedidas=("$@")
construidas=()

for fila in "${IMAGENES[@]}"; do
    IFS='|' read -r nombre contexto dockerfile imagen <<< "$fila"
    if [ ${#pedidas[@]} -gt 0 ] && [[ ! " ${pedidas[*]} " =~ " $nombre " ]]; then
        continue
    fi
    echo
    verde "=== $nombre -> $imagen (arm64) ==="
    extra=()
    # El nodo del monitor necesita un contexto adicional con sus ficheros de despliegue.
    [ "$nombre" = "monitor" ] && extra=(--build-context "despliegue=$REP/docker/monitor")
    docker buildx build \
        --builder "$BUILDER" \
        --platform linux/arm64 \
        -f "$dockerfile" \
        -t "$imagen" \
        "${extra[@]}" \
        --load \
        "$contexto"
    arq=$(docker image inspect "$imagen" --format '{{.Architecture}}')
    [ "$arq" = "arm64" ] || { rojo "$imagen quedo en $arq, no arm64"; exit 1; }
    construidas+=("$imagen")
done

echo
verde "Listas (${#construidas[@]}):"
for i in "${construidas[@]}"; do
    printf '  %-28s %s\n' "$i" "$(docker image inspect "$i" --format '{{.Size}}' | numfmt --to=iec)"
done
echo
echo "Siguiente paso: ./empaquetar.sh"
