#!/bin/bash
# Copia la base del servidor ORIGINAL (solo lectura) a volcado/produccion.sql.
# Ejecutar con la Pi en la red normal, ANTES de darle la IP .155 (scripts/ip.sh).
# Si no hay acceso, vale cualquier volcado de gestion_rfid copiado a volcado/produccion.sql.
set -e
. "$(dirname "$0")/_comun.sh"
read -rsp "Clave de rfidroom en $ORIGEN_PG_HOST: " CLAVE; echo
docker run --rm -e PGPASSWORD="$CLAVE" postgres:18 \
    pg_dump -h "$ORIGEN_PG_HOST" -p "$ORIGEN_PG_PORT" -U rfidroom --no-owner \
    --exclude-schema=traza gestion_rfid > volcado/produccion.sql.tmp
mv volcado/produccion.sql.tmp volcado/produccion.sql
echo "OK: volcado/produccion.sql ($(du -h volcado/produccion.sql | cut -f1))"
