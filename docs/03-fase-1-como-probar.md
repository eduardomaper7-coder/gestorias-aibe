# Cómo probar la fase 1 paso a paso (Windows)

La fase 1 no tiene todavía pantallas propias: el panel llega en la fase 4. Se prueba desde la
**documentación interactiva de la API**, una página web donde cada operación tiene un botón "Try it out".

## 1. Instalar (una sola vez)

1. **Docker Desktop**: https://www.docker.com/products/docker-desktop/
   - Instalar con las opciones por defecto (usa WSL 2) y reiniciar si lo pide.
   - Abrirlo y esperar a que diga "Engine running".
2. **Git para Windows**: https://git-scm.com/download/win (opciones por defecto).

## 2. Preparar la configuración

En la carpeta del proyecto, clic derecho → "Abrir en Terminal" (PowerShell):

```powershell
copy .env.example .env
notepad .env
```

En el Bloc de notas:
- pon dos contraseñas cualesquiera (largas) en `POSTGRES_PASSWORD` y `POSTGRES_APP_PASSWORD`;
- deja el resto como está por ahora;
- guarda.

## 3. Arrancar

```powershell
docker compose up --build -d
```

La primera vez tarda unos minutos (descarga e instala todo). Después:

```powershell
docker compose exec api python -m app.cli generar-claves
```

Copia en `.env` los valores de `SECRET_KEY` y `CLAVE_MAESTRA_CIFRADO` que aparecen, guarda y reinicia la API:

```powershell
docker compose up -d
```

> Las líneas `POSTGRES_...` que genera ese comando sirven para un servidor nuevo. En tu ordenador,
> no cambies las contraseñas de la base de datos una vez creada.

## 4. Crear tu usuario y datos de ejemplo

```powershell
docker compose exec api python -m app.cli crear-admin --email tu@aibetech.es --nombre "Tu nombre"
docker compose exec api python -m app.cli datos-demo
```

`datos-demo` crea dos gestorías desde la plantilla "fiscal de autónomos" y muestra el usuario y la
contraseña de cada responsable. **Apúntalos.**

## 5. Probar en el navegador

Abre http://localhost:8000/docs

1. **Entrar como Aibe.** `POST /auth/login` → *Try it out* → escribe tu correo y contraseña → *Execute*.
   La respuesta 200 muestra tus datos. El navegador guarda la sesión.
2. **Ver las gestorías.** `GET /admin/gestorias` → *Execute*.
   - Verás las dos gestorías en modo `simulacion`.
   - Cada una muestra su estado: buzones, mensajes del mes, coste de IA del mes y presupuesto.
3. **Ver la plantilla.** `GET /admin/plantillas`: la plantilla "Gestoría fiscal de autónomos" completa.
4. **Dar de alta una gestoría.** `POST /admin/gestorias` con el `plantilla_id` del paso anterior.
5. **Autorizar el agente.** `POST /admin/gestorias/{id}/agente` con `{"estado": "activo"}`.
   Prueba también `pausado`.
6. **Comprobar el aislamiento.**
   - `POST /auth/logout` y vuelve a entrar con el usuario de "Gestoría Ejemplo Norte".
   - `GET /gestoria/clientes`: solo ves sus 2 clientes, nunca el de "Asesoría Demo Sur".
   - `GET /admin/gestorias` responde 403 (prohibido).
7. **Editar la base de conocimiento.** `GET /gestoria/conocimiento`, y luego `PUT` sobre una entrada.
8. **Coste de IA.** Ejecuta en PowerShell:
   ```powershell
   docker compose exec api python -m app.cli probar-ia --gestoria gestoria-ejemplo-norte
   ```
   Después, `GET /gestoria/uso-ia` muestra la llamada y su coste. Con `PROVEEDOR_LLM=falso` no cuesta nada.

## 6. (Opcional) Probar Claude de verdad

Cuando tengas la clave de API de Anthropic:
1. En `.env`, pon `PROVEEDOR_LLM=claude` y `ANTHROPIC_API_KEY=...`.
2. Ejecuta `docker compose up -d`.
3. Repite el paso 8. La llamada usa Haiku y cuesta menos de una centésima de céntimo.

## 7. Pruebas automáticas

```powershell
docker compose run --rm api pytest
```

Deben salir **46 passed**. Comprueban, entre otras cosas, que una gestoría nunca puede ver ni
modificar datos de otra.

## Parar

```powershell
docker compose down      # los datos se conservan
```
