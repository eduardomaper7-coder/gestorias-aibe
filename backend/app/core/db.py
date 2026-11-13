"""Conexiones a PostgreSQL y aislamiento entre gestorías.

Cómo se garantiza que una gestoría nunca vea datos de otra (dos barreras):

1. En el código: todo lo que hace una gestoría (su panel, su agente) usa una
   "sesión de gestoría", que lleva fijado el identificador de esa gestoría.
2. En la propia base de datos: el usuario "aibe_app" está sometido a
   Seguridad a Nivel de Fila (RLS). Cada tabla con datos de gestorías tiene una
   regla que dice "solo puedes ver/escribir filas cuya gestoria_id coincida con
   app.gestoria_id". Aunque el código tuviera un fallo y olvidara filtrar, la
   base de datos no devolvería datos de otra gestoría.

La "sesión de sistema" (propietario de las tablas) salta esas reglas y solo se
usa para: migraciones, login y el panel de administración de Aibe.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def engine_sistema() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def engine_app() -> Engine:
    return create_engine(get_settings().database_url_app, pool_pre_ping=True)


def _fabrica(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _fijar_gestoria(session: Session, transaction, connection) -> None:
    """Al empezar cada transacción, fija la gestoría activa (solo dura esa transacción)."""
    gestoria_id = session.info.get("gestoria_id")
    if gestoria_id is not None:
        connection.execute(
            text("SELECT set_config('app.gestoria_id', :g, true)"), {"g": str(gestoria_id)}
        )


@contextmanager
def sesion_sistema() -> Iterator[Session]:
    """Sesión sin restricción de gestoría. Usar solo en administración de Aibe y procesos internos."""
    with _fabrica(engine_sistema())() as session:
        session.info["tipo"] = "sistema"
        yield session


@contextmanager
def sesion_gestoria(gestoria_id: UUID) -> Iterator[Session]:
    """Sesión limitada por la base de datos a los datos de UNA gestoría."""
    if gestoria_id is None:
        raise ValueError("sesion_gestoria requiere un gestoria_id")
    with _fabrica(engine_app())() as session:
        session.info["tipo"] = "gestoria"
        session.info["gestoria_id"] = gestoria_id
        yield session


def reiniciar_engines() -> None:
    """Para pruebas: obliga a recrear las conexiones con la configuración actual."""
    for fn in (engine_sistema, engine_app):
        if fn.cache_info().currsize:
            fn().dispose()
        fn.cache_clear()
