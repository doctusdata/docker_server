# Parches provisionales montados en los contenedores

**Esto no debería existir.** Son dos ficheros que van montados encima de lo que traen las
imágenes, porque el 31/10 y el 1/11 no se pudieron mover las imágenes nuevas a la Pi de la
sala: `scp` se cuelga contra ese enlace y son 56 y 83 MB. Los ficheros sueltos sí caben.

| fichero | qué sustituye | qué aporta |
|---|---|---|
| `repo.py` | `irfid/almacen/repo.py` | **el nucleo**: una ventana `corta` ya no invalida el ciclo. Imprescindible para leer en serie |
| `api.py` | `irfid/inventario/api.py` | el grupo **`observacion`** —las que aparecen y desaparecen, contadas como dentro—, el campo `umbral_ciclos` en `/resumen` y el **POST** que reinicia el contador de pasadas |
| `visor-inventario.py` | `/app/app/routers/inventario.py` del visor | la ruta **POST** `/observacion/reiniciar`, que la imagen no trae |
| `visor-rfid-client.py` | `/app/app/rfid_client.py` del visor | el `post()` del cliente, que **vacía la caché**: con TTL de 10 s, sin eso la pantalla enseña las cifras de antes justo después de pulsar |
| `web/` | `/app/web` del visor | el panel de cifras del inventario: cuatro de serie y la quinta —«En observación», con su tabla de **pasadas sin leer**— sólo con `?tecnico=1`. Y las fechas con segundos |

## Por qué montados y no copiados dentro

Un contenedor es la imagen de sólo lectura más una capa de escritura. `docker cp` deja el
fichero en esa capa, y **`docker compose up -d` destruye el contenedor al recrearlo**, así
que el parche se va con él. Pasó el 1/11 al aplicar el umbral de 15 pasadas: la cifra de
«en observación» desapareció del panel sin que nadie tocara el visor.

Montado desde el disco de la Pi no vive en esa capa y sobrevive a cualquier recreación. Es
el mismo mecanismo que el compose ya usa para `topologia.json`, `api/app.json` y la
configuración de Mosquitto.

## Y uno de ellos ya no es cosmetico

`repo.py` **no es presentacion, es la logica del ciclo de inventario**. Mientras este
montado, la Pi ejecuta una version de `almacen/repo.py` que no es la de su imagen, y de eso
depende que la lectura en serie funcione. Esta commiteado en `irfid`
(`832fce7`), asi que la imagen siguiente lo traera dentro: **ese es el momento de quitar
este montaje**, y no antes.

## CUÁNDO QUITARLOS

**En cuanto se despliegue una imagen que ya lleve estos cambios dentro.**

Un montaje **tapa lo que traiga la imagen, en silencio**. Si se queda puesto, la Pi seguirá
ejecutando estos ficheros aunque la imagen nueva traiga otros, y no hay ningún aviso: el
sistema arranca, funciona, y ejecuta código viejo. Es exactamente el tipo de cosa que
cuesta un día de diagnóstico seis meses después.

Para quitarlos: borrar las líneas `- ./parches/...` de `clon/docker-compose.yml` y
`docker compose up -d irfid-almacen visor`.

**Y ojo con `api.py`: cambiar el fichero no basta.** El montaje es el mismo, así que
`up -d` no ve ninguna diferencia de configuración y no recrea nada; Python ya tiene el
módulo importado. Hay que **`docker compose restart irfid-almacen`** para que lo vuelva a
leer. El del visor igual.

## Y una trampa de la ruta

El montaje de `api.py` apunta a `/usr/local/lib/python3.12/site-packages/...`, **con la
versión de Python dentro**. Si una imagen futura cambia de versión, esa ruta deja de ser la
del paquete: el parche no se aplicaría, o Docker crearía ahí un fichero suelto. Otra razón
para que esto dure poco.

## El origen de cada uno

- `api.py` — rama `topologia-papelera` de `irfid`, `servicio/src/irfid/inventario/api.py`,
  con el grupo `observacion` añadido al diccionario `GRUPOS`.
- `web/` — rama `inventario-estable` de `raspi_visor`, `pnpm build` sobre `frontend/`.
