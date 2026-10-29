#!/bin/bash
# Deshace un despliegue en la Pi: devuelve la imagen y la base al punto anterior.
#
# **Por que hace falta un script y no bastan cuatro comandos sueltos.** En la Pi
# volver atras tiene una trampa que no se ve: `irfid-almacen` arranca con
# `python -m irfid migrar`, asi que restaurar el volcado y levantar reaplica
# sql/010..020 encima y deshace el rescate en segundos. Hay que parar primero,
# devolver la IMAGEN y solo despues la base. Ese orden es todo el script.
#
# **Y por que la imagen y no la rama.** El codigo esta en git, si, pero la Pi no
# ejecuta un checkout: ejecuta una imagen. Volver por git obliga a reconstruir —media
# hora y con internet, que en la sala puede no haber—. Por eso `empezar-de-cero.sh`
# etiqueta la imagen anterior antes de tocar nada, y por eso esto empareja cada
# volcado con su etiqueta: son las dos mitades del mismo punto de restauracion.
#
# `migrar` solo va hacia delante y `018` reconstruye el ENUM de estados borrando el
# viejo, asi que no hay downgrade posible: el volcado es el unico camino.
#
# Uso:  volver-atras.sh [AAAAMMDD-HHMM]      sin argumento, lista los puntos
set -e
. "$(dirname "$0")/_comun.sh"

v=$'\e[32m'; r=$'\e[31m'; a=$'\e[33m'; n=$'\e[0m'

# Un punto de restauracion es un volcado; la etiqueta de imagen del mismo sello es su
# otra mitad. Puede faltar (copia hecha a mano, o instalacion que no tenia imagen
# previa): se avisa, no se aborta, porque restaurar solo la base sigue siendo mejor
# que nada mientras se sepa que el codigo no vuelve.
sello_de() { basename "$1" | sed -E 's/^antes-de-cero-(.*)\.sql\.gz$/\1/'; }
hay_imagen() { docker image inspect "roomfid/irfid:antes-de-cero-$1" >/dev/null 2>&1; }

# Bucle y no `mapfile`: no existe en bash 3.2 y estos scripts se leen y se prueban
# tambien desde el Mac.
# Ordenado por NOMBRE y no por `ls -t`: el sello es AAAAMMDD-HHMM, que ordena solo, y
# es lo que el usuario ve y teclea. La fecha del fichero dice otra cosa en cuanto
# alguien copia los volcados a otra maquina o los recupera de un backup, y entonces el
# "mas reciente primero" miente justo cuando mas se mira.
COPIAS=()
while IFS= read -r c; do [ -n "$c" ] && COPIAS+=("$c"); done \
    < <(ls -1 "$HOME"/antes-de-cero-*.sql.gz 2>/dev/null | sort -r || true)
if [ ${#COPIAS[@]} -eq 0 ]; then
    printf '%sNo hay ninguna copia en %s/antes-de-cero-*.sql.gz%s\n' "$r" "$HOME" "$n"
    echo "Sin volcado no hay vuelta atras: la Pi no tiene downgrade." >&2
    exit 1
fi

if [ -z "${1:-}" ]; then
    echo
    echo "Puntos de restauracion disponibles (el mas reciente primero):"
    echo
    for c in "${COPIAS[@]}"; do
        s=$(sello_de "$c")
        if hay_imagen "$s"; then
            printf '  %s  %-6s  %s+ imagen%s\n' "$s" "$(du -h "$c" | cut -f1)" "$v" "$n"
        else
            printf '  %s  %-6s  %ssolo base, sin imagen%s\n' "$s" "$(du -h "$c" | cut -f1)" "$a" "$n"
        fi
    done
    echo
    echo "Uso: $(basename "$0") $(sello_de "${COPIAS[0]}")"
    exit 0
fi

SELLO="$1"
FICHERO="$HOME/antes-de-cero-$SELLO.sql.gz"
[ -f "$FICHERO" ] || { printf '%sNo existe %s%s\n' "$r" "$FICHERO" "$n"; exit 1; }

# Comprobar la copia ANTES de destruir nada. Un volcado truncado descubierto a mitad
# deja la Pi sin base vieja y sin base nueva, que es el peor sitio donde estar.
# Sobre el flujo entero, no sobre `tail`: en PostgreSQL 18 el `\unrestrict` final
# empuja la marca y cualquier recorte fijo acabaria dando un falso truncado.
gzip -dc "$FICHERO" | grep -q "PostgreSQL database dump complete" \
    || { printf '%sLa copia esta truncada. No sigo.%s\n' "$r" "$n"; exit 1; }

echo
printf '%s== Volver al punto %s ==%s\n' "$a" "$SELLO" "$n"
echo
echo "  base:    $FICHERO ($(du -h "$FICHERO" | cut -f1))"
if hay_imagen "$SELLO"; then
    echo "  imagen:  roomfid/irfid:antes-de-cero-$SELLO"
else
    printf '  imagen:  %sno existe%s\n' "$a" "$n"
    echo
    printf '%s  Solo vuelve la base. El contenedor seguira con el codigo nuevo y, como\n' "$a"
    printf '  arranca con `migrar`, volvera a aplicar sql/010..020 sobre lo restaurado.\n'
    printf '  Para volver del todo: git checkout de la rama anterior y construir.sh\n'
    printf '  (media hora, y necesita internet).%s\n' "$n"
fi
echo
printf 'Escribe %svolver%s para continuar: ' "$r" "$n"
read -r respuesta
[ "$respuesta" = "volver" ] || { echo "Cancelado."; exit 1; }

# --- 1. Parar. Mientras algo corra, migra. --------------------------------------------
echo
echo "== Parando todo =="
docker compose "${PERFILES[@]}" down

# --- 2. La imagen, ANTES que la base --------------------------------------------------
if hay_imagen "$SELLO"; then
    echo
    echo "== Devolviendo la imagen =="
    # Se guarda la actual por si la vuelta tampoco convence: sin esto, retomar el
    # despliegue nuevo obligaria a reconstruir, que es el problema del que se venia.
    if docker image inspect roomfid/irfid:latest >/dev/null 2>&1; then
        docker tag roomfid/irfid:latest "roomfid/irfid:antes-de-volver-$SELLO"
        printf '%s✓%s la que habia queda como roomfid/irfid:antes-de-volver-%s\n' "$v" "$n" "$SELLO"
    fi
    docker tag "roomfid/irfid:antes-de-cero-$SELLO" roomfid/irfid:latest
    printf '%s✓%s roomfid/irfid:latest apunta al codigo de %s\n' "$v" "$n" "$SELLO"
fi

# --- 3. La base -----------------------------------------------------------------------
echo
echo "== Restaurando la base =="
docker compose up -d pg
# Esperar a que acepte conexiones: `up -d` vuelve en cuanto arranca, no cuando esta lista.
for _ in $(seq 60); do
    docker compose exec -T pg pg_isready -U rfidroom -d postgres >/dev/null 2>&1 && break
    sleep 1
done

# DROP/CREATE y no restaurar encima: sobre una base ya migrada quedarian las tablas
# nuevas conviviendo con el esquema viejo, que no es ni lo uno ni lo otro.
docker compose exec -T pg psql -U rfidroom -d postgres -q \
    -c 'DROP DATABASE IF EXISTS gestion_rfid' -c 'CREATE DATABASE gestion_rfid'
gzip -dc "$FICHERO" | docker compose exec -T pg psql -U rfidroom -d gestion_rfid -q
printf '%s✓%s base restaurada\n' "$v" "$n"

# --- 4. Levantar ----------------------------------------------------------------------
echo
echo "== Levantando =="
docker compose "${PERFILES[@]}" up -d

echo
printf '%s✓ De vuelta en %s%s\n' "$v" "$SELLO" "$n"
echo
echo "Comprueba con:  ./scripts/verificar-sincronizacion.sh --esquema"
