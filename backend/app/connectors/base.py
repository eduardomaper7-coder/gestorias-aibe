"""Interfaz común de los conectores con los programas de la gestoría.

El agente nunca habla directamente con un programa: usa herramientas, que usan
un conector. Todos los conectores devuelven los mismos tipos de datos, así el
agente funciona igual si la gestoría usa a3ASESOR, un Excel u otro programa.

Orden de preferencia para conectar un programa:
  1. API oficial  2. base de datos en solo lectura  3. ficheros Excel/CSV
  4. interfaz como texto (DOM / UI Automation)  5. OCR local (último recurso)

Solo lectura: en esta fase ningún conector escribe en los programas.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class EstadoModelo(str, Enum):
    PENDIENTE = "pendiente"      # aún no calculado
    CALCULADO = "calculado"      # calculado, sin presentar
    PRESENTADO = "presentado"
    DESCONOCIDO = "desconocido"  # el programa da un estado que no sabemos interpretar


class ResultadoModelo(str, Enum):
    A_INGRESAR = "a_ingresar"
    A_DEVOLVER = "a_devolver"
    A_COMPENSAR = "a_compensar"
    NEGATIVO = "negativo"
    CERO = "cero"
    SIN_ACTIVIDAD = "sin_actividad"
    DESCONOCIDO = "desconocido"


@dataclass
class ClienteExterno:
    nif: str
    nombre: str
    tipo: str | None = None          # autonomo | sociedad | ...
    emails: list[str] = field(default_factory=list)
    id_externo: str | None = None


@dataclass
class ModeloFiscal:
    nif: str
    modelo: str                      # "303", "130", ...
    ejercicio: int
    periodo: str                     # "1T".."4T", "0A" (anual), "01".."12"
    estado: EstadoModelo
    importe: Decimal | None = None
    resultado: ResultadoModelo | None = None
    fecha_presentacion: date | None = None


@dataclass
class DocumentoPendiente:
    nif: str
    descripcion: str
    ejercicio: int | None = None
    periodo: str | None = None


class ErrorConector(Exception):
    """El programa no respondió o los datos no tienen la forma esperada. El agente debe decirlo."""


class Conector(ABC):
    tipo: str = "base"

    @abstractmethod
    def probar_conexion(self) -> None:
        """Lanza ErrorConector si no se puede leer."""

    @abstractmethod
    def listar_clientes(self) -> list[ClienteExterno]: ...

    @abstractmethod
    def estado_modelos(self, nif: str, ejercicio: int | None = None,
                       periodo: str | None = None) -> list[ModeloFiscal]: ...

    def documentacion_pendiente(self, nif: str) -> list[DocumentoPendiente]:
        """No todos los programas guardan esto: por defecto, nada."""
        return []


def normalizar_nif(nif: str | None) -> str:
    return (nif or "").replace("-", "").replace(" ", "").upper()


def normalizar_periodo(valor) -> str:
    """Acepta 1, "1", "1T", "T1", "1º trimestre"... y devuelve "1T". Meses: "01".."12". Anual: "0A"."""
    texto = str(valor).strip().upper().replace("º", "").replace("TRIMESTRE", "T").replace(" ", "")
    if texto in {"0A", "A", "ANUAL", "0"}:
        return "0A"
    if texto.startswith("T") and texto[1:].isdigit():
        texto = texto[1:] + "T"
    if texto.endswith("T") and texto[:-1].isdigit() and 1 <= int(texto[:-1]) <= 4:
        return f"{int(texto[:-1])}T"
    if texto.isdigit() and 1 <= int(texto) <= 4:
        return f"{int(texto)}T"
    if texto.isdigit() and 1 <= int(texto) <= 12:
        return f"{int(texto):02d}"
    return texto
