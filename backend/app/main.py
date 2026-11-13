"""Punto de entrada de la API.

Con el servidor en marcha, la documentación interactiva está en /docs
(desde ahí se puede probar todo hasta que exista el panel web en la fase 4).
"""
from fastapi import FastAPI
from sqlalchemy import text

from app.api import admin, auth, gestoria
from app.core.config import get_settings
from app.core.db import engine_sistema


def crear_app() -> FastAPI:
    ajustes = get_settings()
    app = FastAPI(
        title="Aibe · Agentes IA para gestorías",
        version="0.1.0",
        docs_url=None if ajustes.es_produccion else "/docs",
        redoc_url=None,
    )
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(gestoria.router)

    @app.get("/salud", tags=["Sistema"])
    def salud():
        """Comprueba que la base de datos responde y que existen los ficheros de configuración."""
        with engine_sistema().connect() as c:
            c.execute(text("SELECT 1"))
        problemas = [f"No existe {r}" for r in (ajustes.ruta_precios, ajustes.ruta_recetas) if not r.exists()]
        if not ajustes.clave_maestra_cifrado:
            problemas.append("Falta CLAVE_MAESTRA_CIFRADO")
        return {"estado": "ok" if not problemas else "con_avisos", "entorno": ajustes.entorno,
                "avisos": problemas}

    return app


app = crear_app()
