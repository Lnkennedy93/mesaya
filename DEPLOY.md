# Despliegue y operación de MesaYa

Guía para publicar MesaYa y mantenerla viva. Dos caminos: **VPS propio** (Docker + HTTPS automático) o **Fly.io**.
En ambos, MesaYa corre como **un solo proceso**: el tiempo real de la cocina y los límites de intentos viven en memoria.

## 0. Antes de empezar (una sola vez)

| Qué | Cómo |
|---|---|
| **Dominio** | Compra uno (ej. `mesaya.co`) y decide el subdominio de la carta (ej. `carta.mesaya.co`). **Los QR llevan el dominio dentro**: si lo cambias después, hay que reimprimirlos. |
| **Claves** | `python -c "import secrets; print(secrets.token_urlsafe(32))"` → `MESAYA_ADMIN_KEY`<br>`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` → `MESAYA_SECRET_KEY`. Guarda ambas en un gestor de contraseñas. |
| **Datos de tu empresa** | `MESAYA_COMPANY_*` (razón social, NIT, dirección, ciudad, correo y teléfono para reclamos). Salen en `/terminos` y `/privacidad`. Mientras falten, esas páginas muestran un aviso de **BORRADOR**. |
| **Correo (SMTP)** | Para recuperar contraseñas. Opciones con plan gratis o barato: Brevo, Zoho Mail, Google Workspace, Amazon SES. Configura SPF/DKIM de tu dominio para que no caiga en spam. Sin SMTP funciona, pero el enlace lo generas tú (ver §5). |
| **IA para leer cartas** | Crea una clave en Google AI Studio (https://aistudio.google.com/apikey) y ponla en `GEMINI_API_KEY`. Restríngela allí (solo la API de Generative Language) y fija un tope de gasto. Los restaurantes suben foto/PDF/.txt/.csv y revisan el borrador antes de agregarlo. **Ojo con el nivel gratuito:** cada modelo tiene un cupo diario pequeño (la app salta sola al modelo de respaldo cuando se agota) y, según los términos de Google, el contenido enviado puede usarse para mejorar sus productos. Para producción activa la facturación en Google AI Studio (nivel de pago). La lectura de una carta tarda ~15 s y corre en segundo plano. |
| **Lectura local de cartas (sin IA)** | Ya viene activa: PDF con texto, Word y Excel se leen en tu servidor sin costo. La imagen Docker incluye Tesseract (OCR en español) para fotos y PDF escaneados. La IA es solo respaldo; sin clave todo lo demás funciona. |
| **Abogado** | Que revise `web/terminos.html` y `web/privacidad.html`. Son un punto de partida, **no** asesoría legal. |

Copia `.env.example` a `.env` y completa los valores. Con `MESAYA_ENV=production` la app **se niega a arrancar** si falta HTTPS, la clave de administrador es débil, `MESAYA_DEMO=1` está activo, falta `MESAYA_SECRET_KEY` o no completaste los datos de tu empresa.

## 1. Opción A: servidor propio (VPS)

Funciona en cualquier VPS con Docker (DigitalOcean, Hetzner, Vultr, etc.). 1 vCPU / 1 GB de RAM alcanza para empezar.

```bash
git clone <tu-repositorio> mesaya && cd mesaya       # o copia la carpeta
cp .env.example .env && nano .env                    # completa los valores
# DNS: crea un registro A  carta.tudominio.com -> IP del servidor (antes de arrancar)
docker compose up -d --build
docker compose logs -f app                           # debe decir "Application startup complete"
```

Caddy obtiene y renueva el certificado HTTPS solo. Abre `https://carta.tudominio.com/healthz`: debe responder `{"ok":true,...}`.
Los datos viven en `./storage/` (base de datos, fotos y copias de seguridad).

Actualizar a una versión nueva: `git pull && docker compose up -d --build` (la base se migra sola al arrancar).

## 2. Opción B: Fly.io

```bash
fly launch --no-deploy --copy-config      # edita el nombre en fly.toml
fly volumes create mesaya_data --size 3
fly secrets set MESAYA_ADMIN_KEY=... MESAYA_SECRET_KEY=... MESAYA_COMPANY_NAME=... MESAYA_COMPANY_NIT=... \
  MESAYA_COMPANY_ADDRESS=... MESAYA_COMPANY_CITY=... MESAYA_COMPANY_EMAIL=... MESAYA_COMPANY_PHONE=... \
  MESAYA_SMTP_HOST=... MESAYA_SMTP_USER=... MESAYA_SMTP_PASSWORD=... MESAYA_SMTP_FROM=...
fly deploy
fly certs add carta.tudominio.com         # y apunta tu DNS como indica; luego cambia MESAYA_BASE_URL
```

Mantén **una sola máquina** (`min_machines_running = 1`, sin escalar a varias): con varias, los pedidos no llegarían a todas las pantallas de cocina.

## 2b. Base de datos: SQLite (por defecto) o PostgreSQL

MesaYa funciona con **SQLite** (cero configuración; la base es un archivo en `data/`) o con **PostgreSQL** si defines `MESAYA_DATABASE_URL`.
El esquema se crea y se actualiza solo al arrancar; no hay que correr migraciones a mano.

| | SQLite | PostgreSQL |
|---|---|---|
| Cuándo | Piloto y pocos restaurantes | Datos fuera del servidor de la app, copias/PITR del proveedor, crecer sin depender de un disco |
| Dónde vive | Disco de la app (`data/mesaya.db`) | Servicio aparte (Neon, Supabase, RDS) o contenedor `db` |
| Copias de la base | Las hace MesaYa (`data/backups/`) | **Las haces tú / tu proveedor** (la copia de MesaYa solo lleva las fotos) |

**PostgreSQL gestionado (Neon, Supabase…):** crea la base y copia la cadena de conexión (la «directa» o «session pooler», no la de *transaction* si tu proveedor ofrece ambas):
`MESAYA_DATABASE_URL=postgresql://usuario:clave@host/mesaya?sslmode=require`. En Fly: `fly secrets set MESAYA_DATABASE_URL=...`.

**PostgreSQL propio en tu VPS:** añade `POSTGRES_PASSWORD` a tu `.env` y arranca con el archivo extra
(la base no se expone a internet, solo la app la ve):

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
```

Copia diaria de la base en el VPS (guarda el `.sql.gz` fuera del servidor, igual que las copias de §4):

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml exec -T db pg_dump -U mesaya mesaya | gzip > mesaya-$(date +%F).sql.gz
# restaurar:  gunzip -c mesaya-AAAA-MM-DD.sql.gz | docker compose ... exec -T db psql -U mesaya mesaya
```

Notas: las escrituras (pedidos, pagos) se serializan con un candado de transacción para que el número de pedido y los pagos no se pisen;
a esta escala no se nota (probado con 300 mesas pidiendo a la vez). Las fotos siguen en disco (`uploads/`), y el tiempo real de la cocina sigue
siendo de **un solo proceso**, así que PostgreSQL no cambia la regla de una sola máquina. Si ya tienes datos en SQLite, avísame para migrarlos.

## 3. Primeros pasos tras publicar

1. Entra a `/signup` y crea **tu propio restaurante de prueba**. Haz un pedido real desde un celular con datos móviles (no con tu WiFi) y verifícalo en `/kitchen` desde otro dispositivo.
2. Si usas Cloudflare delante, comprueba que el pedido aparece en cocina **sin recargar** (el tiempo real exige que no se almacene en búfer la respuesta; Caddy ya lo configura).
3. Pide a un amigo que cree otra cuenta y verifica que no ve nada tuyo.
4. Prueba «¿Olvidaste tu contraseña?» de punta a punta.
5. Activa la monitorización (§6) y haz una **prueba de restauración** (§4).

## 4. Copias de seguridad

Automáticas: cada `MESAYA_BACKUP_EVERY_HOURS` (24 h por defecto) se guarda en `data/backups/` un `.zip` con la base de datos (verificada con `PRAGMA integrity_check`) y las fotos; se conservan las últimas `MESAYA_BACKUP_KEEP` (14). También al arrancar si la última es antigua.

```bash
# Manual / desde el host con docker compose:
docker compose exec app python -m app.backup now
docker compose exec app python -m app.backup list
```

**Una copia en el mismo disco no te salva si el disco se pierde.** Saca las copias del servidor:

- **VPS + rclone (recomendado):** instala rclone en el host, configura un destino (Google Drive, Backblaze B2, S3…) con `rclone config` y programa en `crontab -e`:
  `30 3 * * * rclone copy /ruta/a/mesaya/storage/backups remoto:mesaya-copias --max-age 3d`
- **Fly.io:** además de sus snapshots de volumen, descarga una copia con `fly ssh sftp get /app/data/backups/<archivo>` o usa `MESAYA_BACKUP_HOOK` con una imagen que incluya rclone.
- La **clave `MESAYA_SECRET_KEY` NO va dentro de las copias**: guárdala aparte (gestor de contraseñas). Sin ella no se pueden leer las credenciales de terceros guardadas.

### Restaurar (practícalo una vez, antes de necesitarlo)

```bash
docker compose stop app
docker compose run --rm app python -m app.backup restore /app/data/backups/mesaya-AAAAMMDD-HHMMSS.zip --yes
docker compose start app
```

Antes de reemplazar, se guarda lo que había como `mesaya.db.before-restore`.

## 5. Soporte: contraseña olvidada

- **Con SMTP:** el dueño usa «¿Olvidaste tu contraseña?» y recibe un enlace válido por 60 minutos, de un solo uso (al usarlo se cierran todas sus sesiones).
- **Sin SMTP o si el correo no llega:** genera el enlace tú y envíalo por WhatsApp:

```bash
curl -s -X POST https://carta.tudominio.com/api/superadmin/reset-link \
  -H "x-admin-key: TU_CLAVE" -H "content-type: application/json" -d '{"email":"dueno@restaurante.co"}'
```

Verifica antes que quien lo pide es realmente el dueño (por ejemplo, que escriba desde el teléfono registrado).

## 6. Monitoreo

- **Disponibilidad:** crea un monitor (UptimeRobot, Better Stack, etc.) sobre `https://carta.tudominio.com/healthz` cada 1–5 min con alerta a tu WhatsApp/correo.
- **Copias:** haz que el monitor busque el texto `"backup_stale":false`; si pasa a `true` (no hay copias recientes), te avisa.
- **Disco:** revisa el espacio (`df -h`) cada semana o configura la alerta del proveedor.
- **Logs:** `docker compose logs --tail 200 app`.

## 7. Datos personales: tareas que te tocan

- **Borrado:** el dueño puede borrar su cuenta y sus datos desde Ajustes → *Tus datos*. Las copias que lo contengan se destruyen con la rotación (14 días por defecto: ajusta la Política si cambias `MESAYA_BACKUP_KEEP`).
- **Reclamos:** atiende en 10 días hábiles las consultas y en 15 los reclamos (Ley 1581 de 2012) al correo que pusiste en `MESAYA_COMPANY_EMAIL`.
- **Versión de términos:** si cambias los textos, sube `TERMS_VERSION` en `app/config.py`; a cada dueño se le pedirá aceptar de nuevo al entrar al panel.
- **RNBD:** consulta con tu abogado si debes inscribir tu base de datos en el Registro Nacional de Bases de Datos de la SIC.

## 8. Lista de comprobación final

- [ ] `https://…/healthz` responde `ok` y `backup_age_hours` aparece tras el primer día.
- [ ] `/terminos` y `/privacidad` sin aviso de BORRADOR y revisadas por un abogado.
- [ ] Recuperar contraseña probado de extremo a extremo.
- [ ] Restauración de copia probada una vez.
- [ ] Copias saliendo del servidor (rclone/snapshots) y `MESAYA_SECRET_KEY` guardada fuera.
- [ ] Monitor de disponibilidad con alertas activas.
- [ ] Pedido real desde celular con datos móviles recibido en cocina.
- [ ] QR impresos **después** de fijar el dominio definitivo.
