#!/bin/bash
# Diagnostico de los lectores de inventario, SOLO LECTURA: no reinicia ni cambia nada.
#
# Separa las tres cosas que se confunden cuando "no se lee bien":
#   1. el lector no entrega   -> MQTT (conexiones en bucle, nada publicado)
#   2. el lector entrega poco -> reparto por antena
#   3. se lee, pero no siempre lo mismo -> sombras de etiquetas presentes
#
# En la Pi:          ./diagnostico-lectores.sh [horas]        (por defecto 3)
# Desde fuera:       ssh -p 2015 andy@IP 'bash -s' < clon/diagnostico-lectores.sh
set -uo pipefail

HORAS="${1:-3}"
DIR="${ROOMFID_DIR:-$HOME/roomfid}"
cd "$DIR" || { echo "No existe $DIR" >&2; exit 1; }

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
titulo() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# --- 1. Lo que dice irfid de cada lector -----------------------------------------------
# /estado ya calcula "publica_hace_s" y el reparto por antena; aqui solo se resume.
titulo "Lectores segun irfid (/estado)"
curl -s -m 10 http://127.0.0.1:8090/estado | python3 -c '
import json, sys
e = json.load(sys.stdin)
def s(v):
    return "-" if v is None else str(round(v))
for alm in e.get("almacenes", []):
    m = alm.get("metricas", {})
    print("%s: %s  stock=%s  ultimo ciclo valido hace %s s"
          % (alm["codigo"], alm["estado"], m.get("stock"), s(m.get("ciclo_valido_hace_s"))))
    for l in alm.get("lectores", []):
        lm = l["metricas"]
        pub = lm.get("publica_hace_s")
        aviso = "  <-- NO ENTREGA LECTURAS" if pub is None or pub > 600 else ""
        print("  %s  publica hace %s s, control ok hace %s s%s"
              % (l["devip"], s(pub), s(lm.get("control_ok_hace_s")), aviso))
        ant = [(a["antena"], a["metricas"].get("lecturas_ultima_ventana") or 0) for a in l["antenas"]]
        tot = sum(n for _, n in ant) or 1
        print("    antenas (ultima ventana): " +
              "  ".join("%s:%s (%d%%)" % (a, n, 100 * n // tot) for a, n in ant))
' || rojo "  irfid no responde en :8090"

# --- 2. MQTT: entregan o no ------------------------------------------------------------
# Un lector con dos clientes MQTT del mismo client id se expulsan entre si sin parar
# ("session taken over"): la RF lee, el orquestador lo enciende, y no llega nada.
titulo "MQTT: expulsiones en las ultimas 5000 lineas del broker"
docker logs --tail 5000 banco-mosquitto 2>&1 | grep "session taken over" \
  | grep -oE "Client [^ ]+ \[[0-9.]+" | sed 's/\[//' | sort | uniq -c \
  | awk '{print "  " $1 " expulsiones de " $3 " (" $4 ")"}' | grep . \
  && rojo "  Hay clientes expulsandose en bucle: ver el punto 1 de docs/diagnostico-lectores-2026-10-26.md" \
  || verde "  ninguna"

titulo "MQTT: mensajes recibidos en 15 s, por lector"
MP=$(docker exec banco-irfid-almacen printenv IRFID_MQTT_PASSWORD 2>/dev/null)
MU=$(docker exec banco-irfid-almacen printenv IRFID_MQTT_USERNAME 2>/dev/null)
docker exec banco-mosquitto mosquitto_sub -h 127.0.0.1 -u "$MU" -P "$MP" \
    -i "diagnostico-$$" -t TAG_readings -W 15 2>/dev/null \
  | grep -oE '"devip": *"[0-9.]+"' | grep -oE '[0-9.]+' | sort | uniq -c \
  | awk '{print "  " $2 ": " $1}'
echo "  (un lector de inventario encendido que no aparece aqui no esta entregando)"

# --- 3. La base: ventanas, ciclos, sombras y antenas -----------------------------------
titulo "Base: ultimas $HORAS h"
docker compose exec -T pg psql -U rfidroom -d gestion_rfid -X -q <<SQL
\pset footer off
SET TIME ZONE 'Europe/Madrid';
\echo '-- ventanas por lector y hora'
SELECT l.devip, to_char(date_trunc('hour', v.inicio), 'DD HH24"h"') AS hora,
       count(*) FILTER (WHERE v.valida) AS validas, sum(v.lecturas) AS lecturas,
       round(avg(v.epcs_distintos) FILTER (WHERE v.valida)) AS epcs_media
  FROM traza.ventana_lectura v JOIN traza.lector l ON l.id = v.lector_id
 WHERE v.inicio >= now() - interval '$HORAS hours' AND l.rol = 'inventario'
 GROUP BY 1, 2 ORDER BY 1, 2;
\echo '-- ciclos por hora'
SELECT to_char(date_trunc('hour', inicio), 'DD HH24"h"') AS hora, count(*) AS ciclos,
       count(*) FILTER (WHERE valido) AS validos, string_agg(DISTINCT motivo_invalido, ' / ') AS motivos,
       round(avg(presentes) FILTER (WHERE valido)) AS presentes,
       min(faltantes) FILTER (WHERE valido) AS falt_min, max(faltantes) FILTER (WHERE valido) AS falt_max
  FROM traza.ciclo WHERE inicio >= now() - interval '$HORAS hours' GROUP BY 1 ORDER BY 1;
\echo '-- sombras de etiquetas presentes en 24 h (salida_temporal -> retorno, segundos)'
WITH s AS (
  SELECT m.epc, m.at, (SELECT min(r.at) FROM traza.movimiento r
                        WHERE r.epc = m.epc AND r.tipo = 'retorno' AND r.at > m.at) AS vuelta
    FROM traza.movimiento m
   WHERE m.tipo = 'salida_temporal' AND m.at >= now() - interval '24 hours')
SELECT count(*) AS sombras, count(DISTINCT epc) AS etiquetas,
       round(percentile_disc(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM vuelta - at))) AS p50,
       round(percentile_disc(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM vuelta - at))) AS p90,
       round(percentile_disc(0.99) WITHIN GROUP (ORDER BY extract(epoch FROM vuelta - at))) AS p99,
       round(max(extract(epoch FROM vuelta - at))) AS max
  FROM s WHERE vuelta IS NOT NULL;
\echo '-- pasos a circulante en 24 h que despues se volvieron a leer (acusaciones falsas)'
SELECT count(*) AS a_circulante,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM traza.movimiento r
                         WHERE r.epc = c.epc AND r.tipo = 'retorno' AND r.at > c.at)) AS volvieron
  FROM traza.movimiento c WHERE c.tipo = 'circulante' AND c.at >= now() - interval '24 hours';
\echo '-- antenas: total acumulado'
SELECT l.devip, a.antena, a.lecturas_total,
       round(100.0 * a.lecturas_total / nullif(sum(a.lecturas_total) OVER (PARTITION BY l.devip), 0)) AS pct,
       to_char(a.ultima_lectura_at, 'DD HH24:MI') AS ultima
  FROM traza.lector_antena a JOIN traza.lector l ON l.id = a.lector_id
 WHERE l.rol = 'inventario' ORDER BY 1, 2;
SQL

titulo "Umbrales en el proceso (no en el .env: ver punto 3 de docs/instalacion-26-10.md)"
docker exec banco-irfid-almacen env | grep -E "^IRFID_(CICLOS|MINUTOS)_PARA_CIRCULANTE" | sed 's/^/  /'
docker exec banco-irfid-orquestador env | grep -E "^IRFID_ORQ_(VENTANA|PERIODO)_S" | sed 's/^/  /'
