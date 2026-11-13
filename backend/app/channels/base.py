"""Interfaz común de los canales de comunicación.

Correo IMAP/SMTP (fase 2) es la primera implementación. Gmail/Google Workspace,
Microsoft 365 (OAuth), WhatsApp Business (API oficial) y otros serán nuevas
implementaciones de esta misma interfaz, sin cambiar el agente.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AdjuntoEntrante:
    nombre: str
    tipo_mime: str | None
    contenido: bytes


@dataclass
class MensajeEntrante:
    canal: str
    id_externo: str                    # Message-ID, id de WhatsApp...
    remitente: str                     # dirección o teléfono, normalizado
    destinatarios: list[str]
    asunto: str | None
    texto: str
    recibido_en: datetime
    en_respuesta_a: str | None = None
    referencias: list[str] = field(default_factory=list)
    es_automatico: bool = False        # auto-respuestas, sistemas de tickets...
    adjuntos: list[AdjuntoEntrante] = field(default_factory=list)
    cabeceras: dict = field(default_factory=dict)


@dataclass
class MensajeSaliente:
    destinatarios: list[str]
    asunto: str | None
    texto: str
    en_respuesta_a: str | None = None  # para enviarlo dentro del hilo correcto
    referencias: list[str] = field(default_factory=list)


@dataclass
class ResultadoEnvio:
    id_externo: str
    enviado_en: datetime


class Canal(ABC):
    nombre: str = "base"

    @abstractmethod
    def probar_conexion(self) -> None: ...

    @abstractmethod
    def recibir_nuevos(self) -> list[MensajeEntrante]:
        """Mensajes nuevos desde la última vez (sin duplicados)."""

    @abstractmethod
    def enviar(self, mensaje: MensajeSaliente) -> ResultadoEnvio: ...

    @abstractmethod
    def clave_hilo(self, mensaje: MensajeEntrante) -> str:
        """Identificador estable del hilo de conversación al que pertenece el mensaje."""

    def identificar_remitente(self, mensaje: MensajeEntrante) -> str:
        """Dato con el que buscamos al cliente (correo en minúsculas, teléfono en formato E.164...)."""
        return mensaje.remitente.strip().lower()
