"""Gestorías (perfiles), plantillas, usuarios, clientes finales y su configuración."""
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ConFechas, ConId, DeGestoria, enum_col
from app.models.enums import (
    AccesoPrograma,
    CategoriaConocimiento,
    EstadoAgente,
    EstadoAlta,
    EstadoConexion,
    Rol,
    TipoCliente,
)


class Gestoria(ConId, ConFechas, Base):
    """Un perfil de gestoría. Todo lo demás cuelga de aquí."""

    __tablename__ = "gestorias"

    nombre: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    nif: Mapped[str | None] = mapped_column(String(20))
    email_contacto: Mapped[str | None] = mapped_column(String(254))
    telefono: Mapped[str | None] = mapped_column(String(40))
    direccion: Mapped[str | None] = mapped_column(String(300))

    estado_agente: Mapped[EstadoAgente] = mapped_column(
        enum_col(EstadoAgente, "estado_agente"), default=EstadoAgente.SIMULACION
    )
    # La gestoría solo puede encender el agente (modo activo) si Aibe lo ha autorizado antes
    activacion_autorizada: Mapped[bool] = mapped_column(Boolean, default=False)
    estado_alta: Mapped[EstadoAlta] = mapped_column(enum_col(EstadoAlta, "estado_alta"), default=EstadoAlta.ACTIVA)
    dado_de_baja_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plantilla_origen_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("plantillas_perfil.id", ondelete="SET NULL")
    )
    # Configuración del agente (tono, firma, reglas de derivación, límites...). Ver tenancy/esquemas.py
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    retencion_meses: Mapped[int] = mapped_column(Integer, default=24)
    presupuesto_ia_mensual_eur: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("60"))


class PlantillaPerfil(ConId, ConFechas, Base):
    """Punto de partida para dar de alta gestorías parecidas (p. ej. "fiscal de autónomos")."""

    __tablename__ = "plantillas_perfil"

    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    descripcion: Mapped[str | None] = mapped_column(Text)
    contenido: Mapped[dict] = mapped_column(JSONB, default=dict)  # ver tenancy/esquemas.ContenidoPlantilla
    version: Mapped[int] = mapped_column(Integer, default=1)


class Usuario(ConId, ConFechas, Base):
    """Persona con acceso al panel. Los admin de Aibe no pertenecen a ninguna gestoría."""

    __tablename__ = "usuarios"
    __es_de_gestoria__ = True  # protegida por RLS (las filas sin gestoría son invisibles para "app")

    gestoria_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("gestorias.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(254), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    hash_password: Mapped[str] = mapped_column(String(300))
    rol: Mapped[Rol] = mapped_column(enum_col(Rol, "rol"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_secreto_cifrado: Mapped[str | None] = mapped_column(Text)
    totp_activo: Mapped[bool] = mapped_column(Boolean, default=False)
    version_sesion: Mapped[int] = mapped_column(Integer, default=1)  # subirla cierra todas sus sesiones
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EntradaConocimiento(ConId, ConFechas, DeGestoria, Base):
    """Base de conocimiento de la gestoría: servicios, normas, horarios, tono, preguntas frecuentes."""

    __tablename__ = "entradas_conocimiento"

    categoria: Mapped[CategoriaConocimiento] = mapped_column(enum_col(CategoriaConocimiento, "categoria"))
    titulo: Mapped[str] = mapped_column(String(200))
    contenido: Mapped[str] = mapped_column(Text)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class TemaSensible(ConId, ConFechas, DeGestoria, Base):
    """Temas que el agente nunca responde solo: siempre los deriva a una persona."""

    __tablename__ = "temas_sensibles"

    tema: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    derivar_a_email: Mapped[str | None] = mapped_column(String(254))  # vacío = responsable general


class ClienteFinal(ConId, ConFechas, DeGestoria, Base):
    """Cliente de la gestoría (autónomo, empresa...)."""

    __tablename__ = "clientes_finales"
    __table_args__ = (UniqueConstraint("gestoria_id", "nif", name="uq_clientes_finales_gestoria_nif"),)

    nombre: Mapped[str] = mapped_column(String(250))
    nif: Mapped[str | None] = mapped_column(String(20))
    tipo: Mapped[TipoCliente] = mapped_column(enum_col(TipoCliente, "tipo_cliente"), default=TipoCliente.AUTONOMO)
    telefono: Mapped[str | None] = mapped_column(String(40))
    id_externo: Mapped[str | None] = mapped_column(String(80))  # código en su programa (p. ej. a3)
    gestor_asignado_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Memoria: resumen corto en vez de enviar conversaciones enteras al modelo
    resumen_memoria: Mapped[str | None] = mapped_column(Text)
    datos_memoria: Mapped[dict] = mapped_column(JSONB, default=dict)

    contactos: Mapped[list["ContactoCliente"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan", lazy="selectin"
    )


class ContactoCliente(ConId, ConFechas, DeGestoria, Base):
    """Direcciones de correo (y en el futuro teléfonos de WhatsApp) que identifican a un cliente."""

    __tablename__ = "contactos_cliente"
    __table_args__ = (UniqueConstraint("gestoria_id", "canal", "valor", name="uq_contactos_cliente_valor"),)

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clientes_finales.id", ondelete="CASCADE"), index=True
    )
    canal: Mapped[str] = mapped_column(String(20), default="email")
    valor: Mapped[str] = mapped_column(String(254))  # siempre en minúsculas

    cliente: Mapped[ClienteFinal] = relationship(back_populates="contactos")


class Buzon(ConId, ConFechas, DeGestoria, Base):
    """Buzón de correo conectado (IMAP para recibir, SMTP para enviar)."""

    __tablename__ = "buzones"
    __table_args__ = (UniqueConstraint("gestoria_id", "direccion", name="uq_buzones_gestoria_direccion"),)

    direccion: Mapped[str] = mapped_column(String(254))
    nombre_visible: Mapped[str | None] = mapped_column(String(200))
    imap_host: Mapped[str] = mapped_column(String(200))
    imap_puerto: Mapped[int] = mapped_column(Integer, default=993)
    smtp_host: Mapped[str] = mapped_column(String(200))
    smtp_puerto: Mapped[int] = mapped_column(Integer, default=465)
    smtp_seguridad: Mapped[str] = mapped_column(String(10), default="ssl")  # ssl | starttls
    usuario: Mapped[str] = mapped_column(String(254))
    password_cifrada: Mapped[str] = mapped_column(Text)
    carpeta_entrada: Mapped[str] = mapped_column(String(120), default="INBOX")
    carpeta_enviados: Mapped[str | None] = mapped_column(String(120))  # se detecta al conectar
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    estado_conexion: Mapped[EstadoConexion] = mapped_column(
        enum_col(EstadoConexion, "estado_conexion"), default=EstadoConexion.SIN_PROBAR
    )
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    ultima_sincronizacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado_sync: Mapped[dict] = mapped_column(JSONB, default=dict)  # UIDVALIDITY, último UID...


class ProgramaGestoria(ConId, ConFechas, DeGestoria, Base):
    """Un programa que usa la gestoría (a3ASESOR, un Excel...) y cómo se accede a él."""

    __tablename__ = "programas_gestoria"

    nombre: Mapped[str] = mapped_column(String(120))
    tipo_conector: Mapped[str] = mapped_column(String(60))  # excel | a3asesor | ...
    acceso: Mapped[AccesoPrograma] = mapped_column(enum_col(AccesoPrograma, "acceso_programa"))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)  # nada secreto aquí
    credenciales_cifradas: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    estado_conexion: Mapped[EstadoConexion] = mapped_column(
        enum_col(EstadoConexion, "estado_conexion"), default=EstadoConexion.SIN_PROBAR
    )
    ultimo_error: Mapped[str | None] = mapped_column(Text)


class Puente(ConId, ConFechas, DeGestoria, Base):
    """Puente local instalado en un ordenador de la gestoría (se completa en la fase 5)."""

    __tablename__ = "puentes"

    nombre: Mapped[str] = mapped_column(String(120))
    hash_token: Mapped[str | None] = mapped_column(String(300))
    version: Mapped[str | None] = mapped_column(String(40))
    ultimo_contacto: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado_conexion: Mapped[EstadoConexion] = mapped_column(
        enum_col(EstadoConexion, "estado_conexion"), default=EstadoConexion.SIN_PROBAR
    )
