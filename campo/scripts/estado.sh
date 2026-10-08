#!/bin/bash
# Resumen rapido: salud, ultimos ciclos y ventanas, y lectores desconocidos.
set -e
. "$(dirname "$0")/_comun.sh"
curl -s http://127.0.0.1:${PUERTO_HEALTH:-8090}/health | python3 -m json.tool
docker compose exec -T pg psql -U rfidroom -d gestion_rfid -c \
  "SELECT to_char(inicio AT TIME ZONE 'Europe/Madrid','DD HH24:MI') inicio, valido, motivo_invalido, presentes, faltantes, nuevos_temporales, nuevos_circulantes FROM traza.ciclo ORDER BY inicio DESC LIMIT 10" -c \
  "SELECT estado, temporal, count(*) FROM traza.elemento GROUP BY 1,2 ORDER BY 1,2"
