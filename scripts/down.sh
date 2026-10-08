#!/bin/bash
# Para la replica. Con -v borra tambien los volumenes (base de datos incluida).
cd "$(dirname "$0")/.."
docker compose --profile "*" down "$@"
