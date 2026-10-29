# MesaYa en Vercel (todo en un solo proyecto)

Un proyecto de Vercel con **Vercel Services** (beta): el frontend Next.js (`web-next/`) atiende `/` y el backend FastAPI
(`backend/`) atiende `/api`, `/uploads`, `/assets`, `/healthz`, `/terminos` y `/privacidad`. La base de datos es Supabase.
La configuración está en [`vercel.json`](vercel.json). El navegador habla con un solo dominio, así que las cookies de sesión
y la IP del cliente funcionan sin CORS.

> Estado: preparado y probado **en local** (las 8 suites pasan contra Supabase con un esquema temporal). No se pudo desplegar
> desde el equipo de desarrollo (sin CLI ni cuenta de Vercel): el primer despliegue puede pedir ajustes menores.

## Qué cambió respecto al servidor tradicional

Las funciones de Vercel no comparten memoria, no tienen hilos de fondo ni disco, y cada petición admite 4,5 MB.

| Antes (un proceso) | Ahora (Vercel) |
|---|---|
| Tiempo real con SSE | **Sondeo** cada 5 s (cocina y cuenta del comensal): un pedido tarda hasta 5 s en aparecer |
| Límites de intentos en memoria | Tabla `rate_hits` en la base (compartida entre instancias) |
| Fotos y logos en `uploads/` | Tabla `images`; `/uploads/<nombre>` las sirve con caché largo |
| Borradores de importación en disco | Tablas `draft_images` e `import_chunks` |
| Cartas de hasta 30 MB en una petición | Se suben **por partes de 3 MB** (`/api/import/chunk`) y el servidor las reúne |
| Lectura con IA en un hilo + sondeo | Dentro de la misma petición (Vercel permite hasta 300 s) |
| Facturas emitidas en un hilo | Se emiten dentro de la petición; si fallan, se reintentan desde el panel |
| Copias propias, migraciones al arrancar | Copias de Supabase; el esquema se crea a mano (abajo) |
| OCR con Tesseract | **No disponible**: sin Tesseract, las fotos van directo a la IA (si hay `GEMINI_API_KEY`) |

## 1. Variables de entorno (Vercel → Settings → Environment Variables)

| Variable | Valor |
|---|---|
| `MESAYA_ENV` | `production` |
| `MESAYA_BASE_URL` | `https://tu-dominio` (los QR llevan esto dentro: defínelo **antes** de imprimirlos) |
| `MESAYA_DATABASE_URL` | Cadena de Supabase **Transaction pooler** (puerto **6543**), con la contraseña codificada (`#` = `%23`, `@` = `%40`) y `?sslmode=require` |
| `MESAYA_PG_POOL_MAX` | `3` (cada instancia abre pocas conexiones) |
| `MESAYA_BACKUP_EVERY_HOURS` | `0` (no hay disco local; las copias las hace Supabase) |
| `MESAYA_ADMIN_KEY` | Clave de 20+ caracteres para `/api/superadmin/*` |
| `MESAYA_SECRET_KEY` | Clave Fernet (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Guárdala fuera de Vercel |
| `MESAYA_COMPANY_NAME`, `_NIT`, `_ADDRESS`, `_CITY`, `_EMAIL`, `_PHONE` | Datos de tu empresa (salen en Términos y Privacidad). Sin ellos el backend **se niega a arrancar** en producción |
| `GEMINI_API_KEY` | Opcional: lee fotos y PDF difíciles. Con facturación activa en Google AI Studio |
| `MESAYA_SMTP_*` | Opcional: recuperar contraseña por correo (ver `.env.example`) |

No definas `MESAYA_DEMO`. Nunca subas `backend/.env`: `.vercelignore` ya lo excluye.

## 2. Crear el esquema en Supabase (una vez, y cada vez que cambie `app/db.py`)

El backend **no** migra al arrancar en Vercel (sería lento en cada arranque en frío). Desde tu equipo, con `backend/.env` apuntando a
Supabase por el **Session pooler** (puerto 5432, porque usa un candado de sesión):

```bash
cd backend
..\.venv\Scripts\python -m app.db        # Windows
```

Es idempotente: puedes repetirlo sin riesgo.

## 3. Desplegar

1. Sube el repositorio a GitHub.
2. En Vercel: **Add New → Project**, importa el repositorio, deja **Root Directory** en la raíz del repositorio y elige el preset **Services**.
3. Añade las variables del paso 1 y despliega.
4. Abre `https://tu-dominio/healthz`: debe responder `{"ok":true,"engine":"postgres",...}`.
5. Crea tu restaurante en `/signup`, haz un pedido desde un celular con datos móviles y mira que aparezca en `/kitchen` en unos segundos.

## Costos y límites a tener en cuenta

- **Vercel Hobby no permite uso comercial**: para vender, Pro (unos 20 USD/mes por usuario, dato de memoria: verifícalo en vercel.com/pricing). Supabase gratis pausa proyectos inactivos y no incluye copias diarias: para clientes reales, Pro.
- La cocina consulta 5 endpoints cada 5 s por pantalla abierta (~60 peticiones/min). Con muchos locales conviene un endpoint único o Supabase Realtime.
- Los endpoints SSE (`/api/stream`, `/api/public/<slug>/stream`) siguen en el código pero ya no los usa el frontend nuevo; el frontend antiguo (`web/`) sí, y solo funciona con un servidor tradicional (Docker/Fly).
- Si algo de esto no te sirve, el despliegue tradicional sigue disponible: [`DEPLOY.md`](DEPLOY.md) (Docker + Caddy o Fly.io).
