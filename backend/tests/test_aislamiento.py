"""Pruebas de aislamiento total entre gestorías.

Si alguna de estas pruebas falla, NO se debe desplegar: significaría que una
gestoría podría ver o tocar datos de otra.
"""
import pytest
from sqlalchemy import inspect, select, text, update
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.db import engine_app, engine_sistema, sesion_gestoria
from app.models import (
    ClienteFinal,
    EntradaConocimiento,
    Gestoria,
    RegistroEvento,
    TemaSensible,
    UsoIA,
    Usuario,
    tablas_de_gestoria,
)
from app.models.enums import Rol
from app.tenancy.servicio import identificar_cliente_por_email
from tests.conftest import entrar


def test_todas_las_tablas_con_gestoria_tienen_rls():
    """Protege también el futuro: una tabla nueva con gestoria_id sin RLS hace fallar esta prueba."""
    insp = inspect(engine_sistema())
    con_columna = {t for t in insp.get_table_names() if "gestoria_id" in {c["name"] for c in insp.get_columns(t)}}
    # correcciones_receta guarda de qué gestoría vino un fallo, pero no la consulta la aplicación de gestoría
    con_columna -= {"correcciones_receta"}
    assert con_columna == set(tablas_de_gestoria())
    with engine_sistema().connect() as c:
        con_rls = set(c.scalars(text("SELECT relname FROM pg_class WHERE relrowsecurity")))
    assert con_columna | {"gestorias"} <= con_rls


def test_cada_gestoria_solo_ve_sus_datos(dos_gestorias):
    a, b = dos_gestorias["a"], dos_gestorias["b"]
    with sesion_gestoria(a["gestoria_id"]) as s:
        assert [g.id for g in s.scalars(select(Gestoria))] == [a["gestoria_id"]]
        clientes = s.scalars(select(ClienteFinal)).all()
        assert [c.id for c in clientes] == [a["cliente_id"]]
        assert all(e.gestoria_id == a["gestoria_id"] for e in s.scalars(select(EntradaConocimiento)))
        assert all(t.gestoria_id == a["gestoria_id"] for t in s.scalars(select(TemaSensible)))
        assert [u.email for u in s.scalars(select(Usuario))] == [a["usuario_email"]]
        assert all(r.gestoria_id == a["gestoria_id"] for r in s.scalars(select(RegistroEvento)))
        # buscar directamente por id un dato de B: no existe para A
        assert s.get(ClienteFinal, b["cliente_id"]) is None


def test_sin_gestoria_fijada_no_se_ve_nada(dos_gestorias):
    with Session(engine_app()) as s:
        assert s.scalars(select(ClienteFinal)).all() == []
        assert s.scalars(select(Gestoria)).all() == []


def test_no_se_puede_escribir_en_otra_gestoria(dos_gestorias):
    a, b = dos_gestorias["a"], dos_gestorias["b"]
    with sesion_gestoria(a["gestoria_id"]) as s:
        s.add(ClienteFinal(gestoria_id=b["gestoria_id"], nombre="Intruso"))
        with pytest.raises(ProgrammingError, match="row-level security"):
            s.flush()
    with sesion_gestoria(a["gestoria_id"]) as s:
        r = s.execute(update(ClienteFinal).where(ClienteFinal.id == b["cliente_id"]).values(nombre="Cambiado"))
        assert r.rowcount == 0
        s.commit()
    with sesion_gestoria(b["gestoria_id"]) as s:
        assert s.get(ClienteFinal, b["cliente_id"]).nombre == "Cliente de b"


def test_identificar_cliente_no_cruza_gestorias(dos_gestorias):
    a = dos_gestorias["a"]
    with sesion_gestoria(a["gestoria_id"]) as s:
        assert identificar_cliente_por_email(s, a["gestoria_id"], "CLIENTE@a.example").id == a["cliente_id"]
        assert identificar_cliente_por_email(s, a["gestoria_id"], "cliente@b.example") is None


def test_auditoria_y_costes_no_se_pueden_modificar(dos_gestorias):
    a = dos_gestorias["a"]
    with sesion_gestoria(a["gestoria_id"]) as s:
        s.add(UsoIA(gestoria_id=a["gestoria_id"], tarea="prueba", proveedor="falso", modelo="x"))
        s.commit()
    for sql in ("UPDATE registro_eventos SET resultado = 'ok'", "DELETE FROM registro_eventos",
                "UPDATE usos_ia SET coste_eur = 0", "DELETE FROM usos_ia"):
        with sesion_gestoria(a["gestoria_id"]) as s, pytest.raises(DBAPIError, match="permission denied"):
            s.execute(text(sql))


def test_una_gestoria_no_puede_cambiar_su_presupuesto_ni_crear_admins_de_aibe(dos_gestorias):
    a = dos_gestorias["a"]
    with sesion_gestoria(a["gestoria_id"]) as s, pytest.raises(DBAPIError, match="permission denied"):
        s.execute(update(Gestoria).values(presupuesto_ia_mensual_eur=99999))
    with sesion_gestoria(a["gestoria_id"]) as s:
        s.add(Usuario(gestoria_id=a["gestoria_id"], email="x@x.example", nombre="x", hash_password="x",
                      rol=Rol.ADMIN_AIBE))
        with pytest.raises(ProgrammingError, match="row-level security"):
            s.flush()


def test_secretos_cifrados_atados_a_su_gestoria(dos_gestorias):
    a, b = dos_gestorias["a"], dos_gestorias["b"]
    cifrado = crypto.cifrar("contraseña-del-buzon", str(a["gestoria_id"]))
    assert "contraseña" not in cifrado
    assert crypto.descifrar(cifrado, str(a["gestoria_id"])) == "contraseña-del-buzon"
    with pytest.raises(crypto.ErrorCifrado):
        crypto.descifrar(cifrado, str(b["gestoria_id"]))


def test_api_una_gestoria_no_accede_a_otra(dos_gestorias, cliente_http):
    a, b = dos_gestorias["a"], dos_gestorias["b"]
    entrar(cliente_http, a["usuario_email"], "contraseña-segura-1")

    r = cliente_http.get("/gestoria/clientes")
    assert [c["id"] for c in r.json()] == [str(a["cliente_id"])]
    assert cliente_http.get(f"/gestoria/clientes/{b['cliente_id']}").status_code == 404

    with sesion_gestoria(b["gestoria_id"]) as s:
        entrada_b = s.scalar(select(EntradaConocimiento.id))
        tema_b = s.scalar(select(TemaSensible.id))
    cambio = {"categoria": "faq", "titulo": "hackeo", "contenido": "x"}
    assert cliente_http.put(f"/gestoria/conocimiento/{entrada_b}", json=cambio).status_code == 404
    assert cliente_http.delete(f"/gestoria/conocimiento/{entrada_b}").status_code == 404
    assert cliente_http.delete(f"/gestoria/temas-sensibles/{tema_b}").status_code == 404
    assert cliente_http.get("/gestoria/perfil").json()["id"] == str(a["gestoria_id"])
    # y no puede entrar en la administración de Aibe
    assert cliente_http.get("/admin/gestorias").status_code == 403
