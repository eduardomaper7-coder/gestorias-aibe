#!/bin/sh
# Se ejecuta UNA vez, al crear la base de datos por primera vez (contenedor oficial de PostgreSQL).
# Crea el usuario limitado "aibe_app", sometido a las reglas de aislamiento entre gestorías.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE ROLE aibe_app LOGIN PASSWORD '${POSTGRES_APP_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO aibe_app;
  GRANT USAGE ON SCHEMA public TO aibe_app;
EOSQL
