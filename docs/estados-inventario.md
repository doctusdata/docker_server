# Estados del inventario: lo decidido y lo que queda abierto

> **29-30/10/2026.** El modelo de estados tal como quedó, dónde vive cada regla, y las
> decisiones que se dejaron para la vuelta. Escrito para no reconstruirlo de memoria.
>
> El código está en las ramas `topologia-papelera` (irfid y rep_server) e
> `inventario-estable` (raspi_visor). **Nada fusionado a `main`** a propósito: los
> estados se van a revisar, y las tres fusiones son inseparables entre sí (ver el final).

---

## El modelo, tal como quedó

| En pantalla | En la base | Quién lo pone | ¿Suma al total? |
|---|---|---|---|
| **Entrada** | `creado` | La bajada de gestión: alguien lo escaneó en su pantalla de escaneo | **sí** |
| **En almacén** | `almacen` | La Pi, al detectarlo las antenas | **sí** |
| **En tránsito** | `en_transito` | **La Pi**, tras N pasadas sin aparecer | **sí** |
| **Consumido** | `usado` | La papelera, sin incidencia | no |
| **Caducado** | `retirado` + `retirada_motivo='caducidad'` | La papelera, incidencia `caducado` | no |
| **Retirado** | `retirado` + motivo `alerta_sanitaria` \| `destruccion` | La papelera | no |
| **Baja de gestión** | cualquiera + `baja_at` | Gestión: traslado a otra instalación, o borrado | no |

El titular es, literalmente:

```sql
count(*) WHERE baja_at IS NULL AND estado IN ('creado','almacen','en_transito')
```

**Inventario = entrada + almacén + tránsito**, y la suma es exacta por construcción:
las cuatro pestañas salen de la misma consulta cambiando el filtro, así que no pueden
contradecirse. Eso es lo que hace que el titular no pueda bailar: un fallo de antena
mueve una unidad entre «almacén» y «tránsito», que están los dos dentro, así que la
histéresis **reparte y no resta**.

Medido contra la API: **45 constante** mientras `en_almacen` bajaba de 40 a 33 y
`en_transito` subía de 3 a 10.

### Tres cosas que no son obvias y conviene no volver a discutir

**`consumido` y `caducado` no son estados de la base, y no pueden serlo.** Gestión
rechaza de forma terminal cualquier estado que no sea `usado` o `retirado`
(`ESTADOS_ACEPTADOS` en su endpoint de sync), y un rechazo en `traza.envio_estado` **no
se reintenta a propósito**: el consumo se perdería. Son nombres de pantalla sobre el
estado más `retirada_motivo`, que es el discriminante y ya existía vacío desde el SQL
010. Lo mismo impide renombrar `usado` a `consumido`.

**«En almacén» no es «lo que se ve ahora».** Cuenta `estado='almacen'` sin filtrar el
flag `temporal`, así que incluye las que no aparecieron en la última pasada pero todavía
no se dan por salidas. Filtrarlas es exactamente lo que hacía bailar el número.

**La baja de gestión no cambia el estado.** `gestion/bajada.aplicar_baja` pone `baja_at`
y no toca `estado`: son dos autoridades distintas sobre la misma fila. Por eso el filtro
`baja_at IS NULL` está en la métrica y no se resuelve con un estado nuevo.

### Dónde vive cada regla

| Regla | Fichero |
|---|---|
| La máquina de estados entera (pura, sin base ni reloj) | `irfid/servicio/src/irfid/almacen/reglas.py` |
| Incidencia de papelera → motivo de retirada | `reglas.MOTIVO_POR_INCIDENCIA` |
| Umbrales de la histéresis | `config.ciclos_para_circulante=3`, `minutos_para_circulante=30` |
| El titular y su desglose | `almacen/estado.py`, `_SQL_INVENTARIO` |
| Las cuatro pestañas y el vocabulario de pantalla | `inventario/api.py`, `GRUPOS` y `_estado_pantalla` |
| Una entrada corta el inventario | `sql/021_notify_acceso.sql` + `orquestador/accesos.py` |
| Qué sube a gestión | `gestion/estados.py` (sólo `usado` y `retirado`) |
| Qué baja de gestión | `gestion/bajada.py` (la ficha siempre; el estado salvo `local_pendiente`) |

---

## Lo que queda abierto

### 1. El tránsito falso — lo más importante de esta lista

**No es un problema de presentación.** Se escondió la cifra de la pantalla principal
(modo técnico, `?tecnico=1`), pero esconderla **no evita la salida falsa**: el
`en_transito` falso se escribe igual en la traza y **se atribuye a quien entró el
último**. Eso es lo que convierte una sombra de antena en una acusación.

Los datos son vuestros, del informe del 26/10
(`docs/diagnostico-lectores-2026-10-26.md`):

> Sombras de hasta **21 minutos** en etiquetas presentes: **todas las salidas de hoy han
> sido falsas** […] el **100 %** de las salidas de hoy son acusaciones falsas

Con `ciclos_para_circulante=3` y ciclo de cinco minutos, bastan **quince** de sombra para
escalar. Una sombra de 21 escala.

Dos palancas, y la primera es el arreglo de verdad:

- **La antena floja del `.158`**, que el propio informe señala como causa de las sombras.
  La pantalla `/diagnostico` la resalta: `ventanas_sin_lecturas` cuenta ventanas válidas
  seguidas en las que el lector leyó por otras antenas y por ésa no.
- **Subir `IRFID_CICLOS_PARA_CIRCULANTE`** por encima de la sombra medida. Es un número
  en el `.env` y se puede tocar antes de una demo. Con sombras de 21 minutos, 3 ciclos no
  bastan.

### 2. El archivado no lo ejecuta nadie

`traza.archivar_terminados` existe y está bien hecha (respeta `local_pendiente` y los
envíos pendientes o rechazados, y **mueve** a `traza.elemento_historico` en vez de
borrar, con la vista `traza.elemento_todo` que une las dos). Pero **sólo se llama desde
el CLI**: no está en las tareas periódicas del runner, no hay cron y en `deploy/` sólo
hay `irfid.service`, sin timer.

Consecuencia: los terminados desaparecen **de la vista** a los 7 días y se quedan en
`traza.elemento` para siempre. Con ~1.000 unidades no molesta en años, pero no es lo que
se cree.

**Por decidir:** tarea del runner cada 24 h (el patrón `_cada()` está hecho, y
`bootstrap` ya entró así en el `command` de los compose) o línea de cron
(`python -m irfid archivo programar` la imprime). Y el plazo: hoy
`archivo_dias_elemento=180`.

### 3. ¿Debe `entrada` contar en el total?

Hoy **sí**, siguiendo lo que se dijo: *el stock son los que recibe, y que están en estado
entrada*. Es defendible —gestión ya los ha dado de alta y son responsabilidad del
almacén— pero significa que el total incluye unidades que **las antenas no han visto
nunca**.

Hay un límite técnico asociado: un `creado` que no haya pasado por la bajada no tiene
ubicación local de ningún tipo, así que no se puede atribuir a un almacén. Con **un solo
almacén** se le suman (no hay ambigüedad); con varios se quedan fuera. Está en
`estado.py`, en el bloque de los huérfanos.

### 4. La retención de pantalla: 7 días

Elegido así y es un número. Se cambia en `inventario/api.py`, `DIAS_TERMINADOS`. No
pierde nada: el dato sigue en la tabla.

### 5. La política de actualización del panel

El panel va con lo que había: `refetchInterval` de 30 s y `staleTime` de 15 s. Y eso
**da igual** mientras las cifras sólo cambien por hechos — que es vuestro propio hallazgo
del 26/10: *«el arreglo fue qué número se enseña, no cada cuánto se refresca; refrescar
más a menudo lo empeora»*. Si se quiere anclar el repintado al cierre de ciclo, es mover
dónde se dispara el `invalidateQueries`, no rehacer el panel.

### 6. Dos cosas que dependen de otros

- **La MAC de la papelera** (`64:70:60:d2:79:5a`) salió del parche que esperaba en
  `.pendiente/lector-puerta-20261026/`. **No está verificada contra el aparato.**
- **`detalle` se manda y gestión lo descarta.** Su `CambioEstadoIn.detalle` promete
  viajar a `movimientos.detalle`, pero el endpoint no lo pasa y el modelo no tiene esa
  columna. Hay que decirlo a su equipo: o añaden la columna, o se retira el campo del
  contrato y de `gestion/estados.py`.

---

## Para fusionar a `main`, cuando se decida

Las tres ramas van **estrictamente por delante** de main (0 commits por detrás), así que
las tres fusiones son avances limpios sin conflictos posibles:

| Repo | Rama | Por delante |
|---|---|---|
| `raspi_visor` | `inventario-estable` | 5 |
| `irfid` | `topologia-papelera` | 15 (incluye los 9 de `sincronizacion-c`) |
| `rep_server` | `topologia-papelera` | 17 (incluye los 13 de `sincronizacion-c`) |

**Pero no son separables.** El `main` de irfid no tiene `inventario/api.py`,
`orquestador/accesos.py` ni `sql/021`, que es todo lo que el visor nuevo llama. Llevar
sólo el visor deja el panel con el cartel de error. Y llevar irfid implica llevarse los 9
commits de `sincronizacion-c`, que es el canal con gestión: **ésa es la decisión de
fondo, no el diseño.**

La Pi no ejecuta ramas, ejecuta imágenes: lo que está desplegado no depende de en qué
rama estéis.

## Estado del despliegue

Paquete listo y verificado por dentro en `clon/roomfid-actualizar-20261030.tar.gz` y en
`~/actualizar-20261030`. **Sin desplegar**: la Pi (`192.168.0.17`, no la `.60` que decía
la documentación) pide contraseña por SSH.

Lo que ya corre allí es el commit de las 21:19 del 29/10: tiene la métrica estable y la
API de inventario, pero no el endpoint de accesos, ni los arreglos de `bootstrap`, ni el
visor nuevo.
