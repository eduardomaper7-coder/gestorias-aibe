from sqlalchemy import select

from app.core.db import sesion_gestoria, sesion_sistema
from app.models import EntradaConocimiento, Gestoria, PlantillaPerfil, RegistroEvento, TareaProgramada, TemaSensible
from app.models.enums import EstadoAgente, EstadoAlta
from app.tenancy.esquemas import ContenidoPlantilla
from tests.conftest import entrar


def test_plantilla_fiscal_autonomos_es_valida_y_se_aplica(dos_gestorias):
    a = dos_gestorias["a"]
    with sesion_gestoria(a["gestoria_id"]) as s:
        g = s.get(Gestoria, a["gestoria_id"])
        assert g.estado_agente == EstadoAgente.SIMULACION  # nunca empieza enviando de verdad
        assert g.config["firma"] == "Un saludo,\nGestoría A"  # marcador {nombre_gestoria} rellenado
        assert "Gestoría A" in g.config["agente"]["mensaje_derivacion"]
        entradas = s.scalars(select(EntradaConocimiento)).all()
        assert len(entradas) >= 8
        assert any("info@a.example" in e.contenido for e in entradas)
        assert not any("{" + "email_contacto}" in e.contenido for e in entradas)
        assert len(s.scalars(select(TemaSensible)).all()) == 5
        tarea = s.scalar(select(TareaProgramada))
        assert tarea.tipo == "recordatorio_cierre_trimestral" and tarea.config["dias_antes"] == 7
        assert s.scalar(select(RegistroEvento).where(RegistroEvento.tipo == "gestoria.alta"))


def test_cambiar_la_plantilla_no_altera_gestorias_existentes(dos_gestorias, cliente_http, admin_aibe):
    entrar(cliente_http, **admin_aibe)
    plantilla = cliente_http.get("/admin/plantillas").json()[0]
    contenido = ContenidoPlantilla.model_validate(plantilla["contenido"])
    contenido.config.horario = "Solo por la mañana"
    r = cliente_http.patch(f"/admin/plantillas/{plantilla['id']}", json={"contenido": contenido.model_dump(mode="json")})
    assert r.status_code == 200 and r.json()["version"] == 2
    with sesion_sistema() as s:
        g = s.get(Gestoria, dos_gestorias["a"]["gestoria_id"])
        assert g.config["horario"] != "Solo por la mañana"


def test_alta_desde_api_y_guardar_como_plantilla(cliente_http, admin_aibe):
    entrar(cliente_http, **admin_aibe)
    from app.core.db import sesion_sistema as ss
    from app.tenancy.servicio import cargar_plantillas_base

    with ss() as s:
        cargar_plantillas_base(s)
        s.commit()
    plantilla_id = cliente_http.get("/admin/plantillas").json()[0]["id"]
    r = cliente_http.post("/admin/gestorias", json={"nombre": "Gestoría Nueva", "email_contacto": "info@nueva.example",
                                                    "plantilla_id": plantilla_id})
    assert r.status_code == 201, r.text
    nueva = r.json()
    assert nueva["slug"] == "gestoria-nueva" and nueva["estado_agente"] == "simulacion"

    # misma denominación -> identificador distinto
    r2 = cliente_http.post("/admin/gestorias", json={"nombre": "Gestoría Nueva"})
    assert r2.json()["slug"] == "gestoria-nueva-2"

    r = cliente_http.post(f"/admin/gestorias/{nueva['id']}/guardar-como-plantilla",
                          json={"nombre": "Asesoría laboral (base)"})
    assert r.status_code == 201
    assert len(r.json()["contenido"]["temas_sensibles"]) == 5

    listado = cliente_http.get("/admin/gestorias").json()
    assert {g["nombre"] for g in listado} == {"Gestoría Nueva"}
    assert listado[0]["estado"]["coste_ia_mes_eur"] == 0


def test_activar_pausar_y_baja(dos_gestorias, cliente_http, admin_aibe):
    a = dos_gestorias["a"]
    # la gestoría no puede pasar a envío real sin que Aibe lo autorice la primera vez
    entrar(cliente_http, a["usuario_email"], "contraseña-segura-1")
    r = cliente_http.post("/gestoria/agente", json={"estado": "activo"})
    assert r.status_code == 409
    assert cliente_http.post("/gestoria/agente", json={"estado": "pausado"}).json()["estado_agente"] == "pausado"

    cliente_http.post("/auth/logout")
    cliente_http.cookies.clear()
    entrar(cliente_http, **admin_aibe)
    r = cliente_http.post(f"/admin/gestorias/{a['gestoria_id']}/agente", json={"estado": "activo"})
    assert r.json()["estado_agente"] == "activo" and r.json()["activacion_autorizada"] is True

    r = cliente_http.post(f"/admin/gestorias/{a['gestoria_id']}/baja")
    assert r.json()["estado_alta"] == "baja" and r.json()["estado_agente"] == "pausado"
    assert cliente_http.post(f"/admin/gestorias/{a['gestoria_id']}/agente", json={"estado": "activo"}).status_code == 409

    # los datos siguen ahí: la baja no borra nada
    with sesion_gestoria(a["gestoria_id"]) as s:
        assert s.get(Gestoria, a["gestoria_id"]).estado_alta == EstadoAlta.BAJA
        assert s.scalars(select(EntradaConocimiento)).all()

    # una vez autorizada, la gestoría sí puede reanudar ella misma
    r = cliente_http.post(f"/admin/gestorias/{a['gestoria_id']}/reactivar")
    assert r.json()["estado_agente"] == "simulacion"
    cliente_http.cookies.clear()
    entrar(cliente_http, a["usuario_email"], "contraseña-segura-1")
    assert cliente_http.post("/gestoria/agente", json={"estado": "activo"}).json()["estado_agente"] == "activo"


def test_config_invalida_se_rechaza(dos_gestorias, cliente_http):
    entrar(cliente_http, dos_gestorias["a"]["usuario_email"], "contraseña-segura-1")
    perfil = cliente_http.get("/gestoria/perfil").json()
    config = perfil["config"]
    config["agente"]["limite_envios_cliente_dia"] = 0
    assert cliente_http.put("/gestoria/config", json=config).status_code == 422
    config["agente"]["limite_envios_cliente_dia"] = 5
    config["campo_inventado"] = True
    assert cliente_http.put("/gestoria/config", json=config).status_code == 422
    del config["campo_inventado"]
    r = cliente_http.put("/gestoria/config", json=config)
    assert r.status_code == 200 and r.json()["config"]["agente"]["limite_envios_cliente_dia"] == 5


def test_clientes_por_api(dos_gestorias, cliente_http):
    entrar(cliente_http, dos_gestorias["a"]["usuario_email"], "contraseña-segura-1")
    r = cliente_http.post("/gestoria/clientes", json={"nombre": "Ana", "nif": "12345678z",
                                                      "emails": ["Ana@Correo.example"]})
    assert r.status_code == 201
    assert r.json()["nif"] == "12345678Z" and r.json()["emails"] == ["ana@correo.example"]
    # mismo correo en otro cliente de la misma gestoría: no
    r = cliente_http.post("/gestoria/clientes", json={"nombre": "Otra", "emails": ["ana@correo.example"]})
    assert r.status_code == 409


def test_plantillas_base_no_se_duplican():
    from app.tenancy.servicio import cargar_plantillas_base

    with sesion_sistema() as s:
        assert len(cargar_plantillas_base(s)) == 1
        s.commit()
        assert cargar_plantillas_base(s) == []
        assert len(s.scalars(select(PlantillaPerfil)).all()) == 1
