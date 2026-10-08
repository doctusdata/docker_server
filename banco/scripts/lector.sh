#!/bin/bash
# Maneja un lector real a mano desde la Pi.  Uso: lector.sh <157|158|159|205> <start|stop|status>
. "$(dirname "$0")/_comun.sh"
IP="192.168.1.$1"; ORDEN="${2:-status}"
exec curl -s --digest -u "${LECTOR_USER:-admin}:${LECTOR_PASS:-admin}" "http://$IP/device/$ORDEN"; echo
