"""API pública: lo que usa el comensal desde su celular (sin app, sin cuenta)."""
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

import io

import segno

from . import colombia, config, db, events, invoicing, loyalty, payments, service, storage
from .auth import client_ip, is_active, module_on, now, rate_check, rate_hit, rate_limit, safe_eq

router = APIRouter(prefix="/api/public/{slug}")


def _resto(slug: str) -> dict:
    r = db.row("SELECT * FROM restaurants WHERE slug=?", (slug,))
    if not r:
        raise HTTPException(404, "Restaurante no encontrado")
    return r


_ip = client_ip


# Muchos clientes comparten la IP del WiFi del local: el límite por IP es solo un tope alto contra abuso.
# El ritmo "normal" se limita por mesa (ver _table y los rate_limit de cada ruta).
IP_GUARD = 600


def _table(r: dict, label: str, key: str, request: Request) -> dict:
    """Valida mesa + clave. Los intentos con clave errónea sí se cuentan por IP (anti fuerza bruta)."""
    bad = f"badkey:{_ip(request)}:{r['id']}"
    rate_check(bad, 30, 600)
    try:
        return service.table_by_label(r["id"], label, key)
    except HTTPException:
        rate_hit(bad)
        raise


def _plan_allows(r: dict, label: str) -> bool:
    """Con plan Gratis solo las primeras mesas (las que cubre el plan) reciben pedidos digitales."""
    if label.startswith(service.TAKEAWAY_PREFIX):
        return is_active(r)  # para llevar no depende de mesas: requiere plan activo o prueba
    if is_active(r):
        return True
    first = db.rows("SELECT label FROM tables_ WHERE restaurant_id=? ORDER BY CAST(label AS INTEGER), label LIMIT ?",
                    (r["id"], config.PLANS["free"]["tables"]))
    return label in {t["label"] for t in first}


@router.post("/takeaway/start")
def takeaway_start(slug: str, body: dict, request: Request):
    """El QR para llevar trae la clave del negocio; aquí se canjea por una «mesa» propia de este cliente (PL-xxxxxx + clave)."""
    r = _resto(slug)
    rate_limit(f"pl:start:{_ip(request)}:{r['id']}", 60, 600)
    if not (r["takeaway"] and r["takeaway_key"] and module_on(r, "takeaway")) or not safe_eq(body.get("pl", ""), r["takeaway_key"]):
        raise HTTPException(403, "Este código para llevar ya no es válido. Pide uno nuevo en el mostrador.")
    label = service.TAKEAWAY_PREFIX + secrets.token_hex(3).upper()
    return {"table": label, "key": service.takeaway_key(r, label)}


def _signup_resto(slug: str, k: str) -> dict:
    r = _resto(slug)
    if not (r["customers_key"] and module_on(r, "customers") and safe_eq(k, r["customers_key"])):
        raise HTTPException(403, "Este código de registro ya no es válido. Pide uno nuevo en el local.")
    return r


@router.get("/customers/signup")
def customer_signup_info(slug: str, request: Request, k: str = ""):
    """Lo que ve el cliente al escanear el QR de fidelización: el nombre y los colores del restaurante."""
    r = _resto(slug)
    rate_limit(f"cs:info:{_ip(request)}:{r['id']}", 120, 600)
    r = _signup_resto(slug, k)
    return {"name": r["name"], "logo": r["logo"], "brand_color": r["brand_color"], "brand_color2": r["brand_color2"], "brand_color3": r["brand_color3"]}


class SignupIn(BaseModel):
    k: str = Field(max_length=60)
    document: str = Field(max_length=20)
    name: str = Field(min_length=3, max_length=100)
    email: str = Field(max_length=120)
    phone: str = Field(max_length=20)
    consent: bool = False


@router.post("/customers/signup")
def customer_signup(slug: str, body: SignupIn, request: Request):
    """El cliente se registra solo en la fidelización de ESTE restaurante (cada uno tiene su propia base)."""
    r = _resto(slug)
    rate_limit(f"cs:ip:{_ip(request)}:{r['id']}", 40, 3600)  # (varios clientes comparten el WiFi del local)
    rate_limit(f"cs:r:{r['id']}", 300, 3600)
    _signup_resto(slug, body.k)
    try:
        doc, name, email, phone = colombia.loyalty_fields(body.document, body.name, body.email, body.phone)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not body.consent:  # Ley 1581: sin autorización expresa no se guarda nada
        raise HTTPException(400, "Debes autorizar el tratamiento de tus datos para registrarte")
    if not db.row("SELECT 1 FROM customers WHERE restaurant_id=? AND document=?", (r["id"], doc)):  # ya registrado: se responde igual (no se revela quién está en la base)
        t, key = now(), loyalty.new_card_key()
        db.run("INSERT INTO customers(restaurant_id,document,name,email,phone,consent_at,created_at,card_key) VALUES (?,?,?,?,?,?,?,?)", (r["id"], doc, name, email, phone, t, t, key))
        if r["stamps_on"]:
            return {"ok": True, "card": f"/r/{slug}/tarjeta?c={key}&nuevo=1"}  # solo quien se acaba de registrar recibe el enlace de su tarjeta
    return {"ok": True}


def _card(slug: str, c: str, request: Request):
    r = _resto(slug)
    rate_limit(f"lc:{_ip(request)}:{r['id']}", 120, 600)
    cust = loyalty.find(r, card=c) if c else None
    if not cust or not r["stamps_on"] or not module_on(r, "customers"):
        raise HTTPException(404, "Tarjeta no encontrada")
    return r, cust


@router.get("/loyalty/card")
def loyalty_card(slug: str, request: Request, c: str = ""):
    """La tarjeta de sellos de un cliente (se abre con su QR o su tarjeta NFC). Solo muestra su primer nombre y sus sellos."""
    r, cust = _card(slug, c, request)
    st = loyalty.state(r, cust)
    st["name"] = st["name"].split()[0]
    return {**st, "restaurant": {"name": r["name"], "logo": r["logo"], "brand_color": r["brand_color"], "brand_color2": r["brand_color2"], "brand_color3": r["brand_color3"]}}


@router.get("/loyalty/manifest.webmanifest")
def loyalty_manifest(slug: str, request: Request, c: str = ""):
    """Para «Crear acceso directo»: el celular instala un ícono con el nombre y el logo del restaurante que abre la tarjeta de ESTE cliente."""
    r, _ = _card(slug, c, request)
    from urllib.parse import quote
    start = f"/r/{slug}/tarjeta?c={quote(c, safe='')}"
    icon = lambda s: {"src": f"/api/public/{slug}/loyalty/icon.png?c={quote(c, safe='')}&s={s}", "sizes": f"{s}x{s}", "type": "image/png", "purpose": "any"}  # noqa: E731
    body = {"id": start, "name": f"{r['name']} · Mi tarjeta", "short_name": r["name"][:12], "start_url": start, "scope": f"/r/{slug}/", "display": "standalone",
            "background_color": "#ffffff", "theme_color": r["brand_color"] or "#0b0f14", "lang": "es", "icons": [icon(192), icon(512)]}
    return Response(json.dumps(body, ensure_ascii=False), media_type="application/manifest+json", headers={"Cache-Control": "private, max-age=300"})


def _logo_image(r: dict):
    """El logo del restaurante como imagen (de la base o de Blob); None si no hay o no se puede leer."""
    from PIL import Image
    path = r["logo"] or ""
    try:
        if path.startswith("/uploads/"):
            row = db.row("SELECT data FROM images WHERE name=? AND restaurant_id=?", (path.rsplit("/", 1)[-1], r["id"]))
            raw = bytes(row["data"]) if row else None
        elif storage.owns(path, r["id"]):
            import urllib.request
            raw = urllib.request.urlopen(path, timeout=4).read(2_000_000)  # noqa: S310 (solo URLs de Blob de este restaurante)
        else:
            raw = None
        return Image.open(io.BytesIO(raw)).convert("RGBA") if raw else None
    except Exception:
        return None


@router.get("/loyalty/icon.png")
def loyalty_icon(slug: str, request: Request, c: str = "", s: int = 192):
    """Ícono del acceso directo: el logo del restaurante sobre su color de marca (o su inicial si no tiene logo)."""
    from PIL import Image, ImageDraw, ImageFont
    r, _ = _card(slug, c, request)
    size = 512 if s >= 512 else 192
    col = r["brand_color"] if len(r["brand_color"] or "") == 7 else "#0b0f14"
    im = Image.new("RGB", (size, size), col)
    logo = _logo_image(r)
    if logo:
        logo.thumbnail((int(size * .7), int(size * .7)))
        im.paste(logo, ((size - logo.width) // 2, (size - logo.height) // 2), logo)
    else:
        lum = (int(col[1:3], 16) * 299 + int(col[3:5], 16) * 587 + int(col[5:7], 16) * 114) / 1000
        try:
            font = ImageFont.load_default(size=int(size * .55))
        except TypeError:  # Pillow muy viejo: sin tamaño de letra
            font = ImageFont.load_default()
        ImageDraw.Draw(im).text((size / 2, size / 2), (r["name"].strip()[:1] or "M").upper(), fill="#ffffff" if lum < 150 else "#111111", font=font, anchor="mm")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/loyalty/qr.svg")
def loyalty_qr(slug: str, request: Request, c: str = ""):
    r, _ = _card(slug, c, request)
    buf = io.BytesIO()
    segno.make(f"{config.BASE_URL}/r/{slug}/tarjeta?c={c}", error="m").save(
        buf, kind="svg", scale=10, border=2, dark="#111111", light="#ffffff", xmldecl=False, svgns=True, nl=False)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "private, max-age=300"})


@router.get("/menu")
def menu(slug: str, request: Request, t: str = "", k: str = ""):
    r = _resto(slug)
    table_ok = False
    if t:
        try:  # mismo límite de intentos que /orders: este endpoint no puede ser un oráculo de la clave
            _table(r, t, k, request)
            table_ok = True
        except HTTPException:
            pass
    cats = db.rows("SELECT id, name FROM categories WHERE restaurant_id=? ORDER BY sort, id", (r["id"],))
    items = [service.item_public(i) for i in db.rows(
        "SELECT * FROM items WHERE restaurant_id=? ORDER BY sort, id", (r["id"],))]
    for c in cats:
        c["items"] = [i for i in items if i["category_id"] == c["id"]]
    allowed = table_ok and _plan_allows(r, t)
    return {
        "restaurant": {
            "name": r["name"], "tagline": r["tagline"], "logo": r["logo"], "pay_qr": r["pay_qr"], "takeaway_qr": bool(r["takeaway_qr"] and r["pay_qr"]), "brand_color": r["brand_color"], "brand_color2": r["brand_color2"], "brand_color3": r["brand_color3"],
            "currency": r["currency"], "decimals": r["decimals"], "tip_pct": r["tip_pct"],
            "tax_pct": r["tax_pct"], "tax_included": bool(r["tax_included"]),
            "google_review_url": r["google_review_url"], "whatsapp": r["whatsapp"],
            "tax_label": colombia.TAX_TYPES.get(r["tax_type"], colombia.TAX_TYPES["NONE"])["label"].split(" (")[0],
            "invoicing": invoicing.enabled(r),
        },
        "features": {"payments": config.ONLINE_PAYMENTS, "invoicing": config.INVOICING},
        "can_order": bool(allowed and r["accepting_orders"]),
        "table_ok": table_ok,
        "table": t if table_ok else "",
        "paused": not r["accepting_orders"],
        "subscription_ok": is_active(r) or allowed,
        "providers": payments.available_providers(r),
        "categories": [c for c in cats if c["items"]],
    }


class OrderItem(BaseModel):
    item_id: int
    qty: int = 1
    options: list[dict] = []
    note: str = ""


class OrderIn(BaseModel):
    table: str
    key: str
    diner_id: str = Field(max_length=64)
    diner_name: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=200)
    request_id: str = Field(default="", max_length=64)  # lo genera el celular por intento de envío: un reintento no duplica el pedido
    items: list[OrderItem]


@router.post("/orders")
def create_order(slug: str, body: OrderIn, request: Request):
    r = _resto(slug)
    rate_limit(f"order:ip:{_ip(request)}:{r['id']}", IP_GUARD, 600)
    if not r["accepting_orders"]:
        raise HTTPException(409, "En este momento solo se muestra la carta. Pide al mesero.")
    _table(r, body.table, body.key, request)
    if not _plan_allows(r, body.table):
        raise HTTPException(402, "Esta mesa no tiene pedidos digitales en el plan Gratis. Pide al mesero.")
    rate_limit(f"order:t:{r['id']}:{body.table}", 15, 600)
    takeaway = body.table.startswith(service.TAKEAWAY_PREFIX)
    if takeaway and not body.diner_name.strip():
        raise HTTPException(400, "Escribe tu nombre para entregarte el pedido")
    lines = service.price_lines(r, [i.model_dump() for i in body.items])
    with db.tx(r["id"]) as c:  # (la transacción serializa las escrituras: contar y luego insertar no se pisa)
        if body.request_id:
            dup = c.execute("SELECT id, seq FROM orders WHERE restaurant_id=? AND table_label=? AND client_ref=?",
                            (r["id"], body.table, body.request_id)).fetchone()
            if dup:  # el pedido ya había entrado (se perdió la respuesta): se devuelve el mismo, sin crear otro
                return {"ok": True, "order_id": dup["id"], "seq": dup["seq"], "duplicate": True}
        if takeaway and service.takeaway_status(r["id"])["full"]:
            raise HTTPException(409, f"Estamos al tope de pedidos para llevar ({config.TAKEAWAY_MAX}). Podrás pedir apenas se entregue uno.")
        off = timedelta(minutes=r["tz_offset"] or 0)  # el número de pedido se reinicia a la medianoche local, no a la UTC
        today = (datetime.now(timezone.utc) + off).replace(hour=0, minute=0, second=0, microsecond=0)
        today = (today - off).strftime("%Y-%m-%d %H:%M:%S")
        seq = c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM orders WHERE restaurant_id=? AND created_at>=?",
                        (r["id"], today)).fetchone()[0]
        oid = c.execute(
            """INSERT INTO orders(restaurant_id, table_label, seq, status, diner_id, diner_name, note, created_at, client_ref)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (r["id"], body.table, seq, "new", body.diner_id, body.diner_name.strip(), body.note.strip(), now(), body.request_id)).lastrowid
        for ln in lines:
            c.execute(
                """INSERT INTO order_items(order_id, item_id, name, options_text, note, qty, unit_price)
                   VALUES (?,?,?,?,?,?,?)""",
                (oid, ln["item_id"], ln["name"], ln["options_text"], ln["note"], ln["qty"], ln["unit_price"]))
    events.publish(f"r{r['id']}", "order", {"id": oid, "table": body.table})
    events.publish(f"t{r['id']}:{body.table}", "update", {})
    return {"ok": True, "order_id": oid, "seq": seq}


@router.get("/bill")
def bill(slug: str, table: str, k: str, request: Request):
    r = _resto(slug)
    _table(r, table, k, request)
    lines = service.bill_lines(r["id"], table)
    calls = db.rows("SELECT type FROM calls WHERE restaurant_id=? AND table_label=? AND resolved_at IS NULL",
                    (r["id"], table))
    out = {"lines": lines, "calls": [c["type"] for c in calls], "closed": service.table_closed(lines)}
    if table.startswith(service.TAKEAWAY_PREFIX):
        out["takeaway"] = service.takeaway_status(r["id"])  # cupo: se refresca con cada consulta de la cuenta
    return out


@router.get("/stream")
async def stream(slug: str, table: str, k: str, request: Request):
    r = _resto(slug)
    _table(r, table, k, request)
    return StreamingResponse(events.stream(f"t{r['id']}:{table}", request), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


PAY_METHODS = ("cash", "card", "qr")  # cómo pagará: el mesero sabe si lleva datáfono o si el cliente paga con el QR del negocio


def _ask_bill(r: dict, table: str, method: str):
    """Abre la solicitud de cuenta (o actualiza el método si ya estaba abierta) y avisa al equipo."""
    takeaway = table.startswith(service.TAKEAWAY_PREFIX)  # para llevar: el QR de pago solo si el dueño lo habilitó en esa sección
    if method not in PAY_METHODS or (method == "qr" and not (r["pay_qr"] and (r["takeaway_qr"] or not takeaway))):
        raise HTTPException(400, "Elige cómo vas a pagar")
    if db.row("SELECT 1 FROM calls WHERE restaurant_id=? AND table_label=? AND type='bill' AND resolved_at IS NULL", (r["id"], table)):
        db.run("UPDATE calls SET method=? WHERE restaurant_id=? AND table_label=? AND type='bill' AND resolved_at IS NULL", (method, r["id"], table))
    else:
        db.run("INSERT INTO calls(restaurant_id, table_label, type, method, created_at) VALUES (?,?,?,?,?)", (r["id"], table, "bill", method, now()))
    events.publish(f"r{r['id']}", "call", {"table": table, "type": "bill", "method": method})
    events.publish(f"t{r['id']}:{table}", "update", {})


class CallIn(BaseModel):
    table: str
    key: str
    type: str = "waiter"
    method: str = ""


@router.post("/call")
def call(slug: str, body: CallIn, request: Request):
    r = _resto(slug)
    rate_limit(f"call:ip:{_ip(request)}:{r['id']}", IP_GUARD // 2, 300)
    _table(r, body.table, body.key, request)
    rate_limit(f"call:t:{r['id']}:{body.table}", 6, 300)
    if body.type not in ("waiter", "bill"):
        raise HTTPException(400, "Tipo inválido")
    takeaway = body.table.startswith(service.TAKEAWAY_PREFIX)
    if takeaway and body.type != "bill":
        raise HTTPException(400, "Los pedidos para llevar se recogen en el mostrador")
    lines = service.bill_lines(r["id"], body.table)
    if service.table_closed(lines):  # mesa cerrada en sala: ya no hay a quién llamar ni cuenta que pedir
        raise HTTPException(409, "La mesa ya fue cerrada. ¡Gracias por tu visita!")
    if body.type == "bill":
        if takeaway and not any(l["state"] == "unpaid" for l in lines):
            raise HTTPException(400, "Aún no tienes pedidos por pagar")
        _ask_bill(r, body.table, body.method)
        return {"ok": True}
    if not db.row("SELECT 1 FROM calls WHERE restaurant_id=? AND table_label=? AND type=? AND resolved_at IS NULL",
                  (r["id"], body.table, body.type)):
        db.run("INSERT INTO calls(restaurant_id, table_label, type, created_at) VALUES (?,?,?,?)",
               (r["id"], body.table, body.type, now()))
        events.publish(f"r{r['id']}", "call", {"table": body.table, "type": body.type})
        events.publish(f"t{r['id']}:{body.table}", "update", {})
    return {"ok": True}


class PayIn(BaseModel):
    table: str
    key: str
    item_ids: list[int]
    tip_pct: float = 0
    payer: str = Field(default="", max_length=40)
    provider: str = "cashier"
    phone: str = Field(default="", max_length=20)
    email: str = Field(default="", max_length=120)
    invoice: dict | None = None
    method: str = ""  # solo para provider="cashier": cash | card


def _payment_view(p: dict) -> dict:
    inv = db.row("SELECT status, number, public_url, qr_url FROM invoices WHERE payment_id=?", (p["id"],))
    return {"payment_id": p["id"], "status": p["status"], "total": p["total"], "provider": p["provider"],
            "invoice": inv}


def _cutoff():
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(minutes=service.PENDING_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S")


@router.post("/pay")
def pay(slug: str, body: PayIn, request: Request):
    r = _resto(slug)
    rate_limit(f"pay:ip:{_ip(request)}:{r['id']}", IP_GUARD // 2, 600)
    _table(r, body.table, body.key, request)
    rate_limit(f"pay:t:{r['id']}:{body.table}", 10, 600)
    if body.provider not in {p["id"] for p in payments.available_providers(r)}:
        raise HTTPException(400, "Método de pago no disponible")
    if body.provider == "cashier" and (body.method not in PAY_METHODS or (body.method == "qr" and not r["pay_qr"])):
        raise HTTPException(400, "Elige cómo vas a pagar")
    if not body.item_ids:
        raise HTTPException(400, "Elige qué quieres pagar")
    lines = {l["id"]: l for l in service.bill_lines(r["id"], body.table)}
    chosen = []
    for iid in set(body.item_ids):
        l = lines.get(iid)
        if not l or l["state"] != "unpaid":
            raise HTTPException(409, "Alguno de esos platos ya fue pagado o está en proceso de pago")
        chosen.append(l)
    subtotal = sum(l["line_total"] for l in chosen)
    if not 0 <= body.tip_pct <= service.TIP_MAX_PCT:  # (también descarta NaN)
        raise HTTPException(400, f"La propina va de 0 a {service.TIP_MAX_PCT} %")
    tt = service.totals(r, subtotal, body.tip_pct)
    customer = colombia.clean_customer(body.invoice)

    if body.provider == "cashier":
        _ask_bill(r, body.table, body.method)
        return {"ok": True, "mode": "cashier", "total": tt["total"]}

    phone = ""
    if body.provider == "nequi":
        try:
            phone = payments.valid_phone(body.phone)
        except payments.GatewayError as e:
            raise HTTPException(400, str(e))
    status = "paid" if body.provider == "mock" else "pending"
    reference = f"mesaya-{secrets.token_hex(5)}"
    with db.tx(r["id"]) as c:
        for l in chosen:  # revalidar dentro de la transacción: evita doble pago concurrente
            row = c.execute("""SELECT oi.paid_payment_id, o.status AS ostatus FROM order_items oi JOIN orders o ON o.id = oi.order_id
                               WHERE oi.id=?""", (l["id"],)).fetchone()
            if row["ostatus"] == "cancelled":
                raise HTTPException(409, "Alguno de esos platos fue cancelado")
            if row["paid_payment_id"]:
                p = c.execute("SELECT status, created_at FROM payments WHERE id=?", (row["paid_payment_id"],)).fetchone()
                if p and (p["status"] in ("paid", "review") or (p["status"] == "pending" and p["created_at"] >= _cutoff())):
                    raise HTTPException(409, "Alguno de esos platos ya fue pagado")
        pid = c.execute(
            """INSERT INTO payments(restaurant_id, table_label, provider, status, subtotal, tip, total, payer, item_ids,
                                    customer, reference, paid_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["id"], body.table, body.provider, status, subtotal, tt["tip"], tt["total"], body.payer.strip(),
             json.dumps(sorted(set(body.item_ids))), json.dumps(customer), reference,
             now() if status == "paid" else None, now())).lastrowid
        for l in chosen:
            c.execute("UPDATE order_items SET paid_payment_id=? WHERE id=?", (pid, l["id"]))

    def fail(msg):
        db.run("UPDATE payments SET status='failed' WHERE id=?", (pid,))
        events.publish(f"t{r['id']}:{body.table}", "update", {})
        raise HTTPException(502, msg)

    if body.provider == "mock":
        invoicing.enqueue(pid)
        events.publish(f"r{r['id']}", "paid", {"table": body.table, "total": tt["total"]})
        events.publish(f"t{r['id']}:{body.table}", "update", {})
        return {"ok": True, "mode": "paid", "payment_id": pid, **tt}

    if body.provider == "nequi":
        email = customer.get("email") or body.email.strip() or r["email"]
        try:
            res = payments.wompi_create_nequi(r, reference, tt["total"], phone, email)
        except payments.GatewayError as e:
            fail(str(e))
        except Exception:
            fail("No pudimos contactar a Nequi, intenta de nuevo o paga en caja")
        db.run("UPDATE payments SET external_ref=? WHERE id=?", (res["id"], pid))
        return {"ok": True, "mode": "push", "payment_id": pid, **tt}

    if body.provider == "breb":
        return {"ok": True, "mode": "breb", "payment_id": pid, "reference": reference[-6:].upper(),
                "breb": {"key": r["breb_key"], "type": r["breb_key_type"], "holder": r["breb_holder"]}, **tt}

    try:  # stripe
        back = f"{config.BASE_URL}/r/{slug}?t={body.table}&k={body.key}&view=bill"
        res = payments.stripe_checkout(r, pid, tt["total"], back)
        db.run("UPDATE payments SET external_ref=? WHERE id=?", (res["ref"], pid))
        return {"ok": True, "mode": "redirect", "url": res["url"], "payment_id": pid}
    except Exception:
        fail("No se pudo iniciar el pago, intenta de nuevo o paga en caja")


def _own_payment(r: dict, pid: int, table: str, key: str, request: Request) -> dict:
    _table(r, table, key, request)
    p = db.row("SELECT * FROM payments WHERE id=? AND restaurant_id=? AND table_label=?", (pid, r["id"], table))
    if not p:
        raise HTTPException(404, "Pago no encontrado")
    return p


@router.get("/pay/{pid}")
def pay_status(slug: str, pid: int, table: str, k: str, request: Request):
    """Estado del pago. Para Nequi consulta a Wompi como respaldo por si el webhook se demora."""
    r = _resto(slug)
    p = _own_payment(r, pid, table, k, request)
    if p["status"] == "pending" and p["provider"] == "nequi" and p["external_ref"]:
        try:
            st = payments.wompi_get_status(r, p["external_ref"])
            if st == "APPROVED":
                service.finalize_payment(pid, True)
            elif st in ("DECLINED", "ERROR", "VOIDED"):
                service.finalize_payment(pid, False)
        except Exception:
            pass
        p = db.row("SELECT * FROM payments WHERE id=?", (pid,))
    return _payment_view(p)


@router.post("/pay/{pid}/claim")
def pay_claim(slug: str, pid: int, body: dict, request: Request):
    """Bre-B: el cliente avisa que ya transfirió; el equipo lo verifica en su app bancaria y confirma."""
    r = _resto(slug)
    rate_limit(f"claim:ip:{_ip(request)}:{r['id']}", IP_GUARD // 2, 600)
    p = _own_payment(r, pid, str(body.get("table", "")), str(body.get("key", "")), request)
    rate_limit(f"claim:t:{r['id']}:{p['table_label']}", 8, 600)
    if p["provider"] != "breb" or p["status"] not in ("pending", "review"):
        raise HTTPException(409, "Este pago no se puede reportar")
    db.run("UPDATE payments SET status='review' WHERE id=? AND status IN ('pending','review')", (pid,))  # (si ya lo confirmó el equipo, no vuelve a «por confirmar»)
    events.publish(f"r{r['id']}", "payment", {"table": p["table_label"], "total": p["total"]})
    events.publish(f"t{r['id']}:{p['table_label']}", "update", {})
    return {"ok": True}


@router.post("/pay/{pid}/cancel")
def pay_cancel(slug: str, pid: int, body: dict, request: Request):
    r = _resto(slug)
    p = _own_payment(r, pid, str(body.get("table", "")), str(body.get("key", "")), request)
    if p["status"] == "pending":
        db.run("UPDATE payments SET status='failed' WHERE id=? AND status='pending'", (pid,))
        events.publish(f"t{r['id']}:{p['table_label']}", "update", {})
    return {"ok": True}


@router.post("/quote")
def quote(slug: str, body: dict):
    r = _resto(slug)
    try:
        subtotal, tip_pct = int(body.get("subtotal", 0)), float(body.get("tip_pct", 0))
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(400, "Valores inválidos")
    if not (0 <= subtotal <= 100_000_000 and 0 <= tip_pct <= service.TIP_MAX_PCT):  # (también descarta NaN)
        raise HTTPException(400, "Valores inválidos")
    return service.totals(r, subtotal, tip_pct)


class FeedbackIn(BaseModel):
    table: str = Field(default="", max_length=40)
    key: str = Field(default="", max_length=80)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)


@router.post("/feedback")
def feedback(slug: str, body: FeedbackIn, request: Request):
    r = _resto(slug)
    rate_limit(f"fb:ip:{_ip(request)}:{r['id']}", IP_GUARD // 2, 3600)
    _table(r, body.table, body.key, request)  # solo quien está en la mesa (clave del QR) puede calificar
    rate_limit(f"fb:t:{r['id']}:{body.table}", 5, 3600)
    db.run("INSERT INTO feedback(restaurant_id, table_label, rating, comment, created_at) VALUES (?,?,?,?,?)",
           (r["id"], body.table, body.rating, body.comment.strip(), now()))
    return {"ok": True, "review_url": r["google_review_url"] if body.rating >= 4 else ""}
