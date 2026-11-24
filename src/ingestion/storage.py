"""Capa de almacenamiento temporal en disco local.

- ``data/raw/<run_id>/<fuente>.json``: respuesta original de la API (auditoría / reproceso).
- ``data/processed/<nombre>_<run_id>.csv``: registros parseados de todas las fuentes.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ingestion.logger import get_logger

logger = get_logger(__name__)


class LocalStorage:
    def __init__(self, base_dir: Path, run_id: str):
        self.run_id = run_id
        self.raw_dir = base_dir / "raw" / run_id
        self.processed_dir = base_dir / "processed"

    def save_raw(self, source: str, payload: dict[str, Any]) -> Path:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        path = self.raw_dir / f"{source}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("[%s] JSON crudo guardado en %s", source, path)
        return path

    def save_records(self, records: Iterable[dict[str, Any]], name: str) -> Path | None:
        rows = list(records)
        if not rows:
            logger.warning("No hay registros para guardar en '%s'", name)
            return None

        # Unión ordenada de columnas (por si alguna fuente trae variables extra).
        fieldnames: list[str] = []
        for row in rows:
            fieldnames.extend(key for key in row if key not in fieldnames)

        self.processed_dir.mkdir(parents=True, exist_ok=True)
        path = self.processed_dir / f"{name}_{self.run_id}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info("%d registros guardados en %s", len(rows), path)
        return path
