#!/bin/bash
# Levanta el sistema con los perfiles indicados (ver cabecera de docker-compose.yml).
#
#   ./scripts/up.sh                    nucleo (produccion: lectores reales, sin legacy)
#   ./scripts/up.sh sim dev legacy     replica, hito 1: modo sombra junto al sistema actual
#   ./scripts/up.sh sim dev            replica, hito 2: irfid escribe (IRFID_LEGACY_MIRROR=true)
#   ./scripts/up.sh sim dev orquestador  replica, hito 3: sin Node-RED
set -e
cd "$(dirname "$0")/.."
PERFILES=()
for p in "$@"; do PERFILES+=(--profile "$p"); done
# Lo que no este en los perfiles pedidos se para (p. ej. quitar "legacy" en el corte).
docker compose "${PERFILES[@]}" up -d --build --remove-orphans
echo "Esperando a que los servicios esten healthy..."
docker compose "${PERFILES[@]}" ps
