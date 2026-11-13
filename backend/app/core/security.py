"""Contraseñas (Argon2) y doble factor (códigos TOTP tipo Google Authenticator)."""
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

LONGITUD_MINIMA_PASSWORD = 10


def hash_password(password: str) -> str:
    if len(password) < LONGITUD_MINIMA_PASSWORD:
        raise ValueError(f"La contraseña debe tener al menos {LONGITUD_MINIMA_PASSWORD} caracteres")
    return _hasher.hash(password)


def verificar_password(hash_guardado: str, password: str) -> bool:
    try:
        return _hasher.verify(hash_guardado, password)
    except (VerifyMismatchError, VerificationError):
        return False


def nuevo_secreto_totp() -> str:
    return pyotp.random_base32()


def uri_totp(secreto: str, email: str) -> str:
    return pyotp.TOTP(secreto).provisioning_uri(name=email, issuer_name="Aibe Gestorías")


def verificar_totp(secreto: str, codigo: str) -> bool:
    return pyotp.TOTP(secreto).verify(codigo.strip(), valid_window=1)
