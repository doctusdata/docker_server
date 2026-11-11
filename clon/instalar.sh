#!/bin/bash
# Instala RoomFID en una Raspberry recien preparada. Se ejecuta DENTRO del paquete.
#
# La Pi solo ejecuta: carga las imagenes ya construidas, deja la configuracion en su
# sitio y restaura la base. No compila nada ni necesita codigo fuente.
#
#   ./instalar.sh
#
# Es repetible: volver a lanzarlo actualiza imagenes y configuracion sin tocar los datos.
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
DESTINO="${DESTINO:-$HOME/roomfid}"

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
aviso() { printf '\033[33m%s\033[0m\n' "$*"; }

# --- 0. Comprobaciones: mejor fallar ahora que a medias ------------------------------
echo "== Comprobaciones =="
[ "$(uname -m)" = "aarch64" ] || { rojo "esta maquina es $(uname -m), no aarch64. Las imagenes son arm64."; exit 1; }
command -v docker >/dev/null || { rojo "falta docker. Instalalo con: curl -fsSL https://get.docker.com | sh"; exit 1; }
docker compose version >/dev/null 2>&1 || { rojo "falta el plugin docker compose"; exit 1; }
docker info >/dev/null 2>&1 || { rojo "el usuario no puede usar docker. Ejecuta: sudo usermod -aG docker $USER  y vuelve a entrar"; exit 1; }
libre=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc '0-9')
[ "$libre" -ge 8 ] || { rojo "solo quedan ${libre}G libres; hacen falta 8G"; exit 1; }
verde "  aarch64, docker operativo, ${libre}G libres"

mkdir -p "$DESTINO"

# --- 1. Imagenes ----------------------------------------------------------------------
echo "== Cargando imagenes (tarda) =="
docker load -i "$AQUI/imagenes/roomfid.tar.gz" | sed 's/^/  /'
for i in irfid api visor monitor agente; do
    arq=$(docker image inspect "roomfid/$i:latest" --format '{{.Architecture}}' 2>/dev/null || echo FALTA)
    [ "$arq" = "arm64" ] || { rojo "roomfid/$i quedo como '$arq'"; exit 1; }
done
verde "  las cinco, arm64"

# --- 2. Configuracion -------------------------------------------------------------------
echo "== Configuracion =="
cp "$AQUI/docker-compose.yml" "$DESTINO/"
mkdir -p "$DESTINO"/{mosquitto,api,initdb,volcado}
cp -r "$AQUI/config/mosquitto/." "$DESTINO/mosquitto/" 2>/dev/null || true
cp -r "$AQUI/config/api/."       "$DESTINO/api/"       2>/dev/null || true
cp -r "$AQUI/config/initdb/."    "$DESTINO/initdb/"    2>/dev/null || true
for f in topologia.json node.yaml agente.yaml; do
    [ -f "$AQUI/config/$f" ] && cp "$AQUI/config/$f" "$DESTINO/"
done

# El .env lleva credenciales y NO viaja en el paquete. Sin el no arranca nada.
if [ ! -f "$DESTINO/.env" ]; then
    cp "$AQUI/config/env.ejemplo" "$DESTINO/.env" 2>/dev/null || true
    chmod 600 "$DESTINO/.env" 2>/dev/null || true
    aviso "  .env creado desde la plantilla: HAY QUE EDITARLO con las credenciales reales"
    FALTA_ENV=1
else
    echo "  .env ya existe, se respeta"
fi

# --- 3. Mosquitto: el passwd se regenera, no se copia ----------------------------------
# Es del uid 1883 con permisos 0700. Copiado desde otra maquina el broker arranca con
# "Unable to open pwfile" y no publica nadie.
echo "== Mosquitto =="
if [ -f "$DESTINO/.env" ] && grep -q '^MQTT_USER=' "$DESTINO/.env"; then
    . <(grep -E '^(MQTT_USER|MQTT_PASS)=' "$DESTINO/.env")
    if [ -n "${MQTT_PASS:-}" ] && [ "${MQTT_PASS}" != "CAMBIAME" ]; then
        docker run --rm -v "$DESTINO/mosquitto:/m" eclipse-mosquitto:2 \
            sh -c "rm -f /m/passwd && mosquitto_passwd -c -b /m/passwd '$MQTT_USER' '$MQTT_PASS' \
                   && chown 1883:1883 /m/passwd && chmod 0700 /m/passwd" >/dev/null 2>&1
        verde "  passwd generado para '$MQTT_USER' (uid 1883, 0700)"
    else
        aviso "  MQTT_PASS sin definir: tras editar el .env ejecuta ./regenerar-passwd.sh"
    fi
fi

cat > "$DESTINO/regenerar-passwd.sh" <<'EOF'
#!/bin/bash
# Regenera el passwd de Mosquitto desde el .env. Hay que lanzarlo si cambia MQTT_PASS.
set -e
cd "$(dirname "$0")"
. <(grep -E '^(MQTT_USER|MQTT_PASS)=' .env)
docker run --rm -v "$PWD/mosquitto:/m" eclipse-mosquitto:2 \
    sh -c "rm -f /m/passwd && mosquitto_passwd -c -b /m/passwd '$MQTT_USER' '$MQTT_PASS' \
           && chown 1883:1883 /m/passwd && chmod 0700 /m/passwd"
echo "passwd regenerado para $MQTT_USER"
EOF
chmod +x "$DESTINO/regenerar-passwd.sh"

# --- 4. Datos ---------------------------------------------------------------------------
#
# Lo normal desde el enfoque C es que NO haya volcado: una Pi nueva arranca vacia,
# aplica su esquema y pide su inventario a la plataforma de gestion al vincularse. El
# volcado solo tiene sentido para mudar una instalacion que ya estaba funcionando con
# el sistema antiguo, y en ese caso trae tambien el esquema legacy.
if [ -f "$AQUI/datos/gestion_rfid.sql.gz" ]; then
    echo "== Restaurando la base =="
    if [ "${FALTA_ENV:-0}" = "1" ]; then
        aviso "  se omite: edita primero el .env y vuelve a lanzar ./instalar.sh"
    else
        # El initdb del banco espera /volcado/produccion.sql SIN comprimir y con ese
        # nombre exacto; el paquete lo trae comprimido. Se descomprime aqui en vez de
        # tocar el initdb, que es el mismo fichero que usa la instalacion original.
        cp "$AQUI/datos/gestion_rfid.sql.gz" "$DESTINO/volcado/"
        gunzip -c "$AQUI/datos/gestion_rfid.sql.gz" > "$DESTINO/volcado/produccion.sql"
        cd "$DESTINO"
        docker compose up -d pg
        echo -n "  esperando a PostgreSQL"
        for i in $(seq 1 90); do
            docker compose exec -T pg pg_isready -U rfidroom -d gestion_rfid >/dev/null 2>&1 && break
            echo -n "."; sleep 2
        done
        echo
        zcat "$AQUI/datos/gestion_rfid.sql.gz" | docker compose exec -T pg psql -U rfidroom -d gestion_rfid -q 2>&1 \
            | grep -viE "^NOTICE|does not exist, skipping" | head -5 || true
        real=$(docker compose exec -T pg psql -U rfidroom -d gestion_rfid -tAc \
               "SELECT (SELECT count(*) FROM traza.elemento)||' '||(SELECT count(*) FROM traza.movimiento)" 2>/dev/null | tr -d '\r')
        echo "  restaurado (elementos movimientos): $real"
        if [ -f "$AQUI/datos/recuento.txt" ]; then
            esperado=$(tr -d '\r' < "$AQUI/datos/recuento.txt")
            if [ "$real" = "$esperado" ]; then verde "  coincide con el origen"
            else aviso "  el origen tenia: $esperado — revisalo"; fi
        fi
    fi
fi

# --- 5. Resumen -------------------------------------------------------------------------
echo
verde "Instalado en $DESTINO"
echo
if [ "${FALTA_ENV:-0}" = "1" ]; then
    aviso "ANTES DE ARRANCAR:"
    echo "  1. nano $DESTINO/.env        (credenciales reales)"
    echo "  2. cd $DESTINO && ./regenerar-passwd.sh"
    echo "  3. ./instalar.sh             (restaura la base)"
    echo
fi
echo "Arrancar:   cd $DESTINO && docker compose --profile orquestador up -d"
echo "Ver:        docker compose ps"
echo "Registros:  docker compose logs -f irfid-almacen"
echo

# --- 6. Vinculacion -----------------------------------------------------------------
# Solo si la Pi arranca vacia. Con volcado, la vinculacion viene dentro de la base
# restaurada y repetirla rotaria el token del almacen sin necesidad.
if [ ! -f "$AQUI/datos/gestion_rfid.sql.gz" ]; then
    echo "== Siguiente paso: vincular con la gestion =="
    echo
    echo "Esta Pi arranca VACIA. Su inventario no se copia de ningun sitio: lo pide"
    echo "a la plataforma de gestion, y para eso necesita un codigo de vinculacion."
    echo
    echo "  1. En gestion:  Almacenes -> <este almacen> -> Vincular Pi"
    echo "     Anota el codigo (XXXX-XXXX). Caduca en 24 h y es de un solo uso."
    echo
    echo "  2. Aqui:"
    echo "     cd $DESTINO && docker compose exec irfid-almacen \\"
    echo "       python -m irfid vincular --gestion https://TU-GESTION --codigo XXXX-XXXX"
    echo
    echo "  Sin codigo a mano, la Pi puede presentarse con su numero de serie y"
    echo "  esperar a que alguien la apruebe:"
    echo "     ... python -m irfid vincular --gestion https://TU-GESTION"
    echo
    echo "  Comprobar:  curl -s localhost:8090/health | grep -i vincul"
    echo
    echo "  Es la Pi quien llama: la gestion no necesita alcanzar esta maquina, asi"
    echo "  que esto funciona desde la red interna del hospital."
    echo
fi

echo "Puertos:  5432 base · 1883 MQTT · 3000 API · 8020 visor · 8080 monitor"
echo "          8025 correo · 8090 irfid · 8091 orquestador · 8092 papeleras"
