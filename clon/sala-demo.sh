#!/bin/bash
# Pone la Raspberry en la red de la sala demo: toma la IP del servidor original
# (192.168.1.155) y deja la topologia apuntando a los lectores de alli.
#
# Se hace asi, y no reconfigurando los lectores, porque ellos llevan grabado el
# broker MQTT apuntando a .155: si la Pi toma esa IP, publican contra ella sin
# tocarles nada. Es lo que menos se puede estropear en una sala con prisa.
#
#   ./sala-demo.sh on     toma la .155 y actualiza la topologia
#   ./sala-demo.sh off    la devuelve a la red de desarrollo
#   ./sala-demo.sh ver    en que estado esta
#
# La IP se ANADE: la Pi conserva la que ya tenia, asi que no te quedas sin SSH.
set -euo pipefail

IP=192.168.1.155
IFACE="${2:-eth0}"
DIR="${ROOMFID_DIR:-$HOME/roomfid}"

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
aviso() { printf '\033[33m%s\033[0m\n' "$*"; }

CON=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | awk -F: -v d="$IFACE" '$2==d{print $1; exit}')

# --- la IP del servidor original ------------------------------------------------------
tomar_ip() {
    if ip -4 addr show "$IFACE" 2>/dev/null | grep -q "$IP/"; then
        echo "  ya la tiene"; return
    fi
    # Dos equipos con la misma IP rompen el sistema real: antes de nada, mirar.
    if ping -c 2 -W 1 "$IP" >/dev/null 2>&1; then
        rojo "ALTO: $IP ya responde. El servidor original esta conectado; NO sigo."
        exit 1
    fi
    if [ -n "$CON" ]; then
        sudo nmcli con modify "$CON" +ipv4.addresses "$IP/24"
        sudo nmcli con up "$CON" >/dev/null
        echo "  $IP fija en '$CON' (sobrevive a reinicios)"
    else
        sudo ip addr add "$IP/24" dev "$IFACE"
        aviso "  $IP puesta solo hasta el proximo reinicio (no hay NetworkManager en $IFACE)"
    fi
}

soltar_ip() {
    if [ -n "$CON" ] && nmcli -g ipv4.addresses con show "$CON" 2>/dev/null | grep -q "$IP"; then
        sudo nmcli con modify "$CON" -ipv4.addresses "$IP/24"
        sudo nmcli con up "$CON" >/dev/null
    fi
    ip -4 addr show "$IFACE" 2>/dev/null | grep -q "$IP/" && sudo ip addr del "$IP/24" dev "$IFACE" || true
    echo "  $IP quitada"
}

# --- la topologia -----------------------------------------------------------------------
# La IP de cada lector vive en dos sitios: topologia.json (lo que se carga) y
# traza.lector (lo que usa el sistema). Hay que cambiar los dos o al primer
# bootstrap vuelven a discrepar.
mover_lectores() {
    local destino="$1"   # 'demo' (192.168.1.x) o 'desarrollo' (192.168.0.x)
    local de para
    if [ "$destino" = "demo" ]; then de="192.168.0."; para="192.168.1."
    else de="192.168.1."; para="192.168.0."; fi

    cd "$DIR"
    cp topologia.json "topologia.json.bak-$(date +%Y%m%d_%H%M%S)"
    sed -i "s/\"devip\": \"$de/\"devip\": \"$para/g" topologia.json
    echo "  topologia.json -> ${para}x"

    docker compose exec -T pg psql -U rfidroom -d gestion_rfid -v ON_ERROR_STOP=1 -q <<SQL
UPDATE traza.lector SET devip = replace(devip, '$de', '$para') WHERE devip LIKE '$de%';
SQL
    echo "  traza.lector  -> ${para}x"
}

estado() {
    echo "=== IPs de $IFACE ==="
    ip -4 -br addr show "$IFACE" 2>/dev/null || echo "  (sin $IFACE)"
    [ -n "$CON" ] && echo "  permanentes: $(nmcli -g ipv4.addresses con show "$CON" 2>/dev/null)"
    echo
    echo "=== lectores en la base ==="
    cd "$DIR" && docker compose exec -T pg psql -U rfidroom -d gestion_rfid -tAc \
        "SELECT '  '||devid||'  '||devip||'  '||rol||CASE WHEN activo THEN '' ELSE '  (inactivo)' END
           FROM traza.lector ORDER BY rol, devid" 2>/dev/null || echo "  (base no disponible)"
}

case "${1:-ver}" in
  on)
    echo "== Tomando la IP del servidor original =="; tomar_ip
    echo "== Topologia a la red de la sala =="; mover_lectores demo
    echo "== Reiniciando los servicios que leen la topologia =="
    cd "$DIR" && docker compose restart irfid-almacen irfid-orquestador >/dev/null 2>&1 || true
    echo
    verde "Listo. La Pi responde en $IP y los lectores se buscan en 192.168.1.x"
    echo
    aviso "Queda por hacer a mano:"
    echo "  * Terminal de papelera: ponerle una IP 192.168.1.x y, en su configuracion,"
    echo "    PAPELERIA_API_URL=http://$IP:8092/api/papelera/v1"
    echo "    (su lector lo encuentra solo por MAC; si no, PAPELERIA_READER_HOST)"
    echo "  * Gestion: licencias.lector_url -> http://$IP:3000/api";;
  off)
    echo "== Devolviendo a la red de desarrollo =="; soltar_ip
    mover_lectores desarrollo
    cd "$DIR" && docker compose restart irfid-almacen irfid-orquestador >/dev/null 2>&1 || true
    verde "Listo. De vuelta en 192.168.0.x";;
  ver|*) estado;;
esac
