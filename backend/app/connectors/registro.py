"""Catálogo de conectores disponibles. Añadir un programa nuevo = escribir su conector y registrarlo aquí."""
from app.connectors.a3asesor import ConectorA3Asesor
from app.connectors.excel import ConectorExcel

TIPOS_CONECTOR = {
    "excel": {
        "clase": ConectorExcel,
        "descripcion": "Libro Excel (.xlsx) con clientes, estado de modelos y documentación pendiente",
        "accesos": ["servidor", "puente"],
    },
    "a3asesor": {
        "clase": ConectorA3Asesor,
        "descripcion": "a3ASESOR escritorio: lectura de la base SQL de a3asesor Data (o SQL directo) vía puente",
        "accesos": ["puente"],
    },
    # Próximos: "a3innuva" (API Conectia), "sage_despachos", "holded" (API), "web_recetas", "escritorio_recetas"...
}
