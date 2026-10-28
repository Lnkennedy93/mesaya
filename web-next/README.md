# MesaYa · frontend en Next.js

Versión en Next.js (App Router, React 19, TypeScript) del frontend. **No reemplaza nada**: la versión actual
(`web/` + FastAPI en `app/`) sigue intacta y es la que se publica hoy. Este frontend usa el mismo backend,
las mismas cookies de sesión y el mismo contrato `/api/...`; Next.js solo reenvía esas rutas (ver `next.config.mjs`).

## Estado

| Ruta | Estado |
|---|---|
| `/` (portada) | ✅ en Next.js |
| `/r/<slug>?t=&k=` (carta del comensal: pedido, cuenta, pagos, calificación) | ✅ en Next.js |
| `/login`, `/signup`, `/forgot`, `/reset?token=` | ✅ en Next.js |
| `/kitchen?r=` (cocina, sala, agotados, cierre de mesa, entrada del equipo con PIN) | ✅ en Next.js |
| `/admin` (resumen, carta con importación, mesas y QR, opiniones, ajustes, facturas y pagos) y `/print/qr` | ✅ en Next.js |
| `/terminos`, `/privacidad` | ➡️ las sirve el backend actual (rewrite `fallback`): son plantillas con los datos de la empresa que rellena el servidor |

## Correr (sin instalar Node: con Docker)

La URL del backend se fija **al compilar** (los rewrites de Next quedan guardados en el build).

```bash
docker volume create mesaya_nm && docker volume create mesaya_next
docker run --rm -e MESAYA_API_URL=http://host.docker.internal:8000 -v "$PWD:/w" -v mesaya_nm:/w/node_modules -v mesaya_next:/w/.next -w /w node:22-alpine sh -c "npm install && npx next build"
docker run -d --name mesaya-next -p 3000:3000 -v "$PWD:/w" -v mesaya_nm:/w/node_modules -v mesaya_next:/w/.next -w /w node:22-alpine npx next start -p 3000
```

Con Node 22 instalado: `npm install && MESAYA_API_URL=http://127.0.0.1:8000 npm run build && npm start`.
Los volúmenes de Docker mantienen `node_modules` y `.next` fuera de la carpeta sincronizada con OneDrive.
