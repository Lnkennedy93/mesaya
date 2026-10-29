"""Almacén temporal de las fotos de un borrador de carta (hasta que el dueño confirma o pasan 3 horas).

Viven en la base de datos (tabla draft_images): en Vercel no hay disco que persista entre peticiones. El borrador viaja al
navegador como JSON y este solo guarda una referencia [borrador, n]. Al confirmar, las fotos elegidas pasan a la tabla images."""
import re
import secrets
import time

from . import db

TTL_SECONDS = 3 * 3600
_ID = re.compile(r"^[A-Za-z0-9_-]{10,40}$")


def purge(older_than: int = TTL_SECONDS):
    db.run("DELETE FROM draft_images WHERE created_at<?", (time.time() - older_than,))


def create(restaurant_id: int, images: list[bytes]) -> str:
    purge()
    draft_id = secrets.token_urlsafe(12)
    now = time.time()
    with db.tx() as c:
        for n, data in enumerate(images):
            c.execute("INSERT INTO draft_images(restaurant_id, draft_id, n, data, created_at) VALUES (?,?,?,?,?)",
                      (restaurant_id, draft_id, n, data, now))
    return draft_id


def read(restaurant_id: int, draft_id, n) -> bytes | None:
    """Bytes de una foto del borrador, o None. Valida el id y el índice."""
    if not isinstance(draft_id, str) or not _ID.match(draft_id):
        return None
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    r = db.row("SELECT data FROM draft_images WHERE restaurant_id=? AND draft_id=? AND n=? AND created_at>?",
               (restaurant_id, draft_id, n, time.time() - TTL_SECONDS))
    return bytes(r["data"]) if r else None


def delete(restaurant_id: int, draft_id: str):
    if isinstance(draft_id, str) and _ID.match(draft_id):
        db.run("DELETE FROM draft_images WHERE restaurant_id=? AND draft_id=?", (restaurant_id, draft_id))
