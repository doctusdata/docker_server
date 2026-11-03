"""API de lectura del inventario: lo que ensena el visor. Solo GET.

**Por que una API y no /estado.** El arbol de /estado publica escalares, y eso vale para
las cifras de cabecera pero no para una tabla: hacen falta filas con EPC, nombre, estado
y fecha. El servidor de /estado esta hecho a mano, enruta por diccionario de rutas
exactas y descarta la query string (health.py), asi que no puede paginar ni filtrar. De
ahi un FastAPI, con el mismo patron que la API de papeleras: `crear_app` + `servir` como
tarea del runner.

**Por que aqui y no en el visor.** `traza` es el esquema de irfid, y es irfid quien lo
expone. El visor es un proxy sin base, que es su diseno; darle acceso directo a la base
lo acoplaria al esquema y obligaria a mover los dos repositorios a la vez cada vez que
cambie una columna.

**Las dos cifras, y por que son dos.** `/resumen` devuelve:

  * **inventario** — lo que hay en esta instalacion: ni usado, ni retirado, ni dado de
    baja por la gestion. Un fallo de antena NO lo mueve, porque `almacen` y `en_transito`
    estan los dos dentro: la histeresis reparte, no resta. Solo cambia por hechos —la
    papelera, una retirada, una baja de la gestion.
  * **en_almacen** — lo localizado en la ultima pasada, con su hora.

Ensenar una sola cifra obligaba a elegir entre un numero que baila y un numero que
miente. Son dos cosas distintas y se dicen las dos.

Sin autenticacion, igual que /estado: escucha en la red interna de la Pi y solo lee. La
API de papeleras si la exige porque ESCRIBE (aplica sesiones), que no es el caso.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field as CampoModelo

from .. import db
from ..config import Settings

log = logging.getLogger(__name__)

PREFIJO = "/api/inventario/v1"

# Los grupos que ensena el visor, y el filtro de cada uno. Las cuatro pestanas salen de
# la MISMA consulta cambiando solo esto: asi no pueden contradecirse entre si, que es
# justo lo que pasaba cuando cada cifra venia de una fuente distinta.
#
# El vocabulario de pantalla no es el de la base: 'consumido' y 'caducado' no son estados
# —la gestion solo acepta 'usado' y 'retirado'— sino presentacion sobre el estado mas
# `retirada_motivo`. Ver almacen/reglas.MOTIVO_POR_INCIDENCIA.
GRUPOS: dict[str, str] = {
    # El titular. Lo que esta aqui, localizado o no.
    "inventario": "e.baja_at IS NULL AND e.estado IN ('creado','almacen','en_transito')",
    "en_almacen": "e.baja_at IS NULL AND e.estado = 'almacen'",
    "en_transito": "e.baja_at IS NULL AND e.estado = 'en_transito'",
    # **En observacion: aparecen y desaparecen.** Estan en almacen y cuentan como dentro
    # —no se mueve su estado—, pero han fallado alguna pasada y todavia no las suficientes
    # para darlas por salidas. Es la clasificacion que pedia la sala: separar lo seguro de
    # lo que duda, porque mezclarlos es lo que hacia bailar la cifra de cabecera.
    #
    # Es un SUBCONJUNTO de `en_almacen`, no un estado aparte: si se restara, el total
    # dejaria de cuadrar y volveriamos a tener dos cifras que se contradicen.
    "observacion": "e.baja_at IS NULL AND e.estado = 'almacen' AND e.temporal",
    # Lo que la gestion nos dio y las antenas no han leido nunca.
    "entrada": "e.baja_at IS NULL AND e.estado = 'creado'",
    # Terminados. **No suman al inventario**: se ven un tiempo y se van.
    "terminados": "e.estado IN ('usado','retirado')",
    "de_baja": "e.baja_at IS NOT NULL",
}

# Cuantos dias de terminados se ensenan. Es retencion DE PANTALLA: el dato sigue en la
# tabla viva (archivo_dias_elemento, 180 por defecto) y en traza.elemento_todo, asi que
# cambiar esto no pierde nada y es reversible.
DIAS_TERMINADOS = 7

MAX_LIMITE = 500

_SQL_FILAS = """
SELECT e.epc,
       -- El nombre lo da la gestion por el canal de bajada. **Con respaldo**: si ese
       -- canal todavia no esta desplegado, `nombre` es NULL en toda la tabla, y una
       -- columna vacia es peor que un EPC. El visor completa con el catalogo heredado
       -- cuando puede; aqui al menos nunca va vacio.
       coalesce(nullif(trim(e.nombre), ''), e.epc)  AS nombre,
       e.nombre IS NOT NULL                         AS nombre_de_gestion,
       e.estado::text                               AS estado,
       e.temporal,
       e.retirada_motivo::text                      AS retirada_motivo,
       e.baja_at,
       e.baja_motivo,
       e.codigo_lote,
       e.fecha_caducidad,
       e.ultima_lectura_at,
       e.consumido_at,
       e.retirada_at,
       e.patient                                    AS paciente,
       e.operating_room                             AS quirofano,
       u.codigo                                     AS ubicacion,
       uo.codigo                                    AS origen,
       -- A quien se le atribuye la salida, y con cuanta confianza. **La confianza se
       -- ensena**: 'ventana' significa que el acceso cae entre la ultima vez que se vio
       -- la etiqueta y la deteccion de su ausencia, asi que es un candidato firme;
       -- 'ultimo' significa solo que fue la ultima persona que entro. Esconder esa
       -- diferencia convierte una pista en una acusacion.
       e.usuario_nombre                             AS usuario,
       e.usuario_tarjeta                            AS usuario_tarjeta,
       e.usuario_at,
       e.asignacion_confianza::text                 AS confianza,
       e.temporal_desde,
       e.ciclos_sin_leer,
       e.gracia_hasta
  FROM traza.elemento e
  LEFT JOIN traza.ubicacion u  ON u.id  = e.ubicacion_id
  LEFT JOIN traza.ubicacion uo ON uo.id = e.ubicacion_origen_id
"""


# Quien ha entrado, y si su entrada corto una pasada.
#
# **Esta tabla si esta viva.** La pantalla de accesos leia `User_readings`, que solo
# escribia el espejo legacy y lleva congelada desde que se retiro. `traza.acceso` la
# escribe la ingesta en cada paso de carnet.
#
# Y el cruce importa: desde que un acceso aborta el inventario, es la explicacion de una
# pasada que no se completa. Sin el, un almacen con trasiego parece averiado — la misma
# confusion que costo dos horas de diagnostico el 26/10, cuando se busco en
# traza.ventana_lectura un lector que por su rol no escribia alli.
#
# El criterio del cruce es que el acceso caiga DENTRO de la ventana de un ciclo abortado.
# No "poco despues": dentro, que es lo que de verdad lo relaciona.
_SQL_ACCESOS = """
SELECT a.at,
       a.tarjeta_epc,
       a.usuario_nombre,
       a.autorizado,
       u.codigo AS puerta,
       EXISTS (
           SELECT 1 FROM traza.ciclo c
            WHERE NOT c.valido
              AND c.motivo_invalido = 'abort'
              AND a.at BETWEEN c.inicio AND c.cerrado_at
       ) AS interrumpio
  FROM traza.acceso a
  LEFT JOIN traza.ubicacion u ON u.id = a.puerta_id
 WHERE a.at >= %(desde)s AND a.at < %(hasta)s
 ORDER BY a.at DESC
 LIMIT %(limite)s
"""


# Diagnostico de lectura, para la pantalla tecnica.
#
# **No hay log de lecturas individuales, y no es un olvido.** El agregador colapsa las
# decenas de lecturas por segundo de una misma etiqueta en una observacion —es la razon
# de que el sistema escale— y el RSSI se descarta desde que el espejo legacy esta
# apagado. Lo que persiste es el resumen por ventana, los contadores por antena y la
# ultima lectura de cada etiqueta. Con eso se diagnostica igual, y es lo que midio el
# informe del 26/10: la antena floja sale en `ventanas_sin_lecturas`, no en una traza
# de lecturas sueltas.
_SQL_VENTANAS = """
SELECT v.inicio, v.fin, v.epcs_distintos, v.lecturas, v.valida, v.motivo_invalida,
       v.origen, v.ciclo_id IS NOT NULL AS compuesta,
       l.devid, l.devip, l.rol::text AS rol, u.codigo AS ubicacion,
       round(extract(epoch FROM (v.fin - v.inicio))::numeric, 1) AS segundos
  FROM traza.ventana_lectura v
  JOIN traza.lector l    ON l.id = v.lector_id
  LEFT JOIN traza.ubicacion u ON u.id = v.ubicacion_id
 ORDER BY v.inicio DESC
 LIMIT %(limite)s
"""

# Por antena. `ventanas_sin_lecturas` es la cifra que delata una antena floja: ventanas
# validas seguidas en las que el lector leyo por otras y por esta no.
_SQL_ANTENAS = """
SELECT l.devid, l.devip, l.rol::text AS rol, a.antena,
       a.ultima_lectura_at, a.lecturas_total, a.lecturas_ultima_ventana,
       a.ventanas_sin_lecturas
  FROM traza.lector_antena a
  JOIN traza.lector l ON l.id = a.lector_id
 WHERE l.activo
 ORDER BY l.devid, l.devip, a.antena
"""

# Leidos y no entregados por la gestion. No se incorporan a proposito (decision del
# 26/10): aqui se ven para saber que hay material fisico que la gestion no conoce.
_SQL_DESCONOCIDOS = """
SELECT d.epc, d.primera, d.ultima, d.lecturas, u.codigo AS ubicacion
  FROM traza.epc_desconocido d
  LEFT JOIN traza.ubicacion u ON u.id = d.ubicacion_id
 ORDER BY d.ultima DESC
 LIMIT %(limite)s
"""


def _estado_pantalla(fila: dict) -> str:
    """El nombre que ve el usuario. No hay un estado por cada uno: son seis etiquetas
    sobre cinco estados mas el motivo de retirada."""
    estado = fila["estado"]
    if fila["baja_at"] is not None:
        return "de_baja"
    if estado == "usado":
        return "consumido"
    if estado == "retirado":
        return "caducado" if fila["retirada_motivo"] == "caducidad" else "retirado"
    if estado == "creado":
        return "entrada"
    return estado   # almacen | en_transito


class Datos:
    """Acceso a la base para la API. Conexion propia y serializada con un lock.

    Igual que en la API de papeleras: el visor hace pocas peticiones y cortas, asi que
    un lock es mas simple que un pool y suficiente. La conexion del Procesador no se
    toca: la usa la ingesta, que es el camino caliente.
    """

    def __init__(self, dsn: str, tz: str = "Europe/Madrid", umbral_ciclos: int = 3,
                 gracia_min: float = 30.0) -> None:
        self._dsn = dsn
        self._tz = tz
        # El umbral viaja al visor para que la tabla pueda escribir "1 de 15" en vez de
        # un "1" suelto. Sin denominador, la cifra no explica nada: lo que convence a
        # quien mira es ver cuanto falta para que el sistema de algo por salido.
        self._umbral = umbral_ciclos
        self._gracia_min = gracia_min
        self._cx: psycopg.Connection | None = None
        self._lock = asyncio.Lock()

    def _conexion(self) -> psycopg.Connection:
        if self._cx is None or self._cx.closed:
            self._cx = db.connect(self._dsn)
        return self._cx

    def hoy(self) -> date:
        """Hoy en la zona del hospital, que es quien lee la pantalla."""
        return datetime.now(timezone.utc).astimezone(ZoneInfo(self._tz)).date()

    def cerrar(self) -> None:
        if self._cx is not None and not self._cx.closed:
            self._cx.close()

    async def _leer(self, fn, *args):
        async with self._lock:
            return await asyncio.to_thread(self._leer_sync, fn, *args)

    def _leer_sync(self, fn, *args):
        cx = self._conexion()
        try:
            with cx.cursor() as cur:
                # Solo lectura explicito: esta API no escribe, y declararlo impide que
                # un error de programacion futuro lo haga.
                cur.execute("SET TRANSACTION READ ONLY")
                r = fn(cur, *args)
            cx.commit()
            return r
        except Exception:
            cx.rollback()
            raise

    async def _escribir(self, fn, *args):
        async with self._lock:
            return await asyncio.to_thread(self._escribir_sync, fn, *args)

    def _escribir_sync(self, fn, *args):
        """El unico camino de escritura, y a proposito uno solo.

        **Esta API era de solo lectura y ya no lo es.** El `SET TRANSACTION READ ONLY` de
        `_leer_sync` se puso justamente para que no pudiera escribir por descuido, asi que
        la excepcion no se cuela en el camino de lectura: va por su propia funcion, que se
        ve en el `grep` y que solo usa el reinicio de observacion. Si algun dia hace falta
        una segunda escritura, que pase por aqui y se decida entonces si esta API necesita
        autenticacion -- hoy no la tiene (ver la cabecera del modulo).
        """
        cx = self._conexion()
        try:
            with cx.cursor() as cur:
                r = fn(cur, *args)
            cx.commit()
            return r
        except Exception:
            cx.rollback()
            raise

    # --- resumen ------------------------------------------------------------------

    async def resumen(self) -> dict[str, Any]:
        return await self._leer(self._resumen)

    def _resumen(self, cur: psycopg.Cursor) -> dict[str, Any]:
        cuentas = {}
        for nombre, filtro in GRUPOS.items():
            extra = self._corte_terminados() if nombre == "terminados" else ""
            cur.execute(f"SELECT count(*) AS n FROM traza.elemento e WHERE {filtro}{extra}")
            cuentas[nombre] = cur.fetchone()["n"]

        # La ultima pasada valida, de la que sale la cifra de localizados y su hora.
        cur.execute(
            """SELECT DISTINCT ON (ubicacion_id) cerrado_at, presentes, faltantes
                 FROM traza.ciclo WHERE valido
                ORDER BY ubicacion_id, cerrado_at DESC""")
        pasadas = cur.fetchall()
        pasada = min(pasadas, key=lambda p: p["cerrado_at"]) if pasadas else None

        # Y si la ultima pasada NO valio, por que. 'abort' = alguien entro: eso no es
        # una averia, es el sistema negandose a sacar conclusiones con gente dentro.
        cur.execute(
            """SELECT DISTINCT ON (ubicacion_id) valido, motivo_invalido, cerrado_at
                 FROM traza.ciclo ORDER BY ubicacion_id, cerrado_at DESC""")
        ultimos = cur.fetchall()
        invalida = next((u for u in ultimos if not u["valido"]), None)

        return {
            "generado_at": datetime.now(timezone.utc).isoformat(),
            "cuentas": cuentas,
            "dias_terminados": DIAS_TERMINADOS,
            "umbral_ciclos": self._umbral,
            "gracia_devolucion_min": self._gracia_min,
            "pasada": {
                "at": pasada["cerrado_at"].isoformat() if pasada else None,
                "vistas": pasada["presentes"] if pasada else None,
                "faltantes": pasada["faltantes"] if pasada else None,
            },
            "ultima_pasada_invalida": {
                "motivo": invalida["motivo_invalido"],
                "at": invalida["cerrado_at"].isoformat(),
            } if invalida else None,
        }

    def _corte_terminados(self) -> str:
        return (" AND coalesce(e.consumido_at, e.retirada_at, e.modificado_at) >= "
                f"now() - interval '{DIAS_TERMINADOS} days'")

    # --- diagnostico de lectura ---------------------------------------------------

    async def diagnostico(self, limite: int) -> dict[str, Any]:
        return await self._leer(self._diagnostico, limite)

    def _diagnostico(self, cur: psycopg.Cursor, limite: int) -> dict[str, Any]:
        def filas(sql: str, **kw) -> list[dict]:
            cur.execute(sql, kw)
            return [
                {k: (v.isoformat() if isinstance(v, datetime) else
                     float(v) if isinstance(v, Decimal) else
                     str(v) if isinstance(v, UUID) else v)
                 for k, v in f.items()}
                for f in cur.fetchall()
            ]

        return {
            "generado_at": datetime.now(timezone.utc).isoformat(),
            "ventanas": filas(_SQL_VENTANAS, limite=limite),
            "antenas": filas(_SQL_ANTENAS),
            "desconocidos": filas(_SQL_DESCONOCIDOS, limite=limite),
        }

    # --- accesos ------------------------------------------------------------------

    async def accesos(self, dia: date, limite: int) -> dict[str, Any]:
        return await self._leer(self._accesos, dia, limite)

    def _accesos(self, cur: psycopg.Cursor, dia: date, limite: int) -> dict[str, Any]:
        # El dia es el del hospital, no el UTC: la sesion trabaja en UTC (db.connect) y
        # un corte a medianoche UTC parte el dia a las 02:00 de Madrid en verano.
        tz = ZoneInfo(self._tz)
        desde = datetime(dia.year, dia.month, dia.day, tzinfo=tz)
        hasta = desde + timedelta(days=1)
        cur.execute(_SQL_ACCESOS, {"desde": desde, "hasta": hasta, "limite": limite})
        filas = [
            {**{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in f.items()}}
            for f in cur.fetchall()
        ]
        return {"dia": dia.isoformat(), "accesos": filas,
                "interrumpieron": sum(1 for f in filas if f["interrumpio"])}

    # --- filas --------------------------------------------------------------------

    async def elementos(self, grupo: str, limite: int, desplazamiento: int,
                        busqueda: str | None) -> dict[str, Any]:
        return await self._leer(self._elementos, grupo, limite, desplazamiento, busqueda)

    def _elementos(self, cur: psycopg.Cursor, grupo: str, limite: int,
                   desplazamiento: int, busqueda: str | None) -> dict[str, Any]:
        filtro = GRUPOS[grupo]
        if grupo == "terminados":
            filtro += self._corte_terminados()
        params: list[Any] = []
        if busqueda:
            # Sobre EPC y nombre, que es lo que se ve en la tabla. Parametrizado: el
            # texto viene del navegador.
            filtro += " AND (e.epc ILIKE %s OR e.nombre ILIKE %s)"
            patron = f"%{busqueda.strip()}%"
            params += [patron, patron]

        cur.execute(f"SELECT count(*) AS n FROM traza.elemento e WHERE {filtro}", params)
        total = cur.fetchone()["n"]

        # Los terminados por cuando terminaron (lo mas reciente primero, que es lo que
        # alguien quiere ver); el resto por la ultima lectura. NULLS LAST para que lo
        # que nunca se ha leido no encabece la tabla.
        orden = ("e.consumido_at DESC NULLS LAST" if grupo == "terminados"
                 else "e.ultima_lectura_at DESC NULLS LAST")
        cur.execute(
            f"{_SQL_FILAS} WHERE {filtro} ORDER BY {orden}, e.epc LIMIT %s OFFSET %s",
            params + [limite, desplazamiento],
        )
        filas = [self._fila(f) for f in cur.fetchall()]
        return {"total": total, "limite": limite, "desplazamiento": desplazamiento,
                "elementos": filas}

    # --- devolver al almacen ----------------------------------------------------------

    async def devolver_al_almacen(self, grupo: str, epcs: list[str] | None,
                                  todas: bool) -> dict[str, Any]:
        return await self._escribir(self._devolver_al_almacen, grupo, epcs, todas)

    def _devolver_al_almacen(self, cur: psycopg.Cursor, grupo: str,
                             epcs: list[str] | None, todas: bool) -> dict[str, Any]:
        """Declara que la etiqueta esta en su sitio: la devuelve al almacen a cero.

        **Hace lo mismo que una reaparicion**, que es lo unico defendible: `reglas`
        considera localizado un elemento poniendo `temporal=false`, `temporal_desde=NULL`
        y `ciclos_sin_leer=0` (`_localizado`), y ademas **borra la atribucion de
        usuario**. Dejar la atribucion puesta seria lo peor de los dos mundos: declarar
        que la etiqueta esta donde debe y conservar el nombre de quien supuestamente se
        la llevo.

        Vale para los dos grupos de la duda:

          * **observacion** (`almacen` + `temporal`) -- solo hay que apagar `temporal`, y
            con eso el elemento sale de la lista.
          * **en_transito** -- hay que devolver tambien el estado y la ubicacion. Un
            `en_transito` tiene `ubicacion_id` a NULL *a proposito* (no se sabe donde
            esta) y guarda de donde salio en `ubicacion_origen_id`; es de ahi de donde
            vuelve. **Sin ubicacion de origen no se toca**: la restriccion
            `elemento_almacen_con_ubicacion` prohibe estar en almacen sin ubicacion, y
            forzarlo seria cambiar un dato dudoso por uno imposible. Esos EPC se
            devuelven en `sin_ubicacion` para que la pantalla lo pueda decir.

        Si la siguiente pasada vuelve a no verlo, reaparece con 1 de N: no se pierde nada,
        se vuelve a empezar a contar.

        Queda en el historial. Cada devolucion deja un movimiento `ajuste_manual` con el
        estado de origen **real** -- por eso se leen las filas antes de tocarlas, con
        `FOR UPDATE`: un `RETURNING` devuelve los valores nuevos, y anotar
        `en_transito -> en_transito` falsearia justo lo que se quiere auditar.
        """
        if grupo not in GRUPOS_DEVOLVIBLES:
            raise ValueError(f"grupo no devolvible: {grupo}")

        filtro = GRUPOS[grupo]
        params: list[Any] = []
        if not todas:
            filtro += " AND e.epc = ANY(%s)"
            params.append(list(epcs or []))

        cur.execute(
            f"""SELECT e.epc, e.estado, e.temporal, e.ubicacion_id, e.ubicacion_origen_id,
                       e.ciclos_sin_leer
                  FROM traza.elemento e
                 WHERE {filtro}
                   FOR UPDATE""",
            params,
        )
        antes = cur.fetchall()
        if not antes:
            return {"devueltas": 0, "epcs": [], "sin_ubicacion": []}

        sin_ubicacion = [f["epc"] for f in antes
                         if (f["ubicacion_id"] or f["ubicacion_origen_id"]) is None]
        validas = [f for f in antes
                   if (f["ubicacion_id"] or f["ubicacion_origen_id"]) is not None]
        if not validas:
            return {"devueltas": 0, "epcs": [], "sin_ubicacion": sin_ubicacion}

        # **La gracia es lo que hace util al boton.** Sin ella la devolucion compraba una
        # sola pasada de tregua: lo que falla siempre volvia a transito a los tres minutos.
        # Y al contrario, devolver algo que SI estaba fuera reiniciaba su cuenta y
        # retrasaba la deteccion real un umbral entero. Con `gracia_hasta` se aplaza la
        # conclusion sin borrar la evidencia: el contador vuelve a subir desde cero pero no
        # se escala hasta que expire. Ver reglas._escalar y 022_gracia_devolucion.sql.
        gracia = (f"now() + interval '{self._gracia_min} minutes'"
                  if self._gracia_min > 0 else "NULL")
        cur.execute(
            f"""UPDATE traza.elemento e
                  SET estado = 'almacen',
                      ubicacion_id = COALESCE(e.ubicacion_id, e.ubicacion_origen_id),
                      temporal = false,
                      temporal_desde = NULL,
                      ciclos_sin_leer = 0,
                      gracia_hasta = {gracia},
                      usuario_tarjeta = NULL,
                      usuario_nombre = NULL,
                      usuario_at = NULL,
                      asignacion_confianza = NULL
                WHERE e.epc = ANY(%s)
            RETURNING e.epc, e.gracia_hasta""",
            [[f["epc"] for f in validas]],
        )
        hasta = {f["epc"]: f["gracia_hasta"] for f in cur.fetchall()}
        cur.executemany(
            """INSERT INTO traza.movimiento
                      (epc, at, tipo, estado_origen, estado_destino,
                       temporal_origen, temporal_destino,
                       ubicacion_origen_id, ubicacion_destino_id, detalle)
               VALUES (%s, now(), 'ajuste_manual', %s, 'almacen', %s, false, %s, %s, %s)""",
            [(f["epc"], f["estado"], f["temporal"], f["ubicacion_id"],
              f["ubicacion_id"] or f["ubicacion_origen_id"],
              Jsonb({"accion": "devolver_al_almacen", "origen": "visor",
                     "grupo": grupo, "alcance": "todas" if todas else "seleccion",
                     "ciclos_sin_leer": f["ciclos_sin_leer"],
                     "gracia_hasta": hasta.get(f["epc"])}))
             for f in validas],
        )
        return {"devueltas": len(validas), "epcs": [f["epc"] for f in validas],
                "sin_ubicacion": sin_ubicacion,
                "gracia_min": self._gracia_min}

    def _fila(self, f: dict) -> dict[str, Any]:
        d = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in f.items()}
        d["fecha_caducidad"] = f["fecha_caducidad"].isoformat() if f["fecha_caducidad"] else None
        d["estado_pantalla"] = _estado_pantalla(f)
        return d


# Los dos grupos de los que se puede devolver algo al almacen. **No mas**: `terminados` y
# `de_baja` son hechos (se consumio, la gestion lo dio de baja), no dudas de lectura, y
# deshacerlos a mano desde el visor seria otra cosa muy distinta.
GRUPOS_DEVOLVIBLES = ("observacion", "en_transito")


class Devolucion(BaseModel):
    """Que etiquetas devolver al almacen. O una lista, o todas las de un grupo.

    `todas` tiene que venir explicito porque una lista vacia **no** significa "todas":
    significa que el navegador mando una seleccion vacia, y en ese caso lo correcto es no
    tocar nada.
    """

    epcs: list[str] = CampoModelo(default_factory=list, max_length=2000)
    todas: bool = False
    grupo: str = "observacion"


def crear_app(s: Settings, datos: Datos | None = None) -> FastAPI:
    app = FastAPI(title="API de inventario RoomFID", docs_url=None, redoc_url=None)
    d = datos or Datos(s.pg_dsn, s.tz_presentacion, s.ciclos_para_circulante,
                       s.gracia_devolucion_min)
    app.state.datos = d

    @app.get(PREFIJO + "/resumen")
    async def resumen() -> dict[str, Any]:
        return await d.resumen()

    # **La unica ruta que escribe.** Devuelve al almacen lo que el sistema tiene por
    # dudoso o por salido, cuando quien mira sabe que la etiqueta esta ahi y lo que falla
    # es la lectura. Es un POST y no un GET justamente por eso: un GET que cambia datos
    # lo acaba disparando cualquier cosa que precargue enlaces.
    #
    # **Llega a `en_transito`, no solo a `observacion`, y es el motivo de existir.** Un
    # falso positivo ya escalado era lo unico que no se podia corregir desde la pantalla:
    # habia que esperar a que una antena volviera a leerlo. Con la sombra medida de hasta
    # 21 minutos en etiquetas presentes, eso es demasiado rato ensenando una salida que no
    # ha ocurrido.
    @app.post(PREFIJO + "/elementos/devolver")
    async def devolver(cuerpo: Devolucion) -> dict[str, Any]:
        if cuerpo.grupo not in GRUPOS_DEVOLVIBLES:
            raise HTTPException(400, f"grupo no devolvible: {cuerpo.grupo}")
        if not cuerpo.todas and not cuerpo.epcs:
            raise HTTPException(400, "hay que indicar `epcs` o `todas`")
        r = await d.devolver_al_almacen(cuerpo.grupo, cuerpo.epcs, cuerpo.todas)
        log.info("devueltas al almacen desde %s: %d (%s)%s", cuerpo.grupo, r["devueltas"],
                 "todas" if cuerpo.todas else "seleccion",
                 f"; {len(r['sin_ubicacion'])} sin ubicacion de origen"
                 if r["sin_ubicacion"] else "")
        return r

    @app.get(PREFIJO + "/elementos")
    async def elementos(
        grupo: str = Query("inventario", pattern="^(" + "|".join(GRUPOS) + ")$"),
        limite: int = Query(100, ge=1, le=MAX_LIMITE),
        desplazamiento: int = Query(0, ge=0),
        busqueda: str | None = Query(None, max_length=120),
    ) -> dict[str, Any]:
        return await d.elementos(grupo, limite, desplazamiento, busqueda)

    @app.get(PREFIJO + "/accesos")
    async def accesos(
        dia: date | None = Query(None, description="Dia del hospital. Por omision, hoy."),
        limite: int = Query(500, ge=1, le=MAX_LIMITE),
    ) -> dict[str, Any]:
        return await d.accesos(dia or d.hoy(), limite)

    @app.get(PREFIJO + "/diagnostico")
    async def diagnostico(
        limite: int = Query(100, ge=1, le=MAX_LIMITE),
    ) -> dict[str, Any]:
        return await d.diagnostico(limite)

    return app


async def servir(s: Settings) -> None:
    """Arranca la API. Tarea del runner, junto al resto."""
    if not s.inventario_port:
        return
    import uvicorn

    app = crear_app(s)
    config = uvicorn.Config(app, host="0.0.0.0", port=s.inventario_port,
                            log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    log.info("api de inventario en :%d%s", s.inventario_port, PREFIJO)
    try:
        await server.serve()
    finally:
        app.state.datos.cerrar()
