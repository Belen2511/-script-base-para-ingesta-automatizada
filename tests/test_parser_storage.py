"""Tests del parser, del almacenamiento y de la carga de configuración."""

import csv
import json

import pytest

from ingestion import ConfigError, LocalStorage, Location, ParsingError, WeatherParser, load_sources

LOCATION = Location("test_city", -34.6, -58.4)


def test_parser_builds_one_row_per_hour():
    payload = {
        "latitude": -34.6,
        "longitude": -58.4,
        "timezone": "America/Argentina/Buenos_Aires",
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [20.5, 19.8],
            "precipitation": [0.0, 0.2],
        },
    }
    rows = WeatherParser().parse(LOCATION, payload)
    assert len(rows) == 2
    assert rows[1] == {
        "location": "test_city",
        "latitude": -34.6,
        "longitude": -58.4,
        "timezone": "America/Argentina/Buenos_Aires",
        "time": "2026-01-01T01:00",
        "temperature_2m": 19.8,
        "precipitation": 0.2,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"hourly": {}},
        {"hourly": {"time": ["a", "b"], "temperature_2m": [1.0]}},
    ],
)
def test_parser_rejects_malformed_payload(payload):
    with pytest.raises(ParsingError):
        WeatherParser().parse(LOCATION, payload)


def test_storage_writes_raw_json_and_csv(tmp_path):
    storage = LocalStorage(tmp_path, "run1")
    raw = storage.save_raw("city", {"a": 1})
    assert json.loads(raw.read_text(encoding="utf-8")) == {"a": 1}

    path = storage.save_records([{"x": 1, "y": 2}, {"x": 3, "z": 4}], "out")
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert path.name == "out_run1.csv"
    assert rows[0] == {"x": "1", "y": "2", "z": ""}


def test_storage_skips_empty(tmp_path):
    assert LocalStorage(tmp_path, "run1").save_records([], "out") is None


def test_load_sources_validates(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("locations: []\nhourly_variables: [temperature_2m]\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_sources(bad)


def test_project_sources_file_is_valid():
    from ingestion.config import PROJECT_ROOT

    sources = load_sources(PROJECT_ROOT / "config" / "sources.yaml")
    assert len(sources.locations) >= 2
