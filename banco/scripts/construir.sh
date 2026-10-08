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
    printf '  %-40s %s\n' "$img" "$(docker image inspect -f '{{.Size}}' "$img" 2>/dev/null | numfmt --to=iec || echo FALTA)"; done
