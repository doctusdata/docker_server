#!/bin/bash
# Guarda un volcado de la base actual, para poder rebobinar tras las pruebas.
set -e
cd "$(dirname "$0")/.."
OUT="sql/snapshot_$(date +%Y%m%d_%H%M%S).sql"
docker exec rfid-postgres pg_dump -U rfidroom gestion_rfid > "$OUT"
echo "Snapshot guardado en $OUT ($(wc -l < "$OUT") lineas)"
