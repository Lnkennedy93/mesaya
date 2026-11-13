import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from . import db
from .config import BASIC_AI_ADDON_ASKS, PLANS

COOKIE = "mesaya_session"


def client_ip(request: Request) -> str:
    """IP del visitante. Detrás de Vercel o de un proxy, request.client es el proxy: la real viene en x-forwarded-for."""
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "x").split(",")[0].strip()


def safe_eq(a, b) -> bool:
    """Comparación en tiempo constante que no revienta con caracteres no ASCII (compare_digest con str sí)."""
    return secrets.compare_digest(str(a or "").encode(), str(b or "").encode())


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + "$" + dk.hex()


def verify_password(pw: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def tok(token: str) -> str:
    """Las sesiones se guardan con hash: quien lea la tabla no puede usarlas como cookie."""
    return hashlib.sha256(token.encode()).hexdigest()


_DUMMY = ""


def dummy_hash() -> str:
    """Hash de relleno: un correo que no existe tarda lo mismo en responder que uno que sí (no delata cuentas)."""
    global _DUMMY
    _DUMMY = _DUMMY or hash_password("mesaya")
    return _DUMMY


def purge_expired():
    """Sesiones y enlaces de reseteo vencidos: sin esto la tabla solo crece."""
    db.run("DELETE FROM sessions WHERE expires_at < ?", (now(),))
    db.run("DELETE FROM password_resets WHERE expires_at < ?", (now(),))


def create_session(restaurant_id: int, role: str, days: int = 30) -> str:
    if secrets.randbelow(20) == 0:
        purge_expired()
    token = secrets.token_urlsafe(32)
    exp = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    db.run("INSERT INTO sessions(token, restaurant_id, role, expires_at) VALUES (?,?,?,?)",
           (tok(token), restaurant_id, role, exp))
    return token


class Staff:
    def __init__(self, restaurant: dict, role: str):
        self.r = restaurant
        self.id = restaurant["id"]
        self.role = role


def current(request: Request, optional=False):
    token = request.cookies.get(COOKIE)
    if token:
        r = db.row("""SELECT r.*, s.role AS session_role FROM sessions s JOIN restaurants r ON r.id = s.restaurant_id
                      WHERE s.token=? AND s.expires_at > ?""", (tok(token), now()))
        if r:
            return Staff(r, r.pop("session_role"))
    if optional:
        return None
    raise HTTPException(401, "Inicia sesión")


def staff_dep(request: Request) -> Staff:
    return current(request)


# Funciones del panel que el superusuario puede encender o apagar por negocio.
MODULES = ("home", "menu", "tables", "reviews", "customers", "assistant", "settings", "takeaway")


def disabled_modules(r: dict) -> list[str]:
    try:
        return [m for m in json.loads(r["disabled_modules"] or "[]") if m in MODULES]
    except ValueError:
        return []


def module_on(r: dict, name: str) -> bool:
    return name not in disabled_modules(r)


# (método o None, prefijo de ruta, función): qué función del panel usa cada ruta. El orden importa: gana la primera coincidencia.
_GATES = (
    (None, "/api/analytics", "home"), (None, "/api/orders/history", "home"), (None, "/api/export", "home"),
    (None, "/api/categories", "menu"), (None, "/api/items", "menu"), (None, "/api/import", "menu"), ("DELETE", "/api/menu", "menu"),
    (None, "/api/qr/takeaway", "takeaway"), (None, "/api/qr/customers", "customers"), (None, "/api/qr/card", "customers"), (None, "/api/loyalty", "customers"), (None, "/api/takeaway", "takeaway"),
    ("POST", "/api/tables", "tables"), ("DELETE", "/api/tables", "tables"), (None, "/api/qr", "tables"),
    (None, "/api/feedback", "reviews"), (None, "/api/customers", "customers"), (None, "/api/assistant", "assistant"),
    ("PUT", "/api/settings", "settings"), (None, "/api/integrations", "settings"), (None, "/api/logo", "settings"), (None, "/api/pay-qr", "settings"),
)


def module_guard(request: Request):
    """Rechaza (403) lo que el dueño intenta en una función que el superusuario le apagó. La cocina y la sala no se tocan:
    cambiar un plato agotado o cobrar una mesa siguen funcionando."""
    path = request.url.path
    if path.endswith("/availability"):
        return
    for method, prefix, mod in _GATES:
        if path.startswith(prefix) and method in (None, request.method):
            s = current(request, optional=True)
            if s and s.role == "owner" and not module_on(s.r, mod):
                raise HTTPException(403, "Esta función está desactivada para tu cuenta. Escríbenos si la necesitas.")
            return


def owner_dep(request: Request) -> Staff:
    s = current(request)
    if s.role != "owner":
        raise HTTPException(403, "Solo el dueño puede hacer esto")
    return s


def is_active(r: dict) -> bool:
    if r["subscription_status"] == "active":
        if r.get("license_start") and r["license_start"] > now():
            return r["trial_ends_at"] > now()  # licencia programada que aún no empieza: mientras tanto sigue la prueba (o el plan Gratis)
        return not r.get("paid_until") or r["paid_until"] > now()  # '' = sin vencimiento; vencida → plan Gratis, no un bloqueo
    return r["trial_ends_at"] > now()


def plan_info(r: dict):
    if not is_active(r):  # prueba vencida sin pagar: plan Gratis, no un bloqueo
        return PLANS["free"]
    p = PLANS.get(r["plan"], PLANS["basic"])
    p = {**p, "tables": p["tables"] + r["extra_tables"]}  # mesas adicionales: las suma el superusuario en cualquier plan
    if p["name"] == PLANS["basic"]["name"]:  # Esencial: el complemento de IA se contrata aparte
        p["ai_asks"] = BASIC_AI_ADDON_ASKS if r["ai_addon"] else 0
    return p


# --- límite de intentos: vive en la base de datos para que lo compartan todas las instancias (Vercel no comparte memoria)
# shortcut: cuenta y luego inserta (no es atómico), así que bajo concurrencia extrema puede pasarse por unos pocos intentos; usar Redis si hace falta exactitud.
def rate_check(key: str, limit: int, window: int):
    """Falla con 429 si ya se alcanzó el límite, sin contar este intento."""
    n = db.row("SELECT COUNT(*) AS n FROM rate_hits WHERE k=? AND ts>?", (key, time.time() - window))["n"]
    if n >= limit:
        raise HTTPException(429, "Demasiados intentos, espera un momento")


def rate_hit(key: str):
    db.run("INSERT INTO rate_hits(k, ts) VALUES (?,?)", (key, time.time()))
    if secrets.randbelow(50) == 0:  # limpieza ocasional: ninguna ventana dura más de 1 h
        db.run("DELETE FROM rate_hits WHERE ts<?", (time.time() - 7200,))


def rate_limit(key: str, limit: int, window: int):
    rate_check(key, limit, window)
    rate_hit(key)
