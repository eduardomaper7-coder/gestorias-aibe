from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from app.core.db import sesion_gestoria, sesion_sistema
from app.llm.base import BloqueSistema, ErrorProveedorLLM, PeticionLLM, UsoTokens
from app.llm.claude import ProveedorClaude
from app.llm.falso import ProveedorFalso
from app.llm.precios import coste_usd
from app.llm.servicio import PeticionDemasiadoGrande, PresupuestoAgotado, ServicioIA, resumen_uso
from app.models import Gestoria, UsoIA


def peticion(**kw):
    base = dict(tarea="clasificar", nivel="barato", mensajes=[{"role": "user", "content": "hola"}],
                sistema=[BloqueSistema("Instrucciones fijas", cachear=True)])
    return PeticionLLM(**{**base, **kw})


def test_calculo_de_coste():
    # Haiku 5.5: 0,10 $/M entrada, 0,50 $/M salida, 0,01 $/M lectura de caché
    uso = UsoTokens(entrada=10_000, salida=10_000, cache_lectura=10_000)
    assert coste_usd("claude-haiku-5-5", uso) == Decimal("0.0061")
    # nombre con fecha que puede devolver la API
    assert coste_usd("claude-haiku-5-5-20261007", uso) == Decimal("0.0061")
    # por encima de 100.000 tokens de entrada, Haiku cobra el precio largo
    assert coste_usd("claude-haiku-5-5", UsoTokens(entrada=150_000)) == Decimal("0.075")
    # Sonnet 5.5: 2 $/M entrada, 10 $/M salida
    assert coste_usd("claude-sonnet-5-5", UsoTokens(entrada=3000, salida=400)) == Decimal("0.01")
    # modelo desconocido: precio prudente (el caro)
    assert coste_usd("otro-modelo", UsoTokens(salida=1_000_000)) == Decimal("10")


def test_registra_tokens_y_coste_por_gestoria_y_tarea(dos_gestorias):
    a, b = dos_gestorias["a"], dos_gestorias["b"]
    falso = ProveedorFalso(["clasificado"], uso=UsoTokens(entrada=2000, salida=100, cache_lectura=3000))
    r = ServicioIA(a["gestoria_id"], falso).completar(peticion())
    assert r.texto == "clasificado"
    ServicioIA(a["gestoria_id"], ProveedorFalso(uso=UsoTokens(entrada=4000, salida=500))).completar(
        peticion(tarea="redactar", nivel="redaccion"))

    resumen = resumen_uso(a["gestoria_id"])
    assert resumen["llamadas"] == 2
    assert set(resumen["por_tarea"]) == {"clasificar", "redactar"}
    assert resumen["por_tarea"]["redactar"]["coste_eur"] > resumen["por_tarea"]["clasificar"]["coste_eur"] > 0
    assert resumen_uso(b["gestoria_id"])["llamadas"] == 0  # el gasto de A no aparece en B


def test_si_la_ia_falla_se_registra_y_se_avisa(dos_gestorias):
    a = dos_gestorias["a"]
    with pytest.raises(ErrorProveedorLLM):
        ServicioIA(a["gestoria_id"], ProveedorFalso(fallar=True)).completar(peticion())
    with sesion_gestoria(a["gestoria_id"]) as s:
        uso = s.scalar(select(UsoIA))
        assert uso.ok is False and "simulado" in uso.error


def test_presupuesto_agotado_bloquea_llamadas(dos_gestorias):
    a = dos_gestorias["a"]
    with sesion_sistema() as s:
        s.execute(update(Gestoria).where(Gestoria.id == a["gestoria_id"]).values(presupuesto_ia_mensual_eur=0.01))
        s.commit()
    caro = ProveedorFalso(uso=UsoTokens(entrada=10_000, salida=10_000))
    ServicioIA(a["gestoria_id"], caro).completar(peticion(nivel="redaccion"))  # gasta ~0,1 €
    with pytest.raises(PresupuestoAgotado):
        ServicioIA(a["gestoria_id"], caro).completar(peticion())
    assert len(caro.peticiones) == 1  # la segunda nunca llegó al proveedor


def test_peticiones_desproporcionadas_se_rechazan(dos_gestorias):
    falso = ProveedorFalso()
    enorme = "x" * 400_000
    with pytest.raises(PeticionDemasiadoGrande):
        ServicioIA(dos_gestorias["a"]["gestoria_id"], falso).completar(
            peticion(mensajes=[{"role": "user", "content": enorme}]))
    assert falso.peticiones == []


def test_proveedor_claude_prepara_cache_y_lee_el_uso():
    """Comprueba la traducción a la API de Anthropic sin llamarla (cliente simulado)."""
    capturado = {}

    def crear(**kw):
        capturado.update(kw)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Hola")], model="claude-haiku-5-5", stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=900,
                                  cache_creation_input_tokens=0),
        )

    cliente = SimpleNamespace(messages=SimpleNamespace(create=crear))
    p = ProveedorClaude(cliente=cliente)
    r = p.completar(peticion(sistema=[BloqueSistema("Instrucciones", cachear=False),
                                      BloqueSistema("Base de conocimiento", cachear=True)]))
    assert capturado["model"] == "claude-haiku-5-5"
    assert "cache_control" not in capturado["system"][0]
    assert capturado["system"][1]["cache_control"] == {"type": "ephemeral"}
    assert r.texto == "Hola" and r.uso.cache_lectura == 900


def test_proveedor_claude_convierte_errores():
    def crear(**kw):
        raise ConnectionError("sin red")

    p = ProveedorClaude(cliente=SimpleNamespace(messages=SimpleNamespace(create=crear)))
    with pytest.raises(ErrorProveedorLLM, match="sin red"):
        p.completar(peticion())
