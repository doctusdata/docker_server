#!/bin/bash
# DESTRUCTIVO. Deja la Pi vacia y lista para pedir su inventario a la gestion.
#
# **Por que empezar de cero y no migrar.** Decision del 26/10: los datos de operacion
# que hay son de prueba y no valen nada. Migrarlos costaria mas que rehacerlos, y
# arrastraria el estado del sistema antiguo —con su vocabulario viejo y sus altas por
# lectura— a un sistema que ya no funciona asi. Lo que queda despues es una Pi que
# sabe exactamente de donde viene cada cosa: de la gestion.
#
# Lo que borra:  el esquema traza (elementos, movimientos, ciclos, vinculacion).
# Lo que NO:     el esquema public legacy (EPC_master, EPC_readings, Bin), que ya nadie
#                alimenta pero que raspi_visor y la API Node siguen leyendo.
#
# Uso:  empezar-de-cero.sh [--sin-copia]
set -e
. "$(dirname "$0")/_comun.sh"

v=$'\e[32m'; r=$'\e[31m'; a=$'\e[33m'; n=$'\e[0m'
COPIA=1
[ "${1:-}" = "--sin-copia" ] && COPIA=0

psql() { docker compose exec -T pg psql -U rfidroom -d gestion_rfid -tAc "$1" | tr -d '\r'; }

echo
printf '%s== Esto borra el esquema traza de esta Pi ==%s\n' "$a" "$n"
echo
if psql "SELECT 1" >/dev/null 2>&1 && [ "$(psql "SELECT to_regclass('traza.elemento') IS NOT NULL")" = "t" ]; then
    echo "Ahora mismo hay:"
    psql "SELECT '  '||count(*)||' elementos' FROM traza.elemento"
    psql "SELECT '  '||count(*)||' movimientos' FROM traza.movimiento"
    psql "SELECT '  '||count(*)||' vinculaciones' FROM traza.vinculacion" 2>/dev/null || true
else
    echo "  (la base esta vacia o sin esquema traza)"
fi
echo
printf 'Escribe %sborrar%s para continuar: ' "$r" "$n"
read -r respuesta
[ "$respuesta" = "borrar" ] || { echo "Cancelado."; exit 1; }

# --- 1. Red de seguridad --------------------------------------------------------------
if [ "$COPIA" = "1" ]; then
    echo
    echo "== Copia de seguridad =="
    # pg_dump y nunca copiando el volumen: en caliente saldria corrupta, y es un error
    # que no se nota hasta que hace falta restaurar.
    FICHERO="$HOME/antes-de-cero-$(date +%Y%m%d-%H%M).sql.gz"
    docker compose exec -T pg pg_dump -U rfidroom -d gestion_rfid | gzip > "$FICHERO"
    if ! zcat "$FICHERO" | tail -5 | grep -q "PostgreSQL database dump complete"; then
        printf '%s La copia parece truncada. No sigo.%s\n' "$r" "$n"; exit 1
    fi
    printf '%s✓%s %s (%s)\n' "$v" "$n" "$FICHERO" "$(du -h "$FICHERO" | cut -f1)"
fi

# --- 2. Parar lo que escribe ----------------------------------------------------------
echo
echo "== Parando los servicios que escriben =="
docker compose stop irfid-almacen irfid-orquestador 2>/dev/null || true

# --- 3. Borrar y rehacer --------------------------------------------------------------
echo
echo "== Borrando el esquema traza =="
psql "DROP SCHEMA IF EXISTS traza CASCADE" >/dev/null
printf '%s✓%s esquema traza fuera\n' "$v" "$n"

echo
echo "== Aplicando el esquema (sql/010..020) =="
docker compose run --rm irfid-almacen python -m irfid migrar

echo
echo "== Cargando la topologia (ubicaciones, lectores, responsables) =="
# `bootstrap` ya solo hace topologia: la carga de elementos desde el legacy se retiro.
# El inventario lo da la gestion.
docker compose run --rm irfid-almacen python -m irfid bootstrap

echo
echo "== Arrancando =="
docker compose up -d
sleep 5

# --- 4. Comprobacion ------------------------------------------------------------------
echo
echo "== Como ha quedado =="
psql "SELECT '  elementos: '||count(*) FROM traza.elemento"
psql "SELECT '  ubicaciones: '||count(*) FROM traza.ubicacion"
psql "SELECT '  lectores: '||count(*) FROM traza.lector"
echo

printf '%s== Siguiente paso: vincular ==%s\n' "$a" "$n"
cat <<'AYUDA'

Esta Pi esta vacia a proposito. Su inventario no se copia de ningun sitio: lo pide
a la plataforma de gestion, y para eso necesita un codigo.

  1. En gestion, deja la operacion limpia tambien (una sola vez, no por Pi):
       cd backend && python -m scripts.limpiar_operacion --borrar

  2. En gestion: Almacenes -> <este almacen> -> Vincular Pi
     Anota el codigo XXXX-XXXX. Un solo uso, caduca en 24 h.

  3. Aqui:
       docker compose exec irfid-almacen \
         python -m irfid vincular --gestion https://TU-GESTION --codigo XXXX-XXXX

  4. Comprueba que todo esta en su sitio:
       ./scripts/verificar-sincronizacion.sh

  5. Da de alta material en gestion (escaneo) y simula un ciclo:
       ./scripts/simular-ciclo.sh

Es la Pi quien llama: la gestion no necesita alcanzar esta maquina.
AYUDA
