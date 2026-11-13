"""Inicio de sesión, cookies de sesión y doble factor."""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.registro import registrar
from app.core import crypto
from app.core.config import get_settings
from app.core.security import (
    hash_password,
    nuevo_secreto_totp,
    uri_totp,
    verificar_password,
    verificar_totp,
)
from app.models import Usuario
from app.models.enums import Rol

NOMBRE_COOKIE = "aibe_sesion"
_CONTEXTO_TOTP = "totp"


class ErrorAutenticacion(Exception):
    pass


@dataclass
class DatosSesion:
    usuario_id: uuid.UUID
    version: int


def _serializador() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="aibe-sesion")


def crear_token_sesion(usuario: Usuario) -> str:
    return _serializador().dumps({"u": str(usuario.id), "v": usuario.version_sesion})


def leer_token_sesion(token: str) -> DatosSesion | None:
    max_age = get_settings().duracion_sesion_horas * 3600
    try:
        datos = _serializador().loads(token, max_age=max_age)
        return DatosSesion(usuario_id=uuid.UUID(datos["u"]), version=int(datos["v"]))
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        return None


def crear_usuario(
    session: Session, *, email: str, nombre: str, password: str, rol: Rol, actor: str,
    gestoria_id: uuid.UUID | None = None,
) -> Usuario:
    email = email.strip().lower()
    if rol == Rol.ADMIN_AIBE and gestoria_id is not None:
        raise ValueError("Un administrador de Aibe no pertenece a ninguna gestoría")
    if rol != Rol.ADMIN_AIBE and gestoria_id is None:
        raise ValueError("Los usuarios de gestoría necesitan una gestoría")
    if session.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise ValueError(f"Ya existe un usuario con el correo {email}")
    usuario = Usuario(email=email, nombre=nombre, hash_password=hash_password(password), rol=rol,
                      gestoria_id=gestoria_id)
    session.add(usuario)
    session.flush()
    registrar(session, "usuario.creado", actor, gestoria_id=gestoria_id, entidad="usuario",
              entidad_id=usuario.id, detalle={"rol": rol.value})
    return usuario


def autenticar(session: Session, email: str, password: str, codigo_2fa: str | None) -> Usuario:
    """Comprueba credenciales. Mensaje de error genérico a propósito (no revela si el correo existe)."""
    usuario = session.scalar(select(Usuario).where(Usuario.email == email.strip().lower()))
    if not usuario or not usuario.activo or not verificar_password(usuario.hash_password, password):
        registrar(session, "auth.login_fallido", f"email:{email.strip().lower()}", resultado="error",
                  gestoria_id=usuario.gestoria_id if usuario else None)
        session.commit()
        raise ErrorAutenticacion("Correo o contraseña incorrectos")
    if usuario.totp_activo:
        secreto = crypto.descifrar(usuario.totp_secreto_cifrado, _CONTEXTO_TOTP + str(usuario.id))
        if not codigo_2fa or not verificar_totp(secreto, codigo_2fa):
            registrar(session, "auth.2fa_fallido", f"usuario:{usuario.email}", resultado="error",
                      gestoria_id=usuario.gestoria_id)
            session.commit()
            raise ErrorAutenticacion("Código de verificación incorrecto")
    usuario.ultimo_acceso = datetime.now(UTC)
    registrar(session, "auth.login", f"usuario:{usuario.email}", gestoria_id=usuario.gestoria_id)
    return usuario


def iniciar_2fa(session: Session, usuario: Usuario) -> str:
    """Genera un secreto nuevo (aún sin activar). Devuelve la URI para el QR de la app de autenticación."""
    secreto = nuevo_secreto_totp()
    usuario.totp_secreto_cifrado = crypto.cifrar(secreto, _CONTEXTO_TOTP + str(usuario.id))
    usuario.totp_activo = False
    return uri_totp(secreto, usuario.email)


def confirmar_2fa(session: Session, usuario: Usuario, codigo: str) -> None:
    if not usuario.totp_secreto_cifrado:
        raise ErrorAutenticacion("Primero hay que iniciar la activación del doble factor")
    secreto = crypto.descifrar(usuario.totp_secreto_cifrado, _CONTEXTO_TOTP + str(usuario.id))
    if not verificar_totp(secreto, codigo):
        raise ErrorAutenticacion("Código incorrecto")
    usuario.totp_activo = True
    usuario.version_sesion += 1  # cierra las demás sesiones abiertas
    registrar(session, "auth.2fa_activado", f"usuario:{usuario.email}", gestoria_id=usuario.gestoria_id)
