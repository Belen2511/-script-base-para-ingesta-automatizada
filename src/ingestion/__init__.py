"""Motor de ingesta asíncrona del proyecto.

Módulos:
    client     -> DataCollector: sesión HTTP asíncrona, timeout, reintentos.
    parser     -> WeatherParser: respuesta cruda -> registros tabulares.
    storage    -> LocalStorage: guarda JSON crudo y CSV procesado.
    config     -> Settings (.env) y SourcesConfig (config/sources.yaml).
    logger     -> logging estructurado (texto o JSON) a consola y archivo.
    exceptions -> TransientError / PermanentError / ParsingError / ConfigError.
"""

from ingestion.client import DataCollector
from ingestion.config import Location, Settings, SourcesConfig, load_sources
from ingestion.exceptions import (
    ConfigError,
    IngestionError,
    ParsingError,
    PermanentError,
    TransientError,
)
from ingestion.parser import WeatherParser
from ingestion.storage import LocalStorage

__all__ = [
    "ConfigError",
    "DataCollector",
    "IngestionError",
    "LocalStorage",
    "Location",
    "ParsingError",
    "PermanentError",
    "Settings",
    "SourcesConfig",
    "TransientError",
    "WeatherParser",
    "load_sources",
]

__version__ = "0.1.0"
