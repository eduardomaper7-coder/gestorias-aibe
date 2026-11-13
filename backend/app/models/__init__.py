from app.models.base import Base
from app.models.comunicacion import Adjunto, Conversacion, Derivacion, Mensaje
from app.models.enums import *  # noqa: F401,F403
from app.models.operacion import (
    CorreccionReceta,
    EjecucionTarea,
    Receta,
    RegistroEvento,
    TareaProgramada,
    UsoIA,
)
from app.models.tenancy import (
    Buzon,
    ClienteFinal,
    ContactoCliente,
    EntradaConocimiento,
    Gestoria,
    PlantillaPerfil,
    ProgramaGestoria,
    Puente,
    TemaSensible,
    Usuario,
)


def tablas_de_gestoria() -> list[str]:
    """Tablas con datos de gestorías (todas deben tener RLS activada)."""
    return sorted(
        m.class_.__tablename__
        for m in Base.registry.mappers
        if getattr(m.class_, "__es_de_gestoria__", False)
    )


__all__ = [
    "Base",
    "Adjunto",
    "Buzon",
    "ClienteFinal",
    "ContactoCliente",
    "Conversacion",
    "CorreccionReceta",
    "Derivacion",
    "EjecucionTarea",
    "EntradaConocimiento",
    "Gestoria",
    "Mensaje",
    "PlantillaPerfil",
    "ProgramaGestoria",
    "Puente",
    "Receta",
    "RegistroEvento",
    "TareaProgramada",
    "TemaSensible",
    "Usuario",
    "UsoIA",
    "tablas_de_gestoria",
]
