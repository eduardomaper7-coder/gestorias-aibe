"""Operaciones sobre perfiles de gestoría y plantillas."""
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.registro import registrar
from app.core.config import get_settings
from app.models import (
    Buzon,
    ClienteFinal,
    ContactoCliente,
    Derivacion,
    EntradaConocimiento,
    Gestoria,
    Mensaje,
    PlantillaPerfil,
    ProgramaGestoria,
    Puente,
    TareaProgramada,
    TemaSensible,
    UsoIA,
)
from app.models.enums import (
    Direccion,
    EstadoAgente,
    EstadoAlta,
    EstadoConexion,
    EstadoDerivacion,
    TipoCliente,
)
from app.tenancy.esquemas import ConfigGestoria, ContenidoPlantilla, rellenar_marcadores

RUTA_PLANTILLAS_BASE = Path(__file__).parent / "plantillas_base"


class ErrorNegocio(Exception):
    """Error que se puede mostrar tal cual al usuario."""


# ---------------------------------------------------------------- utilidades


def slugify(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")[:60] or "gestoria"


def _slug_libre(session: Session, base: str) -> str:
    slug, n = base, 2
    while session.scalar(select(Gestoria.id).where(Gestoria.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def inicio_mes(ahora: datetime | None = None) -> datetime:
    ahora = ahora or datetime.now(UTC)
    return ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------- plantillas


def crear_plantilla(
    session: Session, nombre: str, descripcion: str | None, contenido: ContenidoPlantilla, actor: str
) -> PlantillaPerfil:
    if session.scalar(select(PlantillaPerfil.id).where(PlantillaPerfil.nombre == nombre)):
        raise ErrorNegocio(f"Ya existe una plantilla llamada «{nombre}»")
    plantilla = PlantillaPerfil(
        nombre=nombre, descripcion=descripcion, contenido=contenido.model_dump(mode="json"), version=1
    )
    session.add(plantilla)
    session.flush()
    registrar(session, "plantilla.creada", actor, entidad="plantilla", entidad_id=plantilla.id)
    return plantilla


def actualizar_plantilla(
    session: Session,
    plantilla: PlantillaPerfil,
    actor: str,
    *,
    nombre: str | None = None,
    descripcion: str | None = None,
    contenido: ContenidoPlantilla | None = None,
) -> PlantillaPerfil:
    if nombre is not None:
        plantilla.nombre = nombre
    if descripcion is not None:
        plantilla.descripcion = descripcion
    if contenido is not None:
        plantilla.contenido = contenido.model_dump(mode="json")
    plantilla.version += 1  # las gestorías ya creadas no cambian: la plantilla solo es el punto de partida
    registrar(session, "plantilla.actualizada", actor, entidad="plantilla", entidad_id=plantilla.id,
              detalle={"version": plantilla.version})
    return plantilla


def cargar_plantillas_base(session: Session, actor: str = "sistema") -> list[PlantillaPerfil]:
    """Crea las plantillas incluidas en el producto si aún no existen."""
    creadas = []
    for fichero in sorted(RUTA_PLANTILLAS_BASE.glob("*.yaml")):
        datos = yaml.safe_load(fichero.read_text(encoding="utf-8"))
        if session.scalar(select(PlantillaPerfil.id).where(PlantillaPerfil.nombre == datos["nombre"])):
            continue
        contenido = ContenidoPlantilla.model_validate(datos["contenido"])
        creadas.append(crear_plantilla(session, datos["nombre"], datos.get("descripcion"), contenido, actor))
    return creadas


def plantilla_desde_gestoria(
    session: Session, gestoria: Gestoria, nombre: str, descripcion: str | None, actor: str
) -> PlantillaPerfil:
    """Guarda la configuración de una gestoría como plantilla (sin clientes, buzones ni credenciales)."""
    g = gestoria.id
    contenido = ContenidoPlantilla(
        config=ConfigGestoria.model_validate(gestoria.config or {}),
        conocimiento=[
            {"categoria": e.categoria, "titulo": e.titulo, "contenido": e.contenido, "orden": e.orden}
            for e in session.scalars(
                select(EntradaConocimiento).where(EntradaConocimiento.gestoria_id == g, EntradaConocimiento.activo)
            )
        ],
        temas_sensibles=[
            {"tema": t.tema, "descripcion": t.descripcion}
            for t in session.scalars(select(TemaSensible).where(TemaSensible.gestoria_id == g))
        ],
        tareas=[
            {"tipo": t.tipo, "nombre": t.nombre, "activa": t.activa, "config": t.config}
            for t in session.scalars(select(TareaProgramada).where(TareaProgramada.gestoria_id == g))
        ],
    )
    return crear_plantilla(session, nombre, descripcion, contenido, actor)


# ---------------------------------------------------------------- gestorías


def alta_gestoria(
    session: Session,
    *,
    nombre: str,
    actor: str,
    nif: str | None = None,
    email_contacto: str | None = None,
    telefono: str | None = None,
    direccion: str | None = None,
    plantilla_id: uuid.UUID | None = None,
) -> Gestoria:
    """Da de alta una gestoría. Siempre empieza en modo SIMULACIÓN (no envía nada hasta activarla)."""
    plantilla = None
    contenido = ContenidoPlantilla()
    if plantilla_id:
        plantilla = session.get(PlantillaPerfil, plantilla_id)
        if not plantilla:
            raise ErrorNegocio("La plantilla indicada no existe")
        contenido = ContenidoPlantilla.model_validate(plantilla.contenido)

    datos = {"nombre_gestoria": nombre, "email_contacto": email_contacto, "telefono": telefono}
    contenido = ContenidoPlantilla.model_validate(rellenar_marcadores(contenido.model_dump(mode="json"), datos))

    gestoria = Gestoria(
        nombre=nombre,
        slug=_slug_libre(session, slugify(nombre)),
        nif=nif,
        email_contacto=email_contacto,
        telefono=telefono,
        direccion=direccion,
        estado_agente=EstadoAgente.SIMULACION,
        estado_alta=EstadoAlta.ACTIVA,
        plantilla_origen_id=plantilla.id if plantilla else None,
        config=contenido.config.model_dump(mode="json"),
        presupuesto_ia_mensual_eur=Decimal(str(get_settings().presupuesto_ia_mensual_eur_defecto)),
    )
    session.add(gestoria)
    session.flush()

    for e in contenido.conocimiento:
        session.add(EntradaConocimiento(gestoria_id=gestoria.id, **e.model_dump()))
    for t in contenido.temas_sensibles:
        session.add(TemaSensible(gestoria_id=gestoria.id, **t.model_dump()))
    for t in contenido.tareas:
        session.add(TareaProgramada(gestoria_id=gestoria.id, **t.model_dump()))
    for p in contenido.programas:
        session.add(ProgramaGestoria(gestoria_id=gestoria.id, **p.model_dump()))

    registrar(
        session, "gestoria.alta", actor, gestoria_id=gestoria.id, entidad="gestoria", entidad_id=gestoria.id,
        detalle={"plantilla": plantilla.nombre if plantilla else None,
                 "plantilla_version": plantilla.version if plantilla else None},
    )
    return gestoria


def actualizar_config(session: Session, gestoria: Gestoria, config: ConfigGestoria, actor: str) -> Gestoria:
    gestoria.config = config.model_dump(mode="json")
    registrar(session, "gestoria.config_actualizada", actor, gestoria_id=gestoria.id,
              entidad="gestoria", entidad_id=gestoria.id)
    return gestoria


def cambiar_estado_agente(
    session: Session, gestoria: Gestoria, estado: EstadoAgente, actor: str, *, por_aibe: bool
) -> Gestoria:
    """Pausar siempre se puede. Pasar a ACTIVO (envío real) lo autoriza Aibe la primera vez."""
    if gestoria.estado_alta == EstadoAlta.BAJA and estado != EstadoAgente.PAUSADO:
        raise ErrorNegocio("La gestoría está dada de baja: reactívela antes de encender el agente")
    if estado == EstadoAgente.ACTIVO:
        if por_aibe:
            gestoria.activacion_autorizada = True
        elif not gestoria.activacion_autorizada:
            raise ErrorNegocio("Aibe debe revisar el modo simulación y autorizar la activación la primera vez")
    anterior = gestoria.estado_agente
    gestoria.estado_agente = estado
    registrar(session, "gestoria.agente_estado", actor, gestoria_id=gestoria.id, entidad="gestoria",
              entidad_id=gestoria.id, detalle={"antes": anterior.value, "ahora": estado.value})
    return gestoria


def dar_de_baja(session: Session, gestoria: Gestoria, actor: str) -> Gestoria:
    """Baja "suave": se pausa todo y se conservan los datos. El borrado definitivo es otra operación (fase 6)."""
    gestoria.estado_alta = EstadoAlta.BAJA
    gestoria.estado_agente = EstadoAgente.PAUSADO
    gestoria.dado_de_baja_en = datetime.now(UTC)
    for buzon in session.scalars(select(Buzon).where(Buzon.gestoria_id == gestoria.id)):
        buzon.activo = False
    registrar(session, "gestoria.baja", actor, gestoria_id=gestoria.id, entidad="gestoria", entidad_id=gestoria.id)
    return gestoria


def reactivar(session: Session, gestoria: Gestoria, actor: str) -> Gestoria:
    gestoria.estado_alta = EstadoAlta.ACTIVA
    gestoria.dado_de_baja_en = None
    gestoria.estado_agente = EstadoAgente.SIMULACION  # vuelve con precaución
    registrar(session, "gestoria.reactivada", actor, gestoria_id=gestoria.id, entidad="gestoria",
              entidad_id=gestoria.id)
    return gestoria


def resumen_estado(session: Session, gestoria: Gestoria) -> dict:
    """Lo que ve Aibe en su panel por cada gestoría."""
    g = gestoria.id
    desde = inicio_mes()
    buzones = session.execute(
        select(Buzon.estado_conexion, func.count()).where(Buzon.gestoria_id == g, Buzon.activo)
        .group_by(Buzon.estado_conexion)
    ).all()
    puentes_ok = session.scalar(
        select(func.count()).select_from(Puente).where(Puente.gestoria_id == g,
                                                       Puente.estado_conexion == EstadoConexion.OK)
    )
    return {
        "buzones_activos": sum(n for _, n in buzones),
        "buzones_con_error": sum(n for e, n in buzones if e == EstadoConexion.ERROR),
        "puente_conectado": bool(puentes_ok),
        "mensajes_recibidos_mes": session.scalar(
            select(func.count()).select_from(Mensaje).where(
                Mensaje.gestoria_id == g, Mensaje.direccion == Direccion.ENTRANTE, Mensaje.creado_en >= desde)
        ),
        "derivaciones_pendientes": session.scalar(
            select(func.count()).select_from(Derivacion).where(
                Derivacion.gestoria_id == g, Derivacion.estado == EstadoDerivacion.PENDIENTE)
        ),
        "coste_ia_mes_eur": float(
            session.scalar(select(func.coalesce(func.sum(UsoIA.coste_eur), 0)).where(
                UsoIA.gestoria_id == g, UsoIA.creado_en >= desde)) or 0
        ),
        "presupuesto_ia_mensual_eur": float(gestoria.presupuesto_ia_mensual_eur),
    }


# ---------------------------------------------------------------- clientes finales


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def crear_cliente(
    session: Session,
    gestoria_id: uuid.UUID,
    *,
    nombre: str,
    actor: str,
    nif: str | None = None,
    tipo: TipoCliente = TipoCliente.AUTONOMO,
    emails: list[str] | None = None,
    telefono: str | None = None,
    id_externo: str | None = None,
) -> ClienteFinal:
    nif = nif.strip().upper() if nif else None
    if nif and session.scalar(
        select(ClienteFinal.id).where(ClienteFinal.gestoria_id == gestoria_id, ClienteFinal.nif == nif)
    ):
        raise ErrorNegocio(f"Ya existe un cliente con NIF {nif}")
    cliente = ClienteFinal(
        gestoria_id=gestoria_id, nombre=nombre, nif=nif, tipo=tipo, telefono=telefono, id_externo=id_externo
    )
    session.add(cliente)
    session.flush()
    for email in emails or []:
        valor = normalizar_email(email)
        if session.scalar(select(ContactoCliente.id).where(
                ContactoCliente.gestoria_id == gestoria_id, ContactoCliente.valor == valor)):
            raise ErrorNegocio(f"El correo {valor} ya está asignado a otro cliente")
        session.add(ContactoCliente(gestoria_id=gestoria_id, cliente_id=cliente.id, canal="email", valor=valor))
    session.flush()
    session.refresh(cliente)
    registrar(session, "cliente.creado", actor, gestoria_id=gestoria_id, entidad="cliente", entidad_id=cliente.id)
    return cliente


def identificar_cliente_por_email(session: Session, gestoria_id: uuid.UUID, email: str) -> ClienteFinal | None:
    """Paso 2 del flujo del agente: ¿de qué cliente es este correo? (sin IA)."""
    return session.scalar(
        select(ClienteFinal)
        .join(ContactoCliente, ContactoCliente.cliente_id == ClienteFinal.id)
        .where(ContactoCliente.gestoria_id == gestoria_id, ContactoCliente.canal == "email",
               ContactoCliente.valor == normalizar_email(email), ClienteFinal.activo)
    )
