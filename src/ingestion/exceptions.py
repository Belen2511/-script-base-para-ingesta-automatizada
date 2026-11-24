"""Jerarquía de excepciones del motor de ingesta.

Separar errores *transitorios* de *permanentes* permite decidir si vale la pena
reintentar una solicitud:

- ``TransientError``: el problema puede resolverse solo (timeout, caída de red,
  HTTP 429 / 5xx). Se reintenta con backoff exponencial.
- ``PermanentError``: reintentar no sirve (API key inválida, recurso inexistente,
  parámetros mal formados, respuesta no-JSON). Se registra y se aborta esa fuente.
"""


class IngestionError(Exception):
    """Error base de la ingesta. Guarda la fuente que lo originó."""

    def __init__(self, message: str, source: str = "", status_code: int | None = None):
        super().__init__(message)
        self.source = source
        self.status_code = status_code


class TransientError(IngestionError):
    """Error temporal: la solicitud puede tener éxito si se reintenta."""


class PermanentError(IngestionError):
    """Error definitivo: reintentar no cambia el resultado."""


class ParsingError(IngestionError):
    """La respuesta llegó, pero su estructura no es la esperada."""


class ConfigError(Exception):
    """Configuración inválida o incompleta (variables de entorno o YAML)."""
