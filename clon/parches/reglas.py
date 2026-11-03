"""Maquina de estados de los elementos. PURA: sin base de datos ni reloj.

**El vocabulario es el de la gestion**, no uno propio:

    creado -> almacen <-> en_transito -> usado
                                      -> retirado

Decision del 26/10/2026: la gestion es la unica fuente del catalogo de estados y aqui
se usan sus codigos. Antes habia dos juegos de nombres para lo mismo
(stock/almacen, circulante/en_transito, consumido/usado), y eso obliga a traducir en
cada frontera y a buscar "cosas que son lo mismo" cada vez que algo no cuadra.

Aparte del estado hay dos cosas ortogonales:

  * el flag ``temporal`` — se ha detectado la salida pero todavia no se da por perdida.
    **Es lo que impide reportar ``en_transito`` al primer fallo**: una ausencia tiene que
    repetirse (por ciclos o por tiempo) para que escale;
  * ``retirada_motivo`` — por que se retiro (caducidad, alerta sanitaria, destruccion).
    Ahora el estado ``retirado`` dice "terminado por un problema" y este campo dice cual.

Y la regla de la papelera, de la misma decision: una sesion **con incidencia** deja la
unidad en ``retirado``; sin incidencia, en ``usado``.

Cada funcion recibe el elemento y el hecho, y devuelve un ``Resultado`` con el elemento
modificado (una copia), los movimientos para el historial y las alertas a generar. El
llamante (repo.py) lo persiste todo en una transaccion.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

# Claves de ubicacion, lector y ciclo (UUID v7 en base).
Id = UUID

CREADO, ALMACEN, EN_TRANSITO, USADO, RETIRADO = (
    "creado", "almacen", "en_transito", "usado", "retirado",
)

# Los dos estados en los que una unidad ha terminado su vida. Se agrupan porque casi
# todas las comprobaciones son "ya termino", no "termino de una forma concreta".
TERMINADOS = (USADO, RETIRADO)

# Tipo de movimiento de la escalada. Antes se llamaba "circulante", como el estado;
# ese valor sigue en el enum porque los movimientos ya escritos lo llevan, pero lo que
# se emite desde 018 es este.
MOV_TRANSITO = "transito"

# Lo que la papelera puede decir y NO es una incidencia. El operario declaro que la
# fecha del catalogo estaba mal, y su criterio gana: eso es un consumo normal, no una
# retirada. Esta decidido asi desde que existe el terminal (ver papelera/proceso.py).
NO_ES_INCIDENCIA = ("anulada",)

# De lo que dice la papelera al motivo de traza.motivo_retirada.
#
# El terminal tiene un vocabulario cerrado de tres valores, con CHECK en su propia base
# (papelerIA, tabla `lectura`), y hasta ahora los tres se colapsaban en un booleano: los
# tres acababan en 'retirado' sin distinguir cual. El matiz solo sobrevivia en el detalle
# del movimiento, de donde no se puede consultar. Los huecos del enum ya estaban hechos
# desde 010 y nadie los rellenaba.
#
# **No se inventa un motivo cuando no se sabe.** El kiosco permite texto libre, y de ahi
# solo se puede concluir que hubo una incidencia: el estado queda en 'retirado' y el
# motivo a NULL, con el texto crudo en el detalle del movimiento. Poner 'destruccion' por
# defecto seria afirmar algo que nadie ha dicho.
MOTIVO_POR_INCIDENCIA = {
    "caducado": "caducidad",
    "alerta_sanitaria": "alerta_sanitaria",
    "desechado": "destruccion",
}


def motivo_de_incidencia(incidencia: Any) -> str | None:
    """El motivo de retirada que corresponde a lo que dijo la papelera, o None."""
    texto = str(incidencia).strip().lower() if incidencia is not None else ""
    return MOTIVO_POR_INCIDENCIA.get(texto)


@dataclass(slots=True)
class Elemento:
    epc: str
    estado: str = CREADO
    temporal: bool = False
    temporal_desde: datetime | None = None
    ciclos_sin_leer: int = 0
    # Hasta cuando una devolucion manual del visor protege a este elemento de escalar.
    # Es una afirmacion con caducidad ("esta aqui, lo he comprobado"), no una lectura:
    # mientras dura, `ciclos_sin_leer` SIGUE subiendo. Ver 022_gracia_devolucion.sql.
    gracia_hasta: datetime | None = None
    ubicacion_id: Id | None = None
    ubicacion_origen_id: Id | None = None
    ultima_lectura_at: datetime | None = None
    ultimo_lector_id: Id | None = None
    usuario_tarjeta: str | None = None
    usuario_nombre: str | None = None
    usuario_at: datetime | None = None
    asignacion_confianza: str | None = None
    retirada_motivo: str | None = None
    retirada_at: datetime | None = None
    retirada_por: str | None = None
    consumido_at: datetime | None = None
    consumido_lector_id: Id | None = None
    patient: str | None = None
    operating_room: str | None = None

    CAMPOS_MUTABLES = (
        "estado", "temporal", "temporal_desde", "ciclos_sin_leer", "gracia_hasta",
        "ubicacion_id",
        "ubicacion_origen_id", "ultima_lectura_at", "ultimo_lector_id", "usuario_tarjeta",
        "usuario_nombre", "usuario_at", "asignacion_confianza", "consumido_at",
        "consumido_lector_id", "patient", "operating_room",
        # Los pone `lectura_papelera` cuando la sesion trae incidencia. Sin estar aqui,
        # repo.py no los guardaria: el UPDATE de _guardar se construye sobre esta tupla,
        # y el estado 'retirado' se quedaria sin fecha y sin motivo.
        "retirada_at",
        "retirada_motivo",
    )

    @classmethod
    def desde_fila(cls, fila: dict[str, Any]) -> "Elemento":
        campos = {k: fila[k] for k in cls.__dataclass_fields__ if k in fila}
        return cls(**campos)


@dataclass(slots=True)
class Movimiento:
    epc: str
    tipo: str
    at: datetime
    estado_origen: str | None
    estado_destino: str | None
    temporal_origen: bool | None
    temporal_destino: bool | None
    ubicacion_origen_id: Id | None
    ubicacion_destino_id: Id | None
    usuario_tarjeta: str | None = None
    lector_id: Id | None = None
    ciclo_id: Id | None = None
    detalle: dict[str, Any] | None = None


@dataclass(slots=True)
class AlertaNueva:
    tipo: str
    epc: str | None
    ubicacion_id: Id | None
    detalle: dict[str, Any] | None = None


@dataclass(slots=True)
class Resultado:
    elemento: Elemento
    movimientos: list[Movimiento] = field(default_factory=list)
    alertas: list[AlertaNueva] = field(default_factory=list)

    @property
    def tipos(self) -> list[str]:
        return [m.tipo for m in self.movimientos]


@dataclass(frozen=True, slots=True)
class Umbrales:
    ciclos_para_circulante: int = 3
    minutos_para_circulante: float = 30.0


@dataclass(frozen=True, slots=True)
class Acceso:
    """Ultimo acceso registrado en la puerta del almacen antes de detectar la salida."""

    tarjeta: str
    nombre: str | None
    at: datetime


def _mov(antes: Elemento, despues: Elemento, tipo: str, at: datetime, **kw) -> Movimiento:
    return Movimiento(
        epc=despues.epc, tipo=tipo, at=at,
        estado_origen=antes.estado, estado_destino=despues.estado,
        temporal_origen=antes.temporal, temporal_destino=despues.temporal,
        ubicacion_origen_id=antes.ubicacion_id, ubicacion_destino_id=despues.ubicacion_id,
        **kw,
    )


def _localizado(e: Elemento) -> None:
    """El elemento ya se sabe donde esta: fuera temporal y asignacion."""
    e.temporal = False
    e.temporal_desde = None
    e.ciclos_sin_leer = 0
    # La gracia era una afirmacion a falta de lectura. Con la lectura sobra, y dejarla
    # puesta protegeria una ausencia posterior que ya nadie ha afirmado.
    e.gracia_hasta = None
    e.usuario_tarjeta = e.usuario_nombre = None
    e.usuario_at = None
    e.asignacion_confianza = None


def _refrescar_lectura(e: Elemento, at: datetime, lector_id: Id) -> None:
    if e.ultima_lectura_at is None or at >= e.ultima_lectura_at:
        e.ultima_lectura_at = at
        e.ultimo_lector_id = lector_id


# --- Lecturas positivas ------------------------------------------------------------


def lectura_inventario(e0: Elemento, ubicacion_id: Id, lector_id: Id, at: datetime) -> Resultado:
    """El elemento se ha leido en un almacen."""
    e = copy.copy(e0)
    r = Resultado(e)
    _refrescar_lectura(e, at, lector_id)

    if e0.retirada_motivo:
        r.alertas.append(AlertaNueva(
            "retirado_detectado", e.epc, ubicacion_id,
            {"motivo": e0.retirada_motivo, "retirada_at": e0.retirada_at},
        ))

    if e0.estado in TERMINADOS:
        # No deberia volver a leerse. No se "resucita": se avisa y se deja rastro, una
        # sola vez por ubicacion.
        r.alertas.append(AlertaNueva("consumido_detectado", e.epc, ubicacion_id,
                                     {"consumido_at": e0.consumido_at}))
        if e0.ubicacion_id != ubicacion_id:
            e.ubicacion_id = ubicacion_id
            r.movimientos.append(_mov(e0, e, "anomalia", at, lector_id=lector_id,
                                      detalle={"causa": "consumido_detectado"}))
        return r

    if e0.estado == CREADO:
        e.estado, e.ubicacion_id = ALMACEN, ubicacion_id
        _localizado(e)
        r.movimientos.append(_mov(e0, e, "entrada", at, lector_id=lector_id))
        return r

    if e0.estado == ALMACEN and e0.ubicacion_id == ubicacion_id:
        if e0.temporal:
            _localizado(e)
            r.movimientos.append(_mov(e0, e, "retorno", at, lector_id=lector_id,
                                      usuario_tarjeta=e0.usuario_tarjeta))
        return r

    # Aparece en otro almacen (stock en B) o vuelve de circular.
    tipo = "traslado"
    if e0.estado == EN_TRANSITO and e0.ubicacion_origen_id == ubicacion_id:
        tipo = "retorno"
    e.estado, e.ubicacion_id = ALMACEN, ubicacion_id
    _localizado(e)
    r.movimientos.append(_mov(e0, e, tipo, at, lector_id=lector_id,
                              usuario_tarjeta=e0.usuario_tarjeta))
    return r


def es_incidencia(incidencia: Any) -> bool:
    """Si lo que dijo la papelera cuenta como incidencia.

    Libre y minuscula a proposito: es la frontera entre ``usado`` y ``retirado``, y
    conviene poder leerla y probarla sola.

    ``"anulada"`` **no** cuenta: significa que el operario declaro que la fecha de
    caducidad del catalogo estaba mal, y su criterio gana. Eso es un consumo normal, no
    una retirada.
    """
    # Se normaliza ANTES de comprobar si esta vacia: una cadena de espacios es
    # truthy en Python, y sin esto un campo en blanco del terminal retiraria la
    # unidad. El terminal es una pantalla en kiosco y manda lo que le teclean.
    texto = str(incidencia).strip().lower() if incidencia is not None else ""
    if not texto:
        return False
    return texto not in NO_ES_INCIDENCIA


def lectura_papelera(e0: Elemento, ubicacion_id: Id, lector_id: Id, at: datetime,
                     patient: str | None = None, operating_room: str | None = None,
                     almacen_id: Id | None = None, quirofano: str | None = None,
                     incidencia: str | None = None) -> Resultado:
    """El elemento se ha leido en una papelera: ha terminado su vida.

    **Con incidencia termina en ``retirado``; sin incidencia, en ``usado``.** Es la
    decision del 26/10 y la razon de que el parametro llegue hasta aqui: antes la
    incidencia solo acababa en el espejo legacy y en el detalle del movimiento, asi que
    el estado no la reflejaba y la gestion no podia distinguir una unidad gastada de una
    retirada por un problema.

    Las papeleras son la salida de los quirofanos: si la trama no dice de que quirofano
    viene (operating_room), se toma el de la papelera. ``almacen_id`` es el almacen al que
    pertenece la papelera; si el elemento salio de otro, se deja constancia.
    """
    e = copy.copy(e0)
    r = Resultado(e)
    _refrescar_lectura(e, at, lector_id)
    if e0.estado in TERMINADOS:
        return r
    usuario = e0.usuario_tarjeta
    con_incidencia = es_incidencia(incidencia)
    e.estado = RETIRADO if con_incidencia else USADO
    e.ubicacion_id = ubicacion_id
    e.temporal, e.temporal_desde, e.ciclos_sin_leer = False, None, 0
    e.gracia_hasta = None   # termino: ya no hay ausencia que proteger
    # `consumido_at` se rellena en los dos casos: significa "cuando termino", y
    # renombrarlo obligaria a tocar el espejo legacy, el visor y la API Node, que son
    # otros repositorios. El estado ya distingue COMO termino.
    e.consumido_at, e.consumido_lector_id = at, lector_id
    if con_incidencia:
        # `retirada_motivo` dice POR QUE. La papelera SI lo sabe —manda 'caducado',
        # 'alerta_sanitaria' o 'desechado'— y hasta ahora se tiraba aqui. Si lo que trae
        # no esta en ese vocabulario (el kiosco admite texto libre), el motivo queda a
        # NULL: consta que hubo incidencia, y el texto crudo sigue en el detalle.
        e.retirada_at = at
        e.retirada_motivo = motivo_de_incidencia(incidencia) or e0.retirada_motivo
    e.patient = patient or e0.patient
    e.operating_room = operating_room or e0.operating_room or quirofano
    origen = e0.ubicacion_origen_id if e0.estado == EN_TRANSITO or e0.temporal else e0.ubicacion_id
    detalle: dict[str, Any] = {k: v for k, v in (("patient", e.patient),
                                                 ("operating_room", e.operating_room),
                                                 ("quirofano", quirofano),
                                                 ("incidencia", incidencia)) if v}
    if almacen_id is not None:
        detalle["almacen_id"] = almacen_id
        if origen is not None and origen != almacen_id:
            detalle["otro_almacen"] = True
    # Se conserva el usuario asignado: es quien lo saco del almacen.
    r.movimientos.append(_mov(
        e0, e, "consumo", at, lector_id=lector_id, usuario_tarjeta=usuario, detalle=detalle,
    ))
    return r


# --- Lecturas negativas -------------------------------------------------------------


def _escalar(e0: Elemento, e: Elemento, r: Resultado, at: datetime, u: Umbrales,
             ciclo_id: Id | None) -> None:
    if not e.temporal or e.estado != ALMACEN:
        return
    # **Alguien ha dicho que esta ahi.** Una devolucion manual no borra evidencia, aplaza
    # la conclusion: el contador sigue subiendo (lo hace quien llama, antes de esto), pero
    # no se escala mientras dure la gracia. Al expirar, lo que siga sin leerse sale en la
    # pasada siguiente y no tras otra cuenta completa, que es el motivo de no haber
    # resuelto esto poniendo el contador a cero.
    if e.gracia_hasta is not None and at < e.gracia_hasta:
        return
    por_ciclos = e.ciclos_sin_leer >= u.ciclos_para_circulante
    por_tiempo = (e.temporal_desde is not None
                  and at - e.temporal_desde >= timedelta(minutes=u.minutos_para_circulante))
    if not (por_ciclos or por_tiempo):
        return
    antes = copy.copy(e)
    e.estado = EN_TRANSITO
    e.ubicacion_id = None   # no se sabe donde esta; el origen queda en ubicacion_origen_id
    r.movimientos.append(_mov(
        antes, e, MOV_TRANSITO, at, usuario_tarjeta=e.usuario_tarjeta, ciclo_id=ciclo_id,
        detalle={"ciclos_sin_leer": e.ciclos_sin_leer,
                 "criterio": "ciclos" if por_ciclos else "tiempo"},
    ))


def faltante_en_ciclo(e0: Elemento, at: datetime, u: Umbrales, acceso: Acceso | None,
                      ciclo_id: Id | None = None) -> Resultado:
    """El elemento esta en stock en el almacen y no se ha leido en un ciclo valido completo."""
    e = copy.copy(e0)
    r = Resultado(e)
    if e0.estado != ALMACEN:
        return r
    if not e0.temporal:
        e.temporal = True
        e.temporal_desde = at
        e.ciclos_sin_leer = 1
        e.ubicacion_origen_id = e0.ubicacion_id
        if acceso is not None:
            e.usuario_tarjeta, e.usuario_nombre, e.usuario_at = acceso.tarjeta, acceso.nombre, acceso.at
            # "ventana": el acceso cae entre la ultima vez que se vio y la deteccion; es
            # un candidato firme. "ultimo": solo es la ultima persona que entro.
            firme = e0.ultima_lectura_at is not None and acceso.at >= e0.ultima_lectura_at
            e.asignacion_confianza = "ventana" if firme else "ultimo"
        r.movimientos.append(_mov(
            e0, e, "salida_temporal", at, usuario_tarjeta=e.usuario_tarjeta, ciclo_id=ciclo_id,
            detalle={"confianza": e.asignacion_confianza,
                     "ultima_lectura_at": e0.ultima_lectura_at},
        ))
    else:
        e.ciclos_sin_leer = e0.ciclos_sin_leer + 1
    _escalar(e0, e, r, at, u, ciclo_id)
    return r


def escalar_por_tiempo(e0: Elemento, now: datetime, u: Umbrales) -> Resultado:
    """Temporizador: un temporal que lleva T minutos sin localizarse pasa a circulante,
    aunque no se cierren ciclos (p. ej. lectores parados)."""
    e = copy.copy(e0)
    r = Resultado(e)
    _escalar(e0, e, r, now, u, None)
    return r
