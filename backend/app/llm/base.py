"""Interfaz común para cualquier proveedor de IA.

El resto del sistema solo conoce estas clases. Para cambiar de modelo o de
proveedor (otro modelo de Claude, Claude vía AWS en la UE, otro proveedor...)
basta con escribir otra implementación de `ProveedorLLM`.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

# "barato": clasificar, extraer datos, navegar programas (Haiku)
# "redaccion": escribir respuestas a clientes (Sonnet)
Nivel = Literal["barato", "redaccion"]


@dataclass
class BloqueSistema:
    """Parte de las instrucciones. Si cachear=True y se repite, se cobra a precio de caché."""

    texto: str
    cachear: bool = False


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    esquema_entrada: dict


@dataclass
class PeticionLLM:
    tarea: str                      # para el registro de coste: clasificar | redactar | extraer | ...
    nivel: Nivel
    mensajes: list[dict]            # [{"role": "user", "content": "..."}]
    sistema: list[BloqueSistema] = field(default_factory=list)
    max_tokens: int = 1024
    herramientas: list[Herramienta] = field(default_factory=list)
    temperatura: float | None = None


@dataclass
class UsoTokens:
    entrada: int = 0
    salida: int = 0
    cache_lectura: int = 0
    cache_escritura: int = 0

    @property
    def entrada_total(self) -> int:
        return self.entrada + self.cache_lectura + self.cache_escritura


@dataclass
class LlamadaHerramienta:
    id: str
    nombre: str
    argumentos: dict[str, Any]


@dataclass
class RespuestaLLM:
    texto: str
    modelo: str
    uso: UsoTokens
    motivo_fin: str | None = None
    llamadas_herramienta: list[LlamadaHerramienta] = field(default_factory=list)
    bruto: Any = None  # respuesta original del proveedor (para depurar)


class ErrorProveedorLLM(Exception):
    """El proveedor falló (red, límites, caída...). El agente debe decirlo, nunca inventar."""


class ProveedorLLM(ABC):
    nombre: str = "base"

    @abstractmethod
    def modelo_para(self, nivel: Nivel) -> str: ...

    @abstractmethod
    def completar(self, peticion: PeticionLLM) -> RespuestaLLM: ...
