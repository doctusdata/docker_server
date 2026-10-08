#!/bin/bash
# Arranca el banco. La primera vez restaura el volcado y hace el bootstrap.
set -e
. "$(dirname "$0")/_comun.sh"
[ -s volcado/produccion.sql ] || { echo "Falta volcado/produccion.sql (scripts/volcado.sh)" >&2; exit 1; }
# Fichero de claves de Mosquitto con el usuario de los lectores. Lo genera el propio
# contenedor para que quede con el propietario (uid 1883) y permisos que exige.
if [ ! -s mosquitto/passwd ]; then
    rm -f mosquitto/passwd
    docker run --rm -v "$PWD/mosquitto:/m" eclipse-mosquitto:2 sh -c \
        "mosquitto_passwd -b -c /m/passwd '$MQTT_USER' '$MQTT_PASS' && chown 1883:1883 /m/passwd && chmod 700 /m/passwd"
fi
# Sin --build ni pull: en la nave puede no haber internet. Las imagenes se construyen
# antes, en casa, con scripts/construir.sh.
FALTAN=$(docker compose "${PERFILES[@]}" config --images | while read -r img; do
    docker image inspect "$img" >/dev/null 2>&1 || echo "$img"; done)
if [ -n "$FALTAN" ]; then
    echo "Faltan imagenes (ejecuta scripts/construir.sh con internet):" >&2; echo "$FALTAN" >&2; exit 1
fi
docker compose "${PERFILES[@]}" up -d --no-build --pull never --remove-orphans
echo "Esperando a irfid-almacen..."
for i in $(seq 1 90); do curl -sf http://127.0.0.1:8090/health >/dev/null && break; sleep 5; done
curl -sf http://127.0.0.1:8090/health >/dev/null || { echo "irfid-almacen no responde: docker compose logs irfid-almacen" >&2; exit 1; }
docker compose exec -T irfid-almacen python -m irfid bootstrap
# Recarga inmediata de la topologia recien cargada (si no, tarda hasta 60 s).
docker compose "${PERFILES[@]}" restart irfid-almacen $( [ ${#PERFILES[@]} -gt 0 ] && echo irfid-orquestador ) >/dev/null
IP=$(hostname -I | awk '{print $1}')
echo
echo "Banco en marcha ($IP):  visor :8020   monitor :8080   correo :8025   estado :8090/health  orquestador :8091/health"
