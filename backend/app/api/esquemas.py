"""Datos que entran y salen de la API."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import CategoriaConocimiento, EstadoAgente, EstadoAlta, Rol, TipoCliente
from app.tenancy.esquemas import ContenidoPlantilla


class Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- autenticación
class LoginEntrada(BaseModel):
    email: EmailStr
    password: str
    codigo_2fa: str | None = None


class UsuarioSalida(Salida):
    id: uuid.UUID
    email: str
    nombre: str
    rol: Rol
    gestoria_id: uuid.UUID | None
    totp_activo: bool


class Activar2faSalida(BaseModel):
    uri: str
    instrucciones: str = "Añada esta clave a su app de autenticación y confirme con un código de 6 dígitos."


class CodigoEntrada(BaseModel):
    codigo: str = Field(min_length=6, max_length=8)


# --- plantillas
class PlantillaEntrada(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    descripcion: str | None = None
    contenido: ContenidoPlantilla = ContenidoPlantilla()


class PlantillaCambios(BaseModel):
    nombre: str | None = Field(None, min_length=3, max_length=120)
    descripcion: str | None = None
    contenido: ContenidoPlantilla | None = None


class PlantillaSalida(Salida):
    id: uuid.UUID
    nombre: str
    descripcion: str | None
    version: int
    contenido: dict


class PlantillaDesdeGestoria(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    descripcion: str | None = None


# --- gestorías
class GestoriaAlta(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    nif: str | None = None
    email_contacto: EmailStr | None = None
    telefono: str | None = None
    direccion: str | None = None
    plantilla_id: uuid.UUID | None = None


class GestoriaCambios(BaseModel):
    nombre: str | None = Field(None, min_length=2, max_length=200)
    nif: str | None = None
    email_contacto: EmailStr | None = None
    telefono: str | None = None
    direccion: str | None = None
    retencion_meses: int | None = Field(None, ge=1, le=120)
    presupuesto_ia_mensual_eur: float | None = Field(None, ge=0, le=10_000)  # solo Aibe


class GestoriaSalida(Salida):
    id: uuid.UUID
    nombre: str
    slug: str
    nif: str | None
    email_contacto: str | None
    telefono: str | None
    direccion: str | None
    estado_agente: EstadoAgente
    activacion_autorizada: bool
    estado_alta: EstadoAlta
    plantilla_origen_id: uuid.UUID | None
    retencion_meses: int
    presupuesto_ia_mensual_eur: float
    config: dict
    creado_en: datetime


class GestoriaConEstado(GestoriaSalida):
    estado: dict


class EstadoAgenteEntrada(BaseModel):
    estado: EstadoAgente


class UsuarioAlta(BaseModel):
    email: EmailStr
    nombre: str
    password: str = Field(min_length=10)
    rol: Rol = Rol.ADMIN_GESTORIA


# --- base de conocimiento y temas sensibles
class ConocimientoEntrada(BaseModel):
    categoria: CategoriaConocimiento
    titulo: str = Field(min_length=2, max_length=200)
    contenido: str = Field(min_length=1, max_length=20_000)
    orden: int = 0
    activo: bool = True


class ConocimientoSalida(ConocimientoEntrada, Salida):
    id: uuid.UUID


class TemaSensibleEntrada(BaseModel):
    tema: str = Field(min_length=2, max_length=200)
    descripcion: str | None = None
    derivar_a_email: EmailStr | None = None


class TemaSensibleSalida(TemaSensibleEntrada, Salida):
    id: uuid.UUID


# --- clientes finales
class ClienteEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=250)
    nif: str | None = None
    tipo: TipoCliente = TipoCliente.AUTONOMO
    emails: list[EmailStr] = []
    telefono: str | None = None
    id_externo: str | None = None


class ClienteSalida(Salida):
    id: uuid.UUID
    nombre: str
    nif: str | None
    tipo: TipoCliente
    telefono: str | None
    id_externo: str | None
    activo: bool
    emails: list[str]


class UsoIAResumen(BaseModel):
    desde: datetime
    coste_eur: float
    presupuesto_eur: float
    llamadas: int
    por_tarea: dict[str, dict]
