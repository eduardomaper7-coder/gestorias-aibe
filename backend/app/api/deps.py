"""Dependencias comunes de la API: quién es el usuario y qué sesión de base de datos le toca."""
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.servicio import NOMBRE_COOKIE, leer_token_sesion
from app.core.config import get_settings
from app.core.db import sesion_gestoria, sesion_sistema
from app.models import Usuario
from app.models.enums import Rol


def db_sistema() -> Iterator[Session]:
    with sesion_sistema() as session:
        yield session


def usuario_actual(request: Request, db: Session = Depends(db_sistema)) -> Usuario:
    token = request.cookies.get(NOMBRE_COOKIE)
    datos = leer_token_sesion(token) if token else None
    usuario = db.get(Usuario, datos.usuario_id) if datos else None
    if not usuario or not usuario.activo or usuario.version_sesion != datos.version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicie sesión")
    return usuario


def admin_aibe(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol != Rol.ADMIN_AIBE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para administradores de Aibe")
    if get_settings().exigir_2fa_admin and not usuario.totp_activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Active el doble factor para usar la administración")
    return usuario


def usuario_gestoria(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol == Rol.ADMIN_AIBE or usuario.gestoria_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para usuarios de una gestoría")
    return usuario


def admin_gestoria(usuario: Usuario = Depends(usuario_gestoria)) -> Usuario:
    if usuario.rol != Rol.ADMIN_GESTORIA:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el responsable de la gestoría puede cambiar esto")
    return usuario


def db_gestoria(usuario: Usuario = Depends(usuario_gestoria)) -> Iterator[Session]:
    """Sesión limitada por la base de datos a la gestoría del usuario."""
    with sesion_gestoria(usuario.gestoria_id) as session:
        yield session


def actor(usuario: Usuario) -> str:
    return f"usuario:{usuario.email}"
