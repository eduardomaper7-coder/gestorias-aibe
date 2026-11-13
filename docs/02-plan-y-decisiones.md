# Plan por fases y decisiones tomadas

Aprobado el 13-11-2026.

## Decisiones

| Tema | Decisión |
|---|---|
| Dónde procesa Claude los datos | **API directa de Anthropic.** Antes del primer cliente real: firmar el acuerdo de tratamiento de datos (DPA) de Anthropic y declararlo como transferencia internacional en los contratos con las gestorías. El módulo de IA es intercambiable: se puede pasar a Claude vía AWS o Google Cloud en región UE sin rehacer nada. |
| Puesta en marcha | Toda gestoría nueva empieza en **modo simulación**. La primera activación la autoriza Aibe. |
| Programas | Sistema preparado para cualquier programa (API, base de datos, ficheros, interfaz, OCR). **Excel incluido desde ya.** Primer programa objetivo: **a3ASESOR** (ver abajo). |
| Aplicación de demostración | La crea Aibe aparte, imitando a3ASESOR (escritorio Windows + SQL Server). El conector está preparado para probarse contra ella. |
| Retención de datos | Configurable por gestoría; **24 meses** por defecto. |
| Dominio | **aibetech.es** (panel en, p. ej., `panel.aibetech.es`). También se dispone de aibetech.com. |
| Primera plantilla | **Gestoría fiscal de autónomos.** |

### a3ASESOR: cómo nos integramos

- Escritorio Windows con base de datos SQL Server, sin API pública.
- **Lectura:** el puente local consulta en solo lectura la base SQL que genera el módulo **a3asesor Data**.
  Alternativa, con permiso de la gestoría: la base de datos de a3ASESOR directamente.
- **Escritura (más adelante):** ficheros Excel para el **Importador de datos** de a3, nunca escribiendo en su base de datos.
- **a3innuva** (nube) tiene API oficial (Conectia): será otro conector.
- Como la estructura de tablas no es pública, los nombres de tablas y campos están en un **mapeo YAML
  versionado** (`recetas/a3asesor/mapeo-a3asesor-data.v0.yaml`), no en el código. La versión 0 es
  hipotética; se creará la versión 1 cuando tengamos una instalación real o la aplicación de demostración.

## Previsión de volumen por gestoría (media española)

**Perfil típico de la gestoría.** <!-- fuentes al final -->
- Según el Barómetro de Wolters Kluwer, la mayoría de despachos tienen entre 4 y 10 profesionales.
- Esos despachos suelen tener carteras de menos de 200 clientes.
- Según otra intervención de la misma empresa, el 75 % de las asesorías tiene de media unos 200 clientes.

**Hipótesis propia, a validar con la gestoría piloto:**

| Concepto | Mes normal | Mes de cierre trimestral (abril, julio, octubre, enero) |
|---|---|---|
| Clientes finales | ~200 | ~200 |
| Correos de clientes recibidos | 400–600 | 1.000–1.500 |
| Atendidos por el agente sin intervención (≈60–70 %) | 250–400 | 650–1.000 |
| Recordatorios proactivos enviados | — | ~150–200 |

**Coste de IA estimado** (Haiku 5.5 para clasificar y Sonnet 5.5 para redactar, con caché):
- Clasificar un correo cuesta menos de 0,1 céntimos.
- Redactar una respuesta cuesta entre 1 y 2 céntimos.
- Total: **≈ 8–15 € en un mes normal y ≈ 20–35 € en un mes de cierre.**
- Queda por debajo del objetivo de 40–60 €.
- El presupuesto por gestoría (60 € por defecto) corta el gasto si algo se descontrola.

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 · Plan | Preguntas, arquitectura, costes | ✅ |
| 1 · Núcleo | Modelo de datos, perfiles y plantillas, aislamiento con pruebas, autenticación y doble factor, módulo de Claude con coste y presupuesto, conectores Excel y a3ASESOR (mapeo), interfaz de canales | ✅ |
| 2 · Correo profesional | IMAP (IDLE + sondeo), hilos, adjuntos cifrados, envío SMTP dentro del hilo, copia en "Enviados", detección de respuestas automáticas, documento sobre Gmail y Microsoft 365 | Siguiente |
| 3 · Agente | Clasificación, herramientas, base de conocimiento con caché, memoria por cliente, respuesta automática, derivación, salvaguardas, modo simulación, tarea de cierre trimestral | |
| 4 · Panel | Administración de Aibe y panel de gestoría (HTML + HTMX), subida de Excel | |
| 5 · Puente y recetas | Puente local Windows, motor de recetas, conector a3 contra la aplicación de demostración, recetas web y escritorio, corrección asistida por IA, nota legal | |
| 6 · Endurecimiento | Copias de seguridad, monitorización y alertas, exportación y borrado de una gestoría, revisión de seguridad, despliegue en la UE | |

## Coste de servidores (aproximado, sin IVA; confirmar precios antes de contratar)

- 1–10 gestorías: un servidor de 4 núcleos y 8 GB en la UE, más copias y almacenamiento: **≈ 30–60 €/mes**.
- 100–300 gestorías: base de datos gestionada, 2–4 servidores de trabajadores y monitorización: **≈ 200–500 €/mes**.
- Hetzner subió precios dos veces en 2026 y algunos planes baratos no se pueden contratar. Antes de
  contratar se compararán Hetzner, OVHcloud y Scaleway.

## Fuentes

- Wolters Kluwer, *Radiografía del despacho profesional*: https://www.wolterskluwer.com/es-es/expert-insights/radiografia-del-despacho-profesional-2023
- Newsbook, *Wolters Kluwer: es el momento del despacho profesional*: https://newsbook.es/actualidad/wolters-kluwer-es-el-momento-del-despacho-profesional-20241002112302.htm
- Precios de Claude: https://platform.claude.com/docs/en/about-claude/pricing
