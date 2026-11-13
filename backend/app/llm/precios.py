"""Cálculo del coste de cada llamada a partir de config/precios_modelos.yaml."""
from decimal import Decimal
from functools import lru_cache

import yaml

from app.core.config import get_settings
from app.llm.base import UsoTokens

MILLON = Decimal(1_000_000)


@lru_cache
def tabla_precios() -> dict:
    return yaml.safe_load(get_settings().ruta_precios.read_text(encoding="utf-8"))


def coste_usd(modelo: str, uso: UsoTokens) -> Decimal:
    tabla = tabla_precios()
    precios = tabla["modelos"].get(modelo)
    if precios is None:  # la API puede devolver el nombre con fecha: claude-haiku-5-5-20261007
        coincidencias = [k for k in tabla["modelos"] if modelo.startswith(k)]
        precios = tabla["modelos"][max(coincidencias, key=len)] if coincidencias else tabla["por_defecto"]
    umbral = precios.get("umbral_largo")
    if umbral and uso.entrada_total > umbral and "largo" in precios:
        precios = {**precios, **precios["largo"]}

    def p(clave: str) -> Decimal:
        return Decimal(str(precios[clave]))

    total = (
        uso.entrada * p("entrada")
        + uso.salida * p("salida")
        + uso.cache_lectura * p("cache_lectura")
        + uso.cache_escritura * p("cache_escritura")
    ) / MILLON
    return total.quantize(Decimal("0.000001"))


def a_euros(usd: Decimal) -> Decimal:
    return (usd * Decimal(str(get_settings().cambio_usd_eur))).quantize(Decimal("0.000001"))
