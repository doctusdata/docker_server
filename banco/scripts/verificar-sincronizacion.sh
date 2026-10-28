#!/bin/bash
# Comprueba, una por una, las piezas de la sincronizacion gestion <-> Pi.
#
# **Para que existe.** Son 16 commits y muchas piezas nuevas; leer un documento no
# dice si funcionan. Esto las prueba en orden de dependencia y dice de cada una si
# esta o no, con el sitio donde mirar cuando no.
#
# No cambia nada: solo lee y pregunta. Lo destructivo esta en `empezar-de-cero.sh`.
#
#   verificar-sincronizacion.sh            todo
#   verificar-sincronizacion.sh --esquema  solo que las migraciones esten aplicadas
#   verificar-sincronizacion.sh --demo     ¿puede esta Pi funcionar SIN la gestion?
set -u
. "$(dirname "$0")/_comun.sh"

v=$'\e[32m'; r=$'\e[31m'; a=$'\e[33m'; g=$'\e[90m'; n=$'\e[0m'
OK=0; MAL=0; AVISOS=0

psql() { docker compose exec -T pg psql -U rfidroom -d gestion_rfid -tAc "$1" 2>/dev/null | tr -d '\r'; }

# comprobar <descripcion> <consulta> <esperado>   (esperado 't' o un numero)
comprobar() {
    local desc="$1" sql="$2" esperado="${3:-t}" pista="${4:-}"
    local res; res=$(psql "$sql")
    if [ "$res" = "$esperado" ]; then
        printf '  %s✓%s %s\n' "$v" "$n" "$desc"; OK=$((OK+1))
    else
        printf '  %s✗%s %s %s(da %s, se esperaba %s)%s\n' "$r" "$n" "$desc" "$g" "${res:-vacio}" "$esperado" "$n"
        [ -n "$pista" ] && printf '      %s→ %s%s\n' "$a" "$pista" "$n"
        MAL=$((MAL+1))
    fi
}

# informar <descripcion> <consulta>   — sin veredicto: es un dato que hay que mirar
informar() {
    printf '  %s·%s %s: %s%s%s\n' "$g" "$n" "$1" "$g" "$(psql "$2")" "$n"
}

avisar() { printf '  %s!%s %s\n' "$a" "$n" "$1"; AVISOS=$((AVISOS+1)); }

titulo() { printf '\n%s== %s%s\n' "$n" "$1" "$n"; }

# --- 0. La base responde -------------------------------------------------------------
titulo "La base"
if ! psql "SELECT 1" >/dev/null 2>&1; then
    printf '  %s✗%s PostgreSQL no responde. Arranca el banco: ./scripts/arrancar.sh\n' "$r" "$n"
    exit 1
fi
comprobar "PostgreSQL 18 o superior (uuidv7)" \
    "SELECT current_setting('server_version_num')::int >= 180000" t \
    "el esquema usa uuidv7(), que no existe antes de la 18"

# --- 1. Esquema: las migraciones nuevas ----------------------------------------------
titulo "Esquema de la Pi (sql/016..020)"
comprobar "016 · traza.gestion (identidad ante la plataforma)" \
    "SELECT to_regclass('traza.gestion') IS NOT NULL" t "python -m irfid migrar"
comprobar "016 · traza.vinculacion (token y cursor por almacen)" \
    "SELECT to_regclass('traza.vinculacion') IS NOT NULL" t "python -m irfid migrar"
comprobar "017 · la ficha dentro de traza.elemento" \
    "SELECT count(*) = 3 FROM information_schema.columns
      WHERE table_schema='traza' AND table_name='elemento'
        AND column_name IN ('nombre','gestion_etiqueta_id','local_pendiente')" t \
    "python -m irfid migrar"
comprobar "017 · traza.bajada_rechazo" \
    "SELECT to_regclass('traza.bajada_rechazo') IS NOT NULL" t
comprobar "018 · estados con el vocabulario de la gestion" \
    "SELECT count(*) = 5 FROM pg_enum
      WHERE enumtypid='traza.estado_elemento'::regtype
        AND enumlabel IN ('creado','almacen','en_transito','usado','retirado')" t \
    "el ENUM sigue con stock/circulante/consumido: falta aplicar 018"
comprobar "018 · el CHECK se renombro con el estado nuevo" \
    "SELECT EXISTS (SELECT 1 FROM pg_constraint
                     WHERE conname = 'elemento_almacen_con_ubicacion')" t
comprobar "018 · traza.ajuste_manual sobrevivio al DROP TYPE" \
    "SELECT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
                     WHERE ns.nspname='traza' AND p.proname='ajuste_manual')" t \
    "la rehizo 018 tras borrar el tipo; si falta, 018 fallo a medias"
comprobar "019 · traza.envio_estado (cola de subida)" \
    "SELECT to_regclass('traza.envio_estado') IS NOT NULL" t
comprobar "020 · historico y su funcion" \
    "SELECT to_regclass('traza.elemento_historico') IS NOT NULL
        AND EXISTS (SELECT 1 FROM pg_proc WHERE proname='archivar_terminados')" t

[ "${1:-}" = "--esquema" ] && { printf '\n%s%d bien, %d mal%s\n' "$n" "$OK" "$MAL" "$n"; exit $(( MAL > 0 )); }

# --- 2. Vinculacion -------------------------------------------------------------------
titulo "Vinculacion con la plataforma"
estado_v=$(psql "SELECT estado FROM traza.gestion WHERE unica")
if [ -z "$estado_v" ]; then
    avisar "esta Pi no esta vinculada todavia."
    printf '      %s→ En gestion: Almacenes → <el almacen> → Vincular Pi%s\n' "$a" "$n"
    printf '      %s  Aqui: docker compose exec irfid-almacen \\%s\n' "$a" "$n"
    printf '      %s        python -m irfid vincular --gestion URL --codigo XXXX-XXXX%s\n' "$a" "$n"
    printf '\n  %sSin vinculacion no se puede comprobar nada de lo que sigue.%s\n' "$a" "$n"
    printf '\n%s%d bien, %d mal, %d aviso(s)%s\n' "$n" "$OK" "$MAL" "$AVISOS" "$n"
    exit 0
fi
comprobar "estado de la vinculacion" "SELECT estado FROM traza.gestion WHERE unica" aprobada \
    "si dice 'pendiente', alguien tiene que aprobarla en gestion"
informar "URL de la gestion" "SELECT url FROM traza.gestion WHERE unica"
comprobar "hay al menos un almacen con token" \
    "SELECT count(*) > 0 FROM traza.vinculacion WHERE estado='activa' AND token <> ''" t
comprobar "cada almacen esta enlazado con la topologia local" \
    "SELECT count(*) = 0 FROM traza.vinculacion WHERE estado='activa' AND ubicacion_id IS NULL" t \
    "la gestion dio un almacen que no esta en topologia.json: ese no se puede leer"
informar "ultimo contacto" "SELECT coalesce(to_char(ultimo_contacto_at,'DD/MM HH24:MI'),'nunca') FROM traza.gestion WHERE unica"
informar "ultimo error" "SELECT coalesce(ultimo_error,'(ninguno)') FROM traza.gestion WHERE unica"

# --- 3. Bajada: lo que la gestion nos ha dado -----------------------------------------
titulo "Canal de bajada (gestion → Pi)"
informar "cursor por almacen" \
    "SELECT string_agg(coalesce(nombre,'?')||'='||cursor, ', ') FROM traza.vinculacion"
total=$(psql "SELECT count(*) FROM traza.elemento WHERE gestion_etiqueta_id IS NOT NULL")
if [ "${total:-0}" = "0" ]; then
    avisar "la gestion no nos ha dado ninguna etiqueta todavia."
    printf '      %s→ Da de alta material en gestion (escaneo) y espera un intervalo.%s\n' "$a" "$n"
    printf '      %s  Si no llega: curl -s localhost:8090/health | python3 -m json.tool | grep -A5 bajada%s\n' "$a" "$n"
else
    printf '  %s✓%s %s etiquetas recibidas de la gestion\n' "$v" "$n" "$total"; OK=$((OK+1))
    comprobar "las etiquetas traen su ficha (nombre), no solo el EPC" \
        "SELECT count(*) = 0 FROM traza.elemento
          WHERE gestion_etiqueta_id IS NOT NULL AND (nombre IS NULL OR nombre = '')" t \
        "si llegan sin nombre, la vista v_etiqueta_sync de gestion no esta resolviendo el arco"
fi
informar "rechazos de la bajada" \
    "SELECT coalesce(string_agg(DISTINCT motivo, ', '),'(ninguno)') FROM traza.bajada_rechazo"
# El rechazo que delata el orden 017 sin 018
pend_enum=$(psql "SELECT count(*) FROM traza.bajada_rechazo WHERE motivo='estado_desconocido'")
[ "${pend_enum:-0}" != "0" ] && avisar "$pend_enum rechazos 'estado_desconocido': falta aplicar 018 (el enum viejo)"

# --- 4. Subida: lo que hemos contado --------------------------------------------------
titulo "Canal de subida (Pi → gestion)"
informar "cola de ciclos" \
    "SELECT coalesce(string_agg(estado||'='||n, ', '),'(vacia)') FROM (SELECT estado, count(*) n FROM traza.envio_gestion GROUP BY 1) t"
informar "cola de consumos y retiradas" \
    "SELECT coalesce(string_agg(estado_envio||'='||n, ', '),'(vacia)') FROM (SELECT estado_envio, count(*) n FROM traza.envio_estado GROUP BY 1) t"
comprobar "nada agotado en la cola de ciclos" \
    "SELECT count(*) = 0 FROM traza.envio_gestion WHERE estado='agotado'" t \
    "casi siempre es el token o el store_id: mira envio_gestion.ultimo_error"
rechazados=$(psql "SELECT count(*) FROM traza.envio_estado WHERE estado_envio='rechazado'")
if [ "${rechazados:-0}" != "0" ]; then
    avisar "$rechazados hechos rechazados por la gestion (no se reintentan a proposito)"
    informar "  motivos" "SELECT string_agg(DISTINCT ultimo_error, ', ') FROM traza.envio_estado WHERE estado_envio='rechazado'"
fi

# --- 5. local_pendiente: la fuga que hay que vigilar ----------------------------------
titulo "La marca de 'decidido y no entregado'"
sin_entregar=$(psql "SELECT count(*) FROM traza.elemento WHERE local_pendiente")
if [ "${sin_entregar:-0}" = "0" ]; then
    printf '  %s✓%s nada pendiente de entregar\n' "$v" "$n"; OK=$((OK+1))
else
    # Con cola pendiente es normal y transitorio. Sin cola, es la fuga: la Pi se
    # queda sorda al estado de la gestion para siempre.
    en_cola=$(psql "SELECT count(*) FROM traza.elemento e
                     WHERE e.local_pendiente AND EXISTS (
                       SELECT 1 FROM traza.envio_estado s WHERE s.epc=e.epc AND s.estado_envio='pendiente')")
    if [ "${en_cola:-0}" = "$sin_entregar" ]; then
        avisar "$sin_entregar con la marca puesta, todos con envio en cola: transitorio, normal"
    else
        printf '  %s✗%s %s con la marca puesta y %s sin nada en cola: %sFUGA%s\n' \
            "$r" "$n" "$sin_entregar" "$(( sin_entregar - ${en_cola:-0} ))" "$r" "$n"
        printf '      %s→ Esos elementos se quedan sordos al estado de la gestion para siempre.%s\n' "$a" "$n"
        printf '      %s  Quien deberia limpiarla: el ack del ciclo o el del canal de estados.%s\n' "$a" "$n"
        MAL=$((MAL+1))
    fi
fi

# --- 6. El corte con el legacy --------------------------------------------------------
titulo "El corte con el maestro legacy"
if grep -qi "^IRFID_LEGACY_MIRROR=true" .env 2>/dev/null; then
    printf '  %s✗%s IRFID_LEGACY_MIRROR=true en banco/.env\n' "$r" "$n"
    printf '      %s→ El servicio NO arranca con eso puesto, a proposito. Ponlo a false.%s\n' "$a" "$n"
    MAL=$((MAL+1))
else
    printf '  %s✓%s IRFID_LEGACY_MIRROR no esta a true\n' "$v" "$n"; OK=$((OK+1))
fi
informar "EPC leidos que la gestion no dio (epc_desconocido)" "SELECT count(*) FROM traza.epc_desconocido"
comprobar "ningun elemento sin procedencia de la gestion" \
    "SELECT count(*) = 0 FROM traza.elemento WHERE gestion_etiqueta_id IS NULL AND baja_at IS NULL" t \
    "quedan elementos del alta por lectura: la base no se limpio antes de empezar"

# --- 7. Salud -------------------------------------------------------------------------
titulo "Salud del servicio"
salud=$(curl -s --max-time 5 http://127.0.0.1:8090/health || echo '')
if [ -z "$salud" ]; then
    printf '  %s✗%s /health no responde en 8090\n' "$r" "$n"
    printf '      %s→ docker compose logs --tail=40 irfid-almacen%s\n' "$a" "$n"
    MAL=$((MAL+1))
else
    for clave in vinculacion bajada estados; do
        if echo "$salud" | grep -q "\"$clave\""; then
            printf '  %s✓%s /health publica "%s"\n' "$v" "$n" "$clave"; OK=$((OK+1))
        else
            printf '  %s✗%s /health no publica "%s" (imagen antigua?)\n' "$r" "$n" "$clave"; MAL=$((MAL+1))
        fi
    done
fi
printf '  %s·%s el orquestador en 503 es ESPERABLE: los lectores estan en otra red%s\n' "$g" "$g" "$n"

# --- 8. ¿Puede funcionar sola? ---------------------------------------------------------
# La pregunta de la demo: la gestion no va a estar siempre encendida.
titulo "Autonomia: ¿aguanta sin la gestion?"

# Lo unico imprescindible es tener el inventario bajado. Sin el, todo lo que se lea
# cae en epc_desconocido y el almacen aparece vacio.
inventario=$(psql "SELECT count(*) FROM traza.elemento
                    WHERE gestion_etiqueta_id IS NOT NULL AND baja_at IS NULL")
if [ "${inventario:-0}" = "0" ]; then
    printf '  %s✗%s sin inventario: esta Pi NO puede funcionar sola todavia\n' "$r" "$n"
    printf '      %s→ Con la gestion encendida, da de alta el material y espera a que baje.%s\n' "$a" "$n"
    printf '      %s  Hasta entonces, todo lo que lea ira a epc_desconocido.%s\n' "$a" "$n"
    MAL=$((MAL+1))
else
    printf '  %s✓%s %s unidades en inventario: puede leer y decidir sin la gestion\n' "$v" "$n" "$inventario"
    OK=$((OK+1))
fi

comprobar "la topologia tiene lectores de inventario" \
    "SELECT count(*) > 0 FROM traza.lector WHERE rol = 'inventario'" t \
    "sin lectores en topologia.json no hay ciclos que cerrar"

printf '\n  %sLo que SIGUE funcionando con la gestion apagada:%s\n' "$g" "$n"
printf '  %s  ciclos de inventario · papelera · trazabilidad · alertas por correo · visor%s\n' "$g" "$n"
printf '  %sLo que NO, y es esperable:%s\n' "$g" "$n"
printf '  %s  material nuevo dado de alta en la gestion no llega hasta que vuelva;%s\n' "$g" "$n"
printf '  %s  los consumos se acumulan en la cola y se entregan al reconectar.%s\n' "$g" "$n"

if [ "${1:-}" = "--demo" ]; then
    pend=$(psql "SELECT count(*) FROM traza.envio_estado WHERE estado_envio = 'pendiente'")
    ciclos=$(psql "SELECT count(*) FROM traza.envio_gestion WHERE estado = 'pendiente'")
    printf '\n  %sPor entregar cuando vuelva la gestion:%s %s consumo(s), %s ciclo(s)\n' \
        "$g" "$n" "${pend:-0}" "${ciclos:-0}"
fi

# --- Resumen --------------------------------------------------------------------------
printf '\n%s────────────────────────────────────────%s\n' "$g" "$n"
if [ "$MAL" = "0" ]; then
    printf '%s%d bien%s, %d aviso(s). Nada roto.\n' "$v" "$OK" "$n" "$AVISOS"
else
    printf '%s%d bien, %d MAL%s, %d aviso(s).\n' "$r" "$OK" "$MAL" "$n" "$AVISOS"
    printf 'Empieza por el primer ✗: estan en orden de dependencia.\n'
fi
exit $(( MAL > 0 ))
