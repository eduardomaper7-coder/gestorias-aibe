"""Conector de a3ASESOR (Wolters Kluwer), versión de escritorio.

a3ASESOR no tiene API pública. Leemos en SOLO LECTURA una base de datos SQL Server:
  - preferente: la base que genera el módulo "a3asesor Data" (pensada para informes);
  - alternativa (con permiso de la gestoría): la base de datos de a3ASESOR directamente.

Las consultas las ejecuta el puente local instalado en la gestoría (fase 5): nuestro
servidor nunca se conecta directamente a su red.

Como la estructura interna de tablas no es pública, los nombres de tablas y campos
NO están en este código: están en un mapeo YAML versionado (recetas/a3asesor/).
Cuando tengamos acceso a una instalación real (o a la aplicación de demostración),
solo habrá que ajustar ese fichero.

Escritura (más adelante): siempre mediante ficheros Excel para el "Importador de
datos" de a3, nunca escribiendo en su base de datos.

a3innuva (versión en la nube) tiene API oficial (Conectia): será otro conector.
"""
import re
from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal

from app.connectors.base import (
    ClienteExterno,
    Conector,
    ErrorConector,
    EstadoModelo,
    ModeloFiscal,
    ResultadoModelo,
    normalizar_nif,
    normalizar_periodo,
)
from app.connectors.mapeos import cargar_mapeo, traducir_valor

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
LIMITE_FILAS = 2000


class EjecutorSQL(ABC):
    """Quien ejecuta realmente la consulta: el puente (producción) o una base de pruebas."""

    dialecto: str = "mssql"

    def ejecutar(self, sql: str, parametros: list) -> list[tuple]:
        if not sql.lstrip().upper().startswith("SELECT") or ";" in sql:
            raise ErrorConector("Solo se permiten consultas de lectura (SELECT)")
        return self._ejecutar(sql, parametros)

    @abstractmethod
    def _ejecutar(self, sql: str, parametros: list) -> list[tuple]: ...


class EjecutorPorPuente(EjecutorSQL):
    """Envía la consulta al puente de la gestoría (se implementa en la fase 5)."""

    def __init__(self, puente_id):
        self.puente_id = puente_id

    def _ejecutar(self, sql: str, parametros: list) -> list[tuple]:
        raise ErrorConector("El puente local todavía no está disponible (fase 5)")


class ConstructorConsultas:
    """Convierte el mapeo YAML en consultas SELECT seguras (identificadores validados, valores parametrizados)."""

    def __init__(self, mapeo: dict, dialecto: str):
        self.mapeo = mapeo
        self.dialecto = dialecto

    def _q(self, ident: str) -> str:
        if not _IDENT.match(ident):
            raise ErrorConector(f"Identificador no válido en el mapeo: {ident!r}")
        partes = ident.split(".")
        if self.dialecto == "mssql":
            return ".".join(f"[{p}]" for p in partes)
        return ".".join(f'"{p}"' for p in partes)

    def entidad(self, nombre: str) -> dict:
        try:
            return self.mapeo["entidades"][nombre]
        except KeyError:
            raise ErrorConector(f"El mapeo no define la entidad «{nombre}»") from None

    def _select(self, campos: list[tuple[str, str]], desde: str, where: str = "") -> str:
        cols = ", ".join(f"{alias}.{self._q(col)}" for alias, col in campos)
        if self.dialecto == "mssql":
            return f"SELECT TOP {LIMITE_FILAS} {cols} FROM {desde}{where}"
        return f"SELECT {cols} FROM {desde}{where} LIMIT {LIMITE_FILAS}"

    def consulta_clientes(self) -> tuple[str, list[str]]:
        e = self.entidad("empresas")
        campos = [c for c in ("codigo", "nif", "nombre", "tipo", "email") if c in e["columnas"]]
        sql = self._select([("e", e["columnas"][c]) for c in campos], f"{self._q(e['tabla'])} e")
        return sql, campos

    def consulta_modelos(self, con_ejercicio: bool) -> tuple[str, list[str]]:
        e, m = self.entidad("empresas"), self.entidad("modelos")
        campos = [c for c in ("modelo", "ejercicio", "periodo", "estado", "importe", "resultado",
                              "fecha_presentacion") if c in m["columnas"]]
        desde = (f"{self._q(m['tabla'])} m JOIN {self._q(e['tabla'])} e "
                 f"ON e.{self._q(e['columnas']['codigo'])} = m.{self._q(m['columnas']['codigo_empresa'])}")
        where = f" WHERE e.{self._q(e['columnas']['nif'])} = ?"
        if con_ejercicio:
            where += f" AND m.{self._q(m['columnas']['ejercicio'])} = ?"
        return self._select([("m", m["columnas"][c]) for c in campos], desde, where), campos


class ConectorA3Asesor(Conector):
    tipo = "a3asesor"

    def __init__(self, config: dict, ejecutor: EjecutorSQL):
        """config: {"mapeo": "a3asesor/mapeo-a3asesor-data.v0"} (o "mapeo_en_linea")."""
        self.mapeo = config.get("mapeo_en_linea") or cargar_mapeo(config["mapeo"])
        self.ejecutor = ejecutor
        self.consultas = ConstructorConsultas(self.mapeo, ejecutor.dialecto)

    def _filas(self, sql: str, params: list, campos: list[str]) -> list[dict]:
        try:
            filas = self.ejecutor.ejecutar(sql, params)
        except ErrorConector:
            raise
        except Exception as exc:
            raise ErrorConector(f"Error al consultar a3ASESOR: {exc}") from exc
        return [dict(zip(campos, f, strict=False)) for f in filas]

    def probar_conexion(self) -> None:
        sql, campos = self.consultas.consulta_clientes()
        self._filas(sql, [], campos)

    def listar_clientes(self) -> list[ClienteExterno]:
        sql, campos = self.consultas.consulta_clientes()
        valores = self.consultas.entidad("empresas").get("valores", {})
        resultado = []
        for f in self._filas(sql, [], campos):
            nif = normalizar_nif(f.get("nif"))
            if not nif:
                continue
            email = (f.get("email") or "").strip().lower()
            resultado.append(ClienteExterno(
                nif=nif, nombre=str(f.get("nombre") or "").strip(),
                tipo=traducir_valor(f.get("tipo"), valores.get("tipo"), por_defecto="otro"),
                emails=[email] if "@" in email else [],
                id_externo=str(f["codigo"]) if f.get("codigo") is not None else None,
            ))
        return resultado

    def estado_modelos(self, nif: str, ejercicio: int | None = None,
                       periodo: str | None = None) -> list[ModeloFiscal]:
        nif = normalizar_nif(nif)
        sql, campos = self.consultas.consulta_modelos(con_ejercicio=ejercicio is not None)
        params = [nif] + ([ejercicio] if ejercicio is not None else [])
        valores = self.consultas.entidad("modelos").get("valores", {})
        periodo = normalizar_periodo(periodo) if periodo else None
        resultado = []
        for f in self._filas(sql, params, campos):
            per = normalizar_periodo(traducir_valor(f.get("periodo"), valores.get("periodo")) or f.get("periodo"))
            if periodo and per != periodo:
                continue
            estado = traducir_valor(f.get("estado"), valores.get("estado"), por_defecto="desconocido")
            res = traducir_valor(f.get("resultado"), valores.get("resultado"), por_defecto="desconocido")
            fecha = f.get("fecha_presentacion")
            if isinstance(fecha, datetime):
                fecha = fecha.date()
            elif isinstance(fecha, str):
                fecha = date.fromisoformat(fecha[:10]) if fecha else None
            resultado.append(ModeloFiscal(
                nif=nif, modelo=str(f.get("modelo")).strip(), ejercicio=int(f.get("ejercicio")), periodo=per,
                estado=EstadoModelo(estado) if estado in EstadoModelo._value2member_map_ else EstadoModelo.DESCONOCIDO,
                importe=Decimal(str(f["importe"])) if f.get("importe") is not None else None,
                resultado=ResultadoModelo(res) if res in ResultadoModelo._value2member_map_ else (
                    ResultadoModelo.DESCONOCIDO if res else None),
                fecha_presentacion=fecha,
            ))
        return resultado
