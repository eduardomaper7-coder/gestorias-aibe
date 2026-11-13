"""Punto ÚNICO por el que el sistema llama a la IA.

Hace tres cosas además de la llamada:
1. Comprueba el presupuesto mensual de la gestoría antes de gastar.
2. Rechaza peticiones desproporcionadas (protección de coste).
3. Registra tokens y coste por gestoría y por tarea, incluso si la llamada falla.

El registro de coste se guarda en su propia transacción: aunque el proceso que
pidió la llamada falle después, el gasto queda apuntado.
"""
import json
import time
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.audit.registro import registrar
from app.core.config import get_settings
from app.core.db import sesion_gestoria
from app.llm.base import ErrorProveedorLLM, PeticionLLM, ProveedorLLM, RespuestaLLM, UsoTokens
from app.llm.precios import a_euros, coste_usd
from app.models import Gestoria, UsoIA
from app.tenancy.servicio import inicio_mes


class PresupuestoAgotado(Exception):
    pass


class PeticionDemasiadoGrande(Exception):
    pass


def obtener_proveedor() -> ProveedorLLM:
    nombre = get_settings().proveedor_llm
    if nombre == "claude":
        from app.llm.claude import ProveedorClaude

        return ProveedorClaude()
    if nombre == "falso":
        from app.llm.falso import ProveedorFalso

        return ProveedorFalso()
    raise ValueError(f"Proveedor de IA desconocido: {nombre}")


def estimar_tokens(peticion: PeticionLLM) -> int:
    """Estimación rápida y prudente (≈ 3,5 caracteres por token en español)."""
    texto = "".join(b.texto for b in peticion.sistema) + json.dumps(peticion.mensajes, ensure_ascii=False)
    texto += json.dumps([h.esquema_entrada for h in peticion.herramientas], ensure_ascii=False)
    return int(len(texto) / 3.5)


def gasto_mes_eur(gestoria_id: uuid.UUID, desde: datetime | None = None) -> Decimal:
    with sesion_gestoria(gestoria_id) as s:
        return Decimal(
            s.scalar(select(func.coalesce(func.sum(UsoIA.coste_eur), 0)).where(
                UsoIA.gestoria_id == gestoria_id, UsoIA.creado_en >= (desde or inicio_mes())))
        )


def resumen_uso(gestoria_id: uuid.UUID) -> dict:
    desde = inicio_mes()
    with sesion_gestoria(gestoria_id) as s:
        filas = s.execute(
            select(UsoIA.tarea, func.count(), func.sum(UsoIA.coste_eur), func.sum(UsoIA.tokens_entrada),
                   func.sum(UsoIA.tokens_salida), func.sum(UsoIA.tokens_cache_lectura))
            .where(UsoIA.gestoria_id == gestoria_id, UsoIA.creado_en >= desde)
            .group_by(UsoIA.tarea)
        ).all()
        presupuesto = s.scalar(select(Gestoria.presupuesto_ia_mensual_eur).where(Gestoria.id == gestoria_id))
    por_tarea = {
        t: {"llamadas": n, "coste_eur": float(c or 0), "tokens_entrada": int(e or 0),
            "tokens_salida": int(o or 0), "tokens_cache_lectura": int(cl or 0)}
        for t, n, c, e, o, cl in filas
    }
    return {
        "desde": desde,
        "coste_eur": round(sum(v["coste_eur"] for v in por_tarea.values()), 4),
        "presupuesto_eur": float(presupuesto or 0),
        "llamadas": sum(v["llamadas"] for v in por_tarea.values()),
        "por_tarea": por_tarea,
    }


class ServicioIA:
    def __init__(self, gestoria_id: uuid.UUID, proveedor: ProveedorLLM | None = None):
        self.gestoria_id = gestoria_id
        self.proveedor = proveedor or obtener_proveedor()

    def _comprobar_presupuesto(self) -> None:
        with sesion_gestoria(self.gestoria_id) as s:
            presupuesto = s.scalar(select(Gestoria.presupuesto_ia_mensual_eur).where(
                Gestoria.id == self.gestoria_id))
        if presupuesto is None:
            raise PresupuestoAgotado("Gestoría no encontrada")
        gastado = gasto_mes_eur(self.gestoria_id)
        if gastado >= presupuesto:
            with sesion_gestoria(self.gestoria_id) as s:
                registrar(s, "ia.presupuesto_agotado", "sistema", resultado="bloqueado",
                          detalle={"gastado_eur": float(gastado), "presupuesto_eur": float(presupuesto)})
                s.commit()
            raise PresupuestoAgotado(
                f"Presupuesto mensual de IA agotado ({gastado:.2f} € de {presupuesto:.2f} €)")

    def _registrar(self, peticion: PeticionLLM, modelo: str, uso: UsoTokens, latencia_ms: int,
                   conversacion_id: uuid.UUID | None, error: str | None) -> UsoIA:
        usd = coste_usd(modelo, uso)
        with sesion_gestoria(self.gestoria_id) as s:
            registro = UsoIA(
                gestoria_id=self.gestoria_id, tarea=peticion.tarea, proveedor=self.proveedor.nombre,
                modelo=modelo, tokens_entrada=uso.entrada, tokens_salida=uso.salida,
                tokens_cache_lectura=uso.cache_lectura, tokens_cache_escritura=uso.cache_escritura,
                coste_usd=usd, coste_eur=a_euros(usd), latencia_ms=latencia_ms, ok=error is None,
                error=error, conversacion_id=conversacion_id,
            )
            s.add(registro)
            s.commit()
        return registro

    def completar(self, peticion: PeticionLLM, conversacion_id: uuid.UUID | None = None) -> RespuestaLLM:
        estimados = estimar_tokens(peticion)
        limite = get_settings().max_tokens_entrada_estimados
        if estimados > limite:
            raise PeticionDemasiadoGrande(f"Petición de ~{estimados} tokens supera el límite de {limite}")
        self._comprobar_presupuesto()

        modelo = self.proveedor.modelo_para(peticion.nivel)
        inicio = time.monotonic()
        try:
            respuesta = self.proveedor.completar(peticion)
        except ErrorProveedorLLM as exc:
            self._registrar(peticion, modelo, UsoTokens(), int((time.monotonic() - inicio) * 1000),
                            conversacion_id, str(exc)[:2000])
            raise
        self._registrar(peticion, respuesta.modelo, respuesta.uso, int((time.monotonic() - inicio) * 1000),
                        conversacion_id, None)
        return respuesta
