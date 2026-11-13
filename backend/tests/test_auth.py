import pyotp
from sqlalchemy import select

from app.core.db import sesion_sistema
from app.models import RegistroEvento
from tests.conftest import entrar


def test_login_correcto_e_incorrecto(cliente_http, admin_aibe):
    r = cliente_http.post("/auth/login", json={"email": admin_aibe["email"], "password": "mala"})
    assert r.status_code == 401
    assert cliente_http.get("/auth/yo").status_code == 401
    entrar(cliente_http, **admin_aibe)
    assert cliente_http.get("/auth/yo").json()["rol"] == "admin_aibe"
    with sesion_sistema() as s:
        tipos = set(s.scalars(select(RegistroEvento.tipo)))
    assert {"auth.login_fallido", "auth.login"} <= tipos


def test_cookie_manipulada_no_vale(cliente_http, admin_aibe):
    entrar(cliente_http, **admin_aibe)
    valor = cliente_http.cookies.get("aibe_sesion")
    cliente_http.cookies.clear()
    cliente_http.cookies.set("aibe_sesion", valor[:-3] + ("abc" if not valor.endswith("abc") else "xyz"))
    assert cliente_http.get("/auth/yo").status_code == 401


def test_admin_debe_activar_doble_factor(cliente_http, admin_aibe, ajustes):
    ajustes(exigir_2fa_admin="true")
    entrar(cliente_http, **admin_aibe)
    r = cliente_http.get("/admin/gestorias")
    assert r.status_code == 403 and "doble factor" in r.json()["detail"]

    uri = cliente_http.post("/auth/2fa/iniciar").json()["uri"]
    totp = pyotp.parse_uri(uri)
    assert cliente_http.post("/auth/2fa/confirmar", json={"codigo": "000000"}).status_code == 400
    r = cliente_http.post("/auth/2fa/confirmar", json={"codigo": totp.now()})
    assert r.status_code == 200 and r.json()["totp_activo"] is True
    assert cliente_http.get("/admin/gestorias").status_code == 200

    # a partir de ahora el código es obligatorio para entrar
    cliente_http.cookies.clear()
    r = cliente_http.post("/auth/login", json={"email": admin_aibe["email"], "password": admin_aibe["password"]})
    assert r.status_code == 401
    entrar(cliente_http, admin_aibe["email"], admin_aibe["password"], totp.now())


def test_usuario_de_gestoria_no_puede_usar_admin_ni_un_gestor_cambiar_config(dos_gestorias, cliente_http,
                                                                            admin_aibe):
    a = dos_gestorias["a"]
    entrar(cliente_http, **admin_aibe)
    r = cliente_http.post(f"/admin/gestorias/{a['gestoria_id']}/usuarios",
                          json={"email": "gestor@a.example", "nombre": "Gestor", "password": "contraseña-gestor-1",
                                "rol": "gestor"})
    assert r.status_code == 201
    r = cliente_http.post(f"/admin/gestorias/{a['gestoria_id']}/usuarios",
                          json={"email": "malo@a.example", "nombre": "x", "password": "contraseña-gestor-1",
                                "rol": "admin_aibe"})
    assert r.status_code == 400

    cliente_http.cookies.clear()
    entrar(cliente_http, "gestor@a.example", "contraseña-gestor-1")
    assert cliente_http.get("/gestoria/conocimiento").status_code == 200  # puede consultar
    perfil = cliente_http.get("/gestoria/perfil").json()
    assert cliente_http.put("/gestoria/config", json=perfil["config"]).status_code == 403  # no puede cambiar
    assert cliente_http.post("/gestoria/agente", json={"estado": "pausado"}).status_code == 403
