#!/bin/bash
# Construye y descarga TODAS las imagenes del banco. Necesita internet: hacerlo en casa.
# Despues, arrancar.sh funciona sin conexion.
set -e
. "$(dirname "$0")/_comun.sh"
docker compose --profile orquestador build
docker compose --profile orquestador pull --ignore-buildable
docker image prune -f >/dev/null
echo "Imagenes listas:"
docker compose --profile orquestador config --images | while read -r img; do
    # Sin `numfmt`: es de GNU coreutils y no viene en macOS, donde tambien se
    # construye ahora (ver clon/construir-arm64.sh).
    bytes="$(docker image inspect -f '{{.Size}}' "$img" 2>/dev/null || echo 0)"
    if [ "${bytes:-0}" = "0" ]; then printf '  %-40s %s\n' "$img" "FALTA"
    else printf '  %-40s %s MB\n' "$img" "$(( bytes / 1000000 ))"; fi; done
