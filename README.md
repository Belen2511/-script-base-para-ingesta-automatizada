# Proyecto IA Automatización — Motor de ingesta asíncrona

Primer componente de la arquitectura de automatización: un paquete de Python
(`src/ingestion/`) que descarga datos de varias fuentes **en paralelo** con `asyncio`,
de forma **resiliente** (timeouts, reintentos, logging estructurado) y con las capas de
conexión, parseo y almacenamiento **desacopladas** en clases.

## Qué datos descarga

Datos meteorológicos horarios de la API pública [Open-Meteo](https://open-meteo.com/en/docs)
(`GET /v1/forecast`) para 8 ciudades argentinas definidas en
[`config/sources.yaml`](config/sources.yaml): Buenos Aires, Córdoba, Rosario, Mendoza,
Salta, Bariloche, Mar del Plata y Ushuaia.

| Variable | Unidad |
|---|---|
| `temperature_2m` | °C |
| `relative_humidity_2m` | % |
| `precipitation` | mm |
| `wind_speed_10m` | km/h |

Se piden las horas observadas del día anterior (`past_days: 1`) y el pronóstico del día
(`forecast_days: 1`): 48 filas por ciudad. Para agregar ciudades o variables solo hay que
editar el YAML; no se toca código.

Open-Meteo es gratuito y no exige clave. `OPEN_METEO_API_KEY` es opcional (planes
comerciales); si se define, el cliente la envía como parámetro `apikey`.

### Salidas

| Ruta | Contenido |
|---|---|
| `data/raw/<run_id>/<ciudad>.json` | Respuesta original de la API, sin tocar |
| `data/processed/weather_hourly_<run_id>.csv` | Todas las ciudades en formato largo (una fila por ciudad y hora) |
| `logs/ingestion.log` | Log de ejecución (rota a 1 MB, conserva 3 archivos) |

`data/` y `logs/` no se versionan.

## Estructura

```
.
├── config/
│   └── sources.yaml          # Ubicaciones y variables a descargar
├── src/
│   ├── main.py               # Script principal: orquesta con asyncio.gather()
│   ├── check_env.py          # Verificación del entorno (Checkpoint 1)
│   └── ingestion/            # Paquete de ingesta
│       ├── client.py         # DataCollector: sesión httpx async, timeout, reintentos
│       ├── parser.py         # WeatherParser: JSON crudo -> registros tabulares
│       ├── storage.py        # LocalStorage: guarda JSON crudo y CSV procesado
│       ├── config.py         # Settings (.env) y SourcesConfig (YAML)
│       ├── logger.py         # Logging con timestamp/nivel/módulo, texto o JSON
│       └── exceptions.py     # TransientError / PermanentError / ParsingError / ConfigError
├── tests/                    # Tests con transporte HTTP simulado (sin red)
├── .devcontainer/  Dockerfile  .env.example  pyproject.toml
├── requirements.txt          # Dependencias de ejecución
└── requirements-dev.txt      # + pytest
```

## Instalación

Requiere Python 3.10 o superior. Desde la raíz del proyecto (o dentro del Dev Container):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Opcionalmente, como paquete instalable (para importarlo desde notebooks u otros módulos):

```bash
pip install -e ".[dev]"
```

### Configuración

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

`.env` está en `.gitignore`: **nunca se sube al repositorio**. Todas las variables de la
ingesta tienen valores por defecto, así que el script funciona aunque no estén definidas.

| Variable | Default | Para qué sirve |
|---|---|---|
| `OPEN_METEO_BASE_URL` | `https://api.open-meteo.com` | URL base de la API |
| `OPEN_METEO_API_KEY` | vacío | Clave opcional (plan comercial) |
| `HTTP_TIMEOUT_SECONDS` | `10` | Timeout de cada solicitud |
| `HTTP_MAX_RETRIES` | `3` | Reintentos ante errores transitorios |
| `HTTP_BACKOFF_SECONDS` | `1` | Espera base del backoff exponencial (1 s, 2 s, 4 s…) |
| `MAX_CONCURRENCY` | `5` | Solicitudes simultáneas como máximo |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `text` | `text` o `json` (una línea JSON por evento) |

## Ejecución

```bash
python src/main.py                # ingesta concurrente
python src/main.py --benchmark    # secuencial vs concurrente, con tiempos
python src/main.py --sources otra_config.yaml
```

Ejemplo de salida:

```
2026-11-24 10:15:02 | INFO     | ingestion.main | Inicio de ingesta run_id=20261124T131502Z | 8 fuentes | timeout=10.0s | reintentos=3 | concurrencia=5
2026-11-24 10:15:03 | INFO     | ingestion.main | [cordoba] OK: 48 registros
...
2026-11-24 10:15:03 | INFO     | ingestion.main | Concurrente (asyncio.gather): 0.41 s
2026-11-24 10:15:03 | INFO     | ingestion.main | BENCHMARK -> secuencial 1.92 s vs concurrente 0.41 s | 4.7x más rápido
2026-11-24 10:15:03 | INFO     | ingestion.storage | 384 registros guardados en data/processed/weather_hourly_20261124T131502Z.csv
2026-11-24 10:15:03 | INFO     | ingestion.main | Ingesta finalizada correctamente: 8/8 fuentes
```

Códigos de salida: `0` todo OK · `1` alguna fuente falló (las demás se guardan igual) ·
`2` configuración inválida · `130` interrumpido con Ctrl+C.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Los tests simulan la API con `httpx.MockTransport`, así que no necesitan red: verifican
reintentos ante 503 y timeouts, que 400/401/403/404 no se reintenten, el envío de la clave,
la ejecución concurrente, el parser y el almacenamiento.

## Cómo funciona

### Asincronía y concurrencia

`main.py` crea una corrutina por ciudad y las lanza juntas con
`asyncio.gather(*tareas, return_exceptions=True)`. Mientras una solicitud espera la red, el
event loop atiende las demás, así que el tiempo total se acerca al de la solicitud más
lenta en lugar de a la suma de todas. `--benchmark` lo mide en cada corrida.

`return_exceptions=True` hace que un fallo en una ciudad no cancele a las otras. Un
`asyncio.Semaphore` limita las solicitudes simultáneas (`MAX_CONCURRENCY`) y la escritura a
disco se delega a un hilo (`asyncio.to_thread`) para no bloquear el loop.

### Resiliencia: errores transitorios vs. permanentes

| Tipo | Casos | Qué hace el cliente |
|---|---|---|
| `TransientError` | Timeout, error de conexión/DNS, HTTP 408, 425, 429, 500, 502, 503, 504 | `logging.error` del intento, reintenta con backoff exponencial; si se agotan los intentos, abandona esa fuente |
| `PermanentError` | HTTP 401/403 (credenciales inválidas), 400/404 (parámetros o recurso inválidos), respuesta no-JSON | `logging.error` y abandona esa fuente sin reintentar |
| `ParsingError` | La respuesta no tiene la estructura esperada | Se registra y la fuente se marca como fallida |
| `ConfigError` | `.env` o YAML inválidos | El programa termina con código 2 antes de hacer solicitudes |

Siempre se cierra la sesión HTTP (`async with`) y se guarda lo que sí se descargó.

Para ver la resiliencia en acción sin cortar la red:

```bash
# Timeouts forzados: cada ciudad reintenta y termina con error de forma ordenada
HTTP_TIMEOUT_SECONDS=0.001 HTTP_MAX_RETRIES=1 python src/main.py
```

En PowerShell: `$env:HTTP_TIMEOUT_SECONDS="0.001"; $env:HTTP_MAX_RETRIES="1"; python src/main.py`
(después, `Remove-Item Env:HTTP_TIMEOUT_SECONDS, Env:HTTP_MAX_RETRIES`).

### Desacoplamiento

| Clase | Responsabilidad | No hace |
|---|---|---|
| `DataCollector` | Conexión, timeout, reintentos, clasificación de errores | No transforma ni guarda datos |
| `WeatherParser` | Convertir el JSON en filas planas y validar su forma | No sabe de HTTP |
| `LocalStorage` | Persistir JSON crudo y CSV | No sabe de la API |

Gracias a esta separación, cambiar de fuente (otra API, archivos) o de destino (base de
datos, S3) toca una sola clase, y un agente de IA puede invocar cada pieza por separado.

## Entorno de desarrollo (Checkpoint 1)

1. Copiar `.env.example` a `.env`.
2. Abrir la carpeta en VS Code con Docker Desktop corriendo →
   `Ctrl+Shift+P` → **Dev Containers: Reopen in Container**.
3. Verificar el entorno: `python src/check_env.py`.

El PDF del Checkpoint 1 se genera con
`python tools/build_pdf.py --apellido TuApellido --nombre TuNombre` (ver capturas en
`docs/capturas/`).
