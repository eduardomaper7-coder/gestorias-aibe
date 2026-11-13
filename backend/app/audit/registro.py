"""Registro de auditoría: "todo queda registrado"."""
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import RegistroEvento


def registrar(
    session: Session,
    tipo: str,
    actor: str,
    *,
    gestoria_id: uuid.UUID | None = None,
    entidad: str | None = None,
    entidad_id: Any = None,
    resultado: str = "ok",
    detalle: dict | None = None,
) -> RegistroEvento:
    """Añade un evento. Se guarda junto con el resto de cambios de la transacción."""
    if gestoria_id is None:
        gestoria_id = session.info.get("gestoria_id")
    evento = RegistroEvento(
        gestoria_id=gestoria_id,
        tipo=tipo,
        actor=actor,
        entidad=entidad,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        resultado=resultado,
        detalle=detalle or {},
    )
    session.add(evento)
    return evento
