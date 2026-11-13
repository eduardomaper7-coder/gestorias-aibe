"""Conector de Excel.

Casi todas las gestorías llevan algo en Excel (seguimiento de modelos, documentación
pendiente...). Este conector lee un libro .xlsx siguiendo un mapeo (qué hoja y qué
columna contiene cada dato). El fichero puede llegar de dos formas:
  - subido a nuestro servidor (acceso = servidor);
  - leído por el puente local en el ordenador de la gestoría (acceso = puente, fase 5).
Por eso la lectura (LectorExcel) está separada de cómo se obtiene el fichero.
"""
import io
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook

from app.connectors.base import (
    ClienteExterno,
    Conector,
    DocumentoPendiente,
    ErrorConector,
    EstadoModelo,
    ModeloFiscal,
    ResultadoModelo,
    normalizar_nif,
    normalizar_periodo,
)
from app.connectors.mapeos import cargar_mapeo, clave_texto, traducir_valor

MAX_FILAS = 50_000
OBLIGATORIAS = {
    "clientes": ["nif", "nombre"],
    "modelos": ["nif", "modelo", "ejercicio", "periodo", "estado"],
    "pendientes": ["nif", "descripcion"],
}


def _a_decimal(valor) -> Decimal | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float, Decimal)):
        return Decimal(str(valor))
    texto = str(valor).replace("€", "").replace(" ", "").strip()
    if "," in texto:  # formato español: 1.234,56
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _a_fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor.strip():
        for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(valor.strip(), formato).date()
            except ValueError:
                pass
    return None


class LectorExcel:
    def __init__(self, contenido: bytes, mapeo: dict):
        self.mapeo = mapeo
        try:
            self.libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        except Exception as exc:
            raise ErrorConector(f"No se pudo abrir el Excel: {exc}") from exc

    def filas(self, entidad: str) -> list[dict]:
        """Devuelve las filas de la hoja de una entidad con nuestros nombres de campo."""
        def_hoja = self.mapeo.get("hojas", {}).get(entidad)
        if not def_hoja:
            return []
        nombres = {clave_texto(n): n for n in self.libro.sheetnames}
        nombre_hoja = nombres.get(clave_texto(def_hoja["hoja"]))
        if not nombre_hoja:
            raise ErrorConector(f"El Excel no tiene la hoja «{def_hoja['hoja']}»")
        hoja = self.libro[nombre_hoja]
        fila_cab = int(def_hoja.get("fila_cabecera", 1))
        filas = hoja.iter_rows(min_row=fila_cab, values_only=True)
        cabecera = [clave_texto(c) if c is not None else "" for c in next(filas, [])]
        indices = {}
        for campo, columna in def_hoja["columnas"].items():
            try:
                indices[campo] = cabecera.index(clave_texto(columna))
            except ValueError:
                if campo in def_hoja.get("obligatorias", OBLIGATORIAS.get(entidad, ["nif"])):
                    raise ErrorConector(f"Falta la columna «{columna}» en la hoja «{nombre_hoja}»") from None
        resultado = []
        for n, fila in enumerate(filas):
            if n >= MAX_FILAS:
                raise ErrorConector(f"La hoja «{nombre_hoja}» supera {MAX_FILAS} filas")
            if not any(v not in (None, "") for v in fila):
                continue
            datos = {c: (fila[i] if i < len(fila) else None) for c, i in indices.items()}
            for campo, tabla in def_hoja.get("valores", {}).items():
                if campo in datos:
                    datos[campo] = traducir_valor(datos[campo], tabla, por_defecto="desconocido")
            resultado.append(datos)
        return resultado


class ConectorExcel(Conector):
    tipo = "excel"

    def __init__(self, config: dict, obtener_fichero: Callable[[], bytes]):
        """config: {"mapeo": "excel/seguimiento-modelos.v1"} (o el mapeo directamente en "mapeo_en_linea")."""
        self.mapeo = config.get("mapeo_en_linea") or cargar_mapeo(config["mapeo"])
        self._obtener_fichero = obtener_fichero
        self._lector: LectorExcel | None = None

    @classmethod
    def desde_ruta(cls, config: dict, ruta: Path) -> "ConectorExcel":
        return cls(config, lambda: Path(ruta).read_bytes())

    @property
    def lector(self) -> LectorExcel:
        if self._lector is None:
            try:
                contenido = self._obtener_fichero()
            except OSError as exc:
                raise ErrorConector(f"No se pudo leer el fichero Excel: {exc}") from exc
            self._lector = LectorExcel(contenido, self.mapeo)
        return self._lector

    def probar_conexion(self) -> None:
        for entidad in self.mapeo.get("hojas", {}):
            self.lector.filas(entidad)

    def listar_clientes(self) -> list[ClienteExterno]:
        clientes = []
        for f in self.lector.filas("clientes"):
            nif = normalizar_nif(f.get("nif"))
            if not nif:
                continue
            emails = [e.strip().lower() for e in str(f.get("emails") or "").replace(";", ",").split(",")
                      if "@" in e]
            clientes.append(ClienteExterno(nif=nif, nombre=str(f.get("nombre") or "").strip(),
                                           tipo=f.get("tipo"), emails=emails,
                                           id_externo=str(f["id_externo"]) if f.get("id_externo") else None))
        return clientes

    def estado_modelos(self, nif: str, ejercicio: int | None = None,
                       periodo: str | None = None) -> list[ModeloFiscal]:
        nif = normalizar_nif(nif)
        periodo = normalizar_periodo(periodo) if periodo else None
        modelos = []
        for f in self.lector.filas("modelos"):
            if normalizar_nif(f.get("nif")) != nif:
                continue
            try:
                ej = int(f.get("ejercicio"))
            except (TypeError, ValueError):
                continue
            per = normalizar_periodo(f.get("periodo"))
            if (ejercicio and ej != ejercicio) or (periodo and per != periodo):
                continue
            estado = f.get("estado")
            resultado = f.get("resultado")
            modelos.append(ModeloFiscal(
                nif=nif, modelo=str(f.get("modelo")).strip(), ejercicio=ej, periodo=per,
                estado=EstadoModelo(estado) if estado in EstadoModelo._value2member_map_ else EstadoModelo.DESCONOCIDO,
                importe=_a_decimal(f.get("importe")),
                resultado=(ResultadoModelo(resultado) if resultado in ResultadoModelo._value2member_map_
                           else (ResultadoModelo.DESCONOCIDO if resultado else None)),
                fecha_presentacion=_a_fecha(f.get("fecha_presentacion")),
            ))
        return modelos

    def documentacion_pendiente(self, nif: str) -> list[DocumentoPendiente]:
        nif = normalizar_nif(nif)
        return [
            DocumentoPendiente(nif=nif, descripcion=str(f.get("descripcion") or "").strip(),
                               ejercicio=int(f["ejercicio"]) if f.get("ejercicio") else None,
                               periodo=normalizar_periodo(f["periodo"]) if f.get("periodo") else None)
            for f in self.lector.filas("pendientes")
            if normalizar_nif(f.get("nif")) == nif and f.get("descripcion")
        ]
