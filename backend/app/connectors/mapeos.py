"""Carga de "mapeos": ficheros YAML (en la carpeta recetas/) que dicen dónde está cada dato
dentro de un programa (qué hoja y columna de un Excel, qué tabla y campo de una base de datos).

Así, cuando un programa cambia o descubrimos su estructura real, se ajusta un YAML
versionado, no el código.
"""
import re
import unicodedata
from pathlib import Path

import yaml

from app.connectors.base import ErrorConector
from app.core.config import get_settings

_REF_VALIDA = re.compile(r"^[a-z0-9_\-]+/[a-z0-9_\-\.]+$")


def cargar_mapeo(ref: str, raiz: Path | None = None) -> dict:
    """ref = "<programa>/<fichero sin .yaml>", p. ej. "a3asesor/mapeo-a3asesor-data.v0"."""
    if not _REF_VALIDA.match(ref):
        raise ErrorConector(f"Referencia de mapeo no válida: {ref}")
    raiz = raiz or get_settings().ruta_recetas
    ruta = (raiz / f"{ref}.yaml").resolve()
    if raiz.resolve() not in ruta.parents:
        raise ErrorConector("Referencia de mapeo fuera de la carpeta de recetas")
    if not ruta.exists():
        raise ErrorConector(f"No existe el mapeo {ref}")
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def clave_texto(texto) -> str:
    """Compara textos sin importar mayúsculas, tildes ni espacios: "Fecha Presentación" == "fecha presentacion"."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def traducir_valor(valor, tabla: dict | None, por_defecto=None):
    """Traduce un valor del programa ("Presentado", "T") a nuestro vocabulario ("presentado")."""
    if valor is None or valor == "":
        return None
    if not tabla:
        return valor
    indice = {clave_texto(k): v for k, v in tabla.items()}
    return indice.get(clave_texto(valor), por_defecto)
