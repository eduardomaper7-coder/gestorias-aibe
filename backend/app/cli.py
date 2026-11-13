"""Comandos de consola.

  python -m app.cli generar-claves                 claves nuevas para el fichero .env
  python -m app.cli crear-admin --email ... --nombre ...   administrador de Aibe
  python -m app.cli cargar-plantillas              plantillas incluidas (p. ej. fiscal de autónomos)
  python -m app.cli datos-demo                     dos gestorías de ejemplo con usuarios y clientes
  python -m app.cli probar-ia --gestoria <slug>    una llamada real y barata a Claude (muestra el coste)
"""
import argparse
import getpass
import secrets
import sys

from sqlalchemy import select

from app.core.crypto import generar_clave
from app.core.db import sesion_sistema
from app.models import Gestoria, PlantillaPerfil
from app.models.enums import Rol, TipoCliente


def cmd_generar_claves(_):
    print("# Copie estas líneas en su fichero .env (y guárdelas en un gestor de contraseñas)")
    print(f"SECRET_KEY={secrets.token_urlsafe(48)}")
    print(f"CLAVE_MAESTRA_CIFRADO={generar_clave()}")
    print(f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}")
    print(f"POSTGRES_APP_PASSWORD={secrets.token_urlsafe(24)}")


def cmd_crear_admin(args):
    from app.auth.servicio import crear_usuario

    password = args.password or getpass.getpass("Contraseña (mín. 10 caracteres): ")
    with sesion_sistema() as db:
        u = crear_usuario(db, email=args.email, nombre=args.nombre, password=password, rol=Rol.ADMIN_AIBE,
                          actor="consola")
        db.commit()
        print(f"Administrador creado: {u.email}")
        print("Al entrar, active el doble factor en /auth/2fa/iniciar y /auth/2fa/confirmar.")


def cmd_cargar_plantillas(_):
    from app.tenancy.servicio import cargar_plantillas_base

    with sesion_sistema() as db:
        creadas = cargar_plantillas_base(db, "consola")
        db.commit()
        print(f"Plantillas creadas: {[p.nombre for p in creadas] or 'ninguna (ya existían)'}")


DEMO = [
    {
        "gestoria": {"nombre": "Gestoría Ejemplo Norte", "nif": "B00000001",
                     "email_contacto": "info@gestoria-norte.example", "telefono": "900 000 001"},
        "usuario": ("responsable@gestoria-norte.example", "Lucía Responsable"),
        "clientes": [
            ("Juan Pérez Autónomo", "00000001R", ["juan.perez@cliente.example"]),
            ("María López Diseño", "00000002W", ["maria@disenolopez.example"]),
        ],
    },
    {
        "gestoria": {"nombre": "Asesoría Demo Sur", "nif": "B00000002",
                     "email_contacto": "hola@asesoria-sur.example", "telefono": "900 000 002"},
        "usuario": ("responsable@asesoria-sur.example", "Pedro Responsable"),
        "clientes": [("Carlos Ruiz Fontanero", "00000003A", ["carlos.ruiz@cliente.example"])],
    },
]


def cmd_datos_demo(_):
    from app.auth.servicio import crear_usuario
    from app.tenancy.servicio import alta_gestoria, cargar_plantillas_base, crear_cliente

    with sesion_sistema() as db:
        cargar_plantillas_base(db, "consola")
        db.flush()
        plantilla = db.scalar(select(PlantillaPerfil).where(PlantillaPerfil.nombre == "Gestoría fiscal de autónomos"))
        for d in DEMO:
            if db.scalar(select(Gestoria.id).where(Gestoria.nombre == d["gestoria"]["nombre"])):
                print(f"Ya existe: {d['gestoria']['nombre']}")
                continue
            g = alta_gestoria(db, actor="consola", plantilla_id=plantilla.id, **d["gestoria"])
            password = secrets.token_urlsafe(10)
            crear_usuario(db, email=d["usuario"][0], nombre=d["usuario"][1], password=password,
                          rol=Rol.ADMIN_GESTORIA, actor="consola", gestoria_id=g.id)
            for nombre, nif, emails in d["clientes"]:
                crear_cliente(db, g.id, nombre=nombre, nif=nif, emails=emails, tipo=TipoCliente.AUTONOMO,
                              actor="consola")
            print(f"Gestoría «{g.nombre}» (modo {g.estado_agente.value}) · usuario {d['usuario'][0]} · "
                  f"contraseña {password}")
        db.commit()


def cmd_probar_ia(args):
    from app.llm.base import BloqueSistema, PeticionLLM
    from app.llm.servicio import ServicioIA

    with sesion_sistema() as db:
        g = db.scalar(select(Gestoria).where(Gestoria.slug == args.gestoria))
        if not g:
            sys.exit(f"No existe la gestoría con identificador «{args.gestoria}»")
    servicio = ServicioIA(g.id)
    r = servicio.completar(PeticionLLM(
        tarea="prueba", nivel="barato", max_tokens=50,
        sistema=[BloqueSistema("Responde en una sola frase corta en español.")],
        mensajes=[{"role": "user", "content": "Di hola y confirma que funcionas."}],
    ))
    print(f"Respuesta: {r.texto}")
    print(f"Modelo: {r.modelo} · tokens entrada {r.uso.entrada} · salida {r.uso.salida}")
    print("El coste ha quedado registrado en usos_ia (consúltelo en /gestoria/uso-ia o en /admin/gestorias).")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(required=True)
    sub.add_parser("generar-claves").set_defaults(fn=cmd_generar_claves)
    a = sub.add_parser("crear-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--nombre", required=True)
    a.add_argument("--password", help="si no se indica, se pide de forma oculta")
    a.set_defaults(fn=cmd_crear_admin)
    sub.add_parser("cargar-plantillas").set_defaults(fn=cmd_cargar_plantillas)
    sub.add_parser("datos-demo").set_defaults(fn=cmd_datos_demo)
    ia = sub.add_parser("probar-ia")
    ia.add_argument("--gestoria", required=True, help="identificador (slug), p. ej. gestoria-ejemplo-norte")
    ia.set_defaults(fn=cmd_probar_ia)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
