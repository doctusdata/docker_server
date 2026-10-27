# Lo medido en la instalación el 26/10/2026

Primer día con conexión a la instalación. Todo lo de aquí está **medido**, no supuesto, y
varias de las conclusiones corrigen cosas que yo mismo había dado por buenas antes. Se
escribe porque nada de esto estaba en el repositorio y volver a deducirlo cuesta una
jornada.

---

## 1 · Una antena está defectuosa: el `.158` rinde a un tercio

**El hallazgo principal.** El lector `192.168.1.158` tiene **dos** antenas (el `.157`
tiene cuatro), y una de las dos aporta un cuarto de lo que aporta su compañera.

Diagnóstico por eliminación, con tres pruebas de dos minutos cada una:

| Prueba | Reparto resultante | Conclusión |
|---|---|---|
| Estado inicial | 20% / 80% | — |
| Intercambiar los cables **en los puertos del lector** | 72% / 28% | el desequilibrio viaja con el cable → **no es el lector ni sus puertos** |
| Intercambiar el **extremo de antena** de los cables | 28% / 72% | viaja con la antena → **no es el cable** |
| Mover y reorientar la antena floja | 26% / 74% (sin cambio) | **no es la orientación** |

**Es la antena.** Se confirma sustituyéndola y repitiendo la medición.

Y el dato que lo hace importante: **el total no cambió nunca**, unas 4.200 lecturas por
ventana entre las dos. Mover el problema de puerto no gana cobertura. Mientras esa antena
rinda al 28%, hay zonas de la estantería donde una etiqueta tarda minutos en verse.

### El método de medición, que es reutilizable

`traza.lector_antena.lecturas_ultima_ventana` se actualiza en **cada ventana** (~2 min),
así que el ajuste físico se hace con realimentación y no a ciegas:

```sql
SELECT a.antena, a.lecturas_ultima_ventana, a.lecturas_total
  FROM traza.lector_antena a JOIN traza.lector l ON l.id = a.lector_id
 WHERE l.devip::text = '192.168.1.158' ORDER BY a.antena;
```

Referencia de lo que es un reparto sano: el `.157`, con **33 / 22 / 18 / 27 %**. Ninguna
por debajo de la mitad de la mayor.

> **No sirve el RSSI del legacy para esto.** Los dos lectores publican con
> `devid: "Almacen-1"`, así que en `EPC_readings` la columna `Antenna` **mezcla** la 1 del
> `.157` con la 1 del `.158`. Además el espejo guarda solo el máximo por etiqueta, que es
> justo el valor que esconde las lecturas débiles.

---

## 2 · La acusación falsa, trazada entera

A las 13:04 el sistema declaró una etiqueta fuera del almacén y se la atribuyó a Carlos
Garcia. **Nunca se movió de la estantería.** La historia completa de
`999900990000000000000176`:

```
12:38:52  pendiente  ->  12:40:26  vuelve   ( 94 s en sombra)
12:42:56  pendiente  ->  12:43:51  vuelve   ( 55 s)
12:49:03  pendiente  ->  12:50:26  vuelve   ( 83 s)
12:53:07  pendiente  ->  12:54:10  vuelve   ( 63 s)
12:59:14  pendiente  ->  13:04:26  CONFIRMADA FUERA  (312 s, criterio "tiempo")
                          13:09:00  vuelve           <- estaba ahi
```

**Esta instalación tiene huecos de sombra de hasta 312 segundos en etiquetas presentes.**
Cualquier umbral por debajo de eso produce acusaciones falsas, y
`IRFID_MINUTOS_PARA_CIRCULANTE=5` está justo en ese límite.

Y el disparo fue el criterio **`tiempo`**, no `ciclos`. Con periodo de 122 s, los 5
minutos llegan antes que los 3 ciclos.

**Mientras no se cambie la antena**, para enseñarlo sin riesgo:
`IRFID_MINUTOS_PARA_CIRCULANTE=15`. Detecta más lento pero no acusa en falso.

---

## 3 · La trampa de la configuración: el `.env` no se relee al reiniciar

Durante horas no se podía confirmar **ninguna** salida. El motivo:

```
en el .env del disco:     IRFID_CICLOS_PARA_CIRCULANTE=2    MINUTOS=5
en el proceso corriendo:  IRFID_CICLOS_PARA_CIRCULANTE=100  MINUTOS=600
```

El contenedor arrastraba el parche del 23/10. **Las variables de entorno se fijan al
*crear* el contenedor**: `docker restart` no las relee. Hay que recrear:

```bash
cd ~/roomfid && docker compose up -d irfid-almacen
```

Se nota que las ha tomado porque el contador `observaciones` de `:8090/health` vuelve a
empezar. **Comprobar siempre con `docker exec <contenedor> env`, no con el fichero.**

---

## 4 · Los tiempos de detección, medidos

Con `orq_periodo_s=60` y ciclos válidos cada **122 s**:

- **Marcar como dudosa: 2 a 4 minutos.** Hace falta un ciclo que *empiece* después de la
  última lectura: si se saca a mitad de ventana, ese ciclo ya la vio
  (`faltan = ... ultima_lectura_at < inicio`).
- **Confirmar fuera: 5 minutos desde que se marca**, pero **el reloj se reinicia en cada
  relectura**. Con parpadeo el tiempo real es impredecible: el caso del punto 2 tardó 25
  minutos por cuatro reinicios.

---

## 5 · Dos diagnósticos míos que los datos tumbaron

Se dejan escritos porque llegué a construir sobre ellos y habría mandado el trabajo por
el camino falso.

**«No llegan los eventos de control al broker.»** FALSO. Escuché 75 s y solo vi
`TAG_readings`, pero las ventanas válidas duran **exactamente 120-121 s** = `orq_ventana_s`,
y eso solo ocurre si el `stop` se recibe (por silencio tardarían 20 s más). Los `start`/
`stop` funcionan.

**«Cinco de cada siete ciclos se tiran, así que la detección va a un tercio de
velocidad.»** FALSO. Las ventanas "corta" duran **0-2 segundos** con 65 EPC de media: son
la **cola del agregador**, que deduplica 5 s antes de emitir, así que las últimas
observaciones llegan cuando el `stop` ya cerró la ventana y abren otra que muere al
instante. Una corta por cada válida, 34 contra 36.

Y no retrasan nada: `_cerrar_ciclo_invalido` (`almacen/repo.py:417`) **solo inserta la fila
del ciclo**, no toca `traza.elemento`. Solo los ciclos válidos cuentan ausencias. Son
ruido en el registro, no en el funcionamiento.

---

## 6 · El visor: dos contabilidades del mismo hecho

El número que la persona receptora veía bailar (951, 947, 945, 952, 946…) venía del KPI
**«En stock ahora»**, que leía de la API heredada. El legacy descuenta al instante lo que
no se ha visto en la última pasada, y con el parpadeo de antena eso cambia **once veces
por minuto**.

```
stock total (traza)   956   <- quieto; solo baja si algo se confirma fuera
pendientes              9   <- parpadean
lo que enseñaba        947   <- bailaba
```

**El arreglo fue qué número se enseña, no cada cuánto se refresca.** Refrescar más a
menudo lo empeora.

Desplegado el 26/10 en `http://192.168.1.155:8020`: tira de tres cifras —*En el almacén ·
Pendientes de confirmar · Fuera del almacén*— con la hora de la última medición, y el KPI
viejo retirado. Ficheros: `raspi_visor/frontend/src/components/Inventario.tsx` y el
`Dashboard`.

> El visor necesita una **segunda fuente**: el stock por ubicación y la salud de los
> lectores salen de irfid (`:8090`), no de la API heredada. Va por nombre de servicio,
> `ALMACEN_API_URL: http://irfid-almacen:8090`; con `127.0.0.1` apuntaría al visor mismo.
> **Y el compose de la Pi es su propia copia**: cambiar el del repositorio no basta.

---

## 7 · La cobertura es buena, pero no falla siempre lo mismo

Un ciclo válido ve **947 de 956 — el 99%**. El problema no es cuánto se lee, es que
**no es el mismo 1% el que falla**: `faltantes` oscila entre 8 y 12 en cada pasada, con
etiquetas distintas. De ahí salen las sombras, y de las sombras la acusación falsa.

Por eso el trabajo está en la antena y no en los umbrales: con cobertura buena los 5
minutos probablemente sobran; con cobertura mala **ningún** umbral es bueno — o acusa en
falso o tarda un cuarto de hora.

---

## 8 · Cosas sueltas que cuestan de encontrar

- **`clon/construir-arm64.sh` no funciona en un Mac Apple Silicon.** Comprueba que haya
  emulación arm64 registrada, correcto en la máquina x86 para la que se escribió, pero
  aquí ARM es nativo y da falso negativo. Se construye directo:
  ```bash
  docker buildx build --platform linux/arm64 -t roomfid/visor:latest \
    -f rep_server/docker/visor/Dockerfile --load raspi_visor
  ```
  Nativo tarda **segundos**, no la emulación que el script asume.
- **Antes de cargar una imagen nueva en la Pi**, renombrar la que hay:
  `docker tag roomfid/visor:latest roomfid/visor:antes-<fecha>`. Da vuelta atrás con un
  comando.
- **Las antenas se declaran.** El `.158` tiene dos y el sistema esperaba cuatro (por
  defecto `[1,2,3,4]`), acumulando **153 ventanas de fallo** de dos puertos inexistentes.
  `estado.py` itera las **declaradas** (`f["antenas"]`), así que basta declarar `[1, 2]`;
  las filas de las fantasma quedan en la tabla pero dejan de evaluarse.
- **`venv` y `node_modules` del repositorio vienen de una máquina Linux** (`/var/raid/
  feterand/...`): sus intérpretes y el binario nativo de rollup no valen en un Mac. Se
  arregla con `python -m pip install -r requirements.txt` y borrando `node_modules` para
  reinstalar con pnpm.
- **La clave SSH de `192.168.1.155`** en `known_hosts` puede ser la del servidor original
  que ocupaba esa dirección. `ssh-keygen -R 192.168.1.155` y volver a conectar.

---

## Pendiente

1. **Cambiar la antena floja del `.158`** y volver a medir con el método del punto 1. Es la
   raíz de todo lo demás.
2. Mientras no esté: `IRFID_MINUTOS_PARA_CIRCULANTE=15` si hay que enseñarlo.
3. Volver a medir los huecos de sombra en una etiqueta concreta. Si los 312 s bajan a
   treinta, los umbrales actuales valen sin tocarlos.
4. El lector de puerta (`LECTOR-159`) ya publica: queda probar la atribución con carnet,
   que es lo que convierte la confianza de `ultimo` en `ventana`.
