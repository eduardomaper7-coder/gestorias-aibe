FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RUTA_RECETAS=/srv/recetas \
    RUTA_PRECIOS=/srv/config/precios_modelos.yaml

WORKDIR /srv/backend

# Dependencias primero (se reaprovechan entre compilaciones si no cambian)
COPY backend/pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py && pip install ".[dev]" && rm -rf app build *.egg-info

COPY backend/ ./
COPY recetas/ /srv/recetas/
COPY config/ /srv/config/
RUN pip install --no-deps . \
    && useradd --create-home --uid 10001 aibe
USER aibe

EXPOSE 8000
# Al arrancar: aplica migraciones pendientes y levanta la API
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
