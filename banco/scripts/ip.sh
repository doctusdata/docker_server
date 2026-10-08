#!/bin/bash
# Da o quita a la Pi la IP del servidor original (192.168.1.155) en la interfaz cableada,
# ADEMAS de la que ya tenga.
#
#   ip.sh on    [interfaz]   la anade hasta el proximo reinicio
#   ip.sh fijar [interfaz]   la anade de forma PERMANENTE (NetworkManager): sobrevive a
#                            reinicios y cortes de luz; con los contenedores, que tambien
#                            vuelven solos, el banco se recupera sin tocar nada
#   ip.sh off   [interfaz]   la quita (temporal y permanente)
#   ip.sh ver   [interfaz]
#
# !! SOLO en la red del banco: si el servidor original esta conectado, dos equipos con
# .155 rompen el sistema real. on/fijar lo comprueban antes y se niegan.
set -e
IFACE="${2:-eth0}"; IP=192.168.1.155
CON=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | awk -F: -v d="$IFACE" '$2==d{print $1; exit}')

comprobar() {
    if ip -4 addr show "$IFACE" | grep -q "$IP/"; then return 0; fi
    if ping -c 2 -W 1 "$IP" >/dev/null 2>&1; then
        echo "ALTO: $IP ya responde en esta red. El servidor original esta conectado: NO sigo." >&2
        exit 1
    fi
}

case "${1:-ver}" in
  on)
    comprobar
    ip -4 addr show "$IFACE" | grep -q "$IP/" || sudo ip addr add "$IP/24" dev "$IFACE"
    echo "OK: $IFACE tiene $IP hasta el proximo reinicio (usa 'fijar' para que sea permanente)";;
  fijar)
    [ -n "$CON" ] || { echo "No encuentro la conexion de NetworkManager de $IFACE" >&2; exit 1; }
    comprobar
    sudo nmcli con modify "$CON" +ipv4.addresses "$IP/24"
    sudo nmcli con up "$CON" >/dev/null
    echo "OK: $IP fija en '$CON' ($IFACE). Se mantiene tras reiniciar. Quitar: ip.sh off";;
  off)
    if [ -n "$CON" ] && nmcli -g ipv4.addresses con show "$CON" | grep -q "$IP"; then
        sudo nmcli con modify "$CON" -ipv4.addresses "$IP/24"
        sudo nmcli con up "$CON" >/dev/null
    fi
    ip -4 addr show "$IFACE" | grep -q "$IP/" && sudo ip addr del "$IP/24" dev "$IFACE"
    echo "OK: $IP quitada de $IFACE";;
  *) ip -4 -br addr show "$IFACE"
     [ -n "$CON" ] && echo "permanentes ($CON): $(nmcli -g ipv4.addresses con show "$CON")";;
esac
