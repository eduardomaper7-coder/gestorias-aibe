"""Cifrado de secretos (contraseñas de correo, credenciales de programas, semillas 2FA).

Usamos AES-256-GCM con una clave maestra que vive fuera de la base de datos
(variable de entorno CLAVE_MAESTRA_CIFRADO). Si alguien roba una copia de la
base de datos, sin esa clave no puede leer los secretos.

Cada secreto se "ata" a su gestoría (dato asociado): un texto cifrado de la
gestoría A no se puede descifrar haciéndolo pasar por la gestoría B.

Formato guardado:  v1:<base64(nonce de 12 bytes + texto cifrado)>
El prefijo de versión permite rotar la clave en el futuro.
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_VERSION = "v1"


class ErrorCifrado(Exception):
    pass


def generar_clave() -> str:
    return base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()


def _clave() -> bytes:
    valor = get_settings().clave_maestra_cifrado
    if not valor:
        raise ErrorCifrado("Falta CLAVE_MAESTRA_CIFRADO en la configuración")
    clave = base64.b64decode(valor)
    if len(clave) != 32:
        raise ErrorCifrado("CLAVE_MAESTRA_CIFRADO debe tener 32 bytes en base64")
    return clave


def cifrar(texto: str, contexto: str = "") -> str:
    nonce = os.urandom(12)
    datos = AESGCM(_clave()).encrypt(nonce, texto.encode(), contexto.encode())
    return f"{_VERSION}:{base64.b64encode(nonce + datos).decode()}"


def descifrar(valor: str, contexto: str = "") -> str:
    try:
        version, cuerpo = valor.split(":", 1)
        if version != _VERSION:
            raise ErrorCifrado(f"Versión de cifrado desconocida: {version}")
        crudo = base64.b64decode(cuerpo)
        return AESGCM(_clave()).decrypt(crudo[:12], crudo[12:], contexto.encode()).decode()
    except ErrorCifrado:
        raise
    except Exception as exc:  # datos manipulados, clave o contexto incorrectos
        raise ErrorCifrado("No se pudo descifrar el valor") from exc
