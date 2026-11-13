"""Aislamiento entre gestorías: permisos del usuario "aibe_app" y Seguridad a Nivel de Fila (RLS).

Regla: el usuario "aibe_app" solo ve y escribe filas cuya gestoria_id coincida con
la gestoría fijada en la sesión (app.gestoria_id). Si no hay gestoría fijada, no ve nada.

IMPORTANTE para futuras migraciones: toda tabla nueva con datos de gestoría debe
activar RLS y su regla igual que aquí. Hay una prueba automática que lo comprueba.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

GESTORIA_ACTUAL = "NULLIF(current_setting('app.gestoria_id', true), '')::uuid"

# Tablas con datos de una gestoría y lo que puede hacer "aibe_app" en ellas
TABLAS = {
    "buzones": "SELECT, INSERT, UPDATE, DELETE",
    "entradas_conocimiento": "SELECT, INSERT, UPDATE, DELETE",
    "temas_sensibles": "SELECT, INSERT, UPDATE, DELETE",
    "clientes_finales": "SELECT, INSERT, UPDATE, DELETE",
    "contactos_cliente": "SELECT, INSERT, UPDATE, DELETE",
    "programas_gestoria": "SELECT, INSERT, UPDATE, DELETE",
    "puentes": "SELECT, UPDATE",
    "conversaciones": "SELECT, INSERT, UPDATE",
    "mensajes": "SELECT, INSERT, UPDATE",
    "adjuntos": "SELECT, INSERT",
    "derivaciones": "SELECT, INSERT, UPDATE",
    "tareas_programadas": "SELECT, INSERT, UPDATE, DELETE",
    "ejecuciones_tarea": "SELECT, INSERT, UPDATE",
    "usos_ia": "SELECT, INSERT",  # el registro de coste no se puede modificar
    "registro_eventos": "SELECT, INSERT",  # la auditoría no se puede modificar ni borrar
    "usuarios": "SELECT, INSERT, UPDATE",
}

# Columnas de "gestorias" que la propia gestoría puede cambiar (no su presupuesto ni su estado de alta)
COLUMNAS_EDITABLES_GESTORIA = (
    "nombre, nif, email_contacto, telefono, direccion, config, estado_agente, retencion_meses, actualizado_en"
)


def _si_existe_app(sql: str) -> str:
    return f"""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aibe_app') THEN
        {sql}
      END IF;
    END $$;
    """


def upgrade() -> None:
    for tabla, permisos in TABLAS.items():
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        check = f"gestoria_id = {GESTORIA_ACTUAL}"
        if tabla == "usuarios":
            # una gestoría nunca puede crear ni convertir a nadie en administrador de Aibe
            check += " AND rol <> 'admin_aibe'"
        op.execute(
            f"CREATE POLICY aislamiento_gestoria ON {tabla} "
            f"USING (gestoria_id = {GESTORIA_ACTUAL}) WITH CHECK ({check})"
        )
        op.execute(_si_existe_app(f"GRANT {permisos} ON {tabla} TO aibe_app;"))

    op.execute("ALTER TABLE gestorias ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY aislamiento_gestoria ON gestorias "
        f"USING (id = {GESTORIA_ACTUAL}) WITH CHECK (id = {GESTORIA_ACTUAL})"
    )
    op.execute(
        _si_existe_app(
            f"GRANT SELECT ON gestorias TO aibe_app; "
            f"GRANT UPDATE ({COLUMNAS_EDITABLES_GESTORIA}) ON gestorias TO aibe_app;"
        )
    )
    # Recetas: compartidas entre gestorías y de solo lectura para la aplicación
    op.execute(_si_existe_app("GRANT SELECT ON recetas TO aibe_app;"))


def downgrade() -> None:
    for tabla in [*TABLAS, "gestorias"]:
        op.execute(f"DROP POLICY IF EXISTS aislamiento_gestoria ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")
        op.execute(_si_existe_app(f"REVOKE ALL ON {tabla} FROM aibe_app;"))
    op.execute(_si_existe_app("REVOKE ALL ON recetas FROM aibe_app;"))
