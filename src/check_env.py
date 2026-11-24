"""Script de verificación del entorno de desarrollo (Checkpoint 1).

Comprueba:
  1. La versión de Python instalada.
  2. Que el código corre dentro de un contenedor Docker.
  3. Que las variables de entorno definidas en .env son accesibles.
  4. Que la estructura de carpetas del proyecto existe.

Todas las rutas son relativas a la raíz del proyecto (sin rutas absolutas).
"""

import os
import platform
import socket
import sys
from pathlib import Path

from dotenv import load_dotenv

# Raíz del proyecto calculada a partir de la ubicación de este archivo
PROJECT_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_VARS = ["OPENAI_API_KEY", "MLFLOW_TRACKING_URI", "DATABASE_URL"]
REQUIRED_DIRS = ["src", "data", "config", "notebooks"]


def running_in_docker() -> bool:
    """Detecta si el proceso corre dentro de un contenedor Docker."""
    if Path("/.dockerenv").exists():
        return True
    cgroup = Path("/proc/1/cgroup")
    return cgroup.exists() and "docker" in cgroup.read_text(errors="ignore")


def mask(value: str) -> str:
    """Oculta el valor de una credencial dejando solo los primeros caracteres."""
    return value[:4] + "*" * max(len(value) - 4, 0) if value else ""


def main() -> int:
    ok = True
    print("=" * 60)
    print(" VERIFICACIÓN DEL ENTORNO - IA Automatización Checkpoint 1")
    print("=" * 60)

    # 1. Python
    print(f"\n[Python]  Versión: {platform.python_version()}")
    print(f"          Ejecutable: {sys.executable}")
    if sys.version_info < (3, 10):
        print("          [ERROR] Se requiere Python 3.10 o superior")
        ok = False
    else:
        print("          [OK] Python >= 3.10")

    # 2. Docker
    in_docker = running_in_docker()
    print(f"\n[Docker]  Hostname del contenedor: {socket.gethostname()}")
    print(f"          Sistema: {platform.system()} {platform.release()}")
    if in_docker:
        print("          [OK] El script se está ejecutando dentro de Docker")
    else:
        print("          [ERROR] No se detectó un contenedor Docker")
        ok = False

    # 3. Variables de entorno
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"\n[Entorno] Archivo cargado: {env_file.relative_to(PROJECT_ROOT)}")
    else:
        print("\n[Entorno] No existe .env (copiá .env.example a .env)")

    for var in REQUIRED_VARS:
        value = os.getenv(var)
        if value:
            print(f"          [OK] {var} = {mask(value)}")
        else:
            print(f"          [ERROR] {var} no está definida")
            ok = False

    # 4. Estructura de carpetas
    print("\n[Carpetas]")
    for folder in REQUIRED_DIRS:
        exists = (PROJECT_ROOT / folder).is_dir()
        print(f"          [{'OK' if exists else 'ERROR'}] {folder}/")
        ok = ok and exists

    print("\n" + "=" * 60)
    print(" RESULTADO: " + ("ENTORNO CONFIGURADO CORRECTAMENTE" if ok else "HAY ERRORES"))
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
