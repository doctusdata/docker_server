#!/bin/bash
# Genera roomfid-pi.tar.gz con SOLO lo necesario para montar en una Raspberry el banco de
# pruebas (rep_server/banco) o la sombra (rep_server/campo): sin node_modules, venvs,
# volcados ni ficheros .env. Ejecutar en la maquina de desarrollo.
set -e
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"   # .../desarrollo
OUT="${1:-$RAIZ/roomfid-pi.tar.gz}"
cd "$RAIZ"
tar czf "$OUT" \
    --exclude='node_modules' --exclude='.venv*' --exclude='venv' --exclude='__pycache__' \
    --exclude='.pytest_cache' --exclude='*.egg-info' --exclude='.git' --exclude='.next' \
    --exclude='ui/out' --exclude='frontend/dist' --exclude='.env' --exclude='*.sqlite3' \
    --exclude='rep_server/*/volcado/*.sql' --exclude='rep_server/banco/mosquitto/passwd' --exclude='rep_server/agente/agente.yaml' --exclude='logs' --exclude='._*' --exclude='.DS_Store' \
    irfid/servicio raspi_visor/backend raspi_visor/frontend raspi_visor/.dockerignore \
    monitor/contracts monitor/packages monitor/node monitor/agent monitor/ui monitor/.dockerignore \
    irfid/gestion-rfid-api \
    rep_server/docker/irfid rep_server/docker/visor rep_server/docker/monitor rep_server/docker/agente \
    rep_server/campo rep_server/banco rep_server/agente
echo "OK: $OUT ($(du -h "$OUT" | cut -f1))"
