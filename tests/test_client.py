"""Tests del DataCollector usando un transporte HTTP simulado (sin red)."""

import asyncio
import time

import httpx
import pytest

from ingestion import DataCollector, Location, PermanentError, Settings, SourcesConfig, TransientError

LOCATION = Location("test_city", -34.6, -58.4)
SOURCES = SourcesConfig(locations=(LOCATION,), hourly_variables=("temperature_2m",))
PAYLOAD = {"hourly": {"time": ["2026-01-01T00:00"], "temperature_2m": [20.5]}}


def make_settings(**overrides) -> Settings:
    base = dict(base_url="https://api.test", max_retries=2, backoff_base_seconds=0, timeout_seconds=1)
    base.update(overrides)
    return Settings(**base)


def fetch(handler, **settings_overrides):
    async def _run():
        transport = httpx.MockTransport(handler)
        async with DataCollector(make_settings(**settings_overrides), transport=transport) as c:
            return await c.fetch_forecast(LOCATION, SOURCES)

    return asyncio.run(_run())


def test_success_returns_json():
    assert fetch(lambda req: httpx.Response(200, json=PAYLOAD)) == PAYLOAD


def test_transient_5xx_is_retried_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503, json={"reason": "overloaded"})
        return httpx.Response(200, json=PAYLOAD)

    assert fetch(handler) == PAYLOAD
    assert len(calls) == 3


def test_timeout_exhausts_retries():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(TransientError):
        fetch(handler)
    assert len(calls) == 3  # 1 intento + 2 reintentos


def test_connection_error_is_transient():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(TransientError):
        fetch(handler, max_retries=0)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_errors_are_not_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": True, "reason": "invalid"})

    with pytest.raises(PermanentError) as excinfo:
        fetch(handler)
    assert len(calls) == 1
    assert excinfo.value.status_code == status


def test_invalid_json_is_permanent():
    with pytest.raises(PermanentError):
        fetch(lambda req: httpx.Response(200, text="<html>oops</html>"))


def test_api_key_is_sent_only_when_configured():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=PAYLOAD)

    fetch(handler)
    fetch(handler, api_key="secret")
    assert "apikey" not in seen[0]
    assert seen[1]["apikey"] == "secret"


def test_requests_run_concurrently():
    """5 solicitudes de 0.2 s cada una deben tardar ~0.2 s, no ~1 s."""

    async def handler(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, json=PAYLOAD)

    async def _run():
        transport = httpx.MockTransport(handler)
        async with DataCollector(make_settings(max_concurrency=5), transport=transport) as c:
            start = time.perf_counter()
            await asyncio.gather(*(c.fetch_forecast(LOCATION, SOURCES) for _ in range(5)))
            return time.perf_counter() - start

    assert asyncio.run(_run()) < 0.6
