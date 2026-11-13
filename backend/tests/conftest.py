"""Preparación de las pruebas: crea una base de datos PostgreSQL de pruebas desde cero.

Necesita un PostgreSQL con:
  - el usuario propietario de DATABASE_URL con permiso para crear bases de datos;
  - el usuario limitado de DATABASE_URL_APP (aibe_app) ya creado.
Con Docker:  docker compose run --rm api pytest
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.crypto import generar_clave

NOMBRE_BD = f"aibe_test_{uuid.uuid4().hex[:8]}"

_url_owner = make_url(os.environ.get("DATABASE_URL", "postgresql+psycopg://aibe_owner:owner@localhost:5432/aibe"))
_url_app = make_url(os.environ.get("DATABASE_URL_APP", "postgresql+psycopg://aibe_app:app@localhost:5432/aibe"))

os.environ.update({
    "ENTORNO": "pruebas",
    "DATABASE_URL": _url_owner.set(database=NOMBRE_BD).render_as_string(hide_password=False),
    "DATABASE_URL_APP": _url_app.set(database=NOMBRE_BD).render_as_string(hide_password=False),
    "CLAVE_MAESTRA_CIFRADO": generar_clave(),
    "SECRET_KEY": "clave-de-pruebas-suficientemente-larga",
    "PROVEEDOR_LLM": "falso",
    "EXIGIR_2FA_ADMIN": "false",
})


@pytest.fixture(scope="session", autouse=True)
def base_de_datos():
    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings
    from app.core.db import reiniciar_engines

    get_settings.cache_clear()
    admin = create_engine(_url_owner.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{NOMBRE_BD}"'))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.upgrade(cfg, "head")
    reiniciar_engines()
    yield
    reiniciar_engines()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{NOMBRE_BD}"'))
    admin.dispose()


@pytest.fixture(autouse=True)
def limpiar_tablas(base_de_datos):
    yield
    from app.core.db import engine_sistema
    from app.models import Base

    nombres = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine_sistema().begin() as c:
        c.execute(text(f"TRUNCATE {nombres} CASCADE"))


@pytest.fixture
def ajustes(monkeypatch):
    """Permite cambiar la configuración en una prueba concreta."""
    from app.core.config import get_settings

    def cambiar(**valores):
        for k, v in valores.items():
            monkeypatch.setenv(k.upper(), str(v))
        get_settings.cache_clear()

    yield cambiar
    get_settings.cache_clear()


@pytest.fixture
def dos_gestorias():
    """Dos gestorías completas (A y B) creadas desde la plantilla, con un usuario y un cliente cada una."""
    from sqlalchemy import select

    from app.auth.servicio import crear_usuario
    from app.core.db import sesion_sistema
    from app.models import PlantillaPerfil
    from app.models.enums import Rol
    from app.tenancy.servicio import alta_gestoria, cargar_plantillas_base, crear_cliente

    datos = {}
    with sesion_sistema() as db:
        cargar_plantillas_base(db)
        db.flush()
        plantilla = db.scalar(select(PlantillaPerfil))
        for letra in ("a", "b"):
            g = alta_gestoria(db, nombre=f"Gestoría {letra.upper()}", actor="pruebas", plantilla_id=plantilla.id,
                              email_contacto=f"info@{letra}.example", telefono="900 000 00" + letra)
            u = crear_usuario(db, email=f"resp@{letra}.example", nombre=f"Responsable {letra}",
                              password="contraseña-segura-1", rol=Rol.ADMIN_GESTORIA, actor="pruebas",
                              gestoria_id=g.id)
            c = crear_cliente(db, g.id, nombre=f"Cliente de {letra}", nif=f"0000000{ord(letra)}X",
                              emails=[f"cliente@{letra}.example"], actor="pruebas")
            datos[letra] = {"gestoria_id": g.id, "usuario_email": u.email, "cliente_id": c.id}
        db.commit()
    return datos


@pytest.fixture
def cliente_http():
    from fastapi.testclient import TestClient

    from app.main import crear_app

    return TestClient(crear_app())


@pytest.fixture
def admin_aibe():
    from app.auth.servicio import crear_usuario
    from app.core.db import sesion_sistema
    from app.models.enums import Rol

    with sesion_sistema() as db:
        crear_usuario(db, email="admin@aibetech.es", nombre="Admin", password="contraseña-admin-1",
                      rol=Rol.ADMIN_AIBE, actor="pruebas")
        db.commit()
    return {"email": "admin@aibetech.es", "password": "contraseña-admin-1"}


def entrar(cliente, email, password, codigo=None):
    r = cliente.post("/auth/login", json={"email": email, "password": password, "codigo_2fa": codigo})
    assert r.status_code == 200, r.text
    return r
