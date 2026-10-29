"""API pública: lo que usa el comensal desde su celular (sin app, sin cuenta)."""
import json
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import colombia, config, db, events, invoicing, payments, service
from .auth import client_ip, is_active, now, rate_check, rate_hit, rate_limit

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
    active = is_active(r)
    return {
        "restaurant": {
            "name": r["name"], "tagline": r["tagline"], "logo": r["logo"], "brand_color": r["brand_color"],
            "currency": r["currency"], "decimals": r["decimals"], "tip_pct": r["tip_pct"],
            "tax_pct": r["tax_pct"], "tax_included": bool(r["tax_included"]),
            "google_review_url": r["google_review_url"], "whatsapp": r["whatsapp"],
            "tax_label": colombia.TAX_TYPES.get(r["tax_type"], colombia.TAX_TYPES["NONE"])["label"].split(" (")[0],
            "invoicing": invoicing.enabled(r),
        },
        "features": {"payments": config.ONLINE_PAYMENTS, "invoicing": config.INVOICING},
        "can_order": bool(table_ok and r["accepting_orders"] and active),
        "table_ok": table_ok,
        "table": t if table_ok else "",
        "paused": not r["accepting_orders"],
        "subscription_ok": active,
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
    items: list[OrderItem]


@router.post("/orders")
def create_order(slug: str, body: OrderIn, request: Request):
    r = _resto(slug)
    rate_limit(f"order:ip:{_ip(request)}:{r['id']}", IP_GUARD, 600)
    if not r["accepting_orders"]:
        raise HTTPException(409, "En este momento solo se muestra la carta. Pide al mesero.")
    if not is_active(r):
        raise HTTPException(402, "Este restaurante no tiene pedidos digitales activos. Pide al mesero.")
    _table(r, body.table, body.key, request)
    rate_limit(f"order:t:{r['id']}:{body.table}", 15, 600)
    lines = service.price_lines(r, [i.model_dump() for i in body.items])
    with db.tx() as c:
        today = now()[:10] + " 00:00:00"
        seq = c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM orders WHERE restaurant_id=? AND created_at>=?",
                        (r["id"], today)).fetchone()[0]
        oid = c.execute(
            """INSERT INTO orders(restaurant_id, table_label, seq, status, diner_id, diner_name, note, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (r["id"], body.table, seq, "new", body.diner_id, body.diner_name.strip(), body.note.strip(), now())).lastrowid
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
    return {"lines": lines, "calls": [c["type"] for c in calls]}


@router.get("/stream")
async def stream(slug: str, table: str, k: str, request: Request):
    r = _resto(slug)
    _table(r, table, k, request)
    return StreamingResponse(events.stream(f"t{r['id']}:{table}", request), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class CallIn(BaseModel):
    table: str
    key: str
    type: str = "waiter"


@router.post("/call")
def call(slug: str, body: CallIn, request: Request):
    r = _resto(slug)
    rate_limit(f"call:ip:{_ip(request)}:{r['id']}", IP_GUARD // 2, 300)
    _table(r, body.table, body.key, request)
    rate_limit(f"call:t:{r['id']}:{body.table}", 6, 300)
    if body.type not in ("waiter", "bill"):
        raise HTTPException(400, "Tipo inválido")
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
    tt = service.totals(r, subtotal, body.tip_pct)
    customer = colombia.clean_customer(body.invoice)

    if body.provider == "cashier":
        if not db.row("SELECT 1 FROM calls WHERE restaurant_id=? AND table_label=? AND type='bill' AND resolved_at IS NULL",
                      (r["id"], body.table)):
            db.run("INSERT INTO calls(restaurant_id, table_label, type, created_at) VALUES (?,?,?,?)",
                   (r["id"], body.table, "bill", now()))
        events.publish(f"r{r['id']}", "call", {"table": body.table, "type": "bill"})
        return {"ok": True, "mode": "cashier"}

    phone = ""
    if body.provider == "nequi":
        try:
            phone = payments.valid_phone(body.phone)
        except payments.GatewayError as e:
            raise HTTPException(400, str(e))
    status = "paid" if body.provider == "mock" else "pending"
    reference = f"mesaya-{secrets.token_hex(5)}"
    with db.tx() as c:
        for l in chosen:  # revalidar dentro de la transacción: evita doble pago concurrente
            row = c.execute("SELECT paid_payment_id FROM order_items WHERE id=?", (l["id"],)).fetchone()
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
    db.run("UPDATE payments SET status='review' WHERE id=?", (pid,))
    events.publish(f"r{r['id']}", "payment", {"table": p["table_label"], "total": p["total"]})
    events.publish(f"t{r['id']}:{p['table_label']}", "update", {})
    return {"ok": True}


@router.post("/pay/{pid}/cancel")
def pay_cancel(slug: str, pid: int, body: dict, request: Request):
    r = _resto(slug)
    p = _own_payment(r, pid, str(body.get("table", "")), str(body.get("key", "")), request)
    if p["status"] == "pending":
        db.run("UPDATE payments SET status='failed' WHERE id=?", (pid,))
        events.publish(f"t{r['id']}:{p['table_label']}", "update", {})
    return {"ok": True}


@router.post("/quote")
def quote(slug: str, body: dict):
    r = _resto(slug)
    return service.totals(r, int(body.get("subtotal", 0)), float(body.get("tip_pct", 0)))


class FeedbackIn(BaseModel):
    table: str = ""
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)


@router.post("/feedback")
def feedback(slug: str, body: FeedbackIn, request: Request):
    r = _resto(slug)
    rate_limit(f"fb:ip:{_ip(request)}:{r['id']}", IP_GUARD // 2, 3600)
    rate_limit(f"fb:t:{r['id']}:{body.table}", 5, 3600)
    db.run("INSERT INTO feedback(restaurant_id, table_label, rating, comment, created_at) VALUES (?,?,?,?,?)",
           (r["id"], body.table, body.rating, body.comment.strip(), now()))
    return {"ok": True, "review_url": r["google_review_url"] if body.rating >= 4 else ""}
