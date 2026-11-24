"""Configuración centralizada de logging.

Cada línea lleva timestamp, nivel, módulo y mensaje. Se escribe a la consola y a
``logs/ingestion.log`` (con rotación). Con ``LOG_FORMAT=json`` se emite una línea
JSON por evento, lista para ser consumida por herramientas de monitoreo.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class JsonFormatter(logging.Formatter):
    """Formatea cada registro como un objeto JSON en una sola línea."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", log_dir: Path | None = None, fmt: str = "text") -> None:
    """Configura el logger raíz. Es idempotente: se puede llamar más de una vez."""
    formatter: logging.Formatter = (
        JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT, DATE_FORMAT)
    )

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "ingestion.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
        )

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(level)

    # httpx registra cada URL a nivel INFO (incluidos query params como la API key).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
