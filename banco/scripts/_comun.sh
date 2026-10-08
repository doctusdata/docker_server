# Comun a los scripts del banco: se situa en banco/ y carga .env
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then echo "Falta banco/.env (copiar de .env.ejemplo)" >&2; exit 1; fi
set -a; . ./.env; set +a
PERFILES=()
[ "${ORQUESTADOR:-si}" = "si" ] && PERFILES=(--profile orquestador)
