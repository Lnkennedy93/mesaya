# MesaYa — menú QR con pedidos, cocina y pago desde la mesa

SaaS multi-restaurante listo para vender. Replica y amplía la solución del reel de Santa IA
(«Tu QR solo muestra la carta y para pedir igual toca esperar al mesero»).

## Qué muestra el video → qué hace MesaYa

| En el video | En MesaYa |
|---|---|
| Menú QR en 5 minutos, con foto de cada plato | Importador (texto / foto / PDF con IA) + foto por plato (se optimiza a WebP) |
| Sin bajar ninguna app | Web móvil (PWA-friendly), sin registro del comensal |
| El pedido llega con el número de mesa | Pantalla de cocina en vivo (SSE): Nuevo → Preparando → Listo, sonido y cronómetro |
| Apagas el plato agotado | Toggle en carta y en cocina; desaparece al instante del celular del cliente |
| Cada uno paga desde su celular | Pago por plato, propina, «PAGADO» visible para toda la mesa, o pedir cuenta en caja |
| Tu venta 100 % tuya, sin comisión | Mensualidad fija; 0 % por pedido |
| 14 días gratis sin tarjeta | Trial automático de 14 días, bloqueo suave al vencer (la carta sigue visible) |

## Funciones extra (para venderlo mejor)

- **QR seguro por mesa**: cada mesa lleva un código secreto renovable; pedidos falsos desde fuera quedan rechazados.
- **Precios calculados en el servidor** (nunca se confía en el precio que manda el celular).
- **Opciones y adicionales** (término, tamaño, extras con recargo), alérgenos y etiquetas.
- **Llamar al mesero / pedir la cuenta**, vista de sala con estado de cada mesa y cobro en caja.
- **Seguimiento del pedido** para el cliente y aviso cuando está listo.
- **Opiniones**: 4–5 ★ se redirigen a tu reseña de Google; el resto llega a tu panel.
- **Reportes**: ventas, ticket promedio, horas pico, platos estrella, tiempo de cocina, propinas, export CSV.
- **Modo «solo carta»**, carta ES/EN, color y logo de marca, impuestos y propina configurables.
- **Planes con límites** (mesas, importaciones IA) y backoffice para activar suscripciones.
- QR imprimibles por mesa (`/print/qr`), landing de ventas (`/`) con precios.

> **Estado actual del producto:** pedir → cocina → terminar mesa. El cliente pide desde la mesa, el pedido llega a cocina
> y el cliente toca «Terminar mesa» para que el equipo cobre en caja y cierre la mesa.
> Los pagos en línea (Nequi / Bre-B / tarjeta) y la factura electrónica **están apagados por defecto** (el código sigue ahí):
> se reactivan con `MESAYA_ONLINE_PAYMENTS=1` y `MESAYA_INVOICING=1`. Con ambos en `0` desaparecen del panel, de la carta y de la API.

## Colombia: factura electrónica DIAN, Nequi y Bre-B (apagado por defecto)

| Necesidad | Cómo está resuelto | Estado |
|---|---|---|
| **Impuestos** | INC 8 % por defecto (o IVA 19/5 %) con precio incluido o no; desglose en la cuenta y en la factura. Propina voluntaria aparte, fuera de la base gravable. | Probado |
| **Factura electrónica DIAN** | Vía proveedor tecnológico (**Factus**): 1 factura por pago, a nombre del cliente (CC/NIT/CE/Pasaporte) o **Consumidor Final**, reintento automático y manual, panel de facturas con errores legibles. | Probado con respuestas simuladas; **falta validar contra tu sandbox de Factus** |
| **Nequi** | Cobro push vía **Wompi** (`POST /v1/transactions`, `NEQUI`), firma de integridad, webhook con checksum SHA256 y validación de monto, consulta de respaldo. | Probado con respuestas simuladas; **falta probar con tus llaves de Wompi sandbox** |
| **Bre-B** | **Confirmación asistida**: el cliente paga a tu llave con el valor exacto y toca «Ya pagué»; cocina/sala confirma que llegó el dinero. | Probado. No hay API pública de cobro Bre-B para comercios; cuando tu pasarela la publique se agrega como `payments.py` |
| **Credenciales** | Cifradas en reposo (Fernet) y nunca devueltas al navegador. Respalda `MESAYA_SECRET_KEY` (o `data/secret.key`). | Probado |

**Por qué no se factura directo a la DIAN.** Hacerlo exige habilitarte como facturador, firma digital XAdES, XML UBL 2.1 y el set de pruebas de la DIAN. Casi todos los SaaS usan un proveedor tecnológico autorizado; por eso MesaYa se integra con uno. Para añadir otro (Alegra, Siigo, Carvajal…) copia `_factus_issue` en `app/invoicing.py`.

**Pasos para dejarlo funcionando con un cliente real**
1. En Factus crea tu cuenta, habilita la resolución de numeración y genera credenciales (empieza en *sandbox*).
2. Panel → *Facturas y pagos*: razón social, NIT, tipo de impuesto, ID de municipio de Factus, credenciales → **Probar conexión** → elige el rango de numeración.
3. En Wompi crea el comercio, activa Nequi y pega la **URL de eventos** que muestra el panel; copia llaves y secretos al panel.
4. Haz un pedido de prueba con celular `3991111111` (aprobado en sandbox de Wompi) y verifica el número de factura.
5. **Revisa con tu contador** régimen (INC vs IVA), Consumidor Final y si debes emitir documento equivalente POS en lugar de factura de venta. Ajusta el mapeo de ids (tributos, documentos, unidad de medida) con el catálogo de tu sandbox: están en `FACTUS_TRIBUTE` y `colombia.ID_TYPES`.

## Arranque local

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Windows  (Linux/Mac: .venv/bin/pip)
.venv\Scripts\python seed.py                        # opcional: restaurante demo
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

En Windows basta con doble clic a `run.bat`.

- Landing: http://localhost:8000/
- Panel del dueño: http://localhost:8000/login → `demo@mesaya.app` / `demo12345`
- Cocina y sala: http://localhost:8000/kitchen → código `dragon-dorado`, PIN `1234`
- Carta del cliente (demo): http://localhost:8000/r/dragon-dorado?t=1&k=demo1

Pruebas (BD temporal, sin llamadas externas): `python -m tests.test_core` (producto base: pedir, cocina, terminar mesa), `python -m tests.test_reader` y `python -m tests.test_import_flow` (lector local: PDFs de varios diseños, Word, Excel, OCR simulado y el recorrido completo; requieren `pip install -r requirements-dev.txt`), `python -m tests.test_ai` (lectura de cartas con la IA simulada: respaldo de modelos, errores, cuota), `python -m tests.test_ops` (recuperar contraseña, términos/datos, borrado de cuenta, copias y restauración, validaciones de producción), y con los pagos activados `tests.test_flow` y `tests.test_colombia` (Nequi/Wompi, Bre-B, factura). En total 129 comprobaciones.

## Variables de entorno

| Variable | Para qué |
|---|---|
| `MESAYA_BASE_URL` | URL pública (los QR se generan con ella). **Obligatoria en producción** (`https://...`) |
| `MESAYA_DB`, `MESAYA_UPLOADS` | Rutas de la base SQLite y de las fotos (monta un volumen) |
| `MESAYA_ADMIN_KEY` | Tu clave de vendedor para `/api/superadmin/*` |
| `GEMINI_API_KEY` | Activa leer la carta que sube el restaurante (foto/PDF) con Google Gemini. Se lee de `.env` en local. Modelo: `MESAYA_GEMINI_MODEL` (por defecto `gemini-3.5-flash`) con respaldos `MESAYA_GEMINI_FALLBACK` |
| `MESAYA_MAX_IMPORT_MB`, `MESAYA_MAX_PHOTO_MB` | Peso máximo del archivo de carta (30 MB; un PDF con fotos pesa fácil 15 MB) y de las fotos de platos (20 MB; se reducen a WebP). Si usas un proxy, ajusta también su límite (Caddy ya viene en 35 MB) |
| `MESAYA_GEMINI_THINKING`, `MESAYA_AI_DEADLINE` | Velocidad de lectura (`low` por defecto) y tiempo máximo total (170 s) |
| `ANTHROPIC_API_KEY` | Alternativa a Gemini (`MESAYA_AI_PROVIDER=auto|gemini|anthropic`) |
| `MESAYA_SECRET_KEY` | Clave Fernet para cifrar credenciales de Wompi/Factus (si no existe se crea `data/secret.key`) |
| `MESAYA_ONLINE_PAYMENTS`, `MESAYA_INVOICING` | `1` reactiva pagos en línea / factura electrónica (apagados por defecto) |
| `MESAYA_DEMO` | `1` habilita el pago y la factura **simulados**. Nunca en producción |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Opcional: tarjetas con Stripe (webhook: `/api/webhooks/stripe`) |
| `MESAYA_TRIAL_DAYS` | Días de prueba (14) |
| `MESAYA_ENV` | `production` activa las validaciones de arranque (HTTPS, claves fuertes, sin demo, datos de tu empresa) |
| `MESAYA_COMPANY_NAME/NIT/ADDRESS/CITY/EMAIL/PHONE` | Tus datos: salen en `/terminos` y `/privacidad` |
| `MESAYA_SMTP_HOST/PORT/USER/PASSWORD/FROM` | Correo para recuperar contraseñas |
| `MESAYA_BACKUP_EVERY_HOURS`, `MESAYA_BACKUP_KEEP`, `MESAYA_BACKUP_DIR`, `MESAYA_BACKUP_HOOK` | Copias automáticas (24 h, últimas 14) y comando para subirlas a la nube |

Hay una plantilla completa en `.env.example`.

Con `MESAYA_DEMO=1` (lo pone `run.bat`) aparece un pago simulado que marca como pagado sin cobrar: solo para mostrar el producto.

## Cobrar tus suscripciones

Mientras no automatices el cobro, activa a cada cliente cuando pague:

```bash
curl -X POST https://TU-DOMINIO/api/superadmin/activate -H "x-admin-key: TU_CLAVE" \
  -H "content-type: application/json" -d '{"email":"cliente@correo.com","plan":"pro"}'
curl https://TU-DOMINIO/api/superadmin/restaurants -H "x-admin-key: TU_CLAVE"   # ver todos y sus pruebas
```

Los precios y límites de plan están en `app/config.py` (`PLANS`) y en `web/landing.html`: ajústalos a tu mercado.

## Lectura de cartas: sin IA primero

El restaurante sube su carta y la app arma un **borrador** (nada entra a la carta hasta que el dueño lo confirma).

| Archivo | Cómo se lee | Costo / privacidad |
|---|---|---|
| PDF con texto (Word, Canva, Google Docs…) | **Local** por posiciones y estilos: títulos = letra más grande, plato = texto con precio, descripción = texto pequeño; entiende 1–2 columnas, precio a la derecha, con puntos guía o debajo del nombre, y tamaños («Margarita (Grande)») | Gratis, ~1 s, no sale del servidor |
| Word `.docx`, Excel `.xlsx`, `.csv`, `.txt` | **Local** | Gratis, no sale del servidor |
| Foto o PDF escaneado | OCR local (Tesseract) si está instalado; con IA configurada se prefiere la IA para fotos | IA: sale a Google/Anthropic |
| Lectura local dudosa | Pasa a la IA de respaldo si está configurada; si no, muestra el borrador con avisos | |

Probado con una carta real de 4 páginas y 2 columnas (21 categorías, 106 platos): lectura local en ~1,3 s con los 106 precios correctos, idéntica a la de la IA.
**Fotos de los platos:** si el PDF trae fotos, la lectura local las extrae con su posición y se las asigna a cada plato (foto a la izquierda, a la derecha o encima del nombre; también en dos columnas). Se re-codifican a WebP, se muestran como miniaturas en el borrador (con ✕ para quitar una, «quitar repetidas» o «quitar todas») y solo se guardan al confirmar. Los borradores con fotos viven en `data/import_drafts/` y se borran al confirmar, a las 3 horas o al borrar la cuenta. Probado con la carta real con fotos (16,8 MB): 106 de 106 fotos asociadas a su plato, 95 únicas (0,8 MB en total). Límites: las fotos solo se extraen en la lectura **local** de PDF (no cuando lee la IA ni en Word/Excel); la resolución es la que tenga el PDF; y el restaurante debe tener derechos sobre las fotos que sube.

`MESAYA_MENU_READER=auto|local|ai` controla la política. El código está en `app/menu_reader.py`.
**Límites honestos:** cartas muy decorativas (texto como imagen, letra manuscrita, diseños circulares) o fotos torcidas necesitan IA u OCR; el OCR (Tesseract) no se probó aquí con fotos reales.

## Despliegue y operación

Ver **[DEPLOY.md](DEPLOY.md)**: VPS con Docker + HTTPS automático (`docker-compose.yml`, `deploy/Caddyfile`) o Fly.io (`fly.toml`),
copias de seguridad y restauración, soporte de contraseñas olvidadas, monitoreo y lista de comprobación final.
Corre **un solo proceso**: el tiempo real y los límites de intentos están en memoria. Para escalar a varios procesos cambia
`app/events.py` por Redis pub/sub y `rate_limit` por Redis.

## Cuenta, datos personales y copias

- **Recuperar contraseña:** `/forgot` envía un enlace (60 min, un solo uso, solo se guarda su hash; cierra todas las sesiones). Sin SMTP, soporte genera el enlace con `/api/superadmin/reset-link`.
- **Términos y Política de datos** (`/terminos`, `/privacidad`): plantillas según la Ley 1581 de 2012 con tus datos de empresa. **Revísalas con un abogado.** El registro exige aceptarlas y guarda fecha y versión; al subir `TERMS_VERSION` se pide aceptar de nuevo.
- **Derecho de supresión:** Ajustes → *Tus datos* borra la cuenta y todo lo asociado (incluidas las fotos). También exporta pedidos en CSV.
- **Copias automáticas:** base (con verificación de integridad) + fotos, rotación, `python -m app.backup now|list|restore`. `/healthz` reporta la edad de la última copia.

## Antes de salir a vender (pendientes honestos)

1. **Validar las integraciones colombianas en sandbox** (Wompi y Factus): se probaron con respuestas simuladas, no contra los servicios reales.
2. **Documento equivalente POS / notas crédito**: hoy solo se emite factura de venta; anulaciones y devoluciones se hacen en el panel de tu proveedor. Integración con POS no incluida.
3. **Cobro automático de tu mensualidad** (hoy manual con `superadmin/activate`).
4. **Revisión legal** de Términos y Política de datos, y consulta sobre inscripción en el RNBD.
5. **Sacar las copias del servidor** (rclone/snapshots; ver DEPLOY.md) y escalar a Postgres si pasas de unos cientos de restaurantes.
6. **Monitoreo externo** de `/healthz` y verificación del correo (SPF/DKIM) para la recuperación de contraseñas.
7. División de **un mismo plato entre varias personas** y pago en partes iguales: hoy se paga por plato.
8. Marca propia: «MesaYa» es un nombre de trabajo; verifica que esté libre antes de registrar dominio/marca.
