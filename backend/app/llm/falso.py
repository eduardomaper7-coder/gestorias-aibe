"""Proveedor de IA simulado: para pruebas automáticas y para probar sin gastar dinero."""
from collections.abc import Callable

from app.llm.base import ErrorProveedorLLM, Nivel, PeticionLLM, ProveedorLLM, RespuestaLLM, UsoTokens


class ProveedorFalso(ProveedorLLM):
    nombre = "falso"

    def __init__(self, respuestas: list[str] | Callable[[PeticionLLM], str] | None = None,
                 uso: UsoTokens | None = None, fallar: bool = False):
        self._respuestas = respuestas
        self._uso = uso or UsoTokens(entrada=500, salida=100)
        self._fallar = fallar
        self.peticiones: list[PeticionLLM] = []

    def modelo_para(self, nivel: Nivel) -> str:
        return {"barato": "claude-haiku-5-5", "redaccion": "claude-sonnet-5-5"}[nivel]

    def completar(self, peticion: PeticionLLM) -> RespuestaLLM:
        self.peticiones.append(peticion)
        if self._fallar:
            raise ErrorProveedorLLM("Fallo simulado del proveedor")
        if callable(self._respuestas):
            texto = self._respuestas(peticion)
        elif self._respuestas:
            texto = self._respuestas.pop(0)
        else:
            texto = "[respuesta simulada]"
        return RespuestaLLM(texto=texto, modelo=self.modelo_para(peticion.nivel), uso=self._uso,
                            motivo_fin="end_turn")
