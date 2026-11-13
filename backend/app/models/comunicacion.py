"""Conversaciones, mensajes, adjuntos y derivaciones a humanos."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConFechas, ConId, DeGestoria, enum_col
from app.models.enums import Autor, Direccion, EstadoConversacion, EstadoDerivacion, EstadoEnvio


class Conversacion(ConId, ConFechas, DeGestoria, Base):
    __tablename__ = "conversaciones"

    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clientes_finales.id", ondelete="SET NULL"), index=True
    )
    canal: Mapped[str] = mapped_column(String(20), default="email")
    buzon_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("buzones.id", ondelete="SET NULL")
    )
    asunto: Mapped[str | None] = mapped_column(String(500))
    clave_hilo: Mapped[str] = mapped_column(String(500), index=True)  # para agrupar respuestas en el mismo hilo
    estado: Mapped[EstadoConversacion] = mapped_column(
        enum_col(EstadoConversacion, "estado_conversacion"), default=EstadoConversacion.ABIERTA
    )
    ultima_actividad: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Mensaje(ConId, ConFechas, DeGestoria, Base):
    __tablename__ = "mensajes"

    conversacion_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversaciones.id", ondelete="CASCADE"), index=True
    )
    direccion: Mapped[Direccion] = mapped_column(enum_col(Direccion, "direccion"))
    autor: Mapped[Autor] = mapped_column(enum_col(Autor, "autor"))
    canal: Mapped[str] = mapped_column(String(20), default="email")
    remitente: Mapped[str | None] = mapped_column(String(254))
    destinatarios: Mapped[list] = mapped_column(JSONB, default=list)
    asunto: Mapped[str | None] = mapped_column(String(500))
    cuerpo_texto: Mapped[str | None] = mapped_column(Text)
    id_externo: Mapped[str | None] = mapped_column(String(500), index=True)  # Message-ID del correo
    en_respuesta_a: Mapped[str | None] = mapped_column(String(500))
    referencias: Mapped[list] = mapped_column(JSONB, default=list)
    es_automatico: Mapped[bool] = mapped_column(Boolean, default=False)  # "fuera de la oficina", tickets...
    clasificacion: Mapped[str | None] = mapped_column(String(40))
    confianza: Mapped[float | None] = mapped_column(Float)
    estado_envio: Mapped[EstadoEnvio] = mapped_column(
        enum_col(EstadoEnvio, "estado_envio"), default=EstadoEnvio.NO_APLICA
    )
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recibido_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadatos: Mapped[dict] = mapped_column(JSONB, default=dict)


class Adjunto(ConId, ConFechas, DeGestoria, Base):
    __tablename__ = "adjuntos"

    mensaje_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("mensajes.id", ondelete="CASCADE"), index=True
    )
    nombre_fichero: Mapped[str] = mapped_column(String(300))
    tipo_mime: Mapped[str | None] = mapped_column(String(120))
    tamano_bytes: Mapped[int] = mapped_column(Integer, default=0)
    ruta_almacen: Mapped[str] = mapped_column(String(500))  # ubicación del fichero cifrado
    sha256: Mapped[str] = mapped_column(String(64))


class Derivacion(ConId, ConFechas, DeGestoria, Base):
    """Caso que el agente ha pasado a una persona de la gestoría."""

    __tablename__ = "derivaciones"

    conversacion_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversaciones.id", ondelete="CASCADE"), index=True
    )
    motivo: Mapped[str] = mapped_column(String(60))  # asesoramiento | sin_datos | pide_humano | tema_sensible...
    detalle: Mapped[str | None] = mapped_column(Text)
    responsable_email: Mapped[str | None] = mapped_column(String(254))
    estado: Mapped[EstadoDerivacion] = mapped_column(
        enum_col(EstadoDerivacion, "estado_derivacion"), default=EstadoDerivacion.PENDIENTE
    )
    atendida_por_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    atendida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notas: Mapped[str | None] = mapped_column(Text)
    intentos_aviso: Mapped[int] = mapped_column(Integer, default=0)
