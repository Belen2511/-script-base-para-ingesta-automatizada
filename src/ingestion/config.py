"""Carga de configuración: variables de entorno (.env) y fuentes (YAML)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ingestion.exceptions import ConfigError

# Raíz del proyecto: src/ingestion/config.py -> ../../
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} debe ser numérico (valor recibido: {raw!r})") from exc


def _env_int(name: str, default: int) -> int:
    value = _env_float(name, default)
    if value != int(value) or value < 0:
        raise ConfigError(f"{name} debe ser un entero >= 0 (valor recibido: {value})")
    return int(value)


@dataclass(frozen=True)
class Settings:
    """Parámetros de conexión y resiliencia. Se leen de variables de entorno."""

    base_url: str = "https://api.open-meteo.com"
    api_key: str | None = None
    timeout_seconds: float = 10.0
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    max_concurrency: int = 5
    log_level: str = "INFO"
    log_format: str = "text"
    data_dir: Path = PROJECT_ROOT / "data"
    log_dir: Path = PROJECT_ROOT / "logs"

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        """Construye la configuración a partir de ``.env`` y del entorno del proceso."""
        load_dotenv(env_file or PROJECT_ROOT / ".env")
        settings = cls(
            base_url=os.getenv("OPEN_METEO_BASE_URL") or cls.base_url,
            api_key=os.getenv("OPEN_METEO_API_KEY") or None,
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", cls.timeout_seconds),
            max_retries=_env_int("HTTP_MAX_RETRIES", cls.max_retries),
            backoff_base_seconds=_env_float("HTTP_BACKOFF_SECONDS", cls.backoff_base_seconds),
            max_concurrency=_env_int("MAX_CONCURRENCY", cls.max_concurrency),
            log_level=(os.getenv("LOG_LEVEL") or cls.log_level).upper(),
            log_format=(os.getenv("LOG_FORMAT") or cls.log_format).lower(),
        )
        if settings.timeout_seconds <= 0:
            raise ConfigError("HTTP_TIMEOUT_SECONDS debe ser mayor que 0")
        if settings.max_concurrency < 1:
            raise ConfigError("MAX_CONCURRENCY debe ser al menos 1")
        if settings.log_format not in {"text", "json"}:
            raise ConfigError("LOG_FORMAT debe ser 'text' o 'json'")
        return settings


@dataclass(frozen=True)
class Location:
    """Una ubicación a consultar (una 'fuente' de la ingesta)."""

    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class SourcesConfig:
    """Qué datos pedir y para qué ubicaciones (definido en ``config/sources.yaml``)."""

    locations: tuple[Location, ...]
    hourly_variables: tuple[str, ...]
    past_days: int = 1
    forecast_days: int = 1


def load_sources(path: Path) -> SourcesConfig:
    """Lee y valida el YAML de fuentes."""
    if not path.is_file():
        raise ConfigError(f"No existe el archivo de fuentes: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML inválido en {path}: {exc}") from exc

    try:
        locations = tuple(
            Location(
                name=str(item["name"]),
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
            )
            for item in raw["locations"]
        )
        variables = tuple(str(v) for v in raw["hourly_variables"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"Estructura inválida en {path}: {exc!r}") from exc

    if not locations:
        raise ConfigError(f"{path} no define ninguna ubicación")
    if not variables:
        raise ConfigError(f"{path} no define ninguna variable horaria")

    names = [loc.name for loc in locations]
    if len(names) != len(set(names)):
        raise ConfigError(f"{path} tiene nombres de ubicación repetidos")

    return SourcesConfig(
        locations=locations,
        hourly_variables=variables,
        past_days=int(raw.get("past_days", 1)),
        forecast_days=int(raw.get("forecast_days", 1)),
    )
