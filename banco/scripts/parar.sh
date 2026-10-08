#!/bin/bash
# Para el banco. Con -v borra tambien su base (empezar de cero con otro volcado).
set -e
. "$(dirname "$0")/_comun.sh"
docker compose --profile orquestador down "$@"
