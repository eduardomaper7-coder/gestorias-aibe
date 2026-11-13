# Aibe · Agentes IA para gestorías

Plataforma multicliente de **Aibe Technologies** (aibetech.es) que instala en cada gestoría un agente de IA.
El agente responde a los clientes de la gestoría con sus datos reales, informa del estado de sus trámites,
reclama documentación antes de cada cierre trimestral y deriva a una persona todo lo que sea asesoramiento.

> Estado: **fase 1 (núcleo) terminada.** Ver [docs/02-plan-y-decisiones.md](docs/02-plan-y-decisiones.md).

## Estructura

```
├── backend/                Servidor (Python + FastAPI)
│   ├── app/
│   │   ├── core/           configuración, base de datos, cifrado, contraseñas
│   │   ├── models/         tablas de la base de datos
│   │   ├── tenancy/        gestorías, plantillas, clientes finales (+ plantilla "fiscal de autónomos")
│   │   ├── auth/           inicio de sesión y doble factor
│   │   ├── api/            direcciones de la API (admin de Aibe y panel de gestoría)
│   │   ├── llm/            módulo de IA (Claude), coste y presupuesto
│   │   ├── connectors/     conectores con programas (Excel, a3ASESOR)
│   │   ├── channels/       interfaz común de canales (correo en la fase 2)
│   │   └── audit/          registro de auditoría
│   ├── migrations/         cambios de la base de datos, en orden
│   └── tests/              pruebas automáticas
├── recetas/                mapeos y recetas versionados (Excel, a3ASESOR...)
├── config/                 precios de los modelos de IA
├── deploy/                 scripts de despliegue (PostgreSQL)
├── docs/                   documentación en lenguaje sencillo
├── docker-compose.yml      entorno local completo
└── .env.example            plantilla de configuración (copiar a .env)
```

## Arrancar en tu ordenador (Windows)

Requisitos (una sola vez): **Docker Desktop** y **Git para Windows**. Pasos detallados en
[docs/03-fase-1-como-probar.md](docs/03-fase-1-como-probar.md).

```powershell
copy .env.example .env                       # y rellenar contraseñas y claves
docker compose up --build -d                 # base de datos + Redis + API
docker compose exec api python -m app.cli generar-claves
docker compose exec api python -m app.cli crear-admin --email tu@aibetech.es --nombre "Tu nombre"
docker compose exec api python -m app.cli datos-demo
```

Documentación interactiva de la API: <http://localhost:8000/docs>

## Pruebas automáticas

```powershell
docker compose run --rm api pytest
```

Incluyen las pruebas de **aislamiento entre gestorías** (`backend/tests/test_aislamiento.py`). Si fallan, no se despliega.

## Documentación

1. [Arquitectura explicada](docs/01-arquitectura.md)
2. [Plan por fases y decisiones](docs/02-plan-y-decisiones.md)
3. [Cómo probar la fase 1](docs/03-fase-1-como-probar.md)
4. [Seguridad y RGPD](docs/04-seguridad-y-rgpd.md)

## Normas del repositorio

- Nunca subir el fichero `.env` ni claves reales (ya está en `.gitignore`).
- Toda tabla nueva con datos de una gestoría lleva `gestoria_id` y su regla de aislamiento (RLS) en la migración.
  Hay una prueba que falla si se olvida.
- Las llamadas a la IA pasan siempre por `app/llm/servicio.py` (presupuesto + registro de coste).
