#!/bin/bash
# Saca un volcado de la base de PRODUCCION (solo lectura: pg_dump no modifica nada) a
# volcado/produccion.sql, sin el esquema traza (la sombra calcula el suyo). Usa un contenedor postgres:18 de un solo uso para tener pg_dump.
set -e
. "$(dirname "$0")/_comun.sh"
mkdir -p volcado
echo "Volcando $PROD_PG_DB de $SERVIDOR:$PROD_PG_PORT ..."
docker run --rm -e PGPASSWORD="$PROD_PG_PASSWORD" postgres:18 \
    pg_dump -h "$SERVIDOR" -p "$PROD_PG_PORT" -U "$PROD_PG_USER" --no-owner \
        --exclude-schema=traza "$PROD_PG_DB" \
    > volcado/produccion.sql.tmp
mv volcado/produccion.sql.tmp volcado/produccion.sql
echo "OK: volcado/produccion.sql ($(du -h volcado/produccion.sql | cut -f1))"
