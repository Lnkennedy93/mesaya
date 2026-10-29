import asyncio
import html
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import account, backup, config, db, events, invoicing, panel, public


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if config.ENV == "production":
        bad = config.blocking_problems()
        if bad:
            raise RuntimeError("Configuración de producción incompleta:\n - " + "\n - ".join(bad))
        for w in config.production_problems():
            logging.getLogger("mesaya").warning(w)
    events.set_loop(asyncio.get_running_loop())
    if not config.SERVERLESS:  # en Vercel no hay hilos de fondo, y el esquema se crea a mano: python -m app.db
        db.init_db()
        invoicing.start_retry_loop()  # reintenta facturas que fallaron (red, proveedor caído)
        backup.start_backup_loop()
    yield


app = FastAPI(title="MesaYa", docs_url=None, redoc_url=None, lifespan=lifespan)
app.include_router(panel.router)
app.include_router(account.router)
app.include_router(public.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if request.url.path.startswith("/api/") and "cache-control" not in resp.headers:
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


def page(name: str):
    def handler():
        return FileResponse(config.WEB_DIR / name, headers={"Cache-Control": "no-cache"})
    return handler


app.get("/", include_in_schema=False)(page("landing.html"))
app.get("/login", include_in_schema=False)(page("auth.html"))
app.get("/signup", include_in_schema=False)(page("auth.html"))
app.get("/forgot", include_in_schema=False)(page("auth.html"))
app.get("/reset", include_in_schema=False)(page("auth.html"))
app.get("/admin", include_in_schema=False)(page("admin.html"))
app.get("/kitchen", include_in_schema=False)(page("kitchen.html"))
app.get("/print/qr", include_in_schema=False)(page("print.html"))
app.get("/r/{slug}", include_in_schema=False)(page("menu.html"))


def legal_page(name: str):
    """Términos y Política de datos: plantillas con los datos de tu empresa (variables MESAYA_COMPANY_*)."""
    def handler():
        text = (config.WEB_DIR / name).read_text(encoding="utf-8")
        for k, v in config.COMPANY.items():
            text = text.replace("{{" + k + "}}", html.escape(v))
        draft = any(v.startswith("[") for v in config.COMPANY.values())
        text = text.replace("{{trial}}", str(config.TRIAL_DAYS)).replace("{{version}}", config.TERMS_VERSION).replace("{{base_url}}", html.escape(config.BASE_URL))
        text = text.replace("{{draft}}", '<div class="draft">BORRADOR: completa los datos de tu empresa y pide revisión de un abogado antes de publicar.</div>' if draft else "")
        return HTMLResponse(text, headers={"Cache-Control": "no-cache"})
    return handler


app.get("/terminos", include_in_schema=False)(legal_page("terminos.html"))
app.get("/privacidad", include_in_schema=False)(legal_page("privacidad.html"))

_started = time.time()


@app.get("/healthz", include_in_schema=False)
def healthz():
    """Para el monitor de disponibilidad (UptimeRobot, Better Stack...). Revisa base de datos y copias."""
    try:
        db.row("SELECT 1 AS x")
        db_ok = True
    except Exception:
        db_ok = False
    age = backup.last_backup_age_hours()
    enabled = config.BACKUP_EVERY_HOURS > 0
    stale = enabled and ((age is None and time.time() - _started > 6 * 3600) or (age is not None and age > config.BACKUP_EVERY_HOURS * 3))
    return JSONResponse({"ok": db_ok, "db": db_ok, "engine": "postgres" if db.IS_PG else "sqlite", "backup_age_hours": age, "backup_stale": bool(stale)}, status_code=200 if db_ok else 503)


@app.get("/uploads/{name}", include_in_schema=False)
def upload(name: str):
    """Fotos de platos y logos: viven en la base (Vercel no tiene disco). El nombre es aleatorio, así que la foto nunca cambia."""
    r = db.row("SELECT data FROM images WHERE name=?", (name,))
    if not r:
        raise HTTPException(404)
    return Response(bytes(r["data"]), media_type="image/webp", headers={"Cache-Control": "public, max-age=31536000, immutable"})


app.mount("/assets", StaticFiles(directory=config.WEB_DIR / "assets"), name="assets")
