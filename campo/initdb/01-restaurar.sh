#!/bin/bash
# Primer arranque de la base propia: rol + base + volcado de produccion.
set -e
if [ ! -s /volcado/produccion.sql ]; then
    echo "[initdb] FALTA /volcado/produccion.sql: ejecuta antes scripts/volcado.sh" >&2
    exit 1
fi
psql -v ON_ERROR_STOP=1 -U postgres <<SQL
CREATE ROLE rfidroom WITH LOGIN PASSWORD '${PG_PASSWORD}' SUPERUSER;
CREATE DATABASE gestion_rfid OWNER rfidroom;
SQL
echo "[initdb] restaurando volcado de produccion..."
psql -q -U rfidroom -d gestion_rfid -f /volcado/produccion.sql
echo "[initdb] listo"
