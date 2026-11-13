# Seguridad y RGPD: qué está hecho y qué falta

## Hecho en la fase 1

- **Aislamiento entre gestorías en dos capas**: el programa y la base de datos (RLS), con pruebas automáticas.
- **Cifrado de secretos** (AES-256-GCM) con una clave maestra fuera de la base de datos. Cada secreto
  está ligado a su gestoría.
- **Contraseñas** guardadas con Argon2 (no se pueden recuperar, solo comprobar).
- **Doble factor obligatorio** para administradores de Aibe (configurable solo para desarrollo local).
- **Sesiones** firmadas y con caducidad. Al activar el doble factor se cierran las demás sesiones.
- **Auditoría inalterable**: la aplicación puede añadir eventos y costes, pero no modificarlos ni borrarlos.
- **Permisos mínimos**:
  - una gestoría no puede cambiar su presupuesto ni su estado de alta, ni crear administradores de Aibe;
  - un "gestor" puede consultar pero no cambiar la configuración.
- **Conectores en solo lectura**: el conector de a3ASESOR solo genera consultas SELECT con
  identificadores validados y valores como parámetros. El ejecutor rechaza cualquier otra cosa.
- **Protección de coste**: presupuesto mensual de IA por gestoría y rechazo de peticiones desproporcionadas.
- **Baja sin pérdida**: dar de baja pausa todo y conserva los datos.

## Pendiente (y en qué fase)

| Tema | Fase |
|---|---|
| Limitar intentos de inicio de sesión (fuerza bruta) | 4 |
| Protección CSRF completa del panel (de momento: cookies SameSite=Lax y API JSON) | 4 |
| Exportación y borrado definitivo de todos los datos de una gestoría | 6 |
| Purga automática según la retención configurada (24 meses por defecto) | 6 |
| Copias de seguridad cifradas y prueba de restauración | 6 |
| Usuario propietario de la base de datos sin privilegios de superusuario en producción | 6 |
| Rotación de la clave maestra de cifrado | 6 |
| Alojamiento en la UE, HTTPS, cortafuegos y monitorización | 6 |

## RGPD: tareas que no son de programación

1. **Contrato de encargo de tratamiento** con cada gestoría. La gestoría es la responsable de los
   datos de sus clientes; Aibe es la encargada.
2. **Subencargados**: el proveedor de nube (UE) y **Anthropic**.
   - Firmar el DPA de Anthropic.
   - La API procesa los datos de forma global, así que hay que reflejarlo como transferencia
     internacional (cláusulas contractuales tipo o el marco UE-EE. UU. que aplique).
   - Revisar con un abogado especializado.
3. **Registro de actividades de tratamiento** de Aibe.
4. **Evaluación de impacto (EIPD)**: probablemente necesaria (datos fiscales, tratamiento automatizado
   a escala). Revisar con el asesor de protección de datos.
5. **Información a los clientes finales**: que les responde un asistente automático y que pueden pedir
   hablar con una persona (el agente ya lo permite).
6. **Reglamento Europeo de IA**: obligación de transparencia. Los clientes deben saber que interactúan
   con una IA. Revisar el texto de la firma automática antes de activar.
