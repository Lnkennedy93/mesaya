"""Medios de pago para Colombia.

  nequi    Cobro por notificación push de Nequi vía Wompi (POST /v1/transactions, type NEQUI).
           Confirmación automática por webhook firmado (+ consulta de respaldo).
  breb     Bre-B: el cliente paga a la llave del negocio desde su app bancaria y el equipo confirma.
           (No hay API pública documentada de cobro Bre-B para comercios; la confirmación es asistida.)
  cashier  Pagar en caja.
  stripe   Opcional (tarjetas internacionales).
  mock     SOLO demo: requiere MESAYA_DEMO=1.
"""
import hashlib
import hmac
import re
import time

import httpx

from . import config, vault

WOMPI_BASES = {"sandbox": "https://sandbox.wompi.co/v1", "production": "https://production.wompi.co/v1"}


class GatewayError(Exception):
    pass


def _req(method: str, url: str, **kw):
    """Único punto de salida HTTP (facilita pruebas con respuestas simuladas)."""
    return httpx.request(method, url, timeout=kw.pop("timeout", 20), **kw)


def keys(r: dict) -> dict:
    return vault.unseal(r.get("pay_secrets", ""))


def wompi_ready(r: dict) -> bool:
    k = keys(r)
    return bool(k.get("wompi_public") and k.get("wompi_private"))


def available_providers(r: dict) -> list[dict]:
    out = []
    if r["online_payments"] and config.ONLINE_PAYMENTS:
        if r.get("nequi_enabled") and wompi_ready(r):
            out.append({"id": "nequi", "label": "Nequi"})
        if r.get("breb_enabled") and r.get("breb_key"):
            out.append({"id": "breb", "label": "Bre-B"})
        if config.STRIPE_SECRET_KEY:
            out.append({"id": "stripe", "label": "Tarjeta"})
        if config.DEMO_MODE:
            out.append({"id": "mock", "label": "Pago en línea (demo)"})
    out.append({"id": "cashier", "label": "Pagar en caja"})
    return out


# ------------------------------------------------------------------ Wompi
def _wompi_base(r):
    return WOMPI_BASES.get(r.get("wompi_env"), WOMPI_BASES["sandbox"])


def valid_phone(phone: str) -> str:
    p = re.sub(r"\D", "", phone or "")
    if p.startswith("57") and len(p) == 12:
        p = p[2:]
    if not re.fullmatch(r"3\d{9}", p):
        raise GatewayError("Ingresa un celular colombiano de 10 dígitos (ej. 3001234567)")
    return p


def wompi_create_nequi(r: dict, reference: str, total: int, phone: str, email: str) -> dict:
    k = keys(r)
    base = _wompi_base(r)
    m = _req("GET", f"{base}/merchants/{k['wompi_public']}")
    if m.status_code != 200:
        raise GatewayError("Wompi rechazó las llaves del comercio")
    acceptance = m.json()["data"]["presigned_acceptance"]["acceptance_token"]
    cents = int(total) * 100 if r["decimals"] == 0 else int(total)
    body = {
        "acceptance_token": acceptance, "amount_in_cents": cents, "currency": r["currency"],
        "customer_email": email, "reference": reference,
        "payment_method": {"type": "NEQUI", "phone_number": valid_phone(phone)},
    }
    if k.get("wompi_integrity"):
        body["signature"] = hashlib.sha256(f"{reference}{cents}{r['currency']}{k['wompi_integrity']}".encode()).hexdigest()
    t = _req("POST", f"{base}/transactions", json=body, headers={"Authorization": f"Bearer {k['wompi_private']}"})
    if t.status_code not in (200, 201):
        raise GatewayError("Wompi no pudo crear el cobro")
    d = t.json()["data"]
    return {"id": d["id"], "status": d.get("status", "PENDING")}


def wompi_get_status(r: dict, tx_id: str) -> str:
    t = _req("GET", f"{_wompi_base(r)}/transactions/{tx_id}")
    if t.status_code != 200:
        return "PENDING"
    return t.json()["data"].get("status", "PENDING")


def _dig(data: dict, path: str):
    cur = data
    for part in path.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return "" if cur is None else str(cur)


def wompi_verify_event(events_secret: str, event: dict) -> bool:
    """Checksum según la guía de Eventos de Wompi: sha256(valores de signature.properties + timestamp + secreto)."""
    try:
        sig = event["signature"]
        raw = "".join(_dig(event["data"], p) for p in sig["properties"]) + str(event["timestamp"]) + events_secret
        return hmac.compare_digest(hashlib.sha256(raw.encode()).hexdigest().lower(), sig["checksum"].lower())
    except Exception:
        return False


# ------------------------------------------------------------------ Stripe (opcional)
def stripe_checkout(restaurant: dict, payment_id: int, total: int, return_url: str) -> dict:
    amount = total * 100 if restaurant["decimals"] == 0 else total
    data = {
        "mode": "payment", "success_url": return_url + "&paid=1", "cancel_url": return_url + "&paid=0",
        "client_reference_id": str(payment_id), "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": restaurant["currency"].lower(),
        "line_items[0][price_data][unit_amount]": str(amount),
        "line_items[0][price_data][product_data][name]": f"Cuenta {restaurant['name']}",
        "metadata[payment_id]": str(payment_id),
    }
    r = _req("POST", "https://api.stripe.com/v1/checkout/sessions", data=data, auth=(config.STRIPE_SECRET_KEY, ""))
    r.raise_for_status()
    j = r.json()
    return {"url": j["url"], "ref": j["id"]}


def verify_stripe_signature(payload: bytes, header: str, tolerance=300) -> bool:
    if not config.STRIPE_WEBHOOK_SECRET:
        return False
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts, sig = parts["t"], parts["v1"]
        if abs(time.time() - int(ts)) > tolerance:
            return False
        expected = hmac.new(config.STRIPE_WEBHOOK_SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False
