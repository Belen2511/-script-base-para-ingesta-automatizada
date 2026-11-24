"""Capa de conexión: descarga asíncrona de datos desde la API de Open-Meteo.

Esta clase SOLO se ocupa de traer bytes de la red de forma resiliente. No limpia
ni transforma datos (eso es responsabilidad de ``parser.py``) ni los guarda
(``storage.py``).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ingestion.config import Location, Settings, SourcesConfig
from ingestion.exceptions import PermanentError, TransientError
from ingestion.logger import get_logger

logger = get_logger(__name__)

# Códigos HTTP que indican un problema temporal del servidor o de cuota.
TRANSIENT_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class DataCollector:
    """Gestiona la sesión HTTP asíncrona y las solicitudes a la API.

    Uso::

        async with DataCollector(settings) as collector:
            data = await collector.fetch_forecast(location, sources)

    - Reutiliza una única sesión ``httpx.AsyncClient`` (pool de conexiones).
    - Aplica timeout a cada solicitud.
    - Limita la concurrencia con un semáforo para no saturar la API.
    - Reintenta errores transitorios con backoff exponencial; los permanentes
      se registran y se propagan sin reintentar.
    """

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._transport = transport  # inyectable para tests
        self._client: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def __aenter__(self) -> DataCollector:
        self._client = httpx.AsyncClient(
            base_url=self.settings.base_url,
            timeout=httpx.Timeout(self.settings.timeout_seconds),
            headers={"User-Agent": "proyecto-ia-ingestion/0.1"},
            transport=self._transport,
        )
        logger.debug("Sesión HTTP abierta contra %s", self.settings.base_url)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("Sesión HTTP cerrada")

    # ------------------------------------------------------------------ API pública
    async def fetch_forecast(self, location: Location, sources: SourcesConfig) -> dict[str, Any]:
        """Descarga los datos horarios de una ubicación."""
        params: dict[str, Any] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": ",".join(sources.hourly_variables),
            "past_days": sources.past_days,
            "forecast_days": sources.forecast_days,
            "timezone": "auto",
        }
        if self.settings.api_key:
            params["apikey"] = self.settings.api_key
        return await self.fetch_json("/v1/forecast", params=params, source=location.name)

    async def fetch_json(
        self, endpoint: str, params: dict[str, Any], source: str
    ) -> dict[str, Any]:
        """GET con reintentos para errores transitorios."""
        total_attempts = self.settings.max_retries + 1
        for attempt in range(1, total_attempts + 1):
            try:
                data = await self._request_once(endpoint, params, source)
            except TransientError:
                if attempt == total_attempts:
                    logger.error(
                        "[%s] Se agotaron los %d intentos; se abandona la fuente",
                        source,
                        total_attempts,
                    )
                    raise
                delay = self.settings.backoff_base_seconds * 2 ** (attempt - 1)
                logger.warning(
                    "[%s] Intento %d/%d fallido; reintentando en %.1f s",
                    source,
                    attempt,
                    total_attempts,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                if attempt > 1:
                    logger.info("[%s] Recuperado en el intento %d", source, attempt)
                return data
        raise AssertionError("unreachable")  # pragma: no cover

    # ------------------------------------------------------------------ internos
    async def _request_once(
        self, endpoint: str, params: dict[str, Any], source: str
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("DataCollector debe usarse dentro de 'async with'")

        async with self._semaphore:
            try:
                response = await self._client.get(endpoint, params=params)
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                logger.error(
                    "[%s] Timeout tras %g s (%s)",
                    source,
                    self.settings.timeout_seconds,
                    type(exc).__name__,
                )
                raise TransientError("timeout", source=source) from exc
            except httpx.TransportError as exc:
                logger.error("[%s] Error de conexión: %s: %s", source, type(exc).__name__, exc)
                raise TransientError(f"error de conexión: {exc}", source=source) from exc
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                detail = _error_detail(exc.response)
                if status in TRANSIENT_STATUS_CODES:
                    logger.error("[%s] HTTP %d transitorio: %s", source, status, detail)
                    raise TransientError(detail, source=source, status_code=status) from exc
                kind = "credenciales inválidas" if status in (401, 403) else "solicitud rechazada"
                logger.error("[%s] HTTP %d permanente (%s): %s", source, status, kind, detail)
                raise PermanentError(detail, source=source, status_code=status) from exc

        try:
            data = response.json()
        except ValueError as exc:
            logger.error("[%s] La respuesta no es JSON válido", source)
            raise PermanentError("respuesta no-JSON", source=source) from exc
        if not isinstance(data, dict):
            logger.error("[%s] Se esperaba un objeto JSON y llegó %s", source, type(data).__name__)
            raise PermanentError("JSON inesperado", source=source)
        return data


def _error_detail(response: httpx.Response) -> str:
    """Extrae un mensaje corto del cuerpo de error (Open-Meteo usa {'reason': ...})."""
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("reason"):
            return str(body["reason"])[:200]
    except ValueError:
        pass
    return (response.text or response.reason_phrase)[:200]
