#!/bin/bash
# Primer arranque: rol + base + volcado de produccion.
# El lector de puerta consulta user_room por JDBC y su driver puede no soportar SCRAM
# (el defecto de PostgreSQL 18): la clave de rfidroom se guarda en md5 y pg_hba usa md5
# (POSTGRES_HOST_AUTH_METHOD=md5), que acepta clientes nuevos y antiguos.
set -e
if [ ! -s /volcado/produccion.sql ]; then
    echo "[initdb] FALTA /volcado/produccion.sql (scripts/volcado.sh o copiar un volcado)" >&2
    exit 1
fi
psql -v ON_ERROR_STOP=1 -U postgres <<SQL
SET password_encryption = 'md5';
CREATE ROLE rfidroom WITH LOGIN PASSWORD '${RFID_PG_PASSWORD}' SUPERUSER;
CREATE DATABASE gestion_rfid OWNER rfidroom;
SQL
echo "[initdb] restaurando volcado..."
psql -q -U rfidroom -d gestion_rfid -f /volcado/produccion.sql
echo "[initdb] listo"
