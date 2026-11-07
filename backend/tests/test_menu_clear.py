"""Eliminar toda la carta.   python -m tests.test_menu_clear"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def build(c):
    for n in ("Entradas", "Fuertes"):
        cat = c.post("/api/categories", json={"name": n}).json()["id"]
        for p in ("A", "B"):
            c.post("/api/items", json={"category_id": cat, "name": f"{n} {p}", "price": 10000})


def count(c):
    cats = c.get("/api/menu").json()["categories"]
    return len(cats), sum(len(x["items"]) for x in cats)


with TestClient(app) as a, TestClient(app) as b, TestClient(app) as anon:
    for cl, mail in ((a, "a@b.co"), (b, "b@b.co")):
        cl.post("/api/signup", json={"accept_terms": True, "name": "Café " + mail, "email": mail, "password": "secreto123", "tables": 2})
        build(cl)
    check(count(a) == (2, 4) and count(b) == (2, 4), "cada negocio tiene 2 categorías y 4 platos")
    check(anon.delete("/api/menu").status_code == 401, "sin sesión: 401")
    check(a.delete("/api/menu").status_code == 200 and count(a) == (0, 0), "se borra toda la carta (categorías y platos)")
    check(count(b) == (2, 4), "la carta del otro negocio queda intacta")
    check(a.delete("/api/menu").status_code == 200, "borrar una carta vacía no falla")
    check(a.post("/api/categories", json={"name": "Nueva"}).status_code == 200 and count(a) == (1, 0), "se puede volver a crear la carta")

print("\nTodo OK")
