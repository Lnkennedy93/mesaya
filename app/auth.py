import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from . import db
from .config import PLANS

COOKIE = "mesaya_session"


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


# --- rate limiting en memoria (suficiente para 1 proceso; usar Redis al escalar) ---
_hits: dict[str, list[float]] = {}


def rate_check(key: str, limit: int, window: int):
    """Falla con 429 si ya se alcanzó el límite, sin contar este intento."""
    t = time.time()
    arr = [x for x in _hits.get(key, []) if t - x < window]
    _hits[key] = arr
    if len(arr) >= limit:
        raise HTTPException(429, "Demasiados intentos, espera un momento")


def rate_hit(key: str):
    _hits.setdefault(key, []).append(time.time())


def rate_limit(key: str, limit: int, window: int):
    rate_check(key, limit, window)
    rate_hit(key)
