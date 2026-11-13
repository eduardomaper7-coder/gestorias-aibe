# Arquitectura explicada en lenguaje sencillo

## La idea en una frase

Un único servidor de Aibe atiende a muchas gestorías a la vez. Cada gestoría es un **perfil**
separado. Lo que entra por sus canales (de momento el correo) pasa por una cadena de pasos fija
y, cuando hace falta, el sistema consulta los programas de la gestoría a través de **conectores**.

```
  Buzones de correo de cada gestoría              Ordenador de la gestoría
          │                                       ┌──────────────────────┐
          ▼                                       │ PUENTE LOCAL (fase 5)│
 ┌──────────────── SERVIDOR AIBE (UE, Docker) ──┐ │ - lee a3ASESOR/Excel │
 │ Escucha de correo ─► Cola (Redis) ─► Trabajadores ◄── conexión cifrada ┤ - solo lectura       │
 │                                    │         │   que sale de la      │ - credenciales       │
 │                       ┌────────────┤         │   gestoría (sin       │   cifradas locales   │
 │                       ▼            ▼         │   abrir puertos)      └──────────────────────┘
 │                Agente (pasos)   Tareas programadas
 │                1 Clasificar (Claude Haiku, barato)
 │                2 Identificar al cliente (sin IA)
 │                3 Consultar datos (herramientas → conectores)
 │                4 Redactar (Claude Sonnet) o derivar a una persona
 │                5 Salvaguardas → enviar → registrar
 │                       │
 │                Módulo de IA: presupuesto + registro de tokens y coste
 │                       │
 │   PostgreSQL (datos separados por gestoría) · Adjuntos cifrados
 │   Panel web: administración de Aibe | panel de cada gestoría
 └──────────────────────────────────────────────┘
```

## Piezas principales

| Pieza | Qué hace | Dónde está |
|---|---|---|
| Perfiles de gestoría | Datos, configuración del agente, base de conocimiento, temas sensibles, clientes, programas, usuarios | `backend/app/tenancy`, `backend/app/models` |
| Plantillas | Punto de partida para dar de alta gestorías parecidas | `tenancy/plantillas_base/*.yaml` |
| Módulo de IA | Única puerta hacia Claude. Comprueba presupuesto, registra coste | `backend/app/llm` |
| Conectores | Leen datos de los programas de la gestoría con un formato común | `backend/app/connectors` |
| Mapeos y recetas | Dónde está cada dato dentro de cada programa (YAML versionado, no código) | `recetas/` |
| Canales | Interfaz común: correo hoy; Gmail, Microsoft 365 y WhatsApp mañana | `backend/app/channels` |
| Auditoría | Cada acción queda registrada con fecha, gestoría y resultado | `backend/app/audit`, tabla `registro_eventos` |

## Cómo se garantiza que una gestoría no vea datos de otra

Hay **dos barreras independientes**:

1. **En el programa.** Todo lo que hace una gestoría usa una conexión "de gestoría" que lleva
   fijado su identificador.
2. **En la propia base de datos.** El usuario de la base de datos que usa la aplicación (`aibe_app`)
   está sometido a *Seguridad a Nivel de Fila*: PostgreSQL solo le deja ver y escribir filas de la
   gestoría fijada. Aunque el programa tuviera un fallo y olvidara filtrar, la base de datos no
   devolvería datos ajenos.

Solo el panel de Aibe y los procesos internos usan la conexión "de sistema", que ve todo.

Además:
- las contraseñas de buzones y programas se guardan **cifradas** y "atadas" a su gestoría: el texto
  cifrado de una gestoría no se puede descifrar como si fuera de otra;
- el registro de auditoría y el de costes **no se pueden modificar ni borrar** desde la aplicación;
- una gestoría no puede cambiarse el presupuesto de IA ni crear administradores de Aibe.

Las pruebas automáticas de `backend/tests/test_aislamiento.py` comprueban todo esto.

## Por qué el agente es una "cadena de pasos" y no un chat libre

Un agente que "decide qué hacer" en cada paso gasta más tokens y es menos predecible. Aquí:
- Haiku (muy barato) clasifica y extrae datos en una llamada corta;
- el cliente se identifica por su correo, sin IA;
- las herramientas se llaman según el tipo de mensaje;
- Sonnet solo redacta, recibiendo únicamente los datos necesarios y el resumen de ese cliente;
- las instrucciones y la base de conocimiento de la gestoría se marcan para **caché**: la segunda
  vez cuestan alrededor de un 5 % (Sonnet) o un 10 % (Haiku) del precio normal.

Resultado esperado: **1–2 céntimos por correo atendido** (ver previsión en el plan).

## Modos del agente de cada gestoría

| Modo | Qué hace |
|---|---|
| **Simulación** | Procesa todo y guarda lo que habría respondido, sin enviar nada. Es el modo de alta. |
| **Activo** | Responde y envía automáticamente, salvo los casos que deriva a una persona. |
| **Pausado** | No procesa nada nuevo (los correos se siguen guardando). |

La primera activación la autoriza Aibe. Después, la gestoría puede pausar y reanudar ella misma.

## Tecnologías y por qué

| Tecnología | Por qué |
|---|---|
| Python + FastAPI | Encaja con el SDK de Anthropic, Playwright y pywinauto. Un solo lenguaje para todo. |
| PostgreSQL | Fiable, con Seguridad a Nivel de Fila (la segunda barrera de aislamiento). |
| Redis | Cola de trabajos y tareas programadas (desde la fase 2). |
| Panel: HTML generado en el servidor + HTMX (fase 4) | Sin una segunda aplicación en JavaScript que mantener. |
| Docker | El mismo entorno en tu ordenador y en el servidor. |
