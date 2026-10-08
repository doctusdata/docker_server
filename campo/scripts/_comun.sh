# Comun a los scripts de campo: se situa en campo/ y carga .env
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then echo "Falta campo/.env (copiar de .env.ejemplo y rellenar)" >&2; exit 1; fi
set -a; . ./.env; set +a
