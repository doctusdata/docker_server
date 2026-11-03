"""Inventario, desde la API de lectura de irfid: las dos cifras y las cuatro pestanas.

*Passthrough* fino, igual que `estado.py`: **aqui no se recalcula nada**. Quien decide
que cuenta como inventario es irfid, que es quien tiene las reglas y el esquema. La
tentacion de sumar o restar en este lado es justo lo que produjo el problema que esto
viene a resolver: el visor hacia `catalogo - stock` en el navegador y el resultado no
significaba nada.

Dos cosas a conservar al tocar esto:

  * **El titular no se recalcula.** `cuentas.inventario` ya es "ni usado, ni retirado, ni
    dado de baja", que es invariante a fallos de lectura. Derivarlo de otra forma aqui
    volveria a hacerlo bailar.
  * **Los query params pasan tal cual.** El grupo lo valida irfid contra una lista
    cerrada (entra en una consulta SQL); replicar esa validacion aqui seria tener dos
    sitios que se pueden desincronizar.
"""
from typing import Any

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..rfid_client import inventario as cliente

router = APIRouter(prefix="/api/inventario", tags=["inventario"])

_RUTA = "/api/inventario/v1"


@router.get("/resumen")
async def resumen() -> dict[str, Any]:
    return await cliente.get(f"{_RUTA}/resumen")


@router.get("/elementos")
async def elementos(
    grupo: str | None = None,
    limite: int | None = None,
    desplazamiento: int | None = None,
    busqueda: str | None = Query(None),
) -> dict[str, Any]:
    return await cliente.get(f"{_RUTA}/elementos", params={
        "grupo": grupo, "limite": limite,
        "desplazamiento": desplazamiento, "busqueda": busqueda,
    })


class Devolucion(BaseModel):
    epcs: list[str] = []
    todas: bool = False
    grupo: str = "observacion"


@router.post("/elementos/devolver")
async def devolver(cuerpo: Devolucion) -> dict[str, Any]:
    """Devuelve al almacen lo que esta en observacion o en transito, con el contador a 0.

    **La unica ruta del visor que escribe.** Sigue siendo *passthrough*: quien decide que
    significa devolver es irfid, que es quien tiene las reglas y las restricciones. Aqui
    solo se reenvia el cuerpo y se tira la cache -- con TTL de 10 s, sin eso la pantalla
    ensenaria las cifras de antes justo despues de pulsar.
    """
    return await cliente.post(f"{_RUTA}/elementos/devolver", json=cuerpo.model_dump())


@router.get("/accesos")
async def accesos(
    dia: date | None = None,
    limite: int | None = None,
) -> dict[str, Any]:
    """Quien ha entrado, y si su entrada corto una pasada de inventario.

    Sustituye al `/api/accesos` heredado, que leia `User_readings`: esa tabla solo la
    escribia el espejo legacy y lleva congelada desde que se retiro. `traza.acceso` si
    la escribe la ingesta en cada paso de carnet.
    """
    return await cliente.get(f"{_RUTA}/accesos", params={
        "dia": dia.isoformat() if dia else None,
        "limite": limite,
    })


@router.get("/diagnostico")
async def diagnostico(limite: int | None = None) -> dict[str, Any]:
    """Ventanas de lectura, antenas y EPC desconocidos. Pantalla tecnica.

    **No hay log de lecturas individuales** y no es un olvido: el agregador de irfid
    colapsa las decenas de lecturas por segundo de una misma etiqueta en una
    observacion —es la razon de que el sistema escale— y el RSSI se descarta desde que
    el espejo legacy esta apagado. Lo que queda es el resumen por ventana y los
    contadores por antena, que es con lo que se diagnostico la antena floja el 26/10.
    """
    return await cliente.get(f"{_RUTA}/diagnostico", params={"limite": limite})
