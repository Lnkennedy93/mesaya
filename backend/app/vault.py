"""Cifrado en reposo de credenciales de terceros (Wompi, Factus...).
Clave: variable MESAYA_SECRET_KEY (Fernet) o, si no existe, un archivo data/secret.key generado una vez.
IMPORTANTE: respalda esa clave; sin ella no se pueden descifrar las credenciales guardadas."""
import json
import os

from cryptography.fernet import Fernet, InvalidToken

from .config import DB_PATH

_f: Fernet | None = None


def _fernet() -> Fernet:
    global _f
    if _f:
        return _f
    key = os.getenv("MESAYA_SECRET_KEY", "").encode()
    if not key:
        path = DB_PATH.parent / "secret.key"
        if path.exists():
            key = path.read_bytes().strip()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            path.write_bytes(key)
    _f = Fernet(key)
    return _f


def seal(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def unseal(token: str) -> dict:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError):
        return {}
