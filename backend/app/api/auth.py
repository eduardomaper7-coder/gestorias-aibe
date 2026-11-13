from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import db_sistema, usuario_actual
from app.api.esquemas import Activar2faSalida, CodigoEntrada, LoginEntrada, UsuarioSalida
from app.auth.servicio import (
    NOMBRE_COOKIE,
    ErrorAutenticacion,
    autenticar,
    confirmar_2fa,
    crear_token_sesion,
    iniciar_2fa,
)
from app.core.config import get_settings
from app.models import Usuario

router = APIRouter(prefix="/auth", tags=["Inicio de sesión"])


def _poner_cookie(response: Response, usuario: Usuario) -> None:
    ajustes = get_settings()
    response.set_cookie(
        NOMBRE_COOKIE, crear_token_sesion(usuario), httponly=True, samesite="lax",
        secure=ajustes.cookies_seguras, max_age=ajustes.duracion_sesion_horas * 3600,
    )


@router.post("/login", response_model=UsuarioSalida)
def login(datos: LoginEntrada, response: Response, db: Session = Depends(db_sistema)):
    try:
        usuario = autenticar(db, datos.email, datos.password, datos.codigo_2fa)
    except ErrorAutenticacion as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    db.commit()
    _poner_cookie(response, usuario)
    return usuario


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(NOMBRE_COOKIE)


@router.get("/yo", response_model=UsuarioSalida)
def yo(usuario: Usuario = Depends(usuario_actual)):
    return usuario


@router.post("/2fa/iniciar", response_model=Activar2faSalida)
def iniciar_doble_factor(usuario: Usuario = Depends(usuario_actual), db: Session = Depends(db_sistema)):
    usuario = db.merge(usuario)
    uri = iniciar_2fa(db, usuario)
    db.commit()
    return Activar2faSalida(uri=uri)


@router.post("/2fa/confirmar", response_model=UsuarioSalida)
def confirmar_doble_factor(datos: CodigoEntrada, response: Response,
                           usuario: Usuario = Depends(usuario_actual), db: Session = Depends(db_sistema)):
    usuario = db.merge(usuario)
    try:
        confirmar_2fa(db, usuario, datos.codigo)
    except ErrorAutenticacion as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    _poner_cookie(response, usuario)  # nueva cookie: las sesiones anteriores quedan cerradas
    return usuario
