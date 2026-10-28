# Clonar RoomFID a una Raspberry nueva

La Raspberry **solo ejecuta**: no lleva código fuente ni compila nada. Las imágenes se
construyen aquí, en la máquina de desarrollo, y allí solo se cargan.

```
  desarrollo (x86_64)                      Raspberry (arm64)
  ──────────────────                       ─────────────────
  código fuente                            imágenes arm64
  construir-arm64.sh  ──┐                  configuración
  empaquetar.sh       ──┴─► paquete ─────► datos
                            ~1,5 GB        docker compose up
```

## Preparar la Raspberry (lo haces tú)

1. **Raspberry Pi OS de 64 bits.** La actual es `aarch64` / Debian 13. Con 32 bits las
   imágenes no arrancan.
2. **Usuario `andy`** — el compose y las rutas lo dan por hecho.
3. **Docker:**
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker andy      # y volver a entrar
   ```

## Clonar

```bash
# 1. Construir las imágenes para ARM (la primera vez tarda: emulación)
./construir-arm64.sh

# 2. Empaquetar. SIN datos: la Pi nueva arranca vacía.
./empaquetar.sh

# 3. Copiar e instalar
scp roomfid-pi-*.tar.gz andy@NUEVA_IP:~/
ssh andy@NUEVA_IP 'tar xzf roomfid-pi-*.tar.gz && cd roomfid-pi && ./instalar.sh'

# 4. Vincular con la gestión (el instalador explica cómo)
#    En gestión: Almacenes → <el almacén> → Vincular Pi
ssh andy@NUEVA_IP 'cd roomfid && docker compose exec irfid-almacen \
  python -m irfid vincular --gestion https://TU-GESTION --codigo XXXX-XXXX'
```

El instalador pide editar el `.env` con las credenciales reales (no viajan en el
paquete) y luego se vuelve a lanzar.

### Una Pi nueva ya no necesita el volcado de otra

Esto cambió con el enfoque C de la sincronización. Antes había que llevarse la base
de una Pi existente (`--desde`) porque el inventario vivía ahí y no había otra forma
de que la Pi nueva supiera qué etiquetas existen. Ahora **el inventario lo tiene la
plataforma de gestión**, que es la única fuente: la Pi arranca vacía, aplica su
esquema con `python -m irfid migrar` y pide lo suyo al vincularse.

Tres cosas mejoran por eso:

- **No se arrastra el esquema legacy** (`EPC_master`, `EPC_readings`, `Bin`) a una
  instalación nueva que no lo necesita;
- **no se copian datos de otro hospital** a una Pi que va a otro sitio, que además
  de incómodo era un problema de confidencialidad;
- el paquete baja de ~183 MB a solo las imágenes y la configuración.

**`--desde` sigue existiendo**, y es lo correcto para un caso concreto: mudar una
instalación que ya estaba funcionando con el sistema antiguo y cuyo histórico hay
que conservar. Para eso trae también el esquema legacy, que es justo lo que se
quiere ahí.

```bash
./empaquetar.sh --desde andy@192.168.0.59     # mudanza, no instalación nueva
```

Con volcado, el instalador **no** propone vincular: la vinculación viene dentro de
la base restaurada, y repetirla rotaría el token del almacén sin necesidad.

## Actualizar después

Cambias código aquí y repites los tres pasos. También se puede una sola imagen:

```bash
./construir-arm64.sh irfid
docker save roomfid/irfid:latest | gzip | ssh andy@IP 'docker load'
ssh andy@IP 'cd roomfid && docker compose up -d irfid-almacen'
```

## Probado en campo

Clonado real a una Raspberry de 128 GB el 19/10/2026 (`192.168.0.60`): las nueve
piezas arrancaron y la base llegó completa (997 elementos, 1.003 movimientos,
idéntico al origen). Tres fallos salieron en esa primera instalación y están ya
corregidos en los scripts:

- **`andy` no estaba en el grupo `docker`.** El instalador lo detecta y lo dice, pero
  hay que arreglarlo antes: `sudo usermod -aG docker andy` y volver a entrar.
- **`mosquitto_passwd -c` no sobrescribe** un fichero existente (`File exists`). Se
  borra antes de generarlo.
- **El `initdb` espera `/volcado/produccion.sql` sin comprimir.** El instalador
  descomprime el volcado con ese nombre. Solo aplica al caso de mudanza
  (`--desde`): sin volcado no interviene.

## Cuatro cosas que conviene saber

**El `passwd` de Mosquitto no se copia.** Es del uid 1883 con permisos 0700; copiado de
otra máquina el broker arranca con `Unable to open pwfile` y no publica nadie. El
instalador lo regenera desde el `.env`, y deja `regenerar-passwd.sh` por si cambia la
contraseña.

**La base se vuelca con `pg_dump`, no copiando el volumen.** Copiar `pgdata` en caliente
da una base corrupta. El empaquetado comprueba que el volcado termina bien y el
instalador verifica que el número de elementos y movimientos coincide con el origen.

**La IP `.155`.** Si la Pi actual la tiene fijada (`scripts/ip.sh fijar`), las dos
pelearían por ella. La nueva no debe tomarla hasta que la vieja esté apagada.

**El `.env` no viaja.** Lleva credenciales en claro: va la plantilla. Hay que copiar los
valores reales a mano (o traerlos de la Pi actual con `scp`).

## Versiones

`ETIQUETA` permite construir y desplegar versiones con nombre, y volver atrás sin tocar
el compose:

```bash
ETIQUETA=v1 ./construir-arm64.sh && ETIQUETA=v1 ./empaquetar.sh
# en la Pi, en el .env:  ETIQUETA=v1
```
