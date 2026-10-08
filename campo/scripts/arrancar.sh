#!/bin/bash
# Construye y arranca la sombra. La primera vez restaura el volcado y hace el bootstrap.
set -e
. "$(dirname "$0")/_comun.sh"
[ -s volcado/produccion.sql ] || { echo "Falta volcado/produccion.sql: ejecuta scripts/volcado.sh" >&2; exit 1; }
docker compose up -d --build
echo "Esperando a irfid-almacen..."
for i in $(seq 1 90); do
    curl -sf http://127.0.0.1:${PUERTO_HEALTH:-8090}/health >/dev/null && break
    sleep 5
done
curl -sf http://127.0.0.1:${PUERTO_HEALTH:-8090}/health >/dev/null || { echo "irfid-almacen no responde; mira: docker compose logs irfid-almacen" >&2; exit 1; }
# Idempotente: la topologia se recarga siempre; los elementos solo la primera vez.
docker compose exec -T irfid-almacen python -m irfid bootstrap
echo
echo "Listo:  visor :${PUERTO_VISOR:-8020}   monitor :${PUERTO_MONITOR:-8080}   estado :${PUERTO_HEALTH:-8090}/health"
