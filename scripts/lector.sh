#!/bin/bash
# Arranca/para un lector simulado.  Uso: lector.sh <157|158|159|205> <start|stop|status>
# Va por el puerto publicado en el host (81xx), asi no depende de ningun contenedor.
PUERTO="8$1"; ACTION="${2:-status}"
if [ "$ACTION" = "status" ]; then
  exec curl -s "http://127.0.0.1:$PUERTO/device/status"
fi
exec curl -s --digest -u admin:admin "http://127.0.0.1:$PUERTO/device/$ACTION"
