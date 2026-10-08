#!/bin/bash
# Regenera el fichero de passwords de Mosquitto.
#
# Mosquitto 2 exige que el pwfile NO sea legible por todos y que pertenezca
# al usuario con el que corre el broker (uid 1883). Sin el chown, el broker
# arranca y muere con "Unable to open pwfile".
set -e
cd "$(dirname "$0")/.."
USER_MQTT="${1:-gestion_rfid}"
PASS_MQTT="${2:-rfid_room@}"
touch docker/mosquitto/passwd
docker run --rm -v "$PWD/docker/mosquitto:/mosquitto/config" eclipse-mosquitto:2 \
  mosquitto_passwd -b /mosquitto/config/passwd "$USER_MQTT" "$PASS_MQTT"
docker run --rm -u 0 -v "$PWD/docker/mosquitto:/cfg" alpine \
  sh -c 'chown 1883:1883 /cfg/passwd && chmod 0700 /cfg/passwd'
echo "passwd regenerado para el usuario $USER_MQTT"
ls -n docker/mosquitto/passwd
