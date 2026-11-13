"""Implementación con Claude (API de Anthropic)."""
from app.core.config import get_settings
from app.llm.base import (
    ErrorProveedorLLM,
    LlamadaHerramienta,
    Nivel,
    PeticionLLM,
    ProveedorLLM,
    RespuestaLLM,
    UsoTokens,
)


class ProveedorClaude(ProveedorLLM):
    nombre = "anthropic"

    def __init__(self, api_key: str | None = None, cliente=None):
        ajustes = get_settings()
        self._modelos = {"barato": ajustes.modelo_barato, "redaccion": ajustes.modelo_redaccion}
        if cliente is None:
            import anthropic

            clave = api_key or ajustes.anthropic_api_key
            if not clave:
                raise ErrorProveedorLLM("Falta ANTHROPIC_API_KEY en la configuración")
            cliente = anthropic.Anthropic(api_key=clave, max_retries=3, timeout=60)
        self._cliente = cliente

    def modelo_para(self, nivel: Nivel) -> str:
        return self._modelos[nivel]

    @staticmethod
    def _sistema(peticion: PeticionLLM) -> list[dict]:
        bloques = []
        for b in peticion.sistema:
            bloque = {"type": "text", "text": b.texto}
            if b.cachear:
                # Marca el final de la parte repetida: todo lo anterior se guarda en caché
                bloque["cache_control"] = {"type": "ephemeral"}
            bloques.append(bloque)
        return bloques

    def completar(self, peticion: PeticionLLM) -> RespuestaLLM:
        modelo = self.modelo_para(peticion.nivel)
        argumentos = {
            "model": modelo,
            "max_tokens": peticion.max_tokens,
            "messages": peticion.mensajes,
        }
        if peticion.sistema:
            argumentos["system"] = self._sistema(peticion)
        if peticion.herramientas:
            argumentos["tools"] = [
                {"name": h.nombre, "description": h.descripcion, "input_schema": h.esquema_entrada}
                for h in peticion.herramientas
            ]
        if peticion.temperatura is not None:
            argumentos["temperature"] = peticion.temperatura

        try:
            r = self._cliente.messages.create(**argumentos)
        except Exception as exc:  # anthropic.APIError y errores de red
            raise ErrorProveedorLLM(f"{type(exc).__name__}: {exc}") from exc

        texto = "".join(getattr(b, "text", "") for b in r.content if getattr(b, "type", "") == "text")
        llamadas = [
            LlamadaHerramienta(id=b.id, nombre=b.name, argumentos=dict(b.input))
            for b in r.content
            if getattr(b, "type", "") == "tool_use"
        ]
        u = r.usage
        uso = UsoTokens(
            entrada=u.input_tokens or 0,
            salida=u.output_tokens or 0,
            cache_lectura=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_escritura=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        return RespuestaLLM(texto=texto, modelo=r.model or modelo, uso=uso, motivo_fin=r.stop_reason,
                            llamadas_herramienta=llamadas, bruto=r)
