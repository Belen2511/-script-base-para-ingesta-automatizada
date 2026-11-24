"""Capa de parseo: convierte la respuesta cruda de la API en registros tabulares.

Está desacoplada de la descarga: recibe un ``dict`` ya obtenido y devuelve filas
planas (una por hora y ubicación), listas para guardar como CSV o cargar en pandas.
"""

from __future__ import annotations

from typing import Any

from ingestion.config import Location
from ingestion.exceptions import ParsingError
from ingestion.logger import get_logger

logger = get_logger(__name__)

Record = dict[str, Any]


class WeatherParser:
    """Normaliza el bloque ``hourly`` de Open-Meteo a formato largo."""

    def parse(self, location: Location, payload: dict[str, Any]) -> list[Record]:
        hourly = payload.get("hourly")
        if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
            raise ParsingError("la respuesta no contiene 'hourly.time'", source=location.name)

        times: list[str] = hourly["time"]
        variables = [key for key in hourly if key != "time"]

        for var in variables:
            if not isinstance(hourly[var], list) or len(hourly[var]) != len(times):
                raise ParsingError(
                    f"la serie '{var}' no coincide en largo con 'time'", source=location.name
                )

        units = payload.get("hourly_units", {})
        records: list[Record] = []
        for i, timestamp in enumerate(times):
            row: Record = {
                "location": location.name,
                "latitude": payload.get("latitude", location.latitude),
                "longitude": payload.get("longitude", location.longitude),
                "timezone": payload.get("timezone"),
                "time": timestamp,
            }
            for var in variables:
                row[var] = hourly[var][i]
            records.append(row)

        logger.debug(
            "[%s] %d filas parseadas (%s)",
            location.name,
            len(records),
            ", ".join(f"{v} [{units.get(v, '?')}]" for v in variables),
        )
        return records
