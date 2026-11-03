"""Fotos, logos y cartas originales en Vercel Blob (tienda pública): no ocupan la base ni se pierden entre despliegues.
Sin credenciales de Blob (desarrollo local, SQLite) `enabled()` es falso y las fotos siguen guardándose en la base.
Todo cuelga de `r<id>/`, así que borrar un restaurante es borrar ese prefijo. Las llamadas son síncronas: desde código async
se llaman con run_in_threadpool."""
import logging
import os
from urllib.parse import urlparse

log = logging.getLogger("mesaya.storage")
_HOST = ".blob.vercel-storage.com"


def enabled() -> bool:
    return bool(os.getenv("BLOB_READ_WRITE_TOKEN") or os.getenv("BLOB_STORE_ID"))


def _blob():
    from vercel.blob import sync as blob
    return blob


def put(pathname: str, data: bytes, content_type: str, random_suffix: bool = False) -> str:
    """Sube y devuelve la URL pública. El nombre aleatorio hace que la URL no se pueda adivinar ni cambie nunca."""
    return _blob().put_blob(pathname, data, access="public", content_type=content_type, add_random_suffix=random_suffix,
                            cache_control_max_age=31536000).url


def owns(url: str, rid: int) -> bool:
    """¿Es una URL de Blob de ESTE restaurante? Nunca se borra algo de otro aunque llegue un texto cualquiera."""
    u = urlparse(url or "")
    return u.scheme == "https" and (u.hostname or "").endswith(_HOST) and u.path.startswith(f"/r{rid}/")


def delete(urls: list[str]) -> None:
    for i in range(0, len(urls), 1000):  # el SDK acepta hasta 1.000 por llamada
        _blob().delete_blob(urls[i:i + 1000])


def delete_prefix(prefix: str, keep: str = "") -> None:
    """Borra todo lo que cuelga del prefijo, salvo la URL `keep`. Falla en voz alta: quien lo llame decide si reintenta."""
    delete([b.url for b in _blob().query_blobs(prefix=prefix) if b.url != keep])


def best_effort(fn, *args) -> None:
    """Para limpiezas que no deben tumbar la petición (una foto huérfana cuesta centavos; un 500 le cuesta al cliente)."""
    try:
        fn(*args)
    except Exception:
        log.warning("Blob: no se pudo limpiar %s", args[:1], exc_info=True)
