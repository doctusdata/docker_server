#!/bin/bash
# Despliega el flow de la entrega en la Raspberry REAL.
#
# ANTES de sustituir nada hace copia de seguridad de lo que haya en la Pi y
# se la trae a raspberry/backup-<fecha>/, para poder revertir.
#
# Uso:  ./scripts/deploy-pi.sh <usuario>[@host]
#   ej. ./scripts/deploy-pi.sh pi
#       ./scripts/deploy-pi.sh rfidroom@192.168.0.64
set -e
cd "$(dirname "$0")/.."

TARGET="${1:?Uso: deploy-pi.sh <usuario>[@host]}"
[[ "$TARGET" == *@* ]] || TARGET="$TARGET@192.168.0.64"
NRDIR="${NRDIR:-~/.node-red}"
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="raspberry/backup-$STAMP"

echo "==> Destino: $TARGET   (directorio Node-RED: $NRDIR)"
ssh "$TARGET" "test -d $NRDIR" || { echo "ERROR: no existe $NRDIR en la Pi"; exit 1; }

echo "==> 1/5 Copia de seguridad de lo que hay ahora"
mkdir -p "$BACKUP"
for f in flows.json flows_cred.json settings.js package.json; do
  scp -q "$TARGET:$NRDIR/$f" "$BACKUP/$f" 2>/dev/null && echo "    guardado $f" || echo "    (sin $f)"
done
ssh "$TARGET" "cd $NRDIR && tar czf /tmp/nodered-backup-$STAMP.tgz flows.json flows_cred.json settings.js 2>/dev/null; ls -la /tmp/nodered-backup-$STAMP.tgz"
echo "    copia local en $BACKUP y remota en /tmp/nodered-backup-$STAMP.tgz"

echo "==> 2/5 Parando Node-RED"
ssh "$TARGET" "sudo systemctl stop nodered" || echo "    (no gestionado por systemd; paralo a mano)"

echo "==> 3/5 Instalando el flow nuevo"
scp -q raspberry/flows.json      "$TARGET:$NRDIR/flows.json"
scp -q raspberry/flows_cred.json "$TARGET:$NRDIR/flows_cred.json"
echo "    flows.json y flows_cred.json instalados"

echo "==> 4/5 Comprobando modulos necesarios"
ssh "$TARGET" "cd $NRDIR && for m in node-red-contrib-postgresql node-red-dashboard node-red-node-ui-table node-red-node-pi-gpio node-red-node-mysql; do
  [ -d node_modules/\$m ] && echo \"    OK \$m\" || echo \"    FALTA \$m  -> npm install \$m\"; done"

echo "==> 5/5 Arrancando Node-RED"
ssh "$TARGET" "sudo systemctl start nodered" || echo "    (arrancalo a mano)"
sleep 6
curl -s -o /dev/null -m 8 -w "    Node-RED responde: %{http_code}\n" http://192.168.0.64:1880/ || true

cat <<MSG

Listo. La Pi apunta ahora a la replica en 192.168.0.4:
  PostgreSQL  192.168.0.4:15432     lectores  :8157 .8158 .8159 .8205 (+8206)
  batch       192.168.0.4:8081/run

Revertir:   scp $BACKUP/flows.json $TARGET:$NRDIR/flows.json && ssh $TARGET sudo systemctl restart nodered
MSG
