"""Configuración de la aplicación.

Todos los valores se leen de variables de entorno (o del fichero .env).
Nunca se escriben claves reales en el código: ver .env.example.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    entorno: str = "desarrollo"  # desarrollo | pruebas | produccion

    # Base de datos. Hay DOS conexiones a propósito:
    # - "sistema": propietario de las tablas. Solo para migraciones, login y administración de Aibe.
    # - "app": usuario limitado. La base de datos le obliga a ver solo los datos de UNA gestoría.
    database_url: str = "postgresql+psycopg://aibe_owner:cambia-esto@localhost:5432/aibe"
    database_url_app: str = "postgresql+psycopg://aibe_app:cambia-esto-tambien@localhost:5432/aibe"

    redis_url: str = "redis://localhost:6379/0"

    # Seguridad
    secret_key: str = Field(default="solo-para-desarrollo-cambiar", min_length=16)
    clave_maestra_cifrado: str = ""  # 32 bytes en base64. Generar con: python -m app.cli generar-clave
    exigir_2fa_admin: bool = True
    duracion_sesion_horas: int = 12
    cookies_seguras: bool = False  # True en producción (solo HTTPS)

    # IA
    proveedor_llm: str = "claude"  # claude | falso (pruebas)
    anthropic_api_key: str = ""
    modelo_barato: str = "claude-haiku-5-5"
    modelo_redaccion: str = "claude-sonnet-5-5"
    cambio_usd_eur: float = 0.92
    max_tokens_entrada_estimados: int = 90_000  # por debajo del umbral de precio alto de Haiku (100K)
    presupuesto_ia_mensual_eur_defecto: float = 60.0

    # Rutas
    ruta_recetas: Path = RAIZ_PROYECTO / "recetas"
    ruta_precios: Path = RAIZ_PROYECTO / "config" / "precios_modelos.yaml"

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "produccion"


@lru_cache
def get_settings() -> Settings:
    return Settings()
