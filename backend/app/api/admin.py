"""Administración de Aibe: alta y gestión de perfiles de gestoría y plantillas."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import actor, admin_aibe, db_sistema
from app.api.esquemas import (
    EstadoAgenteEntrada,
    GestoriaAlta,
    GestoriaCambios,
    GestoriaConEstado,
    GestoriaSalida,
    PlantillaCambios,
    PlantillaDesdeGestoria,
    PlantillaEntrada,
    PlantillaSalida,
    UsuarioAlta,
    UsuarioSalida,
)
from app.audit.registro import registrar
from app.auth.servicio import crear_usuario
from app.connectors.registro import TIPOS_CONECTOR
from app.models import Gestoria, PlantillaPerfil, Usuario
from app.models.enums import Rol
from app.tenancy import servicio as svc

router = APIRouter(prefix="/admin", tags=["Administración de Aibe"])


def _gestoria(db: Session, gestoria_id: uuid.UUID) -> Gestoria:
    g = db.get(Gestoria, gestoria_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gestoría no encontrada")
    return g


def _plantilla(db: Session, plantilla_id: uuid.UUID) -> PlantillaPerfil:
    p = db.get(PlantillaPerfil, plantilla_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plantilla no encontrada")
    return p


def _negocio(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (svc.ErrorNegocio, ValueError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


# ------------------------------------------------------------------ plantillas


@router.get("/plantillas", response_model=list[PlantillaSalida])
def listar_plantillas(_: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    return db.scalars(select(PlantillaPerfil).order_by(PlantillaPerfil.nombre)).all()


@router.post("/plantillas", response_model=PlantillaSalida, status_code=201)
def crear_plantilla(datos: PlantillaEntrada, u: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    p = _negocio(svc.crear_plantilla, db, datos.nombre, datos.descripcion, datos.contenido, actor(u))
    db.commit()
    return p


@router.get("/plantillas/{plantilla_id}", response_model=PlantillaSalida)
def ver_plantilla(plantilla_id: uuid.UUID, _: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    return _plantilla(db, plantilla_id)


@router.patch("/plantillas/{plantilla_id}", response_model=PlantillaSalida)
def editar_plantilla(plantilla_id: uuid.UUID, datos: PlantillaCambios, u: Usuario = Depends(admin_aibe),
                     db: Session = Depends(db_sistema)):
    p = svc.actualizar_plantilla(db, _plantilla(db, plantilla_id), actor(u), nombre=datos.nombre,
                                 descripcion=datos.descripcion, contenido=datos.contenido)
    db.commit()
    return p


@router.delete("/plantillas/{plantilla_id}", status_code=204)
def borrar_plantilla(plantilla_id: uuid.UUID, u: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    p = _plantilla(db, plantilla_id)  # las gestorías creadas con ella no se ven afectadas
    registrar(db, "plantilla.borrada", actor(u), entidad="plantilla", entidad_id=p.id, detalle={"nombre": p.nombre})
    db.delete(p)
    db.commit()


@router.post("/gestorias/{gestoria_id}/guardar-como-plantilla", response_model=PlantillaSalida, status_code=201)
def guardar_como_plantilla(gestoria_id: uuid.UUID, datos: PlantillaDesdeGestoria,
                           u: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    p = _negocio(svc.plantilla_desde_gestoria, db, _gestoria(db, gestoria_id), datos.nombre,
                 datos.descripcion, actor(u))
    db.commit()
    return p


# ------------------------------------------------------------------ gestorías


@router.get("/gestorias", response_model=list[GestoriaConEstado])
def listar_gestorias(_: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    gestorias = db.scalars(select(Gestoria).order_by(Gestoria.nombre)).all()
    return [
        GestoriaConEstado(**GestoriaSalida.model_validate(g).model_dump(), estado=svc.resumen_estado(db, g))
        for g in gestorias
    ]


@router.post("/gestorias", response_model=GestoriaSalida, status_code=201)
def alta_gestoria(datos: GestoriaAlta, u: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    g = _negocio(svc.alta_gestoria, db, actor=actor(u), **datos.model_dump())
    db.commit()
    return g


@router.get("/gestorias/{gestoria_id}", response_model=GestoriaConEstado)
def ver_gestoria(gestoria_id: uuid.UUID, _: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    g = _gestoria(db, gestoria_id)
    return GestoriaConEstado(**GestoriaSalida.model_validate(g).model_dump(), estado=svc.resumen_estado(db, g))


@router.patch("/gestorias/{gestoria_id}", response_model=GestoriaSalida)
def editar_gestoria(gestoria_id: uuid.UUID, datos: GestoriaCambios, u: Usuario = Depends(admin_aibe),
                    db: Session = Depends(db_sistema)):
    g = _gestoria(db, gestoria_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "presupuesto_ia_mensual_eur" in cambios:
        cambios["presupuesto_ia_mensual_eur"] = Decimal(str(cambios["presupuesto_ia_mensual_eur"]))
    for campo, valor in cambios.items():
        setattr(g, campo, valor)
    registrar(db, "gestoria.editada", actor(u), gestoria_id=g.id, entidad="gestoria", entidad_id=g.id,
              detalle={"campos": sorted(cambios)})
    db.commit()
    return g


@router.post("/gestorias/{gestoria_id}/agente", response_model=GestoriaSalida)
def estado_agente(gestoria_id: uuid.UUID, datos: EstadoAgenteEntrada, u: Usuario = Depends(admin_aibe),
                  db: Session = Depends(db_sistema)):
    g = _negocio(svc.cambiar_estado_agente, db, _gestoria(db, gestoria_id), datos.estado, actor(u),
                 por_aibe=True)
    db.commit()
    return g


@router.post("/gestorias/{gestoria_id}/baja", response_model=GestoriaSalida)
def baja(gestoria_id: uuid.UUID, u: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    g = svc.dar_de_baja(db, _gestoria(db, gestoria_id), actor(u))
    db.commit()
    return g


@router.post("/gestorias/{gestoria_id}/reactivar", response_model=GestoriaSalida)
def reactivar(gestoria_id: uuid.UUID, u: Usuario = Depends(admin_aibe), db: Session = Depends(db_sistema)):
    g = svc.reactivar(db, _gestoria(db, gestoria_id), actor(u))
    db.commit()
    return g


@router.post("/gestorias/{gestoria_id}/usuarios", response_model=UsuarioSalida, status_code=201)
def alta_usuario(gestoria_id: uuid.UUID, datos: UsuarioAlta, u: Usuario = Depends(admin_aibe),
                 db: Session = Depends(db_sistema)):
    if datos.rol == Rol.ADMIN_AIBE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Los administradores de Aibe se crean desde la consola")
    _gestoria(db, gestoria_id)
    nuevo = _negocio(crear_usuario, db, email=datos.email, nombre=datos.nombre, password=datos.password,
                     rol=datos.rol, actor=actor(u), gestoria_id=gestoria_id)
    db.commit()
    return nuevo


@router.get("/conectores")
def tipos_de_conector(_: Usuario = Depends(admin_aibe)):
    return {k: {"descripcion": v["descripcion"], "accesos": v["accesos"]} for k, v in TIPOS_CONECTOR.items()}
