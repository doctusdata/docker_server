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

# 2. Empaquetar, con los datos de la Pi actual
./empaquetar.sh --desde andy@192.168.0.59

# 3. Copiar e instalar
scp roomfid-pi-*.tar.gz andy@NUEVA_IP:~/
ssh andy@NUEVA_IP 'tar xzf roomfid-pi-*.tar.gz && cd roomfid-pi && ./instalar.sh'
```

El instalador pide editar el `.env` con las credenciales reales (no viajan en el
paquete) y luego se vuelve a lanzar para restaurar la base.

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
  descomprime el volcado con ese nombre.

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
