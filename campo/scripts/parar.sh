#!/bin/bash
# Para la sombra. Con -v borra tambien su base (para empezar de cero con un volcado nuevo).
set -e
. "$(dirname "$0")/_comun.sh"
docker compose down "$@"
