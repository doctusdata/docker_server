#!/bin/bash
# Construye y arranca el agente de esta maquina, y comprueba que el nodo lo acepta.
set -e
cd "$(dirname "$0")"
[ -f .env ] || { echo "Falta .env (copiar de .env.ejemplo y poner el token)" >&2; exit 1; }
[ -f agente.yaml ] || { echo "Falta agente.yaml (copiar de agente.yaml.ejemplo y editar)" >&2; exit 1; }
set -a; . ./.env; set +a
[ -n "$ROOMFID_AGENTES_TOKEN" ] || { echo "ROOMFID_AGENTES_TOKEN vacio en .env" >&2; exit 1; }
docker compose up -d --build
echo "Primer informe (lo que el agente ve de esta maquina):"
docker compose exec -T agente roomfid-agent --config /etc/roomfid/agente.yaml --una-vez \
  | python3 -c "import json,sys; d=json.load(sys.stdin)
for x in d['devices']: print(' ', x['device_code'], x['type'], {k: v for k, v in x['metrics'].items() if k in ('cpu_pct','temp_c','disk_pct','reachable','containers_running')})"
echo "Esperando a que el nodo acepte los informes..."
for i in $(seq 1 12); do
    docker compose exec -T agente roomfid-agent --config /etc/roomfid/agente.yaml --salud && { echo "OK: el nodo recibe los informes"; exit 0; }
    sleep 5
done
echo "El nodo no acepta los informes: docker compose logs agente" >&2; exit 1
