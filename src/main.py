"""Script principal de ingesta automatizada.

Descarga en paralelo (``asyncio.gather``) los datos horarios de clima de todas las
ubicaciones definidas en ``config/sources.yaml``, guarda el JSON crudo de cada una
y un CSV consolidado con los registros parseados.

Uso:
    python src/main.py                 # ingesta concurrente
    python src/main.py --benchmark     # compara secuencial vs concurrente
    python src/main.py --help
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ingestion import (
    ConfigError,
    DataCollector,
    IngestionError,
    LocalStorage,
    Location,
    Settings,
    SourcesConfig,
    WeatherParser,
    load_sources,
)
from ingestion.config import PROJECT_ROOT
from ingestion.logger import get_logger, setup_logging

logger = get_logger("ingestion.main")

Records = list[dict[str, Any]]


async def ingest_location(
    collector: DataCollector,
    parser: WeatherParser,
    storage: LocalStorage,
    location: Location,
    sources: SourcesConfig,
) -> Records:
    """Pipeline de una fuente: descargar -> guardar crudo -> parsear."""
    payload = await collector.fetch_forecast(location, sources)
    # La escritura a disco es bloqueante: se delega a un hilo para no frenar el event loop.
    await asyncio.to_thread(storage.save_raw, location.name, payload)
    records = parser.parse(location, payload)
    logger.info("[%s] OK: %d registros", location.name, len(records))
    return records


async def run_concurrent(
    collector: DataCollector, parser: WeatherParser, storage: LocalStorage, sources: SourcesConfig
) -> list[Records | BaseException]:
    """Lanza todas las fuentes a la vez. ``return_exceptions`` evita que un fallo cancele al resto."""
    tasks = [
        ingest_location(collector, parser, storage, location, sources)
        for location in sources.locations
    ]
    return await asyncio.gather(*tasks, return_exceptions=True)


async def run_sequential(
    collector: DataCollector, parser: WeatherParser, storage: LocalStorage, sources: SourcesConfig
) -> list[Records | BaseException]:
    """Versión una-por-una, solo para comparar tiempos en modo --benchmark."""
    results: list[Records | BaseException] = []
    for location in sources.locations:
        try:
            results.append(await ingest_location(collector, parser, storage, location, sources))
        except Exception as exc:  # noqa: BLE001 - mismo contrato que gather(return_exceptions=True)
            results.append(exc)
    return results


def summarize(sources: SourcesConfig, results: list[Records | BaseException]) -> tuple[Records, int]:
    """Separa éxitos de fallos y registra cada fallo. Devuelve (registros, cantidad de fallos)."""
    all_records: Records = []
    failures = 0
    for location, result in zip(sources.locations, results):
        if isinstance(result, BaseException):
            failures += 1
            if isinstance(result, IngestionError):
                # El detalle ya fue logueado por el cliente / parser.
                logger.error("[%s] FALLÓ (%s): %s", location.name, type(result).__name__, result)
            else:
                logger.error(
                    "[%s] FALLÓ por un error inesperado",
                    location.name,
                    exc_info=(type(result), result, result.__traceback__),
                )
        else:
            all_records.extend(result)
    return all_records, failures


async def run(sources_path: Path, benchmark: bool, settings: Settings) -> int:
    sources = load_sources(sources_path)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    storage = LocalStorage(settings.data_dir, run_id)
    parser = WeatherParser()

    logger.info(
        "Inicio de ingesta run_id=%s | %d fuentes | timeout=%gs | reintentos=%d | concurrencia=%d",
        run_id,
        len(sources.locations),
        settings.timeout_seconds,
        settings.max_retries,
        settings.max_concurrency,
    )

    async with DataCollector(settings) as collector:
        if benchmark:
            start = time.perf_counter()
            await run_sequential(collector, parser, storage, sources)
            sequential_s = time.perf_counter() - start
            logger.info("Secuencial: %.2f s", sequential_s)

        start = time.perf_counter()
        results = await run_concurrent(collector, parser, storage, sources)
        concurrent_s = time.perf_counter() - start
        logger.info("Concurrente (asyncio.gather): %.2f s", concurrent_s)

        if benchmark:
            logger.info(
                "BENCHMARK -> secuencial %.2f s vs concurrente %.2f s | %.1fx más rápido",
                sequential_s,
                concurrent_s,
                sequential_s / concurrent_s if concurrent_s else float("inf"),
            )

    records, failures = summarize(sources, results)
    await asyncio.to_thread(storage.save_records, records, "weather_hourly")

    ok = len(sources.locations) - failures
    if failures:
        logger.warning("Ingesta finalizada con fallos: %d OK, %d con error", ok, failures)
        return 1
    logger.info("Ingesta finalizada correctamente: %d/%d fuentes", ok, len(sources.locations))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Ingesta asíncrona de datos de clima (Open-Meteo).")
    ap.add_argument(
        "--sources",
        type=Path,
        default=PROJECT_ROOT / "config" / "sources.yaml",
        help="YAML con ubicaciones y variables (default: config/sources.yaml)",
    )
    ap.add_argument(
        "--benchmark",
        action="store_true",
        help="ejecuta primero en modo secuencial y compara tiempos con el concurrente",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        setup_logging()
        logger.error("Configuración inválida: %s", exc)
        return 2

    setup_logging(settings.log_level, settings.log_dir, settings.log_format)
    try:
        return asyncio.run(run(args.sources, args.benchmark, settings))
    except ConfigError as exc:
        logger.error("Configuración inválida: %s", exc)
        return 2
    except KeyboardInterrupt:
        logger.warning("Ingesta interrumpida por el usuario")
        return 130


if __name__ == "__main__":
    sys.exit(main())
