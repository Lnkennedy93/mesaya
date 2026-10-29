import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from . import db
from .config import PLANS

COOKIE = "mesaya_session"


def client_ip(request: Request) -> str:
    """IP del visitante. Detrás de Vercel o de un proxy, request.client es el proxy: la real viene en x-forwarded-for."""
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "x").split(",")[0].strip()


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


def create_session(restaurant_id: int, role: str, days: int = 30) -> str:
    token = secrets.token_urlsafe(32)
    exp = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    db.run("INSERT INTO sessions(token, restaurant_id, role, expires_at) VALUES (?,?,?,?)",
           (token, restaurant_id, role, exp))
    return token


class Staff:
    def __init__(self, restaurant: dict, role: str):
        self.r = restaurant
        self.id = restaurant["id"]
        self.role = role


def current(request: Request, optional=False):
    token = request.cookies.get(COOKIE)
    if token:
        s = db.row("SELECT * FROM sessions WHERE token=? AND expires_at > ?", (token, now()))
        if s:
            r = db.row("SELECT * FROM restaurants WHERE id=?", (s["restaurant_id"],))
            if r:
                return Staff(r, s["role"])
    if optional:
        return None
    raise HTTPException(401, "Inicia sesión")


def staff_dep(request: Request) -> Staff:
    return current(request)


def owner_dep(request: Request) -> Staff:
    s = current(request)
    if s.role != "owner":
        raise HTTPException(403, "Solo el dueño puede hacer esto")
    return s


def is_active(r: dict) -> bool:
    if r["subscription_status"] == "active":
        return True
    return r["trial_ends_at"] > now()


def plan_info(r: dict):
    return PLANS.get(r["plan"], PLANS["basic"])


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
