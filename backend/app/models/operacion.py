"""Tareas programadas, coste de IA, registro de auditoría y recetas."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConFechas, ConId, DeGestoria, enum_col
from app.models.enums import EstadoCorreccion, EstadoEjecucion, EstadoReceta


class TareaProgramada(ConId, ConFechas, DeGestoria, Base):
    """Tarea proactiva, p. ej. "una semana antes del cierre trimestral, reclamar documentación"."""

    __tablename__ = "tareas_programadas"

    tipo: Mapped[str] = mapped_column(String(60))
    nombre: Mapped[str] = mapped_column(String(200))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    ultima_ejecucion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proxima_ejecucion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class EjecucionTarea(ConId, DeGestoria, Base):
    __tablename__ = "ejecuciones_tarea"

    tarea_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tareas_programadas.id", ondelete="CASCADE"), index=True
    )
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[EstadoEjecucion] = mapped_column(
        enum_col(EstadoEjecucion, "estado_ejecucion"), default=EstadoEjecucion.EN_CURSO
    )
    resultado: Mapped[dict] = mapped_column(JSONB, default=dict)


class UsoIA(ConId, DeGestoria, Base):
    """Una llamada al modelo: tokens y coste. Base del control de gasto por gestoría y por tarea."""

    __tablename__ = "usos_ia"

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    tarea: Mapped[str] = mapped_column(String(60), index=True)  # clasificar | redactar | extraer | receta...
    proveedor: Mapped[str] = mapped_column(String(30))
    modelo: Mapped[str] = mapped_column(String(80))
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_salida: Mapped[int] = mapped_column(Integer, default=0)
    tokens_cache_lectura: Mapped[int] = mapped_column(Integer, default=0)
    tokens_cache_escritura: Mapped[int] = mapped_column(Integer, default=0)
    coste_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    coste_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    latencia_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    conversacion_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversaciones.id", ondelete="SET NULL")
    )


class RegistroEvento(ConId, Base):
    """Registro de auditoría: cada mensaje, decisión, consulta a sistemas y envío.

    Solo se añade; el usuario de la aplicación no puede modificar ni borrar filas.
    """

    __tablename__ = "registro_eventos"
    __es_de_gestoria__ = True

    gestoria_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("gestorias.id", ondelete="CASCADE"), index=True
    )
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    tipo: Mapped[str] = mapped_column(String(80), index=True)  # p. ej. gestoria.alta, ia.llamada, correo.enviado
    actor: Mapped[str] = mapped_column(String(120))  # usuario:<email> | agente | sistema | puente:<id>
    entidad: Mapped[str | None] = mapped_column(String(60))
    entidad_id: Mapped[str | None] = mapped_column(String(60))
    resultado: Mapped[str] = mapped_column(String(20), default="ok")  # ok | error | bloqueado
    detalle: Mapped[dict] = mapped_column(JSONB, default=dict)


class Receta(ConId, ConFechas, Base):
    """Operación declarativa sobre un programa (o mapeo de datos). Compartida entre gestorías."""

    __tablename__ = "recetas"
    __table_args__ = (UniqueConstraint("programa", "operacion", "version", name="uq_recetas_version"),)

    programa: Mapped[str] = mapped_column(String(60), index=True)
    operacion: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoReceta] = mapped_column(enum_col(EstadoReceta, "estado_receta"), default=EstadoReceta.BORRADOR)
    contenido_yaml: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    notas: Mapped[str | None] = mapped_column(Text)


class CorreccionReceta(ConId, ConFechas, Base):
    """Corrección propuesta por la IA cuando una receta falla. Queda pendiente de revisión humana."""

    __tablename__ = "correcciones_receta"

    receta_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("recetas.id", ondelete="CASCADE"), index=True
    )
    gestoria_origen_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("gestorias.id", ondelete="SET NULL")
    )
    propuesta_yaml: Mapped[str] = mapped_column(Text)
    motivo: Mapped[str] = mapped_column(Text)
    estado: Mapped[EstadoCorreccion] = mapped_column(
        enum_col(EstadoCorreccion, "estado_correccion"), default=EstadoCorreccion.PENDIENTE
    )
    revisada_por_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    revisada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
