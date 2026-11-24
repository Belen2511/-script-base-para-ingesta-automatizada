# Imagen base: Python 3.10 en versión liviana (Debian slim)
FROM python:3.10-slim

# Evita archivos .pyc y fuerza salida de logs sin buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias de sistema necesarias para compilar librerías de IA
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo dentro del contenedor (ruta relativa al proyecto)
WORKDIR /workspaces/proyecto-ia

# Instalar dependencias de Python primero (aprovecha la caché de capas)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar el código fuente del proyecto
COPY . .

CMD ["python", "src/check_env.py"]
