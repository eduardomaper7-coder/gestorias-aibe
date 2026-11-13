import io
import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.connectors.a3asesor import ConectorA3Asesor, ConstructorConsultas, EjecutorSQL
from app.connectors.base import ErrorConector, EstadoModelo, ResultadoModelo, normalizar_periodo
from app.connectors.excel import ConectorExcel
from app.connectors.mapeos import cargar_mapeo

# ------------------------------------------------------------------ Excel


def libro_ejemplo() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Clientes"
    ws.append(["NIF", "Nombre", "Tipo", "Email", "Código"])
    ws.append(["00000001-R", "Juan Pérez", "Autónomo", "Juan@Ejemplo.example; juan2@ejemplo.example", 101])
    ws.append([None, None, None, None, None])
    ws.append(["B00000009", "Talleres SL", "Sociedad", "", 102])
    m = wb.create_sheet("modelos")  # mayúsculas distintas a propósito
    m.append(["NIF", "Modelo", "Ejercicio", "Periodo", "Estado", "Importe", "Resultado", "Fecha Presentacion"])
    m.append(["00000001R", "303", 2026, "3T", "Presentado", "1.234,56", "A ingresar", "20/10/2026"])
    m.append(["00000001R", "130", 2026, "T3", "Calculado", 210.5, "A ingresar", None])
    m.append(["00000001R", "303", 2026, 2, "Presentado", 0, "Cero", "15/07/2026"])
    m.append(["00000001R", "111", 2026, "3T", "Raro", None, None, None])
    m.append(["B00000009", "303", 2026, "3T", "Pendiente", None, None, None])
    p = wb.create_sheet("Documentación pendiente")
    p.append(["NIF", "Documento", "Ejercicio", "Periodo"])
    p.append(["00000001R", "Facturas de gastos de septiembre", 2026, "3T"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def conector_excel():
    contenido = libro_ejemplo()
    return ConectorExcel({"mapeo": "excel/seguimiento-modelos.v1"}, lambda: contenido)


def test_excel_clientes(conector_excel):
    conector_excel.probar_conexion()
    clientes = conector_excel.listar_clientes()
    assert [c.nif for c in clientes] == ["00000001R", "B00000009"]
    assert clientes[0].emails == ["juan@ejemplo.example", "juan2@ejemplo.example"]
    assert clientes[0].tipo == "autonomo" and clientes[1].tipo == "sociedad"
    assert clientes[0].id_externo == "101"


def test_excel_estado_modelos(conector_excel):
    todos = conector_excel.estado_modelos("00000001-r", ejercicio=2026)
    assert len(todos) == 4
    t3 = conector_excel.estado_modelos("00000001R", ejercicio=2026, periodo="3T")
    m303 = next(m for m in t3 if m.modelo == "303")
    assert m303.estado == EstadoModelo.PRESENTADO
    assert m303.importe == Decimal("1234.56")
    assert m303.resultado == ResultadoModelo.A_INGRESAR
    assert m303.fecha_presentacion == date(2026, 10, 20)
    assert next(m for m in t3 if m.modelo == "130").estado == EstadoModelo.CALCULADO
    # un estado que no sabemos interpretar se marca como desconocido (el agente no inventa)
    assert next(m for m in t3 if m.modelo == "111").estado == EstadoModelo.DESCONOCIDO
    assert conector_excel.estado_modelos("00000001R", periodo="2T")[0].resultado == ResultadoModelo.CERO


def test_excel_documentacion_pendiente(conector_excel):
    pendientes = conector_excel.documentacion_pendiente("00000001R")
    assert len(pendientes) == 1 and pendientes[0].periodo == "3T"
    assert conector_excel.documentacion_pendiente("B00000009") == []


def test_excel_con_columna_obligatoria_ausente():
    mapeo = cargar_mapeo("excel/seguimiento-modelos.v1")
    mapeo["hojas"]["modelos"]["columnas"]["estado"] = "Situación"
    contenido = libro_ejemplo()
    c = ConectorExcel({"mapeo_en_linea": mapeo}, lambda: contenido)
    with pytest.raises(ErrorConector, match="Situación"):
        c.estado_modelos("00000001R")


def test_excel_fichero_ilegible():
    with pytest.raises(ErrorConector):
        ConectorExcel({"mapeo": "excel/seguimiento-modelos.v1"}, lambda: b"no es un excel").listar_clientes()


@pytest.mark.parametrize("entrada,salida", [("1T", "1T"), ("T1", "1T"), (1, "1T"), ("1º trimestre", "1T"),
                                            ("4t", "4T"), ("0A", "0A"), ("anual", "0A"), (11, "11")])
def test_normalizar_periodo(entrada, salida):
    assert normalizar_periodo(entrada) == salida


def test_mapeo_no_puede_salir_de_la_carpeta_de_recetas():
    with pytest.raises(ErrorConector):
        cargar_mapeo("../config/precios_modelos")


# ------------------------------------------------------------------ a3ASESOR


class EjecutorSQLite(EjecutorSQL):
    """Imita la base de a3 con SQLite (mismos nombres que el mapeo, esquema "dbo")."""

    dialecto = "sqlite"

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("ATTACH DATABASE ':memory:' AS dbo")
        self.db.executescript("""
            CREATE TABLE dbo.EMPRESAS (CODIGO_EMPRESA INTEGER, NIF TEXT, RAZON_SOCIAL TEXT, TIPO_PERSONA TEXT,
                                       EMAIL TEXT);
            CREATE TABLE dbo.MODELOS_FISCALES (CODIGO_EMPRESA INTEGER, MODELO TEXT, EJERCICIO INTEGER, PERIODO TEXT,
                                               ESTADO TEXT, IMPORTE REAL, TIPO_RESULTADO TEXT,
                                               FECHA_PRESENTACION TEXT);
            INSERT INTO dbo.EMPRESAS VALUES (1, '00000001R', 'Juan Pérez', 'F', 'JUAN@ejemplo.example'),
                                            (2, 'B00000009', 'Talleres SL', 'J', NULL);
            INSERT INTO dbo.MODELOS_FISCALES VALUES
                (1, '303', 2026, '3T', 'T', 1234.56, 'I', '2026-10-20'),
                (1, '130', 2026, '3T', 'C', 210.5, 'I', NULL),
                (1, '303', 2025, '4T', 'T', 80, 'D', '2026-01-28'),
                (2, '303', 2026, '3T', 'P', NULL, NULL, NULL);
        """)
        self.consultas: list[str] = []

    def _ejecutar(self, sql, parametros):
        self.consultas.append(sql)
        return self.db.execute(sql, parametros).fetchall()


@pytest.fixture
def conector_a3():
    return ConectorA3Asesor({"mapeo": "a3asesor/mapeo-a3asesor-data.v0"}, EjecutorSQLite())


def test_a3_clientes(conector_a3):
    clientes = conector_a3.listar_clientes()
    assert [(c.nif, c.tipo, c.id_externo) for c in clientes] == [("00000001R", "autonomo", "1"),
                                                               ("B00000009", "sociedad", "2")]
    assert clientes[0].emails == ["juan@ejemplo.example"]


def test_a3_estado_modelos(conector_a3):
    t3 = conector_a3.estado_modelos("00000001R", ejercicio=2026, periodo="3T")
    assert {m.modelo: m.estado for m in t3} == {"303": EstadoModelo.PRESENTADO, "130": EstadoModelo.CALCULADO}
    m303 = next(m for m in t3 if m.modelo == "303")
    assert m303.resultado == ResultadoModelo.A_INGRESAR and m303.fecha_presentacion == date(2026, 10, 20)
    assert len(conector_a3.estado_modelos("00000001R")) == 3
    assert conector_a3.estado_modelos("NOEXISTE") == []
    # el NIF va como parámetro, nunca pegado dentro de la consulta
    assert all("00000001R" not in sql for sql in conector_a3.ejecutor.consultas)


def test_a3_consulta_para_sql_server():
    mapeo = cargar_mapeo("a3asesor/mapeo-a3asesor-data.v0")
    sql, campos = ConstructorConsultas(mapeo, "mssql").consulta_modelos(con_ejercicio=True)
    assert sql.startswith("SELECT TOP 2000 m.[MODELO]")
    assert "FROM [dbo].[MODELOS_FISCALES] m JOIN [dbo].[EMPRESAS] e" in sql
    assert sql.endswith("WHERE e.[NIF] = ? AND m.[EJERCICIO] = ?")
    assert campos[0] == "modelo"


def test_a3_mapeo_malicioso_se_rechaza():
    mapeo = cargar_mapeo("a3asesor/mapeo-a3asesor-data.v0")
    mapeo["entidades"]["empresas"]["tabla"] = "EMPRESAS; DROP TABLE X"
    with pytest.raises(ErrorConector, match="Identificador no válido"):
        ConstructorConsultas(mapeo, "mssql").consulta_clientes()


def test_ejecutor_solo_permite_lectura():
    e = EjecutorSQLite()
    for sql in ("DELETE FROM dbo.EMPRESAS", "UPDATE dbo.EMPRESAS SET NIF = 'x'",
                "SELECT 1; DROP TABLE dbo.EMPRESAS"):
        with pytest.raises(ErrorConector, match="Solo se permiten"):
            e.ejecutar(sql, [])
