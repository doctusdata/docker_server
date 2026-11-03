import time
from typing import Any

import httpx
from fastapi import HTTPException

from .config import settings


class RfidClient:
    def __init__(self, base_url: str, api_key: str, ttl: int, nombre: str = "RFID API"):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            timeout=15.0,
        )
        self._ttl = ttl
        self._nombre = nombre
        self._cache: dict[str, tuple[float, Any]] = {}

    async def close(self) -> None:
        await self._client.aclose()

    def _cache_key(self, path: str, params: dict[str, Any] | None) -> str:
        if not params:
            return path
        parts = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
        return f"{path}?{parts}"

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        key = self._cache_key(path, clean_params)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and (now - cached[0]) < self._ttl:
            return cached[1]

        try:
            resp = await self._client.get(path, params=clean_params or None)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"{self._nombre} unreachable: {exc}"
            ) from exc

        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"{self._nombre} error: {resp.text[:200]}",
            )

        data = resp.json()
        self._cache[key] = (now, data)
        return data

    async def post(self, path: str, json: Any = None) -> Any:
        """Escribe, y **tira la cache entera de este cliente**.

        No se invalida por clave: una escritura mueve a la vez el resumen y la tabla de
        varios grupos, y acertar que claves se han quedado viejas es mas facil de
        equivocar que de mantener. Con TTL de 10 s y un POST que se pulsa a mano, vaciar
        el diccionario cuesta menos que una entrada incorrecta: sin esto, quien pulsa el
        boton ve diez segundos las cifras de antes y concluye que no ha funcionado.
        """
        try:
            resp = await self._client.post(path, json=json)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"{self._nombre} unreachable: {exc}"
            ) from exc

        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"{self._nombre} error: {resp.text[:200]}",
            )

        self._cache.clear()
        return resp.json()


client = RfidClient(settings.RFID_API_URL, settings.RFID_API_KEY, settings.CACHE_TTL_SECONDS)

# El servicio de almacen no pide clave: se reusa el mismo cliente por la cache y la
# traduccion de errores, que es lo que aporta.
almacen = RfidClient(
    settings.ALMACEN_API_URL, "", settings.CACHE_TTL_SECONDS, nombre="API de almacen"
)

# El inventario va por su propio puerto, asi que necesita su propia instancia: la
# base_url se fija al construir el httpx.AsyncClient. Tampoco pide clave.
inventario = RfidClient(
    settings.INVENTARIO_API_URL, "", settings.CACHE_TTL_SECONDS,
    nombre="API de inventario",
)
