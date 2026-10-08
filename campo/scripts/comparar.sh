#!/bin/bash
# Compara el estado legacy de produccion (solo lectura) con lo que ha calculado la sombra.
set -e
. "$(dirname "$0")/_comun.sh"
docker compose exec -T irfid-almacen python -m irfid comparar --limite "${1:-40}" \
    --produccion "host=$SERVIDOR port=$PROD_PG_PORT dbname=$PROD_PG_DB user=$PROD_PG_USER password=$PROD_PG_PASSWORD"
