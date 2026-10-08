#!/bin/bash
set -e
echo "[initdb] Restaurando gestion_rfid desde el dump con datos..."
psql -v ON_ERROR_STOP=1 --username rfidroom --dbname gestion_rfid \
     -f /sql/gestion_rfid_cd_cs.sql
echo "[initdb] Restauracion completada."
