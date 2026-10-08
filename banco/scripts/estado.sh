#!/bin/bash
# Salud, ultimos ciclos, recuento por estado y ultimos movimientos.
set -e
. "$(dirname "$0")/_comun.sh"
echo "== irfid-almacen";     curl -s http://127.0.0.1:8090/health | python3 -m json.tool || true
if [ "${ORQUESTADOR:-si}" = "si" ]; then
echo "== orquestador";       curl -s http://127.0.0.1:8091/health | python3 -m json.tool || true
fi
docker compose exec -T pg psql -U rfidroom -d gestion_rfid -c \
  "SELECT to_char(inicio AT TIME ZONE 'Europe/Madrid','DD HH24:MI') inicio, valido, motivo_invalido, presentes, faltantes, nuevos_temporales, nuevos_circulantes FROM traza.ciclo ORDER BY inicio DESC LIMIT 10" -c \
  "SELECT estado, temporal, count(*) FROM traza.elemento GROUP BY 1,2 ORDER BY 1,2" -c \
  "SELECT to_char(at AT TIME ZONE 'Europe/Madrid','DD HH24:MI:SS') hora, epc, tipo, usuario_tarjeta FROM traza.movimiento WHERE tipo <> 'alta' ORDER BY at DESC LIMIT 15" -c \
  "SELECT to_char(at AT TIME ZONE 'Europe/Madrid','DD HH24:MI:SS') hora, tarjeta_epc, usuario_nombre, autorizado FROM traza.acceso ORDER BY at DESC LIMIT 5"
