"""Almacén temporal de las fotos de un borrador de carta (hasta que el dueño confirma o pasan 3 horas).

El borrador viaja al navegador como JSON; las fotos se quedan en el servidor en data/import_drafts/<restaurante>/<borrador>/n.webp
y el navegador solo guarda una referencia [borrador, n]. Al confirmar, las fotos elegidas pasan a uploads/."""
import re
import secrets
import shutil
import time
from pathlib import Path

from . import config

TTL_SECONDS = 3 * 3600
_ID = re.compile(r"^[A-Za-z0-9_-]{10,40}$")


def root() -> Path:
    return config.DB_PATH.parent / "import_drafts"


def purge(older_than: int = TTL_SECONDS):
    base = root()
    if not base.exists():
        return
    now = time.time()
    for rdir in base.iterdir():
        if not rdir.is_dir():
            continue
        for d in rdir.iterdir():
            try:
                if now - d.stat().st_mtime > older_than:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass
        if not any(rdir.iterdir()):
            rdir.rmdir()


def create(restaurant_id: int, images: list[bytes]) -> str:
    purge()
    draft_id = secrets.token_urlsafe(12)
    d = root() / str(restaurant_id) / draft_id
    d.mkdir(parents=True)
    for n, data in enumerate(images):
        (d / f"{n}.webp").write_bytes(data)
    return draft_id


def path(restaurant_id: int, draft_id, n) -> Path | None:
    """Ruta de una foto del borrador, o None. Valida el formato del id para impedir rutas maliciosas."""
    if not isinstance(draft_id, str) or not _ID.match(draft_id):
        return None
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    p = root() / str(restaurant_id) / draft_id / f"{n}.webp"
    return p if p.is_file() else None


def delete(restaurant_id: int, draft_id: str):
    if isinstance(draft_id, str) and _ID.match(draft_id):
        shutil.rmtree(root() / str(restaurant_id) / draft_id, ignore_errors=True)


def delete_restaurant(restaurant_id: int):
    shutil.rmtree(root() / str(restaurant_id), ignore_errors=True)
