# Handoff — MesaYa

Estado a: 27-oct-2026. Carpeta del proyecto: `C:\Users\lnken\OneDrive\Documentos\MesaYa` (no es un repositorio git todavía).

## 1. Objetivo

Construir y dejar listo para vender en **Colombia** un SaaS para restaurantes, cafés y bares, inspirado en el reel de Santa IA («Tu QR solo muestra la carta y para pedir igual toca esperar al mesero»), con funciones extra para diferenciarse.

Alcance **actual** del producto (acotado por el usuario): el cliente escanea el QR de su mesa, **pide desde el celular → el pedido llega a cocina con el número de mesa → termina la mesa** (pide la cuenta) y el equipo la cierra en caja. Los pagos en línea (Nequi / Bre-B / tarjeta) y la factura electrónica DIAN se construyeron pero quedaron **apagados por defecto** («por el momento»).

Objetivo operativo del último tramo: que el restaurante pueda **cargar su carta sin esfuerzo** (PDF, Word, Excel, foto, texto) **sin depender de IA** y con las fotos de los platos, y poder lanzar un **piloto** con 1–2 restaurantes.

## 2. Qué quedó hecho

**Producto base (probado, 260 comprobaciones automáticas en 7 suites + pruebas manuales en navegador)**
- Carta del cliente en celular (PWA-friendly, ES/EN): fotos, etiquetas, alérgenos, opciones/adicionales obligatorios u opcionales, carrito con «×» para quitar y «−» solo si cantidad > 1, seguimiento del pedido en vivo, «Terminar mesa y pedir la cuenta», calificación al cerrar (≥4★ → reseña Google).
- Cocina y sala (`/kitchen`, entra con código del restaurante + PIN): tablero Nuevo/Preparando/Listo con cronómetro y sonido, llamadas de mesero/cuenta, estado de cada mesa, **Cerrar mesa**, apagar platos agotados en un toque.
- Panel del dueño (`/admin`): resumen y reportes (ventas, ticket, horas pico, top platos, CSV), editor de carta, mesas con **QR seguro por mesa** (código secreto renovable) e impresión, opiniones, ajustes (marca, logo, impuesto, modo «solo carta»), cambio de contraseña, borrar cuenta, aceptar nueva versión de términos.
- Multi-restaurante, plan con límites (mesas, lecturas con IA), trial de 14 días sin tarjeta, backoffice por API (`/api/superadmin/*`) para activar suscripciones y generar enlaces de recuperación.
- Landing de ventas (`/`), registro/login (`/signup`, `/login`).

**Colombia (construido, apagado por defecto: `MESAYA_ONLINE_PAYMENTS=1`, `MESAYA_INVOICING=1`)**
- INC 8 % (o IVA 19/5 %) con precio incluido o no; propina voluntaria aparte y fuera de la factura; dígito de verificación de NIT.
- Pago **Nequi vía Wompi** (push + webhook con checksum SHA256 + validación de monto + consulta de respaldo), **Bre-B asistido** (el cliente paga a la llave y el equipo confirma), caja, Stripe opcional; pago dividido por plato.
- **Factura electrónica DIAN vía Factus** (una por pago, a nombre del cliente o Consumidor Final, reintentos, panel de errores). Credenciales cifradas (Fernet).
- Todo probado **con respuestas simuladas**, nunca contra Wompi/Factus reales.

**Operación**
- Recuperar contraseña (enlace 60 min, un solo uso, hash en BD; SMTP o enlace de soporte), `/terminos` y `/privacidad` (plantillas Ley 1581 con datos de la empresa por variables), consentimiento con fecha/versión, supresión de cuenta.
- Copias automáticas (BD verificada + fotos, rotación 14, restauración por CLI, `/healthz` con edad de la última copia), validaciones de arranque en producción, límites de intentos, cabeceras de seguridad.
- Despliegue: `Dockerfile` (usuario no root, healthcheck, Tesseract), `docker-compose.yml` + Caddy (HTTPS automático, SSE), `fly.toml`, `.env.example`, `DEPLOY.md`.

**Lectura de cartas (lo más reciente)**
- **Lector local sin IA** (`app/menu_reader.py`): PDF con texto (posiciones y estilos: título = letra mayor, plato = texto con precio, descripción = texto pequeño; 1–2 columnas, precio a la derecha / con puntos guía / debajo; tamaños → un plato por tamaño), Word `.docx`, Excel `.xlsx`, `.csv`, `.txt`. Política `MESAYA_MENU_READER=auto|local|ai`: local primero, IA solo de respaldo; fotos prefieren IA si existe.
- **IA con Gemini** (`app/ai_import.py`): cadena de modelos con respaldo, salto inmediato si se agota el cupo diario, espera según `retryDelay`, razonamiento bajo (~15 s), trabajos en segundo plano con avance (`app/jobs.py`), foto reducida a 2400 px antes de enviarla.
- **Fotos de platos** (`app/menu_images.py`, `app/drafts.py`): se extraen del PDF con su posición, se asocian al plato (izquierda/derecha/encima, 2 columnas), miniaturas con ✕ en el borrador, «quitar repetidas / todas», se guardan solo al confirmar.
- Límite de carta 30 MB y fotos de platos 20 MB (configurables).
- Verificado con las cartas reales del usuario: `Menu-Cassarola.pdf` y `Menu-Cassarola-con-fotos.pdf` (16,8 MB) → 21 categorías, 106/106 platos con precio, 106/106 fotos asociadas (comprobado visualmente), ~2–5 s, 0 llamadas a IA.

**Cómo ejecutar y probar**
- Arranque local: `run.bat` (crea `.venv` si falta, siembra la demo, abre http://localhost:8000). Hoy hay un servidor corriendo en el puerto 8000.
- Demo `Dragón Dorado`: panel `demo@mesaya.app`; **la contraseña y el PIN fueron rotados** y están en `data/demo-credentials.txt`. Carta del cliente: `http://localhost:8000/r/dragon-dorado?t=1&k=demo1` (mesas 1–8, clave `demoN`).
- Pruebas: `.venv\Scripts\python -m tests.<suite>` con `test_core`, `test_flow`, `test_colombia`, `test_ops`, `test_ai`, `test_reader`, `test_import_flow` (las dos últimas requieren `pip install -r requirements-dev.txt`). `tests/live_gemini.py` es manual y usa la clave real.

## 3. Qué falta

**Bloqueantes para vender**
1. **Publicar**: hosting + dominio + HTTPS; definir `MESAYA_BASE_URL` **antes de imprimir los QR**. `docker build`, `docker compose` y `fly deploy` **no se han ejecutado nunca** (ni siquiera se construyó la imagen).
2. **Probar con celulares reales y red real** (hoy solo navegador de escritorio emulado). No se logró un enlace público para que un compañero pruebe: localhost.run conectaba pero respondía «no tunnel»; quedó pendiente decidir entre **Cloudflare Tunnel** (requiere descargar `cloudflared.exe`, ~40 MB, aprobación del usuario), pinggy.io por SSH, o red local.
3. **Legal**: revisión de abogado de `web/terminos.html` y `web/privacidad.html`; completar `MESAYA_COMPANY_*` (hoy muestran «BORRADOR»); consultar inscripción RNBD; verificar que «MesaYa» esté libre como marca/dominio; los precios de la landing y `ventas@mesaya.app` son provisionales.
4. **Correo real (SMTP)** y SPF/DKIM: la recuperación de contraseña solo se probó con un envío simulado.
5. **Copias fuera del servidor** (rclone o snapshots), guardar `MESAYA_SECRET_KEY` aparte, monitor externo de `/healthz`, y **probar una restauración** en el entorno real.
6. **Cobro de la mensualidad**: hoy es manual (`/api/superadmin/activate`).

**Integraciones Colombia (cuando se reactiven)**
- Crear cuentas: RUT al día, **Wompi** (activar Nequi, llaves sandbox y producción, URL de eventos), **Factus** y **habilitación DIAN** (certificado de firma, set de pruebas, resolución de numeración). El usuario aún no tiene ninguna.
- Validar contra sandbox real y **ajustar el mapeo de ids de Factus** (tributos, tipos de documento, unidad de medida, municipio, `standard_code_id`, `payment_method_code`): salieron de documentación de terceros y memoria, la oficial no se pudo abrir.
- Confirmar con contador: INC vs IVA, factura de venta vs **documento equivalente POS** (no implementado), notas crédito/anulaciones (no implementadas), redondeo por línea (puede diferir 1 peso del total cobrado).
- Bre-B: sin API pública de cobro para comercios; sigue la confirmación asistida.

**Lectura de cartas**
- **OCR real no probado**: esta máquina no tiene Tesseract; el adaptador solo se probó con salida simulada (la imagen Docker lo instala, sin verificar).
- Las **fotos de platos solo se extraen con la lectura local de PDF** (no cuando lee la IA, ni en Word/Excel). Imágenes del `.docx` no soportadas.
- La «bolsa de papel» repetida de la carta de ejemplo no se distingue de una foto real: se deja al dueño quitarla.
- **Gemini en nivel gratuito**: cupo diario por modelo muy bajo (parte se gastó en pruebas) y, según términos de Google, el contenido puede usarse para mejorar sus productos → **activar facturación** para producción. La cuota «3 lecturas con IA» del plan Esencial es **vitalicia**, no mensual (ajuste pendiente).
- Latencia de Gemini variable (6–30 s, a veces 503/429); hay respaldo pero depende de Google.

**Seguridad / higiene**
- **La clave de Gemini se pegó en el chat**: restringirla en Google AI Studio (o rotarla) y poner tope de gasto. `.env` está en una carpeta sincronizada con **OneDrive**: no es sitio para secretos en producción.
- Borrar `data/demo-credentials.txt` y la demo antes de publicar; `run.bat` activa `MESAYA_DEMO=1` (pago/factura simulados): **nunca en producción**.
- Los dos PDFs del cliente (`Menu-Cassarola*.pdf`) están en la raíz del proyecto: moverlos fuera (ya están excluidos de git/Docker con `*.pdf`).
- Inicializar **git** (no hay control de versiones).

**Producto (mejoras ya identificadas)**
- Ticket impreso en cocina, edición/corrección del pedido por el cliente, mover/unir mesas, pedidos tomados por el mesero, integración con caja/POS, repartir un mismo plato entre varias personas y pago en partes iguales, auto-traducción de platos.
- Escala: 1 solo proceso (tiempo real y límites de intentos en memoria) → Redis; SQLite → Postgres si crece.
- Auditar un par de tipos de carta más (precios sin símbolo, columnas con precio pegado al nombre, cartas decorativas) con PDFs reales de otros restaurantes.

## 4. Decisiones tomadas

- **Stack**: Python + FastAPI + SQLite (WAL) + JavaScript/HTML/CSS sin frameworks. Razón: arranque sin instalar nada raro, pantallas livianas para celulares modestos, un solo servicio. Tiempo real por **SSE**.
- **Un solo proceso** en producción (documentado); límite de intentos y pub/sub en memoria.
- **Seguridad**: contraseñas con scrypt; sesiones por cookie `HttpOnly`/`Secure` según `https`; **precios siempre recalculados en el servidor**; QR con **secreto por mesa** renovable; credenciales de terceros **cifradas en reposo** (Fernet) y nunca devueltas al navegador; el pago/factura simulados solo con `MESAYA_DEMO=1`; el servidor **se niega a arrancar** en producción con configuración insegura.
- **Funciones apagadas por flags** en vez de borradas (`MESAYA_ONLINE_PAYMENTS`, `MESAYA_INVOICING`): el usuario pidió quitar pagos/factura «por el momento».
- **Facturación DIAN vía proveedor tecnológico (Factus)**, no firma directa de XML (exige habilitación, XAdES, UBL 2.1). Una factura por pago; la propina no entra a la factura.
- **Pagos Colombia**: Nequi por Wompi (único con API de cobro documentada oficialmente); **Bre-B asistido** porque no encontré API pública de cobro; cada restaurante usa **sus propias credenciales** (el dinero no pasa por MesaYa).
- **Cierre de mesa** (sin pagos en línea): el cliente pide la cuenta, el equipo cobra fuera y toca «Cerrar mesa»; registra un pago de caja interno.
- **Lectura de cartas: local primero, IA de respaldo** (gratis, instantánea, privada). Para fotos se prefiere la IA si existe. El borrador **siempre se revisa y confirma** antes de entrar a la carta; la salida de la IA se sanea (`normalize_draft`).
- **Gemini**: `gemini-3.5-flash` + respaldos `gemini-3.5-flash-lite` y `gemini-3.1-flash-lite` (los 2.5 están retirados para cuentas nuevas y los 3.6–3.8 estaban saturados); razonamiento `low`; el modelo se salta al siguiente cuando el cupo **diario** se agota; la clave se envía por cabecera, nunca en la URL ni en mensajes de error.
- **Lectura en segundo plano** con `job_id` y sondeo (la IA puede tardar >60 s; proxies cortan peticiones largas); un trabajo a la vez por restaurante; solo se descuenta cuota si la IA respondió bien.
- **Fotos**: re-codificadas a WebP (nunca se guarda el PDF), asociación por posición con selección automática de disposición, **no se descartan por repetición** (una foto compartida puede ser legítima): se avisa y el dueño decide. Borradores con fotos en `data/import_drafts/` con caducidad de 3 h.
- **Límites**: carta 30 MB (`MESAYA_MAX_IMPORT_MB`), foto de plato 20 MB, archivo a la IA ≤ 14 MB; Caddy a 35 MB.
- **Privacidad**: los PDF/Word/Excel/CSV leídos localmente no salen del servidor; las fotos/PDF enviados a la IA se declaran en la Política (Google/Anthropic).
- **Ubicación**: el proyecto se movió a `Documentos\MesaYa` y se aplanó (raíz = proyecto); `.venv` se recrea con `run.bat`.
- **Cuenta de prueba segura**: se rotaron la contraseña y el PIN de la demo antes de exponer nada; ningún túnel quedó abierto.
- **Pruebas**: sin red por defecto (Wompi, Factus, Gemini y correo simulados); PDFs/Word/Excel de prueba generados al vuelo con `fpdf2` (dependencia solo de desarrollo).

## 5. Archivos tocados

Todo el proyecto lo creó esta sesión. Se leyeron (sin modificar) `C:\Users\lnken\OneDrive\Desktop\Menu-Cassarola.pdf` y `Menu-Cassarola-con-fotos.pdf`.

**Backend `app/`**
- `main.py` — app FastAPI, rutas de páginas, `/healthz`, páginas legales, arranque (validación de producción, copias, limpieza de borradores).
- `config.py` — variables de entorno, `.env`, planes, límites, flags, datos de la empresa, SMTP, copias, IA.
- `db.py` — esquema SQLite, migraciones por columnas, conexiones.
- `auth.py` — hash de contraseña, sesiones, límites de intentos.
- `service.py` — totales/impuestos, validación de pedidos, cuenta de mesa, `finalize_payment`.
- `public.py` — API del comensal (carta, pedidos, cuenta, llamadas, pagos, calificación).
- `panel.py` — API del panel/cocina (cuenta, carta, mesas/QR, pedidos, reportes, **importación de cartas**, webhooks, backoffice).
- `account.py` — recuperar/cambiar contraseña, aceptar términos, borrar cuenta, enlace de soporte.
- `events.py` — pub/sub SSE. `jobs.py` — trabajos en segundo plano.
- `menu_reader.py` — lector local (PDF/Word/Excel/OCR). `menu_images.py` — fotos del PDF y asociación. `drafts.py` — borradores con fotos. `ai_import.py` — texto/CSV, Gemini/Claude, normalización.
- `payments.py` (Wompi/Nequi, Bre-B, Stripe), `invoicing.py` (Factus/demo), `colombia.py` (impuestos, DV del NIT, tipos de documento), `vault.py` (cifrado), `mailer.py` (SMTP), `backup.py` (copias/restauración).

**Frontend `web/`**
- `menu.html` (carta del cliente), `kitchen.html` (cocina y sala), `admin.html` (panel del dueño, importador con miniaturas), `auth.html` (registro/login/recuperación), `landing.html`, `print.html` (QR), `terminos.html`, `privacidad.html`, `assets/app.css`, `assets/common.js`.

**Pruebas `tests/`**
- `test_core.py`, `test_flow.py`, `test_colombia.py`, `test_ops.py`, `test_ai.py`, `test_reader.py`, `test_import_flow.py`, `menu_fixtures.py` (generadores de PDF/Word/Excel), `live_gemini.py` (manual, usa la clave real).

**Despliegue y documentación (raíz)**
- `Dockerfile`, `docker-compose.yml`, `deploy/Caddyfile`, `fly.toml`, `.dockerignore`, `.gitignore`, `.env.example`, `requirements.txt`, `requirements-dev.txt`, `run.bat`, `seed.py`, `README.md`, `DEPLOY.md`, `handoff.md` (este archivo).

**Archivos locales que NO deben viajar**
- `.env` (clave de Gemini), `data/` (BD demo, `secret.key`, copias, `demo-credentials.txt`, logs), `uploads/`, `.venv/`, y los dos `Menu-Cassarola*.pdf` de la raíz.
