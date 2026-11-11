"""Lógica de negocio compartida: cuentas, totales, validación de pedidos."""
import hmac
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from . import auth, config, db, events, invoicing
from .auth import now

RESERVED_SLUGS = {"admin", "api", "kitchen", "login", "signup", "r", "print", "uploads", "static", "qr", "assets"}
PENDING_TTL_MIN = 15
TABLE_SESSION_HOURS = 12  # shortcut: no hay «sesión de mesa»; lo sin cobrar de hace más de 12 h se da por abandonado (sigue en ventas), upgrade: sesión real por mesa


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:40] or "restaurante"


def unique_slug(base: str) -> str:
    slug = slugify(base)
    if slug in RESERVED_SLUGS:
        slug += "-resto"
    cand, n = slug, 1
    while db.row("SELECT 1 FROM restaurants WHERE slug=?", (cand,)):
        n += 1
        cand = f"{slug}-{n}"
    return cand


def new_secret() -> str:
    return secrets.token_hex(4)


def decimals_for(currency: str) -> int:
    return 0 if currency.upper() in {"COP", "CLP", "PYG", "JPY", "KRW", "VND", "UGX"} else 2


def item_public(i: dict) -> dict:
    return {
        "id": i["id"], "category_id": i["category_id"], "name": i["name"], "description": i["description"],
        "price": i["price"], "image": i["image"], "available": bool(i["available"]),
        "featured": bool(i["featured"]), "tags": db.jl(i["tags"]), "allergens": db.jl(i["allergens"]),
        "options": db.jl(i["options"]),
    }


def totals(r: dict, subtotal: int, tip_pct: float) -> dict:
    tax = 0
    if r["tax_pct"]:
        if r["tax_included"]:
            tax = round(subtotal - subtotal / (1 + r["tax_pct"] / 100))
        else:
            tax = round(subtotal * r["tax_pct"] / 100)
    tip = round(subtotal * max(0, min(tip_pct, 50)) / 100)
    total = subtotal + (0 if r["tax_included"] else tax) + tip
    return {"subtotal": subtotal, "tax": tax, "tip": tip, "total": total}


def price_lines(r: dict, raw_items: list[dict]) -> list[dict]:
    """Recalcula precios en el servidor: nunca confiamos en el precio del cliente."""
    if not raw_items or len(raw_items) > 40:
        raise HTTPException(400, "Pedido vacío o demasiado grande")
    lines = []
    for it in raw_items:
        item = db.row("SELECT * FROM items WHERE id=? AND restaurant_id=?", (it.get("item_id"), r["id"]))
        if not item:
            raise HTTPException(400, "Un plato ya no existe en la carta")
        if not item["available"]:
            raise HTTPException(409, f"«{item['name']}» está agotado")
        qty = it.get("qty", 1)
        if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= 20:
            raise HTTPException(400, "Cantidad inválida")
        groups = db.jl(item["options"])
        chosen = it.get("options") or []
        if len(chosen) > 40:
            raise HTTPException(400, "Demasiadas opciones")
        extra, labels = 0, []
        for g in groups:
            picks = [c for c in chosen if c.get("group") == g["name"]]
            if g.get("required") and not picks:
                raise HTTPException(400, f"Elige una opción en «{g['name']}» para {item['name']}")
            if not g.get("multi") and len(picks) > 1:
                raise HTTPException(400, f"Solo una opción en «{g['name']}»")
            if len({str(p.get("name")) for p in picks}) != len(picks):
                raise HTTPException(400, f"Opción repetida en «{g['name']}»")
            for p in picks:
                opt = next((o for o in g["options"] if o["name"] == p.get("name")), None)
                if not opt:
                    raise HTTPException(400, "Opción inválida")
                extra += int(opt.get("price") or 0)
                labels.append(opt["name"])
        lines.append({
            "item_id": item["id"], "name": item["name"], "qty": qty,
            "unit_price": max(0, item["price"] + extra), "options_text": ", ".join(labels),
            "note": (it.get("note") or "")[:140],
        })
    return lines


TAKEAWAY_PREFIX = "PL-"  # «mesas» virtuales de los pedidos para llevar: una por cliente, así cada uno solo ve lo suyo


def takeaway_key(r: dict, label: str) -> str:
    """Clave de una «mesa» para llevar: se deriva de la clave del QR, así no hace falta guardar una fila por cliente."""
    return hmac.new(r["takeaway_key"].encode(), label.encode(), "sha256").hexdigest()[:16]


def takeaway_status(rid: int) -> dict:
    n = db.row("SELECT COUNT(*) AS n FROM orders WHERE restaurant_id=? AND substr(table_label,1,3)=? AND status IN ('new','preparing','ready')",
               (rid, TAKEAWAY_PREFIX))["n"]
    return {"active": n, "max": config.TAKEAWAY_MAX, "full": n >= config.TAKEAWAY_MAX}


def table_by_label(rid: int, label: str, key: str | None = None, require_key=True):
    if label.startswith(TAKEAWAY_PREFIX):
        r = db.row("SELECT * FROM restaurants WHERE id=?", (rid,))
        if (not r or not r["takeaway"] or not r["takeaway_key"] or not auth.module_on(r, "takeaway")
                or (require_key and not auth.safe_eq(takeaway_key(r, label), key))):
            raise HTTPException(403, "Código no válido. Escanea de nuevo el QR para llevar.")
        return {"label": label}
    t = db.row("SELECT * FROM tables_ WHERE restaurant_id=? AND label=?", (rid, label))
    if not t or (require_key and not auth.safe_eq(t["secret"], key)):
        raise HTTPException(403, "Mesa no válida. Escanea de nuevo el QR de tu mesa.")
    return t


def bill_lines(rid: int, label: str, include_paid_minutes=60) -> list[dict]:
    """Líneas de la cuenta de una mesa: todo lo pendiente + lo pagado recientemente."""
    cutoff_pending = (datetime.now(timezone.utc) - timedelta(minutes=PENDING_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_paid = (datetime.now(timezone.utc) - timedelta(minutes=include_paid_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_stale = (datetime.now(timezone.utc) - timedelta(hours=TABLE_SESSION_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    rs = db.rows(
        """SELECT oi.id, oi.name, oi.qty, oi.unit_price, oi.options_text, oi.note, oi.order_id,
                  o.status AS order_status, o.diner_id, o.diner_name, o.seq, o.created_at,
                  p.status AS pay_status, p.created_at AS pay_created, p.payer
           FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           LEFT JOIN payments p ON p.id = oi.paid_payment_id
           WHERE o.restaurant_id=? AND o.table_label=? AND o.status != 'cancelled'
           ORDER BY o.created_at, oi.id""", (rid, label))
    out = []
    for x in rs:
        ps = x["pay_status"]
        if ps == "paid":
            if x["pay_created"] < cutoff_paid:
                continue
            x["state"] = "paid"
        elif ps == "review" or (ps == "pending" and x["pay_created"] >= cutoff_pending):
            x["state"] = "reserved"
        else:
            if x["created_at"] < cutoff_stale:  # cuenta olvidada de otro turno: no se le muestra ni se le cobra al grupo siguiente
                continue
            x["state"] = "unpaid"
        x["line_total"] = x["qty"] * x["unit_price"]
        out.append(x)
    return out


def table_closed(lines: list[dict]) -> bool:
    """La mesa está cerrada cuando todo lo consumido ya se pagó (p. ej. el equipo la cerró en sala). Un pedido nuevo la reabre solo."""
    return bool(lines) and all(l["state"] == "paid" for l in lines)


def money_fmt(r: dict, v: int) -> str:
    return f"{v:,.{r['decimals']}f}"


def finalize_payment(payment_id: int, approved: bool) -> bool:
    """Cierra un pago pendiente (webhook, consulta de respaldo o confirmación del equipo). Idempotente."""
    with db.tx() as c:
        p = c.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not p or p["status"] not in ("pending", "review"):
            return False
        c.execute("UPDATE payments SET status=?, paid_at=? WHERE id=?",
                  ("paid" if approved else "failed", now() if approved else None, payment_id))
    rid, label = p["restaurant_id"], p["table_label"]
    events.publish(f"r{rid}", "paid" if approved else "call", {"table": label, "total": p["total"]})
    events.publish(f"t{rid}:{label}", "update", {})
    if approved:
        invoicing.enqueue(payment_id)
    return True
