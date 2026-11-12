"""Colores de marca (principal, secundario y de acento) y logo: se guardan, se validan y llegan al panel, a la cocina y a la carta.
python -m tests.test_branding"""
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


with TestClient(app) as o, TestClient(app) as kit, TestClient(app) as cust:
    me = o.post("/api/signup", json={"accept_terms": True, "name": "Colores SAS", "email": "c@x.co", "password": "secreto123", "tables": 3}).json()
    r = me["restaurant"]
    slug, pin = r["slug"], r["staff_pin"]
    check(r["brand_color2"] == "" and r["brand_color3"] == "", "un restaurante nuevo no tiene colores secundario ni de acento: usa los del producto")

    put = lambda **b: o.put("/api/settings", json=b)  # noqa: E731
    x = put(brand_color="#2a6fdb", brand_color2="#ffe9d6", brand_color3="#ff5a1f")
    check(x.status_code == 200 and x.json()["restaurant"]["brand_color"] == "#2a6fdb" and x.json()["restaurant"]["brand_color2"] == "#ffe9d6" and x.json()["restaurant"]["brand_color3"] == "#ff5a1f",
          "los tres colores se guardan y vuelven en la respuesta")
    check(o.get("/api/me").json()["restaurant"]["brand_color3"] == "#ff5a1f", "y en /api/me")
    check(put(brand_color="#12").status_code == 400 and put(brand_color2="rojo").status_code == 400 and put(brand_color3="#12345g").status_code == 400, "un color mal escrito se rechaza")
    check(put(brand_color="").status_code == 400, "el color principal no puede quedar vacío")
    check(o.get("/api/me").json()["restaurant"]["brand_color"] == "#2a6fdb", "y un rechazo no cambia nada")

    pub = cust.get(f"/api/public/{slug}/menu").json()["restaurant"]
    check(pub["brand_color"] == "#2a6fdb" and pub["brand_color2"] == "#ffe9d6" and pub["brand_color3"] == "#ff5a1f", "la carta pública recibe los tres colores")
    st = kit.post("/api/staff-login", json={"slug": slug, "pin": pin}).json()["restaurant"]
    check(st["brand_color2"] == "#ffe9d6" and st["brand_color3"] == "#ff5a1f" and "staff_pin" not in st, "la cocina también (sin los datos que solo ve el dueño)")

    check(put(brand_color2="", brand_color3="").status_code == 200, "secundario y acento se pueden quitar")
    r2 = o.get("/api/me").json()["restaurant"]
    check(r2["brand_color2"] == "" and r2["brand_color3"] == "" and r2["brand_color"] == "#2a6fdb", "y el principal sigue como estaba")
    check(put(name="Colores SAS", staff_pin=pin).status_code == 200 and o.get("/api/me").json()["restaurant"]["brand_color"] == "#2a6fdb", "guardar otros ajustes no toca los colores")

print("Colores ✔")
