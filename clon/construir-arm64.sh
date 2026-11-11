#!/bin/bash
# Construye las cinco imagenes propias para la Raspberry (arm64) DESDE ESTA MAQUINA.
#
# La Pi solo ejecuta: no lleva codigo fuente ni compila nada. Aqui se construye,
# alli se carga la imagen ya hecha. Para actualizar algo en el futuro basta con
# volver a lanzar esto y copiar el paquete.
#
#   ./construir-arm64.sh            las cinco
#   ./construir-arm64.sh irfid      solo una (irfid|api|visor|monitor|agente)
#
# **En un Mac con Apple Silicon (M1/M2/M3) esto es NATIVO**, no emulado: el host ya
# es arm64, asi que se construye a velocidad normal con el builder por defecto y no
# hace falta ni QEMU ni un builder aparte. En una maquina x86_64 si hace falta la
# emulacion, y entonces tarda bastante.
#
# Requisitos: docker buildx y, solo en x86_64, emulacion arm64 registrada.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"     # .../desarrollo
REP="$RAIZ/rep_server"
ETIQUETA="${ETIQUETA:-latest}"
BUILDER="roomfid-arm"

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }

# --- comprobaciones previas: fallar aqui es barato, a mitad de build no -------------
docker buildx version >/dev/null 2>&1 || { rojo "falta docker buildx"; exit 1; }

# El motor primero. En un Mac es la causa mas probable de todo lo demas, y si no se
# comprueba aparte el fallo sale disfrazado de "no puede construir arm64".
if ! docker info >/dev/null 2>&1; then
    rojo "el motor de Docker no responde."
    case "$(uname -s)" in
        Darwin) echo "  Arranca OrbStack (o Docker Desktop) y vuelve a lanzar esto:"
                echo "    open -a OrbStack" ;;
        *)      echo "  systemctl start docker" ;;
    esac
    exit 1
fi

# **En un host arm64 no hace falta emulacion ni builder aparte.** El de por defecto
# construye arm64 nativo, que es mas rapido y una pieza menos. La emulacion solo es
# necesaria en x86_64, y ahi si merece el builder docker-container.
ANFITRION="$(uname -m)"
if [ "$ANFITRION" = "arm64" ] || [ "$ANFITRION" = "aarch64" ]; then
    USAR_BUILDER=()
    verde "host $ANFITRION: arm64 nativo, sin emulacion"
else
    if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
        echo "creando el builder $BUILDER..."
        docker buildx create --name "$BUILDER" --driver docker-container >/dev/null
    fi
    # El arranque del builder tarda la primera vez; se consulta despues de arrancarlo,
    # porque recien creado todavia no informa de las plataformas que soporta.
    docker buildx inspect "$BUILDER" --bootstrap >/dev/null 2>&1 || true

    # **Sin tuberia a proposito.** Esto era
    #     docker buildx inspect X | grep -q "linux/arm64"
    # y con `set -o pipefail` falla SIEMPRE: grep -q sale en cuanto encuentra, cierra
    # la tuberia, docker muere al escribir y pipefail se queda con ESE codigo (255),
    # no con el 0 de grep. La comprobacion daba negativo con la emulacion puesta y
    # sin ella, y el mensaje mandaba a registrar una emulacion que ya estaba.
    PLATAFORMAS="$(docker buildx inspect "$BUILDER" 2>&1 || true)"
    if ! grep -q "linux/arm64" <<< "$PLATAFORMAS"; then
        rojo "el builder no puede construir arm64. Registra la emulacion con:"
        echo "  docker run --privileged --rm tonistiigi/binfmt --install arm64"
        exit 1
    fi
    USAR_BUILDER=(--builder "$BUILDER")
    verde "host $ANFITRION: arm64 por emulacion (tarda)"
fi

# nombre|contexto|dockerfile|imagen
IMAGENES=(
  "irfid|$RAIZ/irfid/servicio|$REP/docker/irfid/Dockerfile|roomfid/irfid:$ETIQUETA"
  "api|$RAIZ/irfid/gestion-rfid-api|$REP/banco/api/Dockerfile|roomfid/api:$ETIQUETA"
  "visor|$RAIZ/raspi_visor|$REP/docker/visor/Dockerfile|roomfid/visor:$ETIQUETA"
  "monitor|$RAIZ/monitor|$REP/docker/monitor/Dockerfile|roomfid/monitor:$ETIQUETA"
  "agente|$RAIZ/monitor|$REP/docker/agente/Dockerfile|roomfid/agente:$ETIQUETA"
)

pedidas=(${@+"$@"})
construidas=()

for fila in "${IMAGENES[@]}"; do
    IFS='|' read -r nombre contexto dockerfile imagen <<< "$fila"
    if [ "${#pedidas[@]}" -gt 0 ] && [[ ! " ${pedidas[*]-} " =~ " $nombre " ]]; then
        continue
    fi
    echo
    verde "=== $nombre -> $imagen (arm64) ==="
    extra=()
    # El nodo del monitor necesita un contexto adicional con sus ficheros de despliegue.
    [ "$nombre" = "monitor" ] && extra=(--build-context "despliegue=$REP/docker/monitor")
    # `${a[@]+"${a[@]}"}` y no `"${a[@]}"`: **macOS trae bash 3.2**, donde expandir
    # un array vacio con `set -u` es un error, no una lista vacia. Con la forma de
    # abajo no se expande nada cuando no hay nada.
    docker buildx build \
        ${USAR_BUILDER[@]+"${USAR_BUILDER[@]}"} \
        --platform linux/arm64 \
        -f "$dockerfile" \
        -t "$imagen" \
        ${extra[@]+"${extra[@]}"} \
        --load \
        "$contexto"
    arq=$(docker image inspect "$imagen" --format '{{.Architecture}}')
    [ "$arq" = "arm64" ] || { rojo "$imagen quedo en $arq, no arm64"; exit 1; }
    construidas+=("$imagen")
done

echo
verde "Listas (${#construidas[@]}):"
for i in "${construidas[@]}"; do
    # El tamano se formatea aqui y no con `numfmt`, que es de GNU coreutils y **no
    # viene en macOS**: dejaba la columna vacia justo al terminar un build de media
    # hora, que es cuando menos apetece dudar de si salio bien.
    bytes="$(docker image inspect "$i" --format '{{.Size}}')"
    printf '  %-28s %s MB\n' "$i" "$(( bytes / 1000000 ))"
done
echo
echo "Siguiente paso: ./empaquetar.sh"
