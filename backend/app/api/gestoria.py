"""Panel de cada gestoría. Todo lo de aquí usa una sesión limitada a SU gestoría (RLS)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import actor, admin_gestoria, db_gestoria, usuario_gestoria
from app.api.esquemas import (
    ClienteEntrada,
    ClienteSalida,
    ConocimientoEntrada,
    ConocimientoSalida,
    EstadoAgenteEntrada,
    GestoriaSalida,
    TemaSensibleEntrada,
    TemaSensibleSalida,
    UsoIAResumen,
)
from app.audit.registro import registrar
from app.llm.servicio import resumen_uso
from app.models import ClienteFinal, EntradaConocimiento, Gestoria, TemaSensible, Usuario
from app.tenancy import servicio as svc
from app.tenancy.esquemas import ConfigGestoria

router = APIRouter(prefix="/gestoria", tags=["Panel de la gestoría"])


def _mi_gestoria(db: Session, u: Usuario) -> Gestoria:
    g = db.get(Gestoria, u.gestoria_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gestoría no encontrada")
    return g


def _cliente_salida(c: ClienteFinal) -> ClienteSalida:
    return ClienteSalida(id=c.id, nombre=c.nombre, nif=c.nif, tipo=c.tipo, telefono=c.telefono,
                         id_externo=c.id_externo, activo=c.activo,
                         emails=[x.valor for x in c.contactos if x.canal == "email"])


# ------------------------------------------------------------------ perfil y agente


@router.get("/perfil", response_model=GestoriaSalida)
def mi_perfil(u: Usuario = Depends(usuario_gestoria), db: Session = Depends(db_gestoria)):
    return _mi_gestoria(db, u)


@router.put("/config", response_model=GestoriaSalida)
def cambiar_config(config: ConfigGestoria, u: Usuario = Depends(admin_gestoria), db: Session = Depends(db_gestoria)):
    g = svc.actualizar_config(db, _mi_gestoria(db, u), config, actor(u))
    db.commit()
    return g


@router.post("/agente", response_model=GestoriaSalida)
def estado_agente(datos: EstadoAgenteEntrada, u: Usuario = Depends(admin_gestoria),
                  db: Session = Depends(db_gestoria)):
    try:
        g = svc.cambiar_estado_agente(db, _mi_gestoria(db, u), datos.estado, actor(u), por_aibe=False)
    except svc.ErrorNegocio as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return g


@router.get("/uso-ia", response_model=UsoIAResumen)
def uso_ia(u: Usuario = Depends(usuario_gestoria)):
    return resumen_uso(u.gestoria_id)


# ------------------------------------------------------------------ base de conocimiento


@router.get("/conocimiento", response_model=list[ConocimientoSalida])
def listar_conocimiento(_: Usuario = Depends(usuario_gestoria), db: Session = Depends(db_gestoria)):
    return db.scalars(select(EntradaConocimiento).order_by(EntradaConocimiento.orden, EntradaConocimiento.titulo)).all()


@router.post("/conocimiento", response_model=ConocimientoSalida, status_code=201)
def crear_conocimiento(datos: ConocimientoEntrada, u: Usuario = Depends(admin_gestoria),
                       db: Session = Depends(db_gestoria)):
    e = EntradaConocimiento(gestoria_id=u.gestoria_id, **datos.model_dump())
    db.add(e)
    db.flush()
    registrar(db, "conocimiento.creado", actor(u), entidad="conocimiento", entidad_id=e.id)
    db.commit()
    return e


def _entrada(db: Session, entrada_id: uuid.UUID) -> EntradaConocimiento:
    e = db.get(EntradaConocimiento, entrada_id)  # la RLS hace que otra gestoría devuelva "no encontrado"
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrada no encontrada")
    return e


@router.put("/conocimiento/{entrada_id}", response_model=ConocimientoSalida)
def editar_conocimiento(entrada_id: uuid.UUID, datos: ConocimientoEntrada, u: Usuario = Depends(admin_gestoria),
                        db: Session = Depends(db_gestoria)):
    e = _entrada(db, entrada_id)
    for campo, valor in datos.model_dump().items():
        setattr(e, campo, valor)
    registrar(db, "conocimiento.editado", actor(u), entidad="conocimiento", entidad_id=e.id)
    db.commit()
    return e


@router.delete("/conocimiento/{entrada_id}", status_code=204)
def borrar_conocimiento(entrada_id: uuid.UUID, u: Usuario = Depends(admin_gestoria),
                        db: Session = Depends(db_gestoria)):
    e = _entrada(db, entrada_id)
    registrar(db, "conocimiento.borrado", actor(u), entidad="conocimiento", entidad_id=e.id,
              detalle={"titulo": e.titulo})
    db.delete(e)
    db.commit()


# ------------------------------------------------------------------ temas sensibles


@router.get("/temas-sensibles", response_model=list[TemaSensibleSalida])
def listar_temas(_: Usuario = Depends(usuario_gestoria), db: Session = Depends(db_gestoria)):
    return db.scalars(select(TemaSensible).order_by(TemaSensible.tema)).all()


@router.post("/temas-sensibles", response_model=TemaSensibleSalida, status_code=201)
def crear_tema(datos: TemaSensibleEntrada, u: Usuario = Depends(admin_gestoria), db: Session = Depends(db_gestoria)):
    t = TemaSensible(gestoria_id=u.gestoria_id, **datos.model_dump())
    db.add(t)
    db.flush()
    registrar(db, "tema_sensible.creado", actor(u), entidad="tema_sensible", entidad_id=t.id)
    db.commit()
    return t


@router.delete("/temas-sensibles/{tema_id}", status_code=204)
def borrar_tema(tema_id: uuid.UUID, u: Usuario = Depends(admin_gestoria), db: Session = Depends(db_gestoria)):
    t = db.get(TemaSensible, tema_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tema no encontrado")
    registrar(db, "tema_sensible.borrado", actor(u), entidad="tema_sensible", entidad_id=t.id,
              detalle={"tema": t.tema})
    db.delete(t)
    db.commit()


# ------------------------------------------------------------------ clientes finales


@router.get("/clientes", response_model=list[ClienteSalida])
def listar_clientes(_: Usuario = Depends(usuario_gestoria), db: Session = Depends(db_gestoria)):
    return [_cliente_salida(c) for c in db.scalars(select(ClienteFinal).order_by(ClienteFinal.nombre))]


@router.post("/clientes", response_model=ClienteSalida, status_code=201)
def crear_cliente(datos: ClienteEntrada, u: Usuario = Depends(usuario_gestoria), db: Session = Depends(db_gestoria)):
    try:
        c = svc.crear_cliente(db, u.gestoria_id, actor=actor(u), **datos.model_dump())
    except svc.ErrorNegocio as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return _cliente_salida(c)


@router.get("/clientes/{cliente_id}", response_model=ClienteSalida)
def ver_cliente(cliente_id: uuid.UUID, _: Usuario = Depends(usuario_gestoria), db: Session = Depends(db_gestoria)):
    c = db.get(ClienteFinal, cliente_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    return _cliente_salida(c)
