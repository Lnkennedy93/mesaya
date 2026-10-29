"""Facturación electrónica DIAN a través de un proveedor tecnológico.

MesaYa NO firma ni transmite XML a la DIAN directamente: eso exige habilitación como facturador,
firma digital (XAdES), XML UBL 2.1 y pruebas de set. Lo habitual (y lo recomendable) es delegarlo en un
proveedor tecnológico autorizado. Proveedores incluidos:

  factus  API REST de Factus (https://factus.com.co). Endpoints y campos tomados de su API pública;
          VERIFICA el mapeo de ids (tributos, documentos, municipios) en tu sandbox antes de producción.
  mock    Genera facturas de mentira para demostraciones y pruebas.

Se emite UNA factura por pago (si la mesa paga dividida, cada comensal recibe la suya).
La propina voluntaria NO se incluye en la factura (no hace parte de la base gravable).
"""
import threading
import time
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from . import colombia, config, db, vault
from .auth import now

FACTUS_BASES = {"sandbox": "https://api-sandbox.factus.com.co", "production": "https://api.factus.com.co"}
FACTUS_TRIBUTE = {"IVA": 1, "IVA5": 1, "INC": 4, "NONE": 21}  # tribute_id por tipo de impuesto (verificar en sandbox)
MAX_ATTEMPTS = 5

_token_cache: dict[int, tuple[str, float]] = {}


class InvoiceError(Exception):
    pass


def _http(method, url, **kw):
    import httpx
    return httpx.request(method, url, timeout=kw.pop("timeout", 30), **kw)


def secrets_of(r: dict) -> dict:
    return vault.unseal(r.get("inv_secrets", ""))


def enabled(r: dict) -> bool:
    return config.INVOICING and r.get("inv_provider") in ("factus", "mock")


def tax_rate(r: dict) -> float:
    return 0.0 if r.get("tax_type", "NONE") == "NONE" else float(r.get("tax_pct") or 0)


def _d(v) -> Decimal:
    return Decimal(str(v))


def build_lines(r: dict, payment_id: int) -> list[dict]:
    rate = _d(tax_rate(r))
    div = Decimal(10) ** r["decimals"]
    out = []
    for l in db.rows("SELECT * FROM order_items WHERE paid_payment_id=? ORDER BY id", (payment_id,)):
        unit = _d(l["unit_price"]) / div
        base = unit / (1 + rate / 100) if r["tax_included"] and rate else unit
        out.append({
            "code": f"P{l['item_id'] or l['id']}",
            "name": (l["name"] + (f" ({l['options_text']})" if l["options_text"] else ""))[:200],
            "qty": l["qty"], "price": base.quantize(Decimal("0.01"), ROUND_HALF_UP), "tax_rate": rate,
        })
    return out


# ------------------------------------------------------------------ Factus
def _factus_token(r: dict) -> str:
    cached = _token_cache.get(r["id"])
    if cached and cached[1] > time.time() + 30:
        return cached[0]
    s = secrets_of(r)
    resp = _http("POST", f"{FACTUS_BASES.get(r['inv_env'], FACTUS_BASES['sandbox'])}/oauth/token", data={
        "grant_type": "password", "client_id": s.get("client_id", ""), "client_secret": s.get("client_secret", ""),
        "username": s.get("username", ""), "password": s.get("password", "")},
        headers={"Accept": "application/json"})
    if resp.status_code != 200:
        raise InvoiceError("Factus rechazó las credenciales (revisa client_id, secreto, usuario y contraseña)")
    j = resp.json()
    _token_cache[r["id"]] = (j["access_token"], time.time() + int(j.get("expires_in", 600)))
    return j["access_token"]


def factus_payload(r: dict, payment: dict, customer: dict, lines: list[dict]) -> dict:
    is_cf = customer["doc_number"] == colombia.CONSUMIDOR_FINAL["doc_number"]
    idt = colombia.ID_TYPES[customer["doc_type"]]
    cust = {
        "identification_document_id": idt["factus"], "identification": customer["doc_number"],
        "names": customer["name"], "email": customer.get("email") or "", "address": customer.get("address", ""),
        "phone": customer.get("phone", ""), "legal_organization_id": 1 if customer["doc_type"] == "NIT" else 2,
        "tribute_id": 21,
    }
    if customer["doc_type"] == "NIT":
        cust["dv"] = customer.get("dv", "")
        cust["company"] = customer["name"]
    if r["fiscal_municipality_id"]:
        cust["municipality_id"] = r["fiscal_municipality_id"]
    if is_cf:
        cust.pop("email"), cust.pop("address"), cust.pop("phone")
    tribute = FACTUS_TRIBUTE.get(r.get("tax_type", "NONE"), 21)
    p = {
        "document": "01", "reference_code": f"mesaya-{payment['id']}",
        "observation": f"Mesa {payment['table_label']}", "payment_form": "1",
        "payment_method_code": "10" if payment["provider"] in ("cashier", "cash") else "47",
        "customer": cust,
        "items": [{
            "code_reference": l["code"], "name": l["name"], "quantity": l["qty"], "discount_rate": 0,
            "price": float(l["price"]), "tax_rate": f"{l['tax_rate']:.2f}", "unit_measure_id": 70,
            "standard_code_id": 1, "is_excluded": 0, "tribute_id": tribute} for l in lines],
    }
    if r["inv_range_id"]:
        p["numbering_range_id"] = r["inv_range_id"]
    return p


def _factus_issue(r: dict, payment: dict, customer: dict, lines: list[dict]) -> dict:
    token = _factus_token(r)
    base = FACTUS_BASES.get(r["inv_env"], FACTUS_BASES["sandbox"])
    resp = _http("POST", f"{base}/v1/bills/validate", json=factus_payload(r, payment, customer, lines),
                 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        j = resp.json()
    except Exception:
        j = {}
    if resp.status_code not in (200, 201):
        detail = j.get("message") or j.get("error") or ""
        errs = j.get("data", {}).get("errors") if isinstance(j.get("data"), dict) else None
        if errs:
            detail += " " + "; ".join(f"{k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in errs.items())
        raise InvoiceError((detail or f"Factus respondió {resp.status_code}")[:400])
    d = j.get("data", {})
    bill = d.get("bill", d)
    if not bill.get("number"):
        raise InvoiceError("Factus no devolvió el número de factura")
    return {"number": bill["number"], "cufe": bill.get("cufe", ""), "qr_url": bill.get("qr", bill.get("qr_url", "")),
            "public_url": bill.get("public_url", "")}


def factus_ranges(r: dict) -> list[dict]:
    """Prueba las credenciales y lista tus rangos de numeración (para elegir inv_range_id)."""
    token = _factus_token(r)
    resp = _http("GET", f"{FACTUS_BASES.get(r['inv_env'], FACTUS_BASES['sandbox'])}/v1/numbering-ranges",
                 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    if resp.status_code != 200:
        raise InvoiceError("No se pudieron consultar los rangos de numeración")
    rows = resp.json().get("data", [])
    rows = rows.get("data", rows) if isinstance(rows, dict) else rows
    return [{"id": x.get("id"), "prefix": x.get("prefix"), "document": x.get("document"),
             "from": x.get("from"), "to": x.get("to"), "current": x.get("current"), "is_active": x.get("is_active")}
            for x in rows]


# ------------------------------------------------------------------ orquestación
def _mock_issue(payment: dict) -> dict:
    n = db.row("SELECT COUNT(*) n FROM invoices WHERE restaurant_id=? AND status='issued'", (payment["restaurant_id"],))["n"] + 1
    return {"number": f"DEMO{n:06d}", "cufe": f"{payment['id']:0>8}" + "0" * 88, "qr_url": "", "public_url": ""}


def create_for_payment(payment_id: int) -> int | None:
    """Registra la factura pendiente (idempotente). La emisión se hace aparte."""
    p = db.row("SELECT * FROM payments WHERE id=?", (payment_id,))
    r = db.row("SELECT * FROM restaurants WHERE id=?", (p["restaurant_id"],))
    if not p or not enabled(r) or p["status"] != "paid":
        return None
    if db.row("SELECT 1 FROM invoices WHERE payment_id=?", (payment_id,)):
        return None
    import json
    customer = colombia.clean_customer(json.loads(p["customer"] or "{}"))
    return db.run("INSERT INTO invoices(restaurant_id,payment_id,provider,status,customer,total,created_at) VALUES (?,?,?,?,?,?,?)",
                  (r["id"], payment_id, r["inv_provider"], "pending", json.dumps(customer), p["subtotal"], now()))


def issue(invoice_id: int) -> dict:
    import json
    inv = db.row("SELECT * FROM invoices WHERE id=?", (invoice_id,))
    if not inv or inv["status"] == "issued":
        return inv or {}
    r = db.row("SELECT * FROM restaurants WHERE id=?", (inv["restaurant_id"],))
    p = db.row("SELECT * FROM payments WHERE id=?", (inv["payment_id"],))
    try:
        if r["inv_provider"] == "factus":
            if not (r["nit"] and r["legal_name"]):
                raise InvoiceError("Faltan los datos fiscales del negocio (razón social y NIT)")
            res = _factus_issue(r, p, json.loads(inv["customer"]), build_lines(r, p["id"]))
        else:
            res = _mock_issue(p)
        db.run("UPDATE invoices SET status='issued', number=?, cufe=?, qr_url=?, public_url=?, error='', issued_at=?, attempts=attempts+1 WHERE id=?",
               (res["number"], res["cufe"], res["qr_url"], res["public_url"], now(), invoice_id))
    except InvoiceError as e:
        db.run("UPDATE invoices SET status='error', error=?, attempts=attempts+1 WHERE id=?", (str(e), invoice_id))
    except Exception as e:  # red caída, timeout, respuesta rara
        db.run("UPDATE invoices SET status='error', error=?, attempts=attempts+1 WHERE id=?", (f"Error de conexión: {type(e).__name__}", invoice_id))
    return db.row("SELECT * FROM invoices WHERE id=?", (invoice_id,))


def enqueue(payment_id: int):
    """Se llama al confirmarse un pago: crea la factura y la emite en esta misma petición (en Vercel no hay hilos de fondo).
    shortcut: bloquea la petición mientras responde el proveedor (máx. 30 s); si falla, queda en error y se reintenta desde el panel."""
    inv_id = create_for_payment(payment_id)
    if inv_id:
        issue(inv_id)


def retry_failed(limit=20):
    for inv in db.rows("SELECT id FROM invoices WHERE status IN ('error','pending') AND attempts < ? ORDER BY id LIMIT ?", (MAX_ATTEMPTS, limit)):
        issue(inv["id"])


def start_retry_loop(interval=300):
    def loop():
        while True:
            time.sleep(interval)
            try:
                retry_failed()
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()
