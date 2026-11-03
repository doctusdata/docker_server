"""Persistencia de la trazabilidad: aplica las reglas sobre la base, en una transaccion.

Recibe lotes de la cola durable (observaciones y cierres de ventana, en orden) y por
cada lote:
  * carga y bloquea los elementos afectados (SELECT ... FOR UPDATE, en orden de EPC
    para no provocar interbloqueos),
  * aplica ``reglas`` y guarda elemento + movimientos + alertas,
  * escribe el espejo legacy si esta activado,
  * con cada ventana cerrada intenta componer un ciclo y evaluar las ausencias.

Todo o nada: si algo falla, rollback y el lote sigue en la cola para reintentarse.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import astuple
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .. import db
from ..lectores import Lector, Lectores
from ..model import Observation, Registro, VentanaCerrada
from . import gestion, reglas
from .legacy import EspejoLegacy
from .reglas import Acceso, AlertaNueva, Elemento, Movimiento, Umbrales

log = logging.getLogger(__name__)

_COLS_ELEMENTO = ", ".join(Elemento.__dataclass_fields__)


def _jsonb(d: dict[str, Any] | None) -> Jsonb | None:
    return Jsonb(d, dumps=lambda o: json.dumps(o, default=str)) if d else None


class Procesador:
    def __init__(self, dsn: str, lectores: Lectores, umbrales: Umbrales,
                 espejo: EspejoLegacy | None, cobertura_minima: float,
                 cobertura_stock_minimo: int, acceso_dedup_s: float,
                 gestion_activo: bool = False, gestion_cobertura_minima: float = 0.9,
                 gestion_max_faltantes: int = 0) -> None:
        self._dsn = dsn
        self.lectores = lectores
        self.u = umbrales
        self.espejo = espejo
        self._cob_min = cobertura_minima
        self._cob_stock_min = cobertura_stock_minimo
        self._dedup = timedelta(seconds=acceso_dedup_s)
        # Reportar los ciclos a la plataforma de gestion. Apagado salvo que se configure.
        self._gestion = gestion_activo
        self._gestion_cob_min = gestion_cobertura_minima
        self._gestion_max_falt = gestion_max_faltantes
        self._cx: psycopg.Connection | None = None
        self._codigos: dict[UUID, str] = {}
        self.instalacion: str | None = None
        # Lectores que publican pero no estan en la topologia: diagnostico en campo.
        self.macs_desconocidas: dict[str, str] = {}
        self.stats: Counter[str] = Counter()

    # --- conexion ----------------------------------------------------------------------

    def conexion(self) -> psycopg.Connection:
        if self._cx is None or self._cx.closed:
            self._cx = db.connect(self._dsn)
            self.recargar()
        return self._cx

    def recargar(self) -> None:
        """Topologia (lectores, ubicaciones) y preparacion del espejo."""
        cx = self.conexion() if self._cx is None else self._cx
        self.lectores.cargar(cx)
        # Una MAC que ya esta en la topologia deja de ser desconocida.
        for mac in [m for m in self.macs_desconocidas if self.lectores.get(m)]:
            del self.macs_desconocidas[mac]
        with cx.cursor() as cur:
            cur.execute("SELECT id, codigo FROM traza.ubicacion")
            self._codigos = {r["id"]: r["codigo"] for r in cur.fetchall()}
            cur.execute("SELECT codigo FROM traza.instalacion")
            fila = cur.fetchone()
            self.instalacion = fila["codigo"] if fila else None
        cx.commit()
        if self.espejo:
            self.espejo.preparar(cx)

    def _descartar_conexion(self) -> None:
        try:
            if self._cx is not None:
                self._cx.close()
        finally:
            self._cx = None

    def cerrar(self) -> None:
        self._descartar_conexion()

    def _tx(self, fn, *args) -> Any:
        cx = self.conexion()
        try:
            with cx.cursor() as cur:
                res = fn(cur, *args)
            cx.commit()
            return res
        except Exception:
            try:
                cx.rollback()
            except Exception:
                pass
            self._descartar_conexion()
            raise

    # --- entrada principal --------------------------------------------------------------

    def procesar(self, registros: list[Registro]) -> int:
        """Procesa un lote de la cola en una sola transaccion. Lanza si falla."""
        if not registros:
            return 0
        return self._tx(self._procesar, registros)

    def _procesar(self, cur: psycopg.Cursor, registros: list[Registro]) -> int:
        tramo: list[Observation] = []
        for r in registros:
            if isinstance(r, VentanaCerrada):
                self._observaciones(cur, tramo)
                tramo = []
                self._ventana(cur, r)
            else:
                tramo.append(r)
        self._observaciones(cur, tramo)
        return len(registros)

    # --- carga / guardado ------------------------------------------------------------------

    def _cargar(self, cur: psycopg.Cursor, epcs: set[str]) -> dict[str, Elemento]:
        if not epcs:
            return {}
        cur.execute(
            f"SELECT {_COLS_ELEMENTO} FROM traza.elemento WHERE epc = ANY(%s) "
            "ORDER BY epc FOR UPDATE",
            (sorted(epcs),),
        )
        return {f["epc"]: Elemento.desde_fila(f) for f in cur.fetchall()}

    def _guardar(self, cur: psycopg.Cursor, elementos: list[Elemento],
                 movimientos: list[Movimiento], alertas: list[AlertaNueva]) -> None:
        campos = Elemento.CAMPOS_MUTABLES
        if elementos:
            sets = ", ".join(f"{c}=%s" for c in campos)
            cur.executemany(
                f"UPDATE traza.elemento SET {sets} WHERE epc=%s",
                [tuple(getattr(e, c) for c in campos) + (e.epc,) for e in elementos],
            )
        if movimientos:
            # Los terminales van de uno en uno porque hacen falta sus ids: ese id es la
            # clave de idempotencia del canal de subida, y sin el la gestion no podria
            # reconocer un reintento. Son uno por consumo, no un camino caliente.
            terminales = [m for m in movimientos if m.estado_destino in reglas.TERMINADOS]
            corrientes = [m for m in movimientos if m.estado_destino not in reglas.TERMINADOS]

            if corrientes:
                cur.executemany(
                    """INSERT INTO traza.movimiento
                           (epc, tipo, at, estado_origen, estado_destino, temporal_origen,
                            temporal_destino, ubicacion_origen_id, ubicacion_destino_id,
                            usuario_tarjeta, lector_id, ciclo_id, detalle)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [astuple(m)[:-1] + (_jsonb(m.detalle),) for m in corrientes],
                )
            for m in terminales:
                cur.execute(
                    """INSERT INTO traza.movimiento
                           (epc, tipo, at, estado_origen, estado_destino, temporal_origen,
                            temporal_destino, ubicacion_origen_id, ubicacion_destino_id,
                            usuario_tarjeta, lector_id, ciclo_id, detalle)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    astuple(m)[:-1] + (_jsonb(m.detalle),),
                )
                self._encolar_estado(cur, m, cur.fetchone()["id"])

            self.stats.update(f"mov_{m.tipo}" for m in movimientos)

        # **Lo que esta Pi ha decidido y la gestion todavia no sabe.**
        #
        # Mientras esta marca este puesta, el canal de bajada actualiza la ficha pero
        # deja el estado quieto. Sin ella hay un bucle entre los dos sistemas: la Pi ve
        # una ausencia, la pasa a en_transito, la bajada le devuelve 'almacen' porque la
        # gestion aun no se ha enterado, y la Pi se desdice de lo que acaba de ver.
        #
        # Se pone aqui, en la MISMA transaccion que el hecho, y la limpia quien lo
        # entrega: el ack del ciclo de inventario (almacen/gestion.py) o el del canal de
        # estados (gestion/estados.py).
        cambios_de_estado = {
            m.epc for m in movimientos if m.estado_origen != m.estado_destino
        }
        if cambios_de_estado:
            cur.execute(
                "UPDATE traza.elemento SET local_pendiente = true WHERE epc = ANY(%s)",
                (sorted(cambios_de_estado),),
            )
        for a in alertas:
            # El indice unico parcial evita duplicar una alerta abierta.
            cur.execute(
                """INSERT INTO traza.alerta (tipo, epc, ubicacion_id, detalle)
                   VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (a.tipo, a.epc, a.ubicacion_id, _jsonb(a.detalle)),
            )

    def _encolar_estado(self, cur: psycopg.Cursor, m: Movimiento, mov_id) -> None:
        """Deja un hecho terminal en la cola de subida. Ver sql/019_envio_estado.sql.

        Dentro de la transaccion del lote a proposito: si el lote se deshace, el envio
        se va con el. Es el mismo reparto que `_encolar_envio` para los ciclos.

        Sin `gestion_store_id` no se encola: significa que este elemento no vino de la
        gestion, y desde la fase 5 eso no deberia poder pasar. Se cuenta para que se
        vea en vez de perderse.
        """
        cur.execute(
            "SELECT gestion_store_id FROM traza.elemento WHERE epc = %s", (m.epc,)
        )
        fila = cur.fetchone()
        store = fila and fila["gestion_store_id"]
        if not store:
            self.stats["estado_sin_store"] += 1
            return

        detalle = m.detalle or {}
        cur.execute(
            """INSERT INTO traza.envio_estado
                      (movimiento_id, epc, gestion_store_id, estado, at,
                       paciente, incidencia, detalle)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (movimiento_id) DO NOTHING""",
            (
                mov_id, m.epc, store, m.estado_destino, m.at,
                detalle.get("patient"), detalle.get("incidencia"), _jsonb(detalle),
            ),
        )
        self.stats["estado_encolado"] += 1

    # --- observaciones -----------------------------------------------------------------------

    def _observaciones(self, cur: psycopg.Cursor, obs: list[Observation]) -> None:
        if not obs:
            return
        con_lector: list[tuple[Observation, Lector]] = []
        vistos: dict[UUID, datetime] = {}
        for o in obs:
            l = self.lectores.get(o.devmac)
            if l is None:
                self.stats["sin_lector"] += 1
                self.macs_desconocidas[o.devmac.lower()] = o.devid
                continue
            con_lector.append((o, l))
            vistos[l.id] = max(vistos.get(l.id, o.last_seen), o.last_seen)
        if vistos:
            cur.executemany(
                "UPDATE traza.lector SET last_seen_at = greatest(last_seen_at, %s) WHERE id=%s",
                [(t, i) for i, t in vistos.items()],
            )

        epcs = {o.epc for o, _ in con_lector}
        elementos = self._cargar(cur, epcs)

        # **El alta por lectura ya no existe.**
        #
        # Hasta la fase 5, un EPC leido que estuviera en "EPC_master" se convertia en
        # elemento aqui mismo. Eso hacia del maestro legacy una fuente de verdad mas: lo
        # que entrara alli —por la API Node, por el batch antiguo o a mano— pasaba a
        # existir en la traza sin que la gestion lo supiera, y el visor acababa
        # ensenando unidades que la gestion no tenia. Era el problema del 26/10.
        #
        # Ahora la Pi **solo incorpora lo que la gestion le dio para este almacen**, y
        # eso llega por el canal de bajada. Lo que se lee y no esta: se detecta, se
        # cuenta y se deja en traza.epc_desconocido, que para eso existe desde 010. No
        # se descarta ni se inventa.

        cambiados: dict[str, Elemento] = {}
        movs: list[Movimiento] = []
        alertas: list[AlertaNueva] = []
        tarjetas: list[tuple[Observation, Lector]] = []

        for o, l in sorted(con_lector, key=lambda x: x[0].last_seen):
            e = elementos.get(o.epc)
            if l.rol == "puerta":
                # En la puerta se leen carnets. Un articulo que pasa por ella no es un acceso.
                if e is None:
                    tarjetas.append((o, l))
                continue
            if e is None:
                self._desconocido(cur, o, l)
                continue
            if l.rol == "inventario":
                r = reglas.lectura_inventario(e, l.ubicacion_id, l.id, o.last_seen)
            else:
                r = reglas.lectura_papelera(e, l.ubicacion_id, l.id, o.last_seen,
                                            o.patient, o.operating_room,
                                            l.almacen_id, l.quirofano_codigo)
            elementos[o.epc] = cambiados[o.epc] = r.elemento
            movs.extend(r.movimientos)
            alertas.extend(r.alertas)
            if self.espejo:
                self._espejo_lectura(cur, r, l, o)

        self._guardar(cur, list(cambiados.values()), movs, alertas)
        if tarjetas:
            self._accesos(cur, tarjetas)
        self.stats["observaciones"] += len(obs)

    # `_crear` se retiro en la fase 5, con el alta por lectura. Creaba el elemento y su
    # movimiento de 'alta' para un EPC que apareciera en "EPC_master". Ahora los
    # elementos los crea el aplicador del canal de bajada (gestion/bajada.py), que es el
    # unico que sabe si la gestion nos dio esa etiqueta para este almacen.

    def _desconocido(self, cur: psycopg.Cursor, o: Observation, l: Lector) -> None:
        self.registrar_desconocido(cur, o.epc, l.ubicacion_id, o.first_seen, o.last_seen,
                                   o.read_count)

    # --- acceso para la API de papeleras ------------------------------------------------
    # Las sesiones de papelera entran por HTTP, no por la cola, pero aplican las mismas
    # reglas y escriben en las mismas tablas: se exponen las piezas en vez de duplicarlas.

    def cargar_elementos(self, cur: psycopg.Cursor, epcs: set[str]) -> dict[str, Elemento]:
        return self._cargar(cur, epcs)

    def guardar(self, cur: psycopg.Cursor, elementos: list[Elemento],
                movimientos: list[Movimiento], alertas: list[AlertaNueva]) -> None:
        self._guardar(cur, elementos, movimientos, alertas)

    def registrar_desconocido(self, cur: psycopg.Cursor, epc: str, ubicacion_id: UUID,
                              primera: datetime, ultima: datetime, lecturas: int) -> None:
        cur.execute(
            """INSERT INTO traza.epc_desconocido (epc, ubicacion_id, primera, ultima, lecturas)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (epc, ubicacion_id) DO UPDATE
                  SET ultima = greatest(traza.epc_desconocido.ultima, EXCLUDED.ultima),
                      lecturas = traza.epc_desconocido.lecturas + EXCLUDED.lecturas""",
            (epc, ubicacion_id, primera, ultima, lecturas),
        )
        self.stats["desconocidos"] += 1

    def _espejo_lectura(self, cur: psycopg.Cursor, r: reglas.Resultado, l: Lector,
                        o: Observation) -> None:
        e, tipos = r.elemento, set(r.tipos)
        assert self.espejo is not None
        if "consumo" in tipos:
            self.espejo.consumido(cur, e, l, o.antenna, o.rssi_max)
        elif tipos & {"entrada", "retorno", "traslado"}:
            codigo = self._codigos[e.ubicacion_id]
            self.espejo.stock(cur, e, codigo, l, o.antenna, o.rssi_max,
                              traslado="traslado" in tipos)
            self.espejo.almacen_master(cur, e.epc, codigo)
        elif e.estado == reglas.ALMACEN and l.rol == "inventario":
            self.espejo.refrescar(cur, e, self._codigos[e.ubicacion_id], o.antenna, o.rssi_max)

    # --- accesos (carnets en la puerta) ------------------------------------------------------

    def _accesos(self, cur: psycopg.Cursor, tarjetas: list[tuple[Observation, Lector]]) -> None:
        # `user_room` es del esquema legacy y en una instalacion nueva NO EXISTE: el
        # catalogo de personas y permisos lo tiene la gestion. Sin esta comprobacion,
        # una lectura de carnet en la puerta reventaba el lote entero con
        # "relation user_room does not exist" — y los accesos son justo lo que hay
        # que registrar aunque no se puedan autorizar.
        #
        # Sin la tabla, el acceso se anota SIN autorizar: queda la traza de quien
        # paso y cuando, que es lo que luego exculpa o acusa. Decidir si tenia
        # permiso es lo que se pierde, y eso tendra que bajar de la gestion cuando
        # exista ese canal.
        permisos: dict[str, list[dict]] = {}
        cur.execute("SELECT to_regclass('public.user_room') IS NOT NULL AS hay")
        if cur.fetchone()["hay"]:
            cur.execute(
                'SELECT epc, "user", door, state FROM user_room WHERE epc = ANY(%s)',
                (sorted({o.epc for o, _ in tarjetas}),),
            )
            for f in cur.fetchall():
                permisos.setdefault(f["epc"], []).append(f)
        else:
            self.stats["accesos_sin_catalogo"] += len(tarjetas)

        for o, l in tarjetas:
            at = o.first_seen
            cur.execute(
                """SELECT 1 FROM traza.acceso
                    WHERE tarjeta_epc=%s AND puerta_id=%s AND at > %s AND at <= %s LIMIT 1""",
                (o.epc, l.ubicacion_id, at - self._dedup, o.last_seen),
            )
            if cur.fetchone():
                continue
            filas = permisos.get(o.epc, [])
            propias = [f for f in filas if f["door"] == l.devid]
            nombre = next((f["user"] for f in propias + filas if f["user"]), None)
            autorizado = any(f["state"] == 1 for f in propias) if filas else None
            cur.execute(
                """INSERT INTO traza.acceso (tarjeta_epc, usuario_nombre, puerta_id, lector_id, at, autorizado)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (o.epc, nombre, l.ubicacion_id, l.id, at, autorizado),
            )
            if self.espejo:
                self.espejo.acceso(cur, l, o.epc, at, o.antenna, o.rssi_max)
            self.stats["accesos"] += 1

    # --- ventanas y ciclos ----------------------------------------------------------------------

    def _ventana(self, cur: psycopg.Cursor, v: VentanaCerrada) -> None:
        l = self.lectores.get(v.devmac)
        if l is None or l.rol != "inventario":
            return
        cur.execute(
            """INSERT INTO traza.ventana_lectura
                   (lector_id, ubicacion_id, inicio, fin, epcs_distintos, lecturas, valida,
                    motivo_invalida, origen, antenas)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (l.id, l.ubicacion_id, v.inicio, v.fin, v.epcs_distintos, v.lecturas, v.valida,
             v.motivo_invalida, v.origen, _jsonb(v.antenas)),
        )
        self.stats["ventanas_validas" if v.valida else "ventanas_invalidas"] += 1
        if v.valida and v.lecturas > 0 and v.antenas is not None:
            self._salud_antenas(cur, l, v.antenas)

        if not v.valida:
            # Una ventana mala invalida el ciclo en curso: mejor esperar al siguiente que
            # evaluar ausencias con datos incompletos.
            #
            # **Menos si solo es corta.** Tras cada `stop` llegan todavia observaciones del
            # agregador —la cola de la rafaga, ya en vuelo cuando se apago el lector— y
            # abren una ventana de 0 a 2 segundos con decenas de EPC. Es un artefacto del
            # apagado, no un ciclo estropeado, y dejarlo invalidar costaba la pasada
            # entera: `_cerrar_ciclo_invalido` asigna TODAS las ventanas pendientes al
            # ciclo descartado, asi que se llevaba por delante los 90 s del lector que
            # esperaba pareja. Medido el 3/11 al pasar a lectura en serie: una sola pasada
            # valida en once minutos, con las dos ventanas reales impecables.
            #
            # No hace falta que invalide para estar protegido: mas abajo un ciclo solo se
            # cierra cuando TODOS los lectores requeridos tienen ventana pendiente **y
            # valida**, asi que un lector cuya unica aportacion sea corta no deja cerrar
            # nada. Un `abort` si tiene que seguir matando el ciclo: ahi alguien ha
            # entrado, y entonces lo que ya se leyo tampoco describe la estanteria.
            if v.motivo_invalida != "corta":
                self._cerrar_ciclo_invalido(cur, l.ubicacion_id, v.fin,
                                            v.motivo_invalida or "invalida")
            return

        cur.execute(
            """SELECT lector_id, min(inicio) AS inicio FROM traza.ventana_lectura
                WHERE ubicacion_id=%s AND ciclo_id IS NULL AND valida
                GROUP BY lector_id""",
            (l.ubicacion_id,),
        )
        pendientes = {f["lector_id"]: f["inicio"] for f in cur.fetchall()}
        requeridos = {x.id for x in self.lectores.de_inventario(l.ubicacion_id)}
        if requeridos and requeridos <= pendientes.keys():
            self._cerrar_ciclo(cur, l, min(pendientes.values()), v.fin)

    def _salud_antenas(self, cur: psycopg.Cursor, l: Lector, antenas: dict[str, int]) -> None:
        """Tras una ventana valida CON lecturas: cada antena esperada que no ha leido suma
        una ventana sin lecturas; la que ha leido vuelve a 0. Con el lector apagado o sin
        lecturas no se juzga nada."""
        cur.executemany(
            """INSERT INTO traza.lector_antena (lector_id, antena, ventanas_sin_lecturas,
                                                lecturas_ultima_ventana)
               VALUES (%(l)s, %(a)s, %(sin)s, %(n)s)
               ON CONFLICT (lector_id, antena) DO UPDATE SET
                   ventanas_sin_lecturas = CASE WHEN %(n)s > 0 THEN 0
                       ELSE traza.lector_antena.ventanas_sin_lecturas + 1 END,
                   lecturas_ultima_ventana = %(n)s""",
            [{"l": l.id, "a": a, "n": antenas.get(str(a), 0),
              "sin": 0 if antenas.get(str(a), 0) > 0 else 1} for a in l.antenas],
        )

    def volcar_antenas(self, recuentos: list) -> int:
        """Vuelca el ContadorAntenas: ultima lectura y total por lector y antena."""
        filas = []
        for r in recuentos:
            l = self.lectores.get(r.devmac)
            if l is not None:
                filas.append((l.id, r.antena, r.ultima, r.lecturas))
        if not filas:
            return 0

        def _volcar(cur: psycopg.Cursor) -> int:
            cur.executemany(
                """INSERT INTO traza.lector_antena (lector_id, antena, ultima_lectura_at, lecturas_total)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (lector_id, antena) DO UPDATE SET
                       ultima_lectura_at = greatest(traza.lector_antena.ultima_lectura_at,
                                                    EXCLUDED.ultima_lectura_at),
                       lecturas_total = traza.lector_antena.lecturas_total + EXCLUDED.lecturas_total""",
                filas,
            )
            return len(filas)

        return self._tx(_volcar)

    def _nuevo_ciclo_id(self, cur: psycopg.Cursor) -> UUID:
        # Se pide antes de insertar el ciclo: los movimientos que genera lo referencian.
        cur.execute("SELECT uuidv7() AS id")
        return cur.fetchone()["id"]

    def _asignar_ventanas(self, cur: psycopg.Cursor, ubicacion_id: UUID, ciclo_id: UUID) -> None:
        cur.execute(
            "UPDATE traza.ventana_lectura SET ciclo_id=%s WHERE ubicacion_id=%s AND ciclo_id IS NULL",
            (ciclo_id, ubicacion_id),
        )

    def _cerrar_ciclo_invalido(self, cur: psycopg.Cursor, ubicacion_id: UUID,
                               cerrado_at: datetime, motivo: str) -> None:
        cur.execute(
            "SELECT min(inicio) AS inicio FROM traza.ventana_lectura WHERE ubicacion_id=%s AND ciclo_id IS NULL",
            (ubicacion_id,),
        )
        inicio = cur.fetchone()["inicio"] or cerrado_at
        cid = self._nuevo_ciclo_id(cur)
        cur.execute(
            """INSERT INTO traza.ciclo (id, ubicacion_id, inicio, cerrado_at, valido, motivo_invalido)
               VALUES (%s, %s, %s, %s, false, %s)""",
            (cid, ubicacion_id, inicio, cerrado_at, motivo),
        )
        self._asignar_ventanas(cur, ubicacion_id, cid)
        self.stats["ciclos_invalidos"] += 1

    def _cerrar_ciclo(self, cur: psycopg.Cursor, l: Lector, inicio: datetime,
                      cerrado_at: datetime) -> None:
        ub = l.ubicacion_id
        cur.execute(
            f"SELECT {_COLS_ELEMENTO} FROM traza.elemento "
            # Las dadas de baja por la gestion no son stock de este ciclo. Contarlas las
            # marca temporales en cada pasada y hunde la cobertura, que es justo lo que
            # decide si el ciclo vale y lo que se reporta a la gestion.
            "WHERE estado='almacen' AND baja_at IS NULL AND ubicacion_id=%s "
            "ORDER BY epc FOR UPDATE",
            (ub,),
        )
        stock = [Elemento.desde_fila(f) for f in cur.fetchall()]
        faltan = [e for e in stock
                  if e.ultima_lectura_at is None or e.ultima_lectura_at < inicio]
        presentes = len(stock) - len(faltan)

        cid = self._nuevo_ciclo_id(cur)
        motivo = None
        if len(stock) >= self._cob_stock_min and stock and presentes / len(stock) < self._cob_min:
            # Faltaria demasiado de golpe: es mas probable un fallo de lectura que una
            # retirada masiva. No se marca nada.
            motivo = "cobertura"
            log.warning("ciclo de %s descartado por cobertura: %d/%d vistos",
                        self._codigos.get(ub), presentes, len(stock))

        nuevos_temp = nuevos_circ = 0
        if motivo is None and faltan:
            acceso = self._ultimo_acceso(cur, l.puerta_id, cerrado_at)
            cambiados, movs = [], []
            for e in faltan:
                r = reglas.faltante_en_ciclo(e, cerrado_at, self.u, acceso, cid)
                cambiados.append(r.elemento)
                movs.extend(r.movimientos)
                nuevos_temp += "salida_temporal" in r.tipos
                nuevos_circ += reglas.MOV_TRANSITO in r.tipos
                if self.espejo:
                    self.espejo.temporal(cur, r.elemento, self._codigos[ub])
            self._guardar(cur, cambiados, movs, [])

        cur.execute(
            """INSERT INTO traza.ciclo (id, ubicacion_id, inicio, cerrado_at, valido, motivo_invalido,
                                        presentes, faltantes, nuevos_temporales, nuevos_circulantes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (cid, ub, inicio, cerrado_at, motivo is None, motivo, presentes, len(faltan),
             nuevos_temp, nuevos_circ),
        )
        self._asignar_ventanas(cur, ub, cid)
        # Los vistos son el complemento exacto de los que faltan sobre el mismo SELECT:
        # no hace falta otra consulta ni guardar los EPC durante la ventana.
        vistos = [e.epc for e in stock
                  if e.ultima_lectura_at is not None and e.ultima_lectura_at >= inicio]
        self._encolar_envio(cur, ub, cid, inicio, cerrado_at, vistos, len(stock), motivo)
        self.stats["ciclos_validos" if motivo is None else "ciclos_invalidos"] += 1
        log.info("ciclo %s cerrado: %d presentes, %d faltan, %d nuevos temporales, "
                 "%d nuevos circulantes%s", self._codigos.get(ub), presentes, len(faltan),
                 nuevos_temp, nuevos_circ, f" (INVALIDO: {motivo})" if motivo else "")

    def _encolar_envio(self, cur: psycopg.Cursor, ubicacion_id: UUID, ciclo_id: UUID,
                       inicio: datetime, cerrado_at: datetime, vistos: list[str],
                       stock: int, motivo: str | None) -> None:
        """Deja el ciclo en la cola de salida hacia la gestion.

        Dentro de la transaccion del lote a proposito: si el lote se deshace, este envio
        no llega a existir. El HTTP lo hace almacen/gestion.py, porque un fallo de red
        aqui haria rollback de toda la trazabilidad del lote.
        """
        if not self._gestion:
            return
        estado, descarte = gestion.decidir(len(vistos), stock, motivo,
                                           self._gestion_cob_min, self._gestion_max_falt)
        if estado is None:
            return
        if descarte:
            log.warning("ciclo de %s no se reporta a la gestion: %s",
                        self._codigos.get(ubicacion_id), descarte)
        cur.execute(
            """INSERT INTO traza.envio_gestion
                   (ciclo_id, ubicacion_id, ciclo_inicio, ciclo_cerrado_at, epcs, vistos,
                    stock, estado, ultimo_error)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (ciclo_id) DO NOTHING""",
            (ciclo_id, ubicacion_id, inicio, cerrado_at, Jsonb(vistos), len(vistos),
             stock, estado, descarte),
        )

    def _ultimo_acceso(self, cur: psycopg.Cursor, puerta_id: UUID | None,
                       hasta: datetime) -> Acceso | None:
        if puerta_id is None:
            return None
        cur.execute(
            """SELECT tarjeta_epc, usuario_nombre, at FROM traza.acceso
                WHERE puerta_id=%s AND at <= %s ORDER BY at DESC LIMIT 1""",
            (puerta_id, hasta),
        )
        f = cur.fetchone()
        return Acceso(f["tarjeta_epc"], f["usuario_nombre"], f["at"]) if f else None

    # --- temporizador -----------------------------------------------------------------------------

    def escalar_temporales(self, now: datetime) -> int:
        return self._tx(self._escalar, now)

    def _escalar(self, cur: psycopg.Cursor, now: datetime) -> int:
        limite = now - timedelta(minutes=self.u.minutos_para_circulante)
        cur.execute(
            f"SELECT {_COLS_ELEMENTO} FROM traza.elemento "
            # Igual que en _cerrar_ciclo: una unidad que la gestion ya dio de baja no
            # tiene que escalar a en_transito. Ya no es nuestra.
            "WHERE temporal AND estado='almacen' AND baja_at IS NULL "
            "AND temporal_desde <= %s ORDER BY epc FOR UPDATE",
            (limite,),
        )
        cambiados, movs = [], []
        for f in cur.fetchall():
            r = reglas.escalar_por_tiempo(Elemento.desde_fila(f), now, self.u)
            if r.movimientos:
                cambiados.append(r.elemento)
                movs.extend(r.movimientos)
        self._guardar(cur, cambiados, movs, [])
        return len(cambiados)
