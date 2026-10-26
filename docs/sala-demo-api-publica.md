# Sala demo — la API heredada hacia la gestión en la nube

**Cambio temporal, hecho a mano en la Pi de la sala (26/10/2026).** No está en
`clon/docker-compose.yml`: un clon nuevo sale con los puertos de siempre.

## Por qué

La gestión corre en la nube y consulta la API heredada (`:3000/api`) a través de la IP
pública de la sala. El router de la sala solo lleva tres puertos a la Pi (`.155`):

| Puerto | Servicio |
|---|---|
| 2015 | SSH |
| 8020 | Visor |
| 8080 | Monitor |

El 3000 no está redirigido, y la administración remota del router está cerrada, así que
tampoco se puede abrir desde fuera. La solución es que la API salga por un puerto que el
router ya redirige.

## Qué se cambió en la Pi

En `~/roomfid/docker-compose.yml`:

```yaml
  api:
    ports:
      - "3000:3000"
      - "8080:3000"      # temporal: la gestion cloud entra por el 8080 del router

  monitor:
    ports:
      - "8081:8080"      # temporal: liberado el 8080 para la API
```

```bash
cd ~/roomfid && docker compose up -d api monitor
```

Así solo se recrean esos dos contenedores. No se reconstruye ninguna imagen ni se pierde
ningún dato: la API no guarda estado y el monitor tiene sus datos en el volumen
`monitor-data`. El visor no nota el cambio, porque llama a la API por la red interna
(`http://api:3000/api`). El `3000:3000` se mantiene para la red local.

## En la gestión

La URL va en la **licencia del hospital**, no en el almacén: la gestión la lee de
`licencia.lector_url` (`gestion/backend/app/services/lector.py`).

```
lector_url = http://<IP pública de la sala>:8080/api
```

Tiene que terminar en `/api`, porque la gestión añade la ruta detrás
(`epc-readings/stock`, `epc-master`…).

| Mensaje de la gestión | Causa |
|---|---|
| No se pudo conectar con el lector en … | Red: la nube no llega a esa IP o a ese puerto |
| El lector respondió 404 | Falta `/api` en la URL |
| El lector respondió 401 / 403 | La `apikey` de la licencia no coincide con el `API_KEY` del `.env` de la Pi |

## Comprobar

Desde fuera de la sala:

```bash
curl -sI http://<IP pública de la sala>:8080/api | head -1    # 401 sin clave: correcto
```

En `/` la API sirve su página antigua (`www/api.html`), "API de gestión de RFID". Que
aparezca no quiere decir que se esté viendo el visor.

## Deshacerlo

Cuando se abra el 3000 en el router (`TCP 3000 → 192.168.1.155:3000`):

1. Quitar las dos líneas temporales del compose de la Pi.
2. `docker compose up -d api monitor`.
3. En la licencia del hospital: `http://<IP pública de la sala>:3000/api`.

## Pendiente

- **El agente de monitorización** puede seguir enviando sus datos al `:8080` de la Pi.
  Si el panel deja de actualizarse, hay que cambiarlo a `:8081` en `~/roomfid/agente.yaml`.
- **`/api/config`** (`irfid/gestion-rfid-api/src/index.js`) devuelve la clave real a
  cualquier IP privada. Desde fuera tiene que responder 403. **Comprobarlo:** si devuelve
  la clave, hay que cerrar el 8080.
- **`www/api.html` se sirve sin autenticación y lleva una clave escrita dentro.** No es la
  del banco, pero sobra ahí.
- **El monitor se veía desde internet sin pedir nada** mientras estuvo en el 8080. En el
  8081 ya no está redirigido. Si vuelve al 8080, necesita autenticación delante.
