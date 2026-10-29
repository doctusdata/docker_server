#!/bin/bash
# Primer arranque: rol + base y, SI HAY, el volcado de produccion.
# El lector de puerta consulta user_room por JDBC y su driver puede no soportar SCRAM
# (el defecto de PostgreSQL 18): la clave de rfidroom se guarda en md5 y pg_hba usa md5
# (POSTGRES_HOST_AUTH_METHOD=md5), que acepta clientes nuevos y antiguos.
#
# El rol y la base se crean SIEMPRE, y el volcado es lo opcional. Al reves —como estaba—
# una Pi sin volcado se iba por el exit 1 antes de crearlos, el healthcheck
# (pg_isready -U rfidroom -d gestion_rfid) no pasaba nunca y ni irfid ni la API
# arrancaban. Y como el directorio de datos ya quedaba inicializado, Postgres no
# reintentaba los guiones: habia que borrar el volumen para salir del atasco. Justo el
# caso de la instalacion nueva, que es la que pide su inventario a la gestion.
set -e

psql -v ON_ERROR_STOP=1 -U postgres <<SQL
SET password_encryption = 'md5';
CREATE ROLE rfidroom WITH LOGIN PASSWORD '${RFID_PG_PASSWORD}' SUPERUSER;
CREATE DATABASE gestion_rfid OWNER rfidroom;
SQL

if [ -s /volcado/produccion.sql ]; then
    echo "[initdb] restaurando volcado..."
    psql -q -U rfidroom -d gestion_rfid -f /volcado/produccion.sql
    echo "[initdb] volcado restaurado"
else
    echo "[initdb] sin volcado: base vacia. El esquema lo aplica 'python -m irfid migrar'"
    echo "[initdb] y el inventario baja de la gestion al vincular."
fi
echo "[initdb] listo"
