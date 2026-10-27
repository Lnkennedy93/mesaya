"""API del panel: cuenta, carta, mesas/QR, cocina, caja y reportes."""
import csv
import io
import json
import secrets
import shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone

import segno
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import ai_import, auth, colombia, config, db, drafts, events, invoicing, jobs, menu_reader, payments, service, vault
from .auth import Staff, now, owner_dep, rate_limit, staff_dep

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- cuenta
class SignupIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=8, max_length=100)
    currency: str = "COP"
    tables: int = Field(default=8, ge=1, le=60)
    accept_terms: bool = False


def _set_cookie(resp: Response, token: str):
    resp.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", secure=config.SECURE_COOKIES,
                    max_age=30 * 86400, path="/")


def _me(r: dict, role: str) -> dict:
    plan = auth.plan_info(r)
    left = None
    if r["subscription_status"] != "active":
        end = datetime.strptime(r["trial_ends_at"], "%Y-%m-%d %H:%M:%S")
        left = max(0, (end - datetime.utcnow()).days + (1 if end > datetime.utcnow() else 0))
    return {
        "role": role,
        "restaurant": {k: r[k] for k in (
            "id", "slug", "name", "email", "staff_pin", "currency", "decimals", "brand_color", "tagline", "logo",
            "tip_pct", "tax_pct", "tax_included", "tz_offset", "google_review_url", "whatsapp",
            "accepting_orders", "online_payments", "plan", "subscription_status", "trial_ends_at",
            "legal_name", "nit", "nit_dv", "tax_type", "fiscal_address", "fiscal_phone", "fiscal_municipality_id",
            "inv_provider", "inv_env", "inv_range_id", "wompi_env", "nequi_enabled", "breb_enabled", "breb_key",
            "breb_key_type", "breb_holder")},
        "integrations": {
            "inv_configured": bool(invoicing.secrets_of(r).get("client_id")),
            "wompi_configured": payments.wompi_ready(r),
            "wompi_events_set": bool(payments.keys(r).get("wompi_events")),
            "wompi_webhook_url": f"{config.BASE_URL}/api/webhooks/wompi/{r['slug']}",
        },
        "catalog": {"tax_types": colombia.TAX_TYPES, "id_types": colombia.ID_TYPES},
        "demo_mode": config.DEMO_MODE,
        "terms_current": r["terms_version"] == config.TERMS_VERSION,
        "features": {"payments": config.ONLINE_PAYMENTS, "invoicing": config.INVOICING},
        "plan": plan, "trial_days_left": left, "active": auth.is_active(r),
        "public_url": f"{config.BASE_URL}/r/{r['slug']}",
        "ai_available": ai_import.ai_available(), "ai_provider": ai_import.provider(), "ocr_available": menu_reader.ocr_available(), "menu_reader": config.MENU_READER, "max_import_mb": config.MAX_IMPORT_MB,
    }


@router.post("/signup")
def signup(body: SignupIn, request: Request, response: Response):
    rate_limit(f"signup:{request.client.host if request.client else 'x'}", 5, 3600)
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "Correo inválido")
    if not body.accept_terms:
        raise HTTPException(400, "Debes aceptar los Términos y la Política de tratamiento de datos para crear tu cuenta")
    if db.row("SELECT 1 FROM restaurants WHERE email=?", (email,)):
        raise HTTPException(409, "Ya existe una cuenta con ese correo")
    cur = body.currency.upper()[:3]
    trial_end = (datetime.now(timezone.utc) + timedelta(days=config.TRIAL_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    slug = service.unique_slug(body.name)
    pin = f"{secrets.randbelow(10000):04d}"
    co = cur == "COP"  # valores por defecto de un restaurante colombiano: INC 8 % incluido y propina sugerida 10 %
    with db.tx() as c:
        rid = c.execute(
            """INSERT INTO restaurants(slug, name, legal_name, email, password_hash, staff_pin, currency, decimals,
                                       tax_type, tax_pct, tax_included, trial_ends_at, created_at, terms_accepted_at, terms_version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (slug, body.name.strip(), body.name.strip(), email, auth.hash_password(body.password), pin, cur,
             service.decimals_for(cur), "INC" if co else "NONE", 8 if co else 0, 1, trial_end, now(),
             now(), config.TERMS_VERSION)).lastrowid
        for n in range(1, body.tables + 1):
            c.execute("INSERT INTO tables_(restaurant_id,label,secret) VALUES (?,?,?)", (rid, str(n), service.new_secret()))
    _set_cookie(response, auth.create_session(rid, "owner"))
    return _me(db.row("SELECT * FROM restaurants WHERE id=?", (rid,)), "owner")


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    rate_limit(f"login:{request.client.host if request.client else 'x'}", 10, 600)
    r = db.row("SELECT * FROM restaurants WHERE email=?", (body.email.strip().lower(),))
    if not r or not auth.verify_password(body.password, r["password_hash"]):
        raise HTTPException(401, "Correo o contraseña incorrectos")
    _set_cookie(response, auth.create_session(r["id"], "owner"))
    return _me(r, "owner")


class StaffLoginIn(BaseModel):
    slug: str
    pin: str


@router.post("/staff-login")
def staff_login(body: StaffLoginIn, request: Request, response: Response):
    rate_limit(f"pin:{request.client.host if request.client else 'x'}", 10, 600)
    r = db.row("SELECT * FROM restaurants WHERE slug=?", (body.slug.strip().lower(),))
    if not r or not secrets.compare_digest(r["staff_pin"], body.pin.strip()):
        raise HTTPException(401, "Restaurante o PIN incorrecto")
    _set_cookie(response, auth.create_session(r["id"], "staff", days=1))
    return _me(r, "staff")


@router.post("/logout")
def logout(request: Request, response: Response):
    tok = request.cookies.get(auth.COOKIE)
    if tok:
        db.run("DELETE FROM sessions WHERE token=?", (tok,))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(s: Staff = Depends(staff_dep)):
    return _me(s.r, s.role)


SETTINGS_FIELDS = {"name": str, "tagline": str, "brand_color": str, "tip_pct": int, "tax_pct": float,
                   "tax_included": int, "tz_offset": int, "google_review_url": str, "whatsapp": str,
                   "accepting_orders": int, "online_payments": int, "currency": str, "staff_pin": str,
                   "legal_name": str, "nit": str, "tax_type": str, "fiscal_address": str, "fiscal_phone": str,
                   "fiscal_municipality_id": int, "inv_provider": str, "inv_env": str, "inv_range_id": int,
                   "wompi_env": str, "nequi_enabled": int, "breb_enabled": int, "breb_key": str,
                   "breb_key_type": str, "breb_holder": str}
ENUMS = {"inv_provider": {"none", "factus", "mock"}, "inv_env": {"sandbox", "production"},
         "wompi_env": {"sandbox", "production"}, "tax_type": set(colombia.TAX_TYPES),
         "breb_key_type": {"celular", "cedula", "nit", "correo", "alfanumerica"}}


@router.put("/settings")
def update_settings(body: dict, s: Staff = Depends(owner_dep)):
    sets, vals = [], []
    for k, typ in SETTINGS_FIELDS.items():
        if k in body:
            v = body[k]
            try:
                v = typ(v)
            except (TypeError, ValueError):
                raise HTTPException(400, f"Valor inválido en {k}")
            if k == "brand_color" and not (len(v) == 7 and v.startswith("#")):
                raise HTTPException(400, "Color inválido")
            if k == "staff_pin" and not (v.isdigit() and 4 <= len(v) <= 8):
                raise HTTPException(400, "El PIN debe tener 4 a 8 dígitos")
            if k == "currency":
                v = v.upper()[:3]
                sets.append("decimals=?")
                vals.append(service.decimals_for(v))
            if k in ENUMS and v not in ENUMS[k]:
                raise HTTPException(400, f"Valor inválido en {k}")
            if k == "nit":
                v = "".join(ch for ch in v if ch.isdigit())[:12]
                sets.append("nit_dv=?")
                vals.append(colombia.nit_dv(v))
            if k == "tax_type" and "tax_pct" not in body:
                sets.append("tax_pct=?")
                vals.append(colombia.TAX_TYPES[v]["pct"])
            if k == "inv_provider" and v == "mock" and not config.DEMO_MODE:
                raise HTTPException(400, "El modo demostración de facturas solo está disponible con MESAYA_DEMO=1")
            if k in ("legal_name", "fiscal_address", "breb_holder", "tagline", "name"):
                v = v.strip()[:120]
            sets.append(f"{k}=?")
            vals.append(v)
    if sets:
        db.run(f"UPDATE restaurants SET {', '.join(sets)} WHERE id=?", (*vals, s.id))
        events.publish(f"r{s.id}", "settings", {})
    return _me(db.row("SELECT * FROM restaurants WHERE id=?", (s.id,)), s.role)


def _save_secrets(column: str, current: str, incoming: dict, allowed: tuple, s: Staff):
    """Guarda credenciales cifradas. Un campo vacío conserva el valor anterior."""
    data = vault.unseal(current)
    for k in allowed:
        v = str(incoming.get(k, "")).strip()
        if v:
            data[k] = v[:300]
    db.run(f"UPDATE restaurants SET {column}=? WHERE id=?", (vault.seal(data), s.id))


@router.put("/integrations/invoicing")
def set_invoicing_secrets(body: dict, s: Staff = Depends(owner_dep)):
    _save_secrets("inv_secrets", s.r["inv_secrets"], body, ("client_id", "client_secret", "username", "password"), s)
    invoicing._token_cache.pop(s.id, None)
    return _me(db.row("SELECT * FROM restaurants WHERE id=?", (s.id,)), s.role)


@router.put("/integrations/payments")
def set_payment_secrets(body: dict, s: Staff = Depends(owner_dep)):
    _save_secrets("pay_secrets", s.r["pay_secrets"], body, ("wompi_public", "wompi_private", "wompi_events", "wompi_integrity"), s)
    return _me(db.row("SELECT * FROM restaurants WHERE id=?", (s.id,)), s.role)


@router.post("/invoicing/test")
def test_invoicing(s: Staff = Depends(owner_dep)):
    """Valida credenciales con el proveedor y devuelve tus rangos de numeración."""
    if s.r["inv_provider"] != "factus":
        raise HTTPException(400, "Selecciona Factus como proveedor y guarda primero")
    try:
        return {"ranges": invoicing.factus_ranges(s.r)}
    except invoicing.InvoiceError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(502, "No se pudo conectar con Factus")


@router.get("/invoices")
def list_invoices(s: Staff = Depends(owner_dep)):
    rows = db.rows("SELECT i.*, p.table_label, p.provider AS pay_provider FROM invoices i JOIN payments p ON p.id=i.payment_id WHERE i.restaurant_id=? ORDER BY i.id DESC LIMIT 100", (s.id,))
    for r in rows:
        r["customer"] = db.jl(r["customer"], {})
    return {"invoices": rows}


@router.post("/invoices/{iid}/retry")
def retry_invoice(iid: int, s: Staff = Depends(owner_dep)):
    inv = db.row("SELECT * FROM invoices WHERE id=? AND restaurant_id=?", (iid, s.id))
    if not inv:
        raise HTTPException(404)
    return {"invoice": invoicing.issue(iid)}


@router.post("/logo")
async def upload_logo(file: UploadFile = File(...), s: Staff = Depends(owner_dep)):
    path = await _save_image(file, s.id, max_px=400)
    db.run("UPDATE restaurants SET logo=? WHERE id=?", (path, s.id))
    return {"logo": path}


# ---------------------------------------------------------------- imágenes
_MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp"}


async def _save_image(file: UploadFile, rid: int, max_px=1000) -> str:
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"La imagen pesa más de {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if not any(data.startswith(m) for m in _MAGIC):
        raise HTTPException(400, "Solo JPG, PNG o WebP")
    name = f"{rid}_{secrets.token_hex(8)}.webp"
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        im.thumbnail((max_px, max_px))
        im.convert("RGB").save(config.UPLOAD_DIR / name, "WEBP", quality=82)
    except Exception:
        raise HTTPException(400, "No se pudo leer la imagen")
    return f"/uploads/{name}"


# ---------------------------------------------------------------- carta
@router.get("/menu")
def admin_menu(s: Staff = Depends(staff_dep)):
    cats = db.rows("SELECT * FROM categories WHERE restaurant_id=? ORDER BY sort, id", (s.id,))
    items = [service.item_public(i) for i in db.rows("SELECT * FROM items WHERE restaurant_id=? ORDER BY sort, id", (s.id,))]
    for c in cats:
        c["items"] = [i for i in items if i["category_id"] == c["id"]]
    return {"categories": cats}


class CatIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.post("/categories")
def add_category(body: CatIn, s: Staff = Depends(owner_dep)):
    n = db.row("SELECT COALESCE(MAX(sort),0)+1 AS n FROM categories WHERE restaurant_id=?", (s.id,))["n"]
    return {"id": db.run("INSERT INTO categories(restaurant_id,name,sort) VALUES (?,?,?)", (s.id, body.name.strip(), n))}


@router.put("/categories/{cid}")
def edit_category(cid: int, body: CatIn, s: Staff = Depends(owner_dep)):
    db.run("UPDATE categories SET name=? WHERE id=? AND restaurant_id=?", (body.name.strip(), cid, s.id))
    return {"ok": True}


@router.delete("/categories/{cid}")
def del_category(cid: int, s: Staff = Depends(owner_dep)):
    db.run("DELETE FROM categories WHERE id=? AND restaurant_id=?", (cid, s.id))
    return {"ok": True}


@router.post("/categories/{cid}/move")
def move_category(cid: int, body: dict, s: Staff = Depends(owner_dep)):
    cats = db.rows("SELECT id FROM categories WHERE restaurant_id=? ORDER BY sort, id", (s.id,))
    ids = [c["id"] for c in cats]
    if cid not in ids:
        raise HTTPException(404)
    i = ids.index(cid)
    j = i + (-1 if body.get("dir") == "up" else 1)
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
        with db.tx() as c:
            for n, x in enumerate(ids):
                c.execute("UPDATE categories SET sort=? WHERE id=?", (n, x))
    return {"ok": True}


class ItemIn(BaseModel):
    category_id: int
    name: str = Field(min_length=1, max_length=90)
    description: str = Field(default="", max_length=400)
    price: int = Field(ge=0, le=100_000_000)
    featured: bool = False
    tags: list[str] = []
    allergens: list[str] = []
    options: list[dict] = []


def _clean_options(opts: list[dict]) -> list[dict]:
    out = []
    for g in opts[:8]:
        name = str(g.get("name", "")).strip()[:50]
        os_ = [{"name": str(o.get("name", "")).strip()[:50], "price": int(o.get("price") or 0)}
               for o in g.get("options", []) if str(o.get("name", "")).strip()][:20]
        if name and os_:
            out.append({"name": name, "required": bool(g.get("required")), "multi": bool(g.get("multi")), "options": os_})
    return out


def _check_cat(s: Staff, cid: int):
    if not db.row("SELECT 1 FROM categories WHERE id=? AND restaurant_id=?", (cid, s.id)):
        raise HTTPException(404, "Categoría no encontrada")


@router.post("/items")
def add_item(body: ItemIn, s: Staff = Depends(owner_dep)):
    _check_cat(s, body.category_id)
    n = db.row("SELECT COALESCE(MAX(sort),0)+1 AS n FROM items WHERE category_id=?", (body.category_id,))["n"]
    iid = db.run(
        """INSERT INTO items(restaurant_id,category_id,name,description,price,featured,tags,allergens,options,sort)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (s.id, body.category_id, body.name.strip(), body.description.strip(), body.price, int(body.featured),
         json.dumps(body.tags[:8]), json.dumps(body.allergens[:14]), json.dumps(_clean_options(body.options)), n))
    return {"id": iid}


@router.put("/items/{iid}")
def edit_item(iid: int, body: ItemIn, s: Staff = Depends(owner_dep)):
    _check_cat(s, body.category_id)
    db.run(
        """UPDATE items SET category_id=?,name=?,description=?,price=?,featured=?,tags=?,allergens=?,options=?
           WHERE id=? AND restaurant_id=?""",
        (body.category_id, body.name.strip(), body.description.strip(), body.price, int(body.featured),
         json.dumps(body.tags[:8]), json.dumps(body.allergens[:14]), json.dumps(_clean_options(body.options)), iid, s.id))
    events.publish(f"r{s.id}", "menu", {})
    return {"ok": True}


@router.delete("/items/{iid}")
def del_item(iid: int, s: Staff = Depends(owner_dep)):
    db.run("DELETE FROM items WHERE id=? AND restaurant_id=?", (iid, s.id))
    return {"ok": True}


@router.post("/items/{iid}/availability")
def set_availability(iid: int, body: dict, s: Staff = Depends(staff_dep)):
    """Apagar un plato agotado en un toque (también lo puede hacer cocina)."""
    db.run("UPDATE items SET available=? WHERE id=? AND restaurant_id=?", (int(bool(body.get("available"))), iid, s.id))
    events.publish(f"r{s.id}", "menu", {})
    return {"ok": True}


@router.post("/items/{iid}/image")
async def item_image(iid: int, file: UploadFile = File(...), s: Staff = Depends(owner_dep)):
    if not db.row("SELECT 1 FROM items WHERE id=? AND restaurant_id=?", (iid, s.id)):
        raise HTTPException(404)
    path = await _save_image(file, s.id)
    db.run("UPDATE items SET image=? WHERE id=?", (path, iid))
    return {"image": path}


# ---------------------------------------------------------------- importar carta
@router.post("/import/text")
def import_text(body: dict, s: Staff = Depends(owner_dep)):
    return ai_import.parse_text(str(body.get("text", ""))[:30000])


def _read_menu(restaurant_id: int, data: bytes, media_type: str) -> dict:
    """Lectura con IA en segundo plano. Solo descuenta del plan si salió bien."""
    res = ai_import.parse_file(data, media_type)
    if not res["categories"]:
        raise ai_import.AIError("No encontramos platos en el archivo. Prueba con una foto más nítida o con el texto pegado.")
    db.run("UPDATE restaurants SET ai_imports_used=ai_imports_used+1 WHERE id=?", (restaurant_id,))
    res["source"], res["warnings"] = "ai", []
    return res


def _local_response(rid: int, local: dict, extra_warnings: list | None = None) -> dict:
    """Quita los bytes de las fotos del JSON: se guardan en el servidor y el navegador recibe solo referencias."""
    local = dict(local)
    imgs = local.pop("images", [])
    local.pop("good", None)
    if extra_warnings:
        local["warnings"] = local["warnings"] + extra_warnings
    did = drafts.create(rid, imgs) if imgs else None
    if did:
        local["draft_id"] = did
    for c in local["categories"]:
        for it in c["items"]:
            n = it.pop("image_idx", None)
            if n is not None and did:
                it["image"] = f"/api/import/draft/{did}/{n}.webp"
                it["image_ref"] = [did, n]
    return local


_KIND = {"application/pdf": "pdf", "image/jpeg": "image", "image/png": "image", "image/webp": "image"}


@router.post("/import/ai")
async def import_ai(file: UploadFile = File(...), s: Staff = Depends(owner_dep)):
    """Lee la carta que sube el restaurante y devuelve un BORRADOR para revisar (nada entra a la carta hasta /import/commit).

    Orden (MESAYA_MENU_READER=auto): .txt/.csv, Word, Excel y PDF con texto se leen LOCALMENTE (gratis, al instante, sin IA).
    Si la lectura local no es confiable, o es una foto, se usa la IA en segundo plano (responde 202 + job_id)."""
    from starlette.concurrency import run_in_threadpool
    rate_limit(f"aiimport:{s.id}", 8, 600)
    limit = config.MAX_IMPORT_MB * 1024 * 1024
    data = await file.read(limit + 1)  # lee solo hasta el límite: un archivo gigante no llena la memoria
    if len(data) > limit:
        raise HTTPException(413, f"El archivo pesa más de {config.MAX_IMPORT_MB} MB. Comprímelo o súbelo sin fotos pesadas (por ejemplo, exporta el PDF en calidad media).")
    mt = ai_import.sniff_media_type(data, file.filename or "")
    office = menu_reader.sniff_office(data)
    kind = _KIND.get(mt) or office
    if not mt and not office:
        raise HTTPException(400, "Sube un PDF, un archivo de Word (.docx) o Excel (.xlsx), una foto JPG/PNG/WebP, o un .txt / .csv")
    if mt in ai_import.TEXT_TYPES:
        try:
            res = ai_import.parse_file(data, mt)
        except Exception:
            raise HTTPException(502, "No se pudo leer el archivo, revisa su formato")
        if not res["categories"]:
            raise HTTPException(422, "No encontramos platos en el archivo. Usa «Nombre - precio» por línea o un CSV con columnas plato y precio.")
        return {**res, "source": "local", "warnings": []}

    mode = config.MENU_READER  # auto | local | ai
    ai_ok = ai_import.ai_available() and kind in ("pdf", "image")
    prefer_ai = kind == "image" and mode != "local" and ai_ok  # una foto la lee mejor la IA que el OCR
    local, local_err = None, ""
    if mode != "ai" and not prefer_ai or kind in ("docx", "xlsx"):
        try:
            local = await run_in_threadpool(menu_reader.read_local, data, kind, s.r["decimals"])
        except menu_reader.Unreadable as e:
            local_err = str(e)
        except Exception:
            local_err = "No se pudo leer el archivo."
        if local and local["good"]:
            return _local_response(s.id, local)
    if kind in ("docx", "xlsx"):
        if local and local["categories"]:
            return _local_response(s.id, local, ["Lectura de baja confianza: revisa con cuidado cada plato y precio."])
        raise HTTPException(422, local_err or "No encontramos platos con precio en el archivo. Revisa que cada plato tenga su precio.")

    # PDF/foto: IA como respaldo (o primera opción para fotos)
    if mode != "local" and ai_ok:
        if s.r["ai_imports_used"] >= auth.plan_info(s.r)["ai_imports"]:
            if local and local["categories"]:
                return _local_response(s.id, local, ["Se acabaron las lecturas con IA de tu plan; esta lectura local es de baja confianza: revísala."])
            raise HTTPException(402, "Llegaste al límite de lecturas con IA de tu plan y este archivo no se pudo leer localmente.")
        if jobs.running_for(s.id):
            raise HTTPException(409, "Ya estamos leyendo otra carta tuya. Espera a que termine.")
        job_id = jobs.start(s.id, _read_menu, s.id, data, mt)
        return JSONResponse({"job_id": job_id, "reason": local_err or ("local_baja_confianza" if local else "")}, status_code=202)
    if local and local["categories"]:
        return _local_response(s.id, local, ["Lectura de baja confianza (sin IA disponible): revisa cada plato y precio antes de agregar."])
    if local_err:
        raise HTTPException(422, local_err + " Mientras tanto puedes pegar el texto de tu carta o subirla en Word, Excel o un PDF con texto.")
    raise HTTPException(422, "No encontramos platos con precio en el archivo.")


@router.get("/import/ai/{job_id}")
def import_ai_status(job_id: str, s: Staff = Depends(owner_dep)):
    j = jobs.get(job_id, s.id)
    if not j:
        raise HTTPException(404, "Ese trabajo ya no existe. Vuelve a subir el archivo.")
    return j


@router.post("/import/commit")
def import_commit(body: dict, s: Staff = Depends(owner_dep)):
    """Agrega el borrador revisado a la carta. Si trae fotos (image_ref), las pasa del borrador a uploads/."""
    added, photos = 0, 0
    copied: dict[tuple, str] = {}
    new_files: list[Path] = []

    def photo_for(it: dict) -> str:
        ref = it.get("image_ref")
        if not (isinstance(ref, (list, tuple)) and len(ref) == 2):
            return ""
        src = drafts.path(s.id, ref[0], ref[1])
        if src is None:
            return ""
        key = (ref[0], src.name)
        if key not in copied:  # la misma foto en varios platos se guarda una sola vez
            config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            name = f"{s.id}_{secrets.token_hex(8)}.webp"
            shutil.copyfile(src, config.UPLOAD_DIR / name)
            new_files.append(config.UPLOAD_DIR / name)
            copied[key] = f"/uploads/{name}"
        return copied[key]

    try:
        with db.tx() as c:
            n = c.execute("SELECT COALESCE(MAX(sort),0) FROM categories WHERE restaurant_id=?", (s.id,)).fetchone()[0]
            for cat in body.get("categories", [])[:40]:
                name = str(cat.get("name", "")).strip()[:60]
                items = cat.get("items", [])[:200]
                if not name or not items:
                    continue
                n += 1
                cid = c.execute("INSERT INTO categories(restaurant_id,name,sort) VALUES (?,?,?)", (s.id, name, n)).lastrowid
                for k, it in enumerate(items):
                    iname = str(it.get("name", "")).strip()[:90]
                    if not iname:
                        continue
                    price = round(float(it.get("price") or 0) * (1 if s.r["decimals"] == 0 else 100))
                    tags = [t for t in it.get("tags", []) if isinstance(t, str)][:6]
                    image = photo_for(it)
                    photos += 1 if image else 0
                    c.execute(
                        "INSERT INTO items(restaurant_id,category_id,name,description,price,tags,sort,image) VALUES (?,?,?,?,?,?,?,?)",
                        (s.id, cid, iname, str(it.get("description", ""))[:400], max(0, price), json.dumps(tags), k, image))
                    added += 1
    except Exception:
        for f in new_files:  # si algo falló, no dejar fotos huérfanas
            f.unlink(missing_ok=True)
        raise
    drafts.delete(s.id, body.get("draft_id"))
    return {"added": added, "photos": photos}


@router.get("/import/draft/{draft_id}/{n}.webp")
def import_draft_photo(draft_id: str, n: int, s: Staff = Depends(owner_dep)):
    """Vista previa de una foto del borrador (solo el dueño que lo creó)."""
    p = drafts.path(s.id, draft_id, n)
    if p is None:
        raise HTTPException(404, "La foto ya no está disponible (el borrador expira a las 3 horas)")
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------- mesas y QR
@router.get("/tables")
def list_tables(s: Staff = Depends(staff_dep)):
    return {"tables": db.rows("SELECT id,label,secret FROM tables_ WHERE restaurant_id=? ORDER BY CAST(label AS INTEGER), label", (s.id,))}


@router.post("/tables")
def add_tables(body: dict, s: Staff = Depends(owner_dep)):
    limit = auth.plan_info(s.r)["tables"]
    have = db.row("SELECT COUNT(*) n FROM tables_ WHERE restaurant_id=?", (s.id,))["n"]
    labels = [str(body["label"]).strip()[:20]] if body.get("label") else []
    if body.get("count"):
        start = have + 1
        labels += [str(n) for n in range(start, start + min(int(body["count"]), 100))]
    if have + len(labels) > limit:
        raise HTTPException(402, f"Tu plan permite {limit} mesas. Mejora tu plan para agregar más.")
    added = 0
    for lb in labels:
        if lb and not db.row("SELECT 1 FROM tables_ WHERE restaurant_id=? AND label=?", (s.id, lb)):
            db.run("INSERT INTO tables_(restaurant_id,label,secret) VALUES (?,?,?)", (s.id, lb, service.new_secret()))
            added += 1
    return {"added": added}


@router.delete("/tables/{tid}")
def del_table(tid: int, s: Staff = Depends(owner_dep)):
    db.run("DELETE FROM tables_ WHERE id=? AND restaurant_id=?", (tid, s.id))
    return {"ok": True}


@router.post("/tables/{tid}/rotate")
def rotate_table(tid: int, s: Staff = Depends(owner_dep)):
    """Cambia el código secreto del QR (si alguien lo fotografió y abusa)."""
    db.run("UPDATE tables_ SET secret=? WHERE id=? AND restaurant_id=?", (service.new_secret(), tid, s.id))
    return {"ok": True}


def table_url(r: dict, t: dict) -> str:
    return f"{config.BASE_URL}/r/{r['slug']}?t={t['label']}&k={t['secret']}"


@router.get("/qr/{tid}.svg")
def qr_svg(tid: int, s: Staff = Depends(staff_dep)):
    t = db.row("SELECT * FROM tables_ WHERE id=? AND restaurant_id=?", (tid, s.id))
    if not t:
        raise HTTPException(404)
    buf = io.BytesIO()
    segno.make(table_url(s.r, t), error="m").save(buf, kind="svg", scale=10, border=1, dark="#111111", xmldecl=False,
                                                  svgns=True, nl=False)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "private, max-age=300"})


# ---------------------------------------------------------------- cocina / sala
def _orders_payload(rid: int, statuses=("new", "preparing", "ready")):
    q = ",".join("?" * len(statuses))
    os_ = db.rows(f"SELECT * FROM orders WHERE restaurant_id=? AND status IN ({q}) ORDER BY created_at", (rid, *statuses))
    for o in os_:
        o["items"] = db.rows("SELECT id,name,qty,options_text,note FROM order_items WHERE order_id=? ORDER BY id", (o["id"],))
    return os_


@router.get("/orders")
def active_orders(s: Staff = Depends(staff_dep)):
    return {"orders": _orders_payload(s.id), "now": now()}


@router.post("/orders/{oid}/status")
def order_status(oid: int, body: dict, s: Staff = Depends(staff_dep)):
    st = body.get("status")
    if st not in ("new", "preparing", "ready", "served", "cancelled"):
        raise HTTPException(400, "Estado inválido")
    o = db.row("SELECT * FROM orders WHERE id=? AND restaurant_id=?", (oid, s.id))
    if not o:
        raise HTTPException(404)
    col = {"preparing": "preparing_at", "ready": "ready_at", "served": "served_at"}.get(st)
    if col:
        db.run(f"UPDATE orders SET status=?, {col}=COALESCE({col}, ?) WHERE id=?", (st, now(), oid))
    else:
        db.run("UPDATE orders SET status=? WHERE id=?", (st, oid))
    events.publish(f"r{s.id}", "order", {"id": oid})
    events.publish(f"t{s.id}:{o['table_label']}", "update", {"status": st})
    return {"ok": True}


@router.get("/calls")
def open_calls(s: Staff = Depends(staff_dep)):
    return {"calls": db.rows("SELECT * FROM calls WHERE restaurant_id=? AND resolved_at IS NULL ORDER BY created_at", (s.id,))}


@router.post("/calls/{cid}/resolve")
def resolve_call(cid: int, s: Staff = Depends(staff_dep)):
    c = db.row("SELECT * FROM calls WHERE id=? AND restaurant_id=?", (cid, s.id))
    if c:
        db.run("UPDATE calls SET resolved_at=? WHERE id=?", (now(), cid))
        events.publish(f"r{s.id}", "call", {})
        events.publish(f"t{s.id}:{c['table_label']}", "update", {})
    return {"ok": True}


@router.get("/floor")
def floor(s: Staff = Depends(staff_dep)):
    """Estado de cada mesa: cuenta pendiente, pedidos activos, llamadas."""
    out = []
    calls = db.rows("SELECT table_label,type FROM calls WHERE restaurant_id=? AND resolved_at IS NULL", (s.id,))
    act = db.rows("SELECT table_label, COUNT(*) n FROM orders WHERE restaurant_id=? AND status IN ('new','preparing','ready') GROUP BY table_label", (s.id,))
    for t in db.rows("SELECT label FROM tables_ WHERE restaurant_id=? ORDER BY CAST(label AS INTEGER), label", (s.id,)):
        lines = service.bill_lines(s.id, t["label"])
        unpaid = sum(l["line_total"] for l in lines if l["state"] != "paid")
        out.append({
            "label": t["label"], "unpaid": unpaid, "has_paid": any(l["state"] == "paid" for l in lines),
            "active": next((a["n"] for a in act if a["table_label"] == t["label"]), 0),
            "calls": [c["type"] for c in calls if c["table_label"] == t["label"]],
        })
    return {"tables": out}


@router.get("/floor/{label}")
def floor_table(label: str, s: Staff = Depends(staff_dep)):
    return {"lines": service.bill_lines(s.id, label)}


@router.post("/floor/{label}/settle")
def settle(label: str, body: dict, s: Staff = Depends(staff_dep)):
    """Cobrar en caja (efectivo/datáfono): marca todo lo pendiente como pagado."""
    lines = [l for l in service.bill_lines(s.id, label) if l["state"] == "unpaid"]
    if not lines:
        return {"ok": True, "total": 0}
    subtotal = sum(l["line_total"] for l in lines)
    tip = int(body.get("tip") or 0)
    tt = service.totals(s.r, subtotal, 0)
    with db.tx() as c:
        pid = c.execute(
            """INSERT INTO payments(restaurant_id,table_label,provider,status,subtotal,tip,total,payer,item_ids,customer,paid_at,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (s.id, label, str(body.get("method", "cashier"))[:12], "paid", subtotal, tip, tt["total"] + tip,
             "caja", json.dumps([l["id"] for l in lines]), json.dumps(colombia.clean_customer(body.get("invoice"))),
             now(), now())).lastrowid
        for l in lines:
            c.execute("UPDATE order_items SET paid_payment_id=? WHERE id=?", (pid, l["id"]))
        c.execute("UPDATE calls SET resolved_at=? WHERE restaurant_id=? AND table_label=? AND type='bill' AND resolved_at IS NULL",
                  (now(), s.id, label))
    invoicing.enqueue(pid)
    events.publish(f"t{s.id}:{label}", "update", {})
    events.publish(f"r{s.id}", "paid", {"table": label})
    return {"ok": True, "total": tt["total"] + tip}


@router.get("/stream")
async def staff_stream(request: Request):
    s = auth.current(request)
    return StreamingResponse(events.stream(f"r{s.id}", request), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- reportes
@router.get("/analytics")
def analytics(days: int = 7, s: Staff = Depends(owner_dep)):
    days = max(1, min(days, 365))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    off = timedelta(minutes=s.r["tz_offset"])
    ords = db.rows(
        """SELECT o.id, o.created_at, o.preparing_at, o.ready_at, o.table_label,
                  (SELECT COALESCE(SUM(qty*unit_price),0) FROM order_items WHERE order_id=o.id) AS total
           FROM orders o WHERE o.restaurant_id=? AND o.status!='cancelled' AND o.created_at>=?""", (s.id, since))
    fmt = "%Y-%m-%d %H:%M:%S"
    daily, hourly = {}, [0] * 24
    prep_secs = []
    for o in ords:
        local = datetime.strptime(o["created_at"], fmt) + off
        d = local.strftime("%Y-%m-%d")
        daily.setdefault(d, {"date": d, "sales": 0, "orders": 0})
        daily[d]["sales"] += o["total"]
        daily[d]["orders"] += 1
        hourly[local.hour] += 1
        if o["ready_at"]:
            prep_secs.append((datetime.strptime(o["ready_at"], fmt) - datetime.strptime(o["created_at"], fmt)).total_seconds())
    top = db.rows(
        """SELECT oi.name, SUM(oi.qty) AS qty, SUM(oi.qty*oi.unit_price) AS revenue FROM order_items oi
           JOIN orders o ON o.id=oi.order_id WHERE o.restaurant_id=? AND o.status!='cancelled' AND o.created_at>=?
           GROUP BY oi.name ORDER BY qty DESC LIMIT 8""", (s.id, since))
    pay = db.row("SELECT COALESCE(SUM(tip),0) tips, COUNT(*) n, COALESCE(SUM(total),0) collected FROM payments WHERE restaurant_id=? AND status='paid' AND created_at>=?", (s.id, since))
    fb = db.row("SELECT COUNT(*) n, AVG(rating) avg FROM feedback WHERE restaurant_id=? AND created_at>=?", (s.id, since))
    sales = sum(o["total"] for o in ords)
    tables = {}
    for o in ords:
        tables[o["table_label"]] = tables.get(o["table_label"], 0) + o["total"]
    return {
        "days": days, "sales": sales, "orders": len(ords), "avg_ticket": round(sales / len(ords)) if ords else 0,
        "avg_prep_min": round(sum(prep_secs) / len(prep_secs) / 60, 1) if prep_secs else None,
        "tips": pay["tips"], "payments": pay["n"], "collected": pay["collected"],
        "rating_avg": round(fb["avg"], 2) if fb["avg"] else None, "rating_count": fb["n"],
        "daily": sorted(daily.values(), key=lambda x: x["date"]), "hourly": hourly, "top": top,
        "top_tables": sorted(({"table": k, "sales": v} for k, v in tables.items()), key=lambda x: -x["sales"])[:5],
    }


@router.get("/feedback")
def list_feedback(s: Staff = Depends(owner_dep)):
    return {"feedback": db.rows("SELECT * FROM feedback WHERE restaurant_id=? ORDER BY created_at DESC LIMIT 100", (s.id,))}


@router.get("/export/orders.csv")
def export_csv(s: Staff = Depends(owner_dep)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["pedido", "fecha_utc", "mesa", "estado", "plato", "opciones", "cantidad", "precio_unitario", "total_linea"])
    for r in db.rows(
        """SELECT o.id, o.created_at, o.table_label, o.status, oi.name, oi.options_text, oi.qty, oi.unit_price
           FROM orders o JOIN order_items oi ON oi.order_id=o.id WHERE o.restaurant_id=? ORDER BY o.id""", (s.id,)):
        w.writerow([r["id"], r["created_at"], r["table_label"], r["status"], r["name"], r["options_text"], r["qty"],
                    r["unit_price"], r["qty"] * r["unit_price"]])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=pedidos.csv"})


# ---------------------------------------------------------------- backoffice del vendedor (tú)
def _admin(request: Request):
    key = request.headers.get("x-admin-key", "")
    if not config.ADMIN_KEY or not secrets.compare_digest(key, config.ADMIN_KEY):
        raise HTTPException(403, "Clave de administrador inválida")


@router.get("/superadmin/restaurants")
def sa_list(request: Request):
    _admin(request)
    return {"restaurants": db.rows(
        "SELECT id,slug,name,email,plan,subscription_status,trial_ends_at,created_at FROM restaurants ORDER BY id DESC")}


@router.post("/superadmin/activate")
def sa_activate(body: dict, request: Request):
    """Activa/renueva una suscripción tras recibir el pago (manual o desde tu pasarela)."""
    _admin(request)
    plan = body.get("plan", "basic")
    if plan not in config.PLANS:
        raise HTTPException(400, "Plan inválido")
    status = body.get("status", "active")
    db.run("UPDATE restaurants SET plan=?, subscription_status=? WHERE email=?",
           (plan, status, str(body.get("email", "")).lower()))
    return {"ok": True}


# ---------------------------------------------------------------- webhooks
@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    raw = await request.body()
    if not payments.verify_stripe_signature(raw, request.headers.get("stripe-signature", "")):
        raise HTTPException(400, "Firma inválida")
    evt = json.loads(raw)
    pid = int(evt.get("data", {}).get("object", {}).get("client_reference_id") or 0)
    if evt.get("type") == "checkout.session.completed":
        service.finalize_payment(pid, True)
    elif evt.get("type") == "checkout.session.expired":
        service.finalize_payment(pid, False)
    return {"received": True}


@router.post("/webhooks/wompi/{slug}")
async def wompi_webhook(slug: str, request: Request):
    """Configura esta URL en Wompi → Desarrolladores → URL de eventos. Cada evento se valida con su checksum."""
    r = db.row("SELECT * FROM restaurants WHERE slug=?", (slug,))
    evt = await request.json()
    secret = payments.keys(r).get("wompi_events", "") if r else ""
    if not r or not secret or not payments.wompi_verify_event(secret, evt):
        raise HTTPException(400, "Firma inválida")
    if evt.get("event") == "transaction.updated":
        t = evt["data"]["transaction"]
        p = db.row("SELECT * FROM payments WHERE restaurant_id=? AND reference=?", (r["id"], t.get("reference", "")))
        cents = (p["total"] * 100 if r["decimals"] == 0 else p["total"]) if p else 0
        if p and t.get("status") == "APPROVED" and int(t.get("amount_in_cents", 0)) == cents:
            service.finalize_payment(p["id"], True)
        elif p and t.get("status") in ("DECLINED", "ERROR", "VOIDED"):
            service.finalize_payment(p["id"], False)
    return {"received": True}


# ---------------------------------------------------------------- Bre-B: confirmación del equipo
@router.get("/payments/review")
def payments_review(s: Staff = Depends(staff_dep)):
    return {"payments": db.rows(
        "SELECT id, table_label, total, payer, reference, created_at FROM payments WHERE restaurant_id=? AND status='review' ORDER BY id", (s.id,))}


@router.post("/payments/{pid}/confirm")
def payment_confirm(pid: int, s: Staff = Depends(staff_dep)):
    p = db.row("SELECT * FROM payments WHERE id=? AND restaurant_id=?", (pid, s.id))
    if not p:
        raise HTTPException(404)
    service.finalize_payment(pid, True)
    return {"ok": True}


@router.post("/payments/{pid}/reject")
def payment_reject(pid: int, s: Staff = Depends(staff_dep)):
    p = db.row("SELECT * FROM payments WHERE id=? AND restaurant_id=?", (pid, s.id))
    if not p:
        raise HTTPException(404)
    service.finalize_payment(pid, False)
    return {"ok": True}
