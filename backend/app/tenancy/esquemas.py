"""Forma que debe tener la configuración de cada gestoría y de cada plantilla.

Se valida al guardar: así un error al editar el perfil no puede romper el agente.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import AccesoPrograma, CategoriaConocimiento

CategoriaMensaje = Literal[
    "consulta_estado",       # "¿está presentado mi 303?"
    "duda_general",          # horarios, cómo enviar documentos, plazos generales...
    "envio_documentacion",   # el cliente manda facturas, tickets...
    "asesoramiento",         # pide consejo fiscal/legal -> SIEMPRE a un humano
    "pide_humano",           # quiere hablar con una persona -> SIEMPRE a un humano
    "spam_otros",
]


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResponsableDerivacion(Estricto):
    nombre: str | None = None
    email: EmailStr | None = None


class ReglasAgente(Estricto):
    # Categorías que el agente puede responder solo. Asesoramiento y "pide_humano" nunca.
    categorias_respuesta_automatica: list[Literal["consulta_estado", "duda_general", "envio_documentacion"]] = [
        "consulta_estado",
        "duda_general",
        "envio_documentacion",
    ]
    confianza_minima: float = Field(0.75, ge=0, le=1)  # por debajo, se deriva
    responsable_derivacion: ResponsableDerivacion = ResponsableDerivacion()
    mensaje_derivacion: str = (
        "Gracias por su mensaje. Una persona de {nombre_gestoria} lo revisará y le contestará lo antes posible."
    )
    limite_envios_cliente_dia: int = Field(3, ge=1, le=50)
    limite_envios_gestoria_dia: int = Field(300, ge=1, le=10_000)
    responder_fuera_horario: bool = True


class ConfigGestoria(Estricto):
    idioma: Literal["es"] = "es"
    zona_horaria: str = "Europe/Madrid"
    tratamiento: Literal["tu", "usted"] = "usted"
    tono: str = "Profesional, cercano y claro. Frases cortas. Sin tecnicismos innecesarios."
    firma: str = "{nombre_gestoria}"
    horario: str = "De lunes a viernes, de 9:00 a 14:00 y de 16:00 a 19:00."
    agente: ReglasAgente = ReglasAgente()


class EntradaConocimientoPlantilla(Estricto):
    categoria: CategoriaConocimiento
    titulo: str
    contenido: str
    orden: int = 0


class TemaSensiblePlantilla(Estricto):
    tema: str
    descripcion: str | None = None


class TareaPlantilla(Estricto):
    tipo: str
    nombre: str
    activa: bool = True
    config: dict = {}


class ProgramaPlantilla(Estricto):
    nombre: str
    tipo_conector: str
    acceso: AccesoPrograma
    config: dict = {}


class ContenidoPlantilla(Estricto):
    config: ConfigGestoria = ConfigGestoria()
    conocimiento: list[EntradaConocimientoPlantilla] = []
    temas_sensibles: list[TemaSensiblePlantilla] = []
    tareas: list[TareaPlantilla] = []
    programas: list[ProgramaPlantilla] = []


# Marcadores que se sustituyen al dar de alta una gestoría desde una plantilla
MARCADORES = ("nombre_gestoria", "email_contacto", "telefono")


def rellenar_marcadores(valor, datos: dict[str, str | None]):
    """Sustituye {nombre_gestoria}, {email_contacto} y {telefono} en todos los textos."""
    if isinstance(valor, str):
        for clave in MARCADORES:
            if datos.get(clave):
                valor = valor.replace("{" + clave + "}", datos[clave])
        return valor
    if isinstance(valor, list):
        return [rellenar_marcadores(v, datos) for v in valor]
    if isinstance(valor, dict):
        return {k: rellenar_marcadores(v, datos) for k, v in valor.items()}
    return valor
